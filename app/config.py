import os

import yaml
from mysql.connector import pooling


class Settings:
    def __init__(self):
        config_path_env = os.getenv("CONFIG_PATH")
        if not config_path_env:
            raise ValueError("CONFIG_PATH environment variable is not set.")
        with open(config_path_env, 'r', encoding="utf-8") as config_file:
            config = yaml.safe_load(config_file)
            self.env: str = config.get("APP_ENV")
            self.webhook_secret: str = config.get("WEBHOOK_SECRET")
            self.client_id: str = config.get("CLIENT_ID")
            self.euler_user: str = config.get("EULER_USER")
            self.euler_password: str = config.get("EULER_PASSWORD")
            self.silicon_token: str = config.get("SILICON_TOKEN")
            self.gitee_token: str = config.get("GITEE_TOKEN")
            self.github_token: str = config.get("GITHUB_TOKEN")
            self.gitcode_token: str = config.get("GITCODE_TOKEN")
            self.os_project: str = config.get("OS_PROJECT")
            self.os_repair_project: str = config.get("OS_REPAIR_PROJECT")
            self.os_variant: str = config.get("OS_VARIANT")
            self.os_arch: str = config.get("OS_ARCH")
            self.ground_projects: list[str] = config.get("GROUND_PROJECTS")
            self.flag_build: bool = config.get("FLAG_BUILD")
            self.flag_publish: bool = config.get("FLAG_PUBLISH")
            self.accept_cmds: list[str] = config.get("ACCEPT_CMDS")
            self.system_prompt: str = config.get("SYSTEM_PROMPT")
            self.user_prompt: str = config.get("USER_PROMPT")
            self.analyze_system_prompt: str = config.get("ANALYZE_SYSTEM_PROMPT")
            self.ai_model: str = config.get("AI_MODEL")
            self.model_max_tokens: int = config.get("MODEL_MAX_TOKENS")
            self.model_temperature: float = config.get("MODEL_TEMPERATURE")
            self.fix_success_comment: str = config.get("FIX_SUCCESS_COMMENT")
            self.fix_failure_comment: str = config.get("FIX_FAILURE_COMMENT")
            self.fix_error_comment: str = config.get("FIX_ERROR_COMMENT")
            self.thread_pool_size: int = config.get("THREAD_POOL_SIZE")
            self.check_interval: int = config.get("CHECK_INTERVAL")
            self.host: str = config.get("HOST")
            self.port: str = config.get("PORT")
            self.user: str = config.get("USER")
            self.password: str = config.get("PASSWORD")
            self.database: str = config.get("DATABASE")
            self.pool_size: int = config.get("POOL_SIZE")
        # os.remove(config_path_env)


settings = Settings()

db_config = {
    "user": settings.user,
    "password": settings.password,
    "host": settings.host,
    "port": settings.port,
    "database": settings.database,
    'charset': 'utf8mb4'
}


def init_db_pool():
    return pooling.MySQLConnectionPool(
        pool_name="request_pool",
        pool_size=settings.pool_size,
        **db_config
    )
