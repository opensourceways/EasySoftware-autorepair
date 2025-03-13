from fastapi import APIRouter, Request, HTTPException, Header

from app.config import settings
from app.utils import fetch_spec
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
        digest = hmac.new(WEBHOOK_SECRET, body, hashlib.sha256).hexdigest()
        if not await verify_signature(body, x_signature):
            raise HTTPException(status_code=403, detail="Invalid signature")

    # 处理数据
    try:
        json_data = await request.json()
        pr_number = json_data["pull_request"]["number"]
        owner, repo = json_data["project"]["namespace"], json_data["project"]["name"]
        spec_content = fetch_spec.get_spec_content(owner, repo, pr_number, f'{repo}.spec')
        return {"status": "success"}
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Missing required field: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
