import json
import os


class Settings:
    def __init__(self):
        config_path_env = "conf.yaml"
        with open(config_path_env, 'r') as config_file:
            config = json.load(config_file)
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


settings = Settings()
