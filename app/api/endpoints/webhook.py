from fastapi import APIRouter, Request, HTTPException, Header
from app.config import settings
from app.utils import git_api
from app.utils.client import silicon_client
from app.utils import euler_maker_api as maker
import hmac
import hashlib
import logging

router = APIRouter()


async def verify_signature(body: bytes, signature: str) -> bool:
    digest = hmac.new(
        settings.webhook_secret.encode(),
        msg=body,
        digestmod=hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(digest, signature)


@router.post("/webhooks/spec")
async def start_repair_job(
        request: Request,
        x_signature: str = Header(None)
):
    # 验证签名
    body = await request.body()
    if x_signature:
        digest = hmac.new(settings.WEBHOOK_SECRET, body, hashlib.sha256).hexdigest()
        if not await verify_signature(body, x_signature):
            raise HTTPException(status_code=403, detail="Invalid signature")
    # 处理数据
    data = await request.json()
    if data.get("noteable_type", "") != "PullRequest":
        return
    if data.get("note", "") not in settings.accept_cmds:
        return
    # 获取必要的信息
    repo_url = data['project']['url']
    source_url = data['pull_request']['head']['repo']['url']
    pr_number = data.get('pull_request', {}).get('number', '')
    repo = data.get('project', {}).get('name', '')

    # 调用 fetch_spec 函数获取 spec 文件内容
    spec_content = git_api.get_spec_content(repo_url, pr_number, f'{repo}.spec')

    # 调用 fetch_build_log 函数获取构建日志内容
    os_project = settings.os_project.format(repo=repo, pr_number=pr_number)
    log_url = maker.get_log_url(maker.get_result_root(maker.get_job_id(os_project, repo)))
    log_content = maker.get_build_log(log_url)

    # 调用 analyze_build_log 函数分析构建日志并返回修正后的 spec 文件内容
    chat = silicon_client.SiliconFlowChat(settings.silicon_token)
    result = chat.analyze_build_log(spec_content, log_content)

    # 创建fork仓库，上传修复后spec文件
    fork_url, sha = git_api.update_spec_file(source_url, result)
    commit_url = f"{fork_url}/commit/{sha}"
    # euler maker上构建
    maker.add_software_package(settings.os_project, repo, "", fork_url)
    maker.add_build_target(settings.os_project, repo, settings.os_variant, settings.os_arch, settings.ground_projects,
                           settings.flag_build, settings.flag_publish)
    maker.start_build_single(settings.os_project, repo)
    maker_url = (f"https://eulermaker.compass-ci.openeuler.openatom.cn/package/overview?osProject={settings.os_project}"
                 f"&packageName={repo}")

    git_api.comment_on_pr(repo_url, pr_number, settings.fix_result_comment.format(
        commit_url=commit_url, maker_url=maker_url))
