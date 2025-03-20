import json
import os


class Settings:
    def __init__(self):
        config_path_env = os.getenv('CONFIG_PATH')
        with open(config_path_env, 'r') as config_file:
            config = json.load(config_file)

            env = config.get("APP_ENV")
            webhook_secret: str = config.get("WEBHOOK_SECRET")
            client_id: str = config.get("CLIENT_ID")
            euler_user: str = config.get("EULER_USER")
            euler_password: str = config.get("EULER_PASSWORD")
            silicon_token: str = config.get("SILICON_TOKEN")
            gitee_token: str = config.get("GITEE_TOKEN")
            github_token: str = config.get("GITHUB_TOKEN")
            gitcode_token: str = config.get("GITCODE_TOKEN")


settings = Settings()
