import os
from pydantic import Field
from pydantic_settings import BaseSettings  # 新的导入方式
from dotenv import load_dotenv

# load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))


class Settings(BaseSettings):
    env: str = Field(default="development", env="APP_ENV")
    webhook_secret: str = Field(..., env="WEBHOOK_SECRET")
    silicon_token: str = Field(..., env="SILICON_TOKEN")
    client_id: str = Field(..., env="CLIENT_ID")
    euler_user: str = Field(..., env="EULER_USER")
    euler_password: str = Field(..., env="EULER_PASSWORD")

    class Config:
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
