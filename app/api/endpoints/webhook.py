# 标准库
import asyncio
import base64
import re
import time
import hmac
import hashlib
import logging

# 第三方库
from fastapi import APIRouter, Request, HTTPException, Header, status, BackgroundTasks

# 应用程序自定义模块
from app.config import settings, init_db_pool
from app.utils import git_api, gitee_tool
from app.utils.client import silicon_client
from app.utils import euler_maker_api as maker

router = APIRouter()
logger = logging.getLogger(__name__)
MAX_RETRIES = 0
db_pool = init_db_pool()


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
        "pr_url": pull_request.get("html_url", ""),
    }


def compute_signature(timestamp: str):
    """
    计算Gitee Webhook签名
    参数格式保持字符串类型以兼容HTTP Header的文本格式
    """
    # 构造签名字符串
    string_to_sign = f"{timestamp}\n{settings.webhook_secret}"
    # 生成HMAC-SHA256签名
    secret_enc = settings.webhook_secret.encode('utf-8')
    string_to_sign_enc = string_to_sign.encode('utf-8')

    hmac_code = hmac.new(secret_enc, string_to_sign_enc, hashlib.sha256).digest()
    # Base64编码并进行URL转义
    return base64.b64encode(hmac_code).decode('utf-8')


@router.post("/webhooks/spec", status_code=status.HTTP_202_ACCEPTED)
async def handle_webhook(
        request: Request,
        x_gitee_token: str = Header(None),  # Gitee的签名
        x_gitee_timestamp: str = Header(None)  # Gitee的时间戳
):
    if not x_gitee_token or not x_gitee_timestamp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required headers"
        )
    server_signature = compute_signature(x_gitee_timestamp)
    # 安全比较签名（防止时序攻击）
    if not hmac.compare_digest(server_signature, x_gitee_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid signature"
        )

    try:
        data = await request.json()
        comment = data.get("note", "").strip().lower()
        logger.info(f"Received webhook request, note: {comment}")
        pr_data = extract_pr_data(data)
    except ValueError as e:
        return
    except Exception as e:
        logger.error(f"Payload processing failed: {e}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid payload")

    try:
        # Fetch spec file
        spec_content = await git_api.get_spec_content(
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

    try:
        logger.info(f"开始入库")
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO pending_requests (repo_url, source_url, pr_number, repo_name, pr_url, spec_content) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                pr_data["repo_url"],
                pr_data["source_url"],
                pr_data["pr_number"],
                pr_data["repo_name"],
                pr_data["pr_url"],
                spec_content
            )
        )
        conn.commit()
        return {"status": "处理已启动"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "数据库写入异常")
    finally:
        cursor.close()
        conn.close()


async def wait_for_build_completion(build_id: str, interval: int = 30, timeout: int = 36000) -> bool:
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


async def handle_build_retries(pr_data: dict, current_spec: str, srcDir: str, build_id: str, retry_count: int,
                               commit_url: str,
                               maker_url: str):
    """处理构建重试逻辑"""
    try:
        build_status = await wait_for_build_completion(build_id)
        logger.info(f'the build result is {build_status}')

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
            job_id = maker.get_job_id(settings.os_repair_project, pr_data["repo_name"])
            log_url = maker.get_log_url(maker.get_result_root(job_id))
            log_content = maker.get_build_log(log_url)

            # 分析新日志生成修正
            chat = silicon_client.SiliconFlowChat(settings.silicon_token)
            new_spec, fail_reason = chat.analyze_build_log(pr_data["repo_name"], current_spec, log_content, srcDir)

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
            maker_url = (
                f"https://eulermaker.compass-ci.openeuler.openatom.cn/package/build-record?"
                f"osProject={settings.os_repair_project}&"
                f"packageName={pr_data['repo_name']}&"
                f"jobId={repair_job_id}"
            )

            # 递归处理
            await handle_build_retries(pr_data, new_spec, srcDir, new_build_id, retry_count + 1, commit_url, maker_url)

        else:
            # 达到最大重试次数
            comment = settings.fix_failure_comment.format(max_retries=MAX_RETRIES, commit_url=commit_url,
                                                          maker_url=maker_url)
            git_api.comment_on_pr(pr_data["repo_url"], pr_data["pr_number"], comment)
            logger.error(f"PR #{pr_data['pr_number']} 构建失败，已达最大重试次数")
            await analyze_error_and_create_issue(pr_data)

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

        srcDir = gitee_tool.get_dir_json(pr_data["pr_url"], settings.gitee_token)

        # Analyze build log
        chat = silicon_client.SiliconFlowChat(settings.silicon_token)
        fixed_spec, fail_reason = chat.analyze_build_log(pr_data["repo_name"], original_spec, log_content, srcDir)

        # Comment Fail Reason In Pr
        git_api.comment_on_pr(pr_data["repo_url"], pr_data["pr_number"], fail_reason)

        # Update spec in fork
        fork_url, commit_sha, branch = git_api.check_and_push(
            pr_data["source_url"],
            fixed_spec,
            pr_data["pr_number"]
        )

        logger.info("start euler maker build")
        # Trigger Euler Maker build
        maker.add_software_package(
            settings.os_repair_project,
            pr_data["repo_name"],
            "",
            fork_url,
            branch
        )
        logger.info("add build target")
        maker.add_build_target(
            settings.os_repair_project,
            pr_data["repo_name"],
            settings.os_variant,
            settings.os_arch,
            settings.ground_projects,
            settings.flag_build,
            settings.flag_publish
        )
        logger.info("start build single")
        repair_build_id = maker.start_build_single(settings.os_repair_project, pr_data["repo_name"])

        repair_job_id = maker.get_job_id(settings.os_repair_project, pr_data["repo_name"])
        commit_url = f"{fork_url}/commit/{commit_sha}"
        maker_url = (f"https://eulermaker.compass-ci.openeuler.openatom.cn/package/build-record?"
                     f"osProject={settings.os_repair_project}&"
                     f"packageName={pr_data['repo_name']}&"
                     f"jobId={repair_job_id}")

        await handle_build_retries(pr_data, fixed_spec, srcDir, repair_build_id, 0, commit_url, maker_url)
    except Exception as e:
        logger.error(f"初始修复流程失败: {e}")
        comment = settings.fix_error_comment.format(error=str(e))
        git_api.comment_on_pr(pr_data["repo_url"], pr_data["pr_number"], comment)


async def analyze_error_and_create_issue(pr_data: dict):
    """分析错误并创建问题"""
    # 分析错误日志
    try:
        # Get build log
        job_id = maker.get_job_id(settings.os_repair_project, pr_data["repo_name"])
        log_url = maker.get_log_url(maker.get_result_root(job_id))
        log_content = maker.get_build_log(log_url)

        warning_patterns = [
            r"Warning:.*",
            r"skipped:.*",
            r"warning:.*"
            r"WARNING:.*",
            r"No matching package to install:.*",
            r".*is not installed.*"
        ]
        warnings = []
        for pattern in warning_patterns:
            matches = re.findall(pattern, log_content)
            warnings.extend(matches)
        logger.info(f"the build warning info : {warnings}")
        chat = silicon_client.SiliconFlowChat(settings.silicon_token)
        title, content = chat.analyze_missing_package(warnings)
        if title and content:
            git_api.create_issue(pr_data["repo_url"], title, content)

    except Exception as e:
        logger.error(f"获取构建日志失败: {e}")
        return
