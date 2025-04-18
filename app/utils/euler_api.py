import json
import logging
from urllib.parse import urlencode, urlparse, parse_qs
from typing import Optional, Dict
import requests
from requests.exceptions import RequestException

from app.config import settings

# 配置日志
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# 常量定义
ONEID_BASE_URL = "https://id.openeuler.org/oneid"
OAUTH_REDIRECT_URI = "https://eulermaker.compass-ci.openeuler.openatom.cn/oauth/"
OAUTH_TOKEN_URL = "https://eulermaker.compass-ci.openeuler.openatom.cn/api/user_auth/oauth_authorize"


class OAuthError(Exception):
    """自定义OAuth流程异常基类"""
    pass


class APIConnectionError(OAuthError):
    """API连接异常"""
    pass


class InvalidResponseError(OAuthError):
    """无效的API响应异常"""
    pass


class MissingParameterError(OAuthError):
    """缺少必要参数异常"""
    pass


class OAuthClient:
    def __init__(self, client_id: str, username: str, password: str):
        self.client_id = client_id
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def _handle_request_exception(self, e: RequestException, context: str = ""):
        """统一处理请求异常"""
        error_msg = f"{context}请求失败: {str(e)}"
        logger.error(error_msg)
        raise APIConnectionError(error_msg) from e

    def get_privacy_version(self) -> str:
        """获取隐私协议版本"""
        url = f"{ONEID_BASE_URL}/privacy/version"
        try:
            response = self.session.get(url, timeout=120)
            response.raise_for_status()

            data = response.json()
            if not isinstance(data, dict):
                raise InvalidResponseError("响应格式异常，预期JSON对象")

            version = data.get("data", {}).get("oneidPrivacyAccepted")
            if not version:
                raise InvalidResponseError("响应中缺少隐私协议版本")
            return str(version)

        except (RequestException, json.JSONDecodeError) as e:
            self._handle_request_exception(e, "获取隐私协议版本")
            return ""

    def authenticate(self, version: str) -> None:
        """进行用户认证并维护会话状态"""
        url = f"{ONEID_BASE_URL}/login"
        params = {
            "client_id": self.client_id,
            "scope": "openid profile email username",
            "redirect_uri": OAUTH_REDIRECT_URI,
            "response_mode": "query"
        }

        payload = {
            "community": "openeuler",
            "permission": "sigRead",
            "account": self.username,
            "client_id": self.client_id,
            "accept_term": 1,  # 假设需要接受条款
            "password": self.password,
            "oneidPrivacyAccepted": version
        }

        try:
            # 清除旧会话状态
            self.session.cookies.clear()

            response = self.session.post(
                url,
                json=payload,
                headers={"Referer": f"https://id.openeuler.org/login?{urlencode(params)}"},
                timeout=120
            )
            response.raise_for_status()

            # 验证认证令牌
            if "_U_T_" not in self.session.cookies:
                raise InvalidResponseError("认证响应中缺少令牌")

        except RequestException as e:
            self._handle_request_exception(e, "用户认证")

    def base_info(self, version: str) -> None:
        url = f"{ONEID_BASE_URL}/update/baseInfo"
        payload = {"oneidPrivacyAccepted": version}
        cookie = self.session.cookies.get_dict()
        cookie_list = []
        for k, v in cookie.items():
            cookie_list.append(f"{k}={v}")
        headers = {
            "Cookie": ";".join(cookie_list),
            "Token": cookie["_U_T_"],
        }
        try:
            response = self.session.post(
                url,
                headers=headers,
                json=payload,
                timeout=120
            )
            response.raise_for_status()
        except RequestException as e:
            self._handle_request_exception(e, "同意协议")

    def get_auth_code(self) -> str:
        """获取授权码"""
        url = f"{ONEID_BASE_URL}/oidc/auth"
        params = {
            "client_id": self.client_id,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid profile email username"
        }
        cookie = self.session.cookies.get_dict()
        cookie_list = []
        for k, v in cookie.items():
            cookie_list.append(f"{k}={v}")
        headers = {
            "Cookie": ";".join(cookie_list),
            "Token": cookie["_U_T_"],
        }
        try:
            response = self.session.get(url, headers=headers, params=params, timeout=120)
            response.raise_for_status()

            data = response.json()
            auth_url = data.get("body", "")
            if not auth_url:
                raise InvalidResponseError("响应中缺少授权URL")

            parsed = urlparse(auth_url)
            code = parse_qs(parsed.query).get("code", [None])[0]

            if not code:
                raise MissingParameterError("授权URL中缺少code参数")
            return code

        except (RequestException, IndexError) as e:
            self._handle_request_exception(e, "获取授权码")
            return ""

    def get_access_token(self, code: str) -> str:
        """使用授权码获取访问令牌"""
        try:
            response = self.session.get(
                f"{OAUTH_TOKEN_URL}?code={code}",
                timeout=120
            )
            response.raise_for_status()

            data = response.json()
            token = data.get("msg", {}).get("token")
            if not token:
                raise InvalidResponseError("响应中缺少访问令牌")
            return token

        except RequestException as e:
            self._handle_request_exception(e, "获取访问令牌")
            return ""

    def execute_flow(self) -> str:
        """执行完整的OAuth流程"""
        try:
            version = self.get_privacy_version()
            self.authenticate(version)
            self.base_info(version)
            auth_code = self.get_auth_code()
            return self.get_access_token(auth_code)
        except OAuthError as e:
            logger.error("OAuth流程失败: %s", str(e))
            raise


# 使用示例
def get_token() -> Optional[str]:
    try:
        client = OAuthClient(
            client_id=settings.client_id,
            username=settings.euler_user,
            password=settings.euler_password
        )
        return client.execute_flow()
    except OAuthError:
        return None
