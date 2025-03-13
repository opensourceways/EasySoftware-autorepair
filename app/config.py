import os
from pydantic import Field
from pydantic_settings import BaseSettings  # 新的导入方式


class Settings(BaseSettings):
    env: str = Field(default="development", env="APP_ENV")
    webhook_secret: str = Field(..., env="WEBHOOK_SECRET")
    silicon_token: str = Field(..., env="SILICON_TOKEN")
    client_id: str = Field(..., env="CLIENT_ID")
    euler_user: str = Field(..., env="EULER_USER")
    euler_password: str = Field(..., env="EULER_PASSWORD")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
