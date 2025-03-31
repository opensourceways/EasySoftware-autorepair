import asyncio
import time

from fastapi import APIRouter, Request, HTTPException, Header, status, BackgroundTasks
from app.config import settings
from app.utils import git_api
from app.utils.client import silicon_client
from app.utils import euler_maker_api as maker
import hmac
import hashlib
import logging

router = APIRouter()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
MAX_RETRIES = 3


def verify_signature(body: bytes, signature: str) -> bool:
    """Verify HMAC signature of webhook payload."""
    try:
        digest = hmac.new(
            settings.webhook_secret.encode(),
            msg=body,
            digestmod=hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(f"sha256={digest}", signature)
    except Exception as e:
        logger.error(f"Signature verification failed: {e}")
        return False


def extract_pr_data(data: dict) -> dict:
    """Extract and validate required PR data from webhook payload."""
    if data.get("noteable_type", "") != "PullRequest":
        raise ValueError("Not a pull request event")

    note = data.get("note", "").strip().lower()
    if note not in [cmd.strip().lower() for cmd in settings.accept_cmds]:
        raise ValueError("Unsupported command")

    pull_request = data.get("pull_request", {})
    project = data.get("project", {})

    return {
        "repo_url": project.get("url", ""),
        "source_url": pull_request.get("head", {}).get("repo", {}).get("url", ""),
        "pr_number": pull_request.get("number", ""),
        "repo_name": project.get("name", ""),
    }


@router.post("/webhooks/spec", status_code=status.HTTP_202_ACCEPTED)
async def handle_webhook(
        request: Request,
        x_signature: str = Header(None),
        background_tasks: BackgroundTasks = None
):
    logger.info("Received webhook request")

    # Verify signature
    body = await request.body()
    if x_signature:
        if not verify_signature(body, x_signature):
            logger.warning("Invalid signature")
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid signature")

    try:
        data = await request.json()
        pr_data = extract_pr_data(data)
    except ValueError as e:
        logger.info(f"Ignoring unsupported event: {e}")
        return
    except Exception as e:
        logger.error(f"Payload processing failed: {e}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid payload")

    try:
        # Fetch spec file
        spec_content = git_api.get_spec_content(
            pr_data["repo_url"],
            pr_data["pr_number"],
            f'{pr_data["repo_name"]}.spec'
        )
    except ValueError as e:
        logger.info(f"忽略不支持的事件: {e}")
        return
    except Exception as e:
        logger.error(f"数据解析失败: {e}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "无效负载")

    # 启动后台任务处理
    background_tasks.add_task(process_initial_repair, pr_data, spec_content)
    return {"status": "处理已启动"}


async def wait_for_build_completion(build_id: str, interval: int = 30, timeout: int = 3600) -> bool:
    """优化后的异步等待构建完成"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        status_data = await maker.get_build_status(build_id)  # 直接调用异步版本
        if status_data:
            build_status = status_data.get('status')
            if build_status == 201:
                return True
            elif build_status == 202:
                return False
        await asyncio.sleep(interval)
    return False


async def handle_build_retries(pr_data: dict, current_spec: str, build_id: str, retry_count: int, commit_url: str,
                               maker_url: str):
    """处理构建重试逻辑"""
    try:
        build_status = await wait_for_build_completion(build_id)

        if build_status:
            # 构建成功，提交评论
            comment = settings.fix_success_comment.format(
                commit_url=commit_url,
                maker_url=maker_url
            )
            git_api.comment_on_pr(pr_data["repo_url"], pr_data["pr_number"], comment)
            logger.info(f"PR #{pr_data['pr_number']} 构建成功，重试次数: {retry_count}")

        elif retry_count < MAX_RETRIES:
            # 获取失败日志
            loop = asyncio.get_event_loop()
            job_id = maker.get_job_id(settings.os_repair_project, pr_data["repo_name"])
            log_url = maker.get_log_url(maker.get_result_root(job_id))
            log_content = await loop.run_in_executor(None, maker.get_build_log, log_url)

            # 分析新日志生成修正
            chat = silicon_client.SiliconFlowChat(settings.silicon_token)
            new_spec = chat.analyze_build_log(pr_data["repo_name"], current_spec, log_content)

            # 提交新修正
            fork_url, commit_sha, branch = git_api.check_and_push(
                pr_data["source_url"],
                new_spec,
                pr_data["pr_number"]
            )

            # 触发新构建
            new_build_id = maker.start_build_single(
                settings.os_repair_project,
                pr_data["repo_name"]
            )
            repair_job_id = maker.get_job_id(settings.os_repair_project, pr_data["repo_name"])
            commit_url = f"{fork_url}/commit/{commit_sha}"
            maker_url = f"https://eulermaker.compass-ci.openeuler.openatom.cn/package/build-record?osProject={settings.os_repair_project}&packageName={pr_data['repo_name']}&jobId={repair_job_id}"

        # 递归处理
            await handle_build_retries(pr_data, new_spec, new_build_id, retry_count + 1, commit_url, maker_url)

        else:
            # 达到最大重试次数
            comment = settings.fix_failure_comment.format(max_retries=MAX_RETRIES, commit_url=commit_url, maker_url=maker_url)
            git_api.comment_on_pr(pr_data["repo_url"], pr_data["pr_number"], comment)
            logger.error(f"PR #{pr_data['pr_number']} 构建失败，已达最大重试次数")

    except Exception as e:
        logger.error(f"处理重试时发生异常: {e}")
        comment = settings.fix_error_comment.format(error=str(e))
        git_api.comment_on_pr(pr_data["repo_url"], pr_data["pr_number"], comment)


async def process_initial_repair(pr_data: dict, original_spec: str):
    """Process initial repair."""
    try:
        # Get build log
        os_project = settings.os_project.format(
            repo=pr_data["repo_name"],
            pr_number=pr_data["pr_number"]
        )
        job_id = maker.get_job_id(os_project, pr_data["repo_name"])
        log_url = maker.get_log_url(maker.get_result_root(job_id))
        log_content = maker.get_build_log(log_url)

        # Analyze build log
        chat = silicon_client.SiliconFlowChat(settings.silicon_token)
        fixed_spec = chat.analyze_build_log(pr_data["repo_name"], original_spec, log_content)

        # Update spec in fork
        fork_url, commit_sha, branch = git_api.check_and_push(
            pr_data["source_url"],
            fixed_spec,
            pr_data["pr_number"]
        )

        # Trigger Euler Maker build
        maker.add_software_package(
            settings.os_repair_project,
            pr_data["repo_name"],
            "",
            fork_url,
            branch
        )
        maker.add_build_target(
            settings.os_repair_project,
            pr_data["repo_name"],
            settings.os_variant,
            settings.os_arch,
            settings.ground_projects,
            settings.flag_build,
            settings.flag_publish
        )
        repair_build_id = maker.start_build_single(settings.os_repair_project, pr_data["repo_name"])

        repair_job_id = maker.get_job_id(settings.os_repair_project, pr_data["repo_name"])
        commit_url = f"{fork_url}/commit/{commit_sha}"
        maker_url = f"https://eulermaker.compass-ci.openeuler.openatom.cn/package/build-record?osProject={settings.os_repair_project}&packageName={pr_data['repo_name']}&jobId={repair_job_id}"

        await handle_build_retries(pr_data, fixed_spec, repair_build_id, 0, commit_url, maker_url)
    except Exception as e:
        logger.error(f"初始修复流程失败: {e}")
        comment = settings.fix_error_comment.format(error=str(e))
        git_api.comment_on_pr(pr_data["repo_url"], pr_data["pr_number"], comment)
