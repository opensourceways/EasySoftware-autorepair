from fastapi import FastAPI, HTTPException, Request, status
from app.api.endpoints import webhook
from app.config import settings


app = FastAPI(title="Spec Webhook Service", version="1.0.0")

app.include_router(webhook.router, prefix="/api/v1", tags=["webhooks"])


@app.middleware("http")
async def validate_config(request: Request, call_next):
    if not settings.webhook_secret or settings.webhook_secret == "default_secret":
        raise HTTPException(500, "Webhook secret not configured")
    return await call_next(request)


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "ok", "env": settings.env}
