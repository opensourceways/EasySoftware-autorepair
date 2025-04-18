# 标准库
import logging
import asyncio

# 第三方库
from fastapi import FastAPI, HTTPException, Request, status

# 应用程序自定义模块
from app.api.endpoints import webhook
from app.config import settings
from app.utils.processor import RequestProcessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Spec Webhook Service", version="1.0.0")

app.include_router(webhook.router, prefix="/api/v1", tags=["webhooks"])
processor = RequestProcessor()


@app.on_event("startup")
def startup_event():
    """
    在应用程序启动时执行的事件处理函数。

    该函数启动后台任务，以确保应用程序在运行时可以执行必要的后台操作。
    """
    # 延迟5秒后执行后台任务
    loop = asyncio.get_running_loop()
    loop.call_later(5, lambda: asyncio.create_task(processor.start()))


@app.middleware("http")
async def log_requests(request: Request, call_next):
    # 记录请求的基本信息
    logger.info(f"Request: {request.method} {request.url} - Headers: {dict(request.headers)}")
    response = await call_next(request)
    logger.info(f"Response: {response.status_code}")

    return response


@app.middleware("http")
async def validate_config(request: Request, call_next):
    if not settings.webhook_secret or settings.webhook_secret == "default_secret":
        raise HTTPException(500, "Webhook secret not configured")
    return await call_next(request)


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "ok", "env": settings.env}
