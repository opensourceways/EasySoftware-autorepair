import requests


class ApiClient:
    BASE_URLS = {
        "gitee": "https://gitee.com/api/v5",
        "github": "https://api.github.com",
        "gitcode": "https://gitcode.net/api/v5"
    }

    HEADERS = {
        "gitee": {
            "Authorization": "token {token}"
        },
        "github": {
            "Authorization": "token {token}",
            "Accept": "application/vnd.github.v3+json"
        },
        "gitcode": {
            "Authorization": "{token}"
        }
    }

    def __init__(self, platform, token=None):
        if platform not in self.BASE_URLS:
            raise ValueError(f"不支持的平台: {platform}")
        self.base_url = self.BASE_URLS[platform]
        self.headers = self._get_headers(platform, token)

    def _get_headers(self, platform, token):
        headers = self.HEADERS.get(platform, {}).copy()  # 拷贝防止修改原字典
        for key, value in headers.items():
            headers[key] = value.format(token=token)  # 对每个 header 字符串格式化 token
        return headers

    def get(self, endpoint):
        url = f"{self.base_url}{endpoint}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response

    def post(self, endpoint, data=None):
        url = f"{self.base_url}{endpoint}"
        response = requests.post(url, headers=self.headers, json=data)
        response.raise_for_status()
        return response

    def delete(self, endpoint):
        url = f"{self.base_url}{endpoint}"
        response = requests.delete(url, headers=self.headers)
        response.raise_for_status()
        return response

    def put(self, endpoint, data=None):
        url = f"{self.base_url}{endpoint}"
        response = requests.put(url, headers=self.headers, json=data)
        response.raise_for_status()
        return response
