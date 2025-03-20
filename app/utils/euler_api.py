import json
import requests
from app.config import settings
from urllib.parse import urlparse, parse_qs


def get_privacy_version():
    api_url = "https://id.openeuler.org/oneid/privacy/version"
    try:
        response = requests.get(
            api_url,
            timeout=50
        )
        response.raise_for_status()
        data = response.json()
        return data['data']['oneidPrivacyAccepted']
    except requests.exceptions.RequestException as e:
        print("请求失败:", e)
        return ""


def get_cookie(version):
    api_url = "https://id.openeuler.org/oneid/login"
    body = {"community": "openeuler", "permission": "sigRead", "account": settings.euler_user,
            "client_id": settings.client_id, "accept_term": 0,
            "password": settings.euler_password,
            "oneidPrivacyAccepted": version}
    headers = {
        "Referer": f"https://id.openeuler.org/login?client_id={settings.client_id}&scope=openid%20profile%20email%20username&redirect_uri=https%3A%2F%2Feulermaker.compass-ci.openeuler.openatom.cn%2Foauth%2F&response_mode=query"
    }
    try:
        response = requests.post(
            api_url,
            json=body,  # 自动设置headers的Content-Type
            headers=headers,
            timeout=50
        )
        response.raise_for_status()  # 自动抛出HTTP错误
        data = response.json()
        # 获取所有的 Set-Cookie 字段
        set_cookies = response.cookies.get_dict()
        return set_cookies
    except requests.exceptions.RequestException as e:
        print("请求失败:", e)
        return ""


def get_auth_url(cookie):
    api_url = f"https://id.openeuler.org/oneid/oidc/auth?client_id={settings.client_id}&redirect_uri=https:%2F%2Feulermaker.compass-ci.openeuler.openatom.cn%2Foauth%2F&response_type=code&scope=openid+profile+email+username"
    cookie_list = []
    for k, v in cookie.items():
        cookie_list.append(f"{k}={v}")
    headers = {
        "Cookie": ";".join(cookie_list),
        "Token": cookie["_U_T_"],
    }
    try:
        response = requests.get(
            api_url,
            headers=headers,
            timeout=50
        )
        response.raise_for_status()  # 自动抛出HTTP错误
        data = response.json()
        return data['body']
    except requests.exceptions.RequestException as e:
        print("请求失败:", e)
        return ""


def get_oauth_token(url):
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)

    # 提取 'code' 参数的值
    code = query_params.get('code', [None])[0]

    if code is None:
        print("URL 中未找到 'code' 参数")
        return ""

    api_url = f"https://eulermaker.compass-ci.openeuler.openatom.cn/api/user_auth/oauth_authorize?code={code}"

    try:
        response = requests.get(
            api_url,
            timeout=50
        )
        response.raise_for_status()  # 自动抛出HTTP错误
        response_data = json.loads(response.text)
        # 提取 token
        final_token = response_data.get("msg", {}).get("token")
        return final_token
    except requests.exceptions.RequestException as e:
        print("请求oauth_token失败 :", e)
        return ""


def get_token():
    version = get_privacy_version()
    cookie = get_cookie(version)
    auth_url = get_auth_url(cookie)
    return get_oauth_token(auth_url)
