from fastapi import APIRouter, Request, HTTPException, Header
from app.config import settings
from app.utils import fetch_spec
from app.utils import fetch_build_log
from app.utils.client import silicon_client
from app.utils.euler_maker_api import get_log_url, get_result_root, get_job_id
import hmac
import hashlib

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
    try:
        json_data = await request.json()
        pr_number = json_data["pull_request"]["number"]
        owner, repo = json_data["project"]["namespace"], json_data["project"]["name"]
        # 调用 fetch_spec 函数获取 spec 文件内容
        spec_content = fetch_spec.get_spec_content(owner, repo, pr_number, f'{repo}.spec')
        # 调用 fetch_build_log 函数获取构建日志内容
        os_project = f"master:x86_64:{repo}:{pr_number}"
        log_url = get_log_url(get_result_root(get_job_id(os_project, repo)))
        log_content = fetch_build_log.get_build_log(log_url)
        # 调用 analyze_build_log 函数分析构建日志并返回修正后的 spec 文件内容
        chat = silicon_client.SiliconFlowChat(settings.silicon_token)
        result = chat.analyze_build_log(spec_content, log_content)

        return {"status": "success"}
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Missing required field: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
