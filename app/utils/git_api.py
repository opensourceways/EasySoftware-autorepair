from abc import ABC, abstractmethod
from base64 import b64encode
from urllib.parse import urlparse
from app.config import settings
import requests
import logging


logger = logging.getLogger("git_api")


# 抽象接口层
class ForkServiceInterface(ABC):
    @abstractmethod
    def create_fork(self, owner, repo):
        pass

    @abstractmethod
    def submit_spec_file(self, fork_owner, fork_repo, content, file_path, branch="master"):
        pass

    @abstractmethod
    def comment_on_pr(self, owner, repo, pr_number, comment):
        pass


# 平台具体实现层
class GiteeForkService(ForkServiceInterface):
    def __init__(self, token):
        self.base_url = "https://gitee.com/api/v5"
        self.token = token
        self.current_user = self._get_current_user()

    def _get_current_user(self):
        """获取当前认证用户信息"""
        url = f"{self.base_url}/user"
        response = requests.get(url, params={"access_token": self.token})
        if response.status_code == 200:
            return response.json()["login"]
        raise Exception(f"Failed to get user info: {response.text}")

    def _get_existing_fork(self, owner, repo):
        """检查是否已存在fork仓库"""
        page = 1
        while True:
            url = f"{self.base_url}/repos/{owner}/{repo}/forks"
            params = {
                "access_token": self.token,
                "page": page,
                "per_page": 100
            }
            response = requests.get(url, params=params)

            if response.status_code != 200 or not response.json():
                break

            # 在fork列表中查找当前用户的fork
            for fork in response.json():
                if fork["owner"]["login"] == self.current_user:
                    return fork["html_url"]

            page += 1
        return None

    def get_file_sha(self, owner, repo, file_path, branch="master"):
        url = f"{self.base_url}/repos/{owner}/{repo}/contents/{file_path}"
        params = {'access_token': self.token, 'ref': branch}
        response = requests.get(url, params=params)
        if response.status_code == 200:
            return response.json().get("sha")
        return None

    def create_fork(self, owner, repo):
        # 先检查是否已存在fork
        existing_fork = self._get_existing_fork(owner, repo)
        if existing_fork:
            return existing_fork

        # 创建fork
        url = f"{self.base_url}/repos/{owner}/{repo}/forks"
        headers = {'Authorization': f'token {self.token}'}

        response = requests.post(url, headers=headers)
        if response.status_code == 201:
            return response.json()["html_url"]
        raise Exception(f"Gitee fork failed: {response.json()}")

    def submit_spec_file(self, fork_owner, fork_repo, content, file_path, branch="master"):
        url = f"{self.base_url}/repos/{fork_owner}/{fork_repo}/contents/{file_path}"
        params = {'access_token': self.token}

        # 获取 SHA 值
        sha = self.get_file_sha(fork_owner, fork_repo, file_path, branch)

        data = {
            "content": b64encode(content.encode()).decode(),
            "message": "Add spec file",
            "branch": branch,
            "sha": sha
        }
        response = requests.put(url, params=params, json=data)
        logger.info(response.json())
        if response.status_code == 200:
            return response.json()["content"]["path"], response.json()["commit"]["sha"]
        raise Exception(f"Gitee提交失败: {response.status_code} {response.text}")

    def comment_on_pr(self, owner, repo, pr_num, comment):
        api_url = f"https://gitee.com/api/v5/repos/{owner}/{repo}/pulls/{pr_num}/comments"
        # 这里假设你使用 GitHub API 来评论PR，需要提供有效的 GitHub 令牌（token）
        headers = {
            "Authorization": f"Bearer {settings.gitee_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        data = {
            "body": comment
        }

        try:
            # 评论 PR
            response = requests.post(api_url, json=data, headers=headers)
            response.raise_for_status()  # 检查是否成功
        except requests.exceptions.RequestException as e:
            print("评论 PR 失败:", e)


class GitHubForkService(ForkServiceInterface):
    def __init__(self, token):
        self.base_url = "https://api.github.com"
        self.token = token

    def create_fork(self, owner, repo):
        url = f"{self.base_url}/repos/{owner}/{repo}/forks"
        headers = {
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json'
        }

        response = requests.post(url, headers=headers)
        if response.status_code == 202:
            return response.json()["clone_url"]
        raise Exception(f"GitHub fork failed: {response.json()}")

    def submit_spec_file(self, fork_owner, fork_repo, content, file_path, branch="main"):
        url = f"{self.base_url}/repos/{fork_owner}/{fork_repo}/contents/{file_path}"
        headers = {
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json'
        }

        data = {
            "message": "Add spec file",
            "content": b64encode(content.encode()).decode(),
            "branch": branch
        }

        response = requests.put(url, headers=headers, json=data)
        if response.status_code == 201:
            return response.json()["content"]["path"]
        raise Exception(f"GitHub提交失败: {response.status_code} {response.text}")

    def comment_on_pr(self, owner, repo, pr_num, comment):
        pass


class GitCodeForkService(ForkServiceInterface):
    def __init__(self, token):
        self.base_url = "https://api.gitcode.com/api/v5"
        self.token = token

    def create_fork(self, owner, repo):
        url = f"{self.base_url}/repos/{owner}/{repo}/forks"

        # 构造请求参数
        params = {'access_token': self.token}
        # 过滤空值参数
        response = requests.post(
            url,
            params=params,
            headers={'Content-Type': 'application/json'}
        )
        if response.status_code == 200:
            return f"https://gitcode.com/{response.json()['full_name']}"
        raise Exception(f"GitCode fork失败: {response.status_code} {response.text}")

    def submit_spec_file(self, fork_owner, fork_repo, content, file_path, branch="main"):
        url = f"{self.base_url}/repos/{fork_owner}/{fork_repo}/contents/{file_path}"
        params = {'access_token': self.token}

        data = {
            "content": b64encode(content.encode()).decode(),
            "message": "Add spec file",
            "branch": branch
        }

        response = requests.post(url, params=params, json=data)
        if response.status_code == 201:
            return response.json()["path"]
        raise Exception(f"GitCode提交失败: {response.status_code} {response.text}")

    def comment_on_pr(self, owner, repo, pr_num, comment):
        pass


# 工厂层
class ForkServiceFactory:
    @staticmethod
    def get_service(platform, token):
        services = {
            "gitee": GiteeForkService,
            "github": GitHubForkService,
            "gitcode": GitCodeForkService
        }
        service_class = services.get(platform.lower())
        if not service_class:
            raise ValueError(f"Unsupported platform: {platform}")
        return service_class(token)


def parse_repo_url(repo_url):
    """解析仓库链接，返回平台标识、owner和repo名称"""
    parsed = urlparse(repo_url)

    # 识别代码平台
    domain = parsed.netloc.lower()
    if 'gitee.com' in domain:
        platform = 'gitee'
        token = settings.gitee_token
    elif 'github.com' in domain:
        platform = 'github'
        token = settings.github_token
    elif 'gitcode.com' in domain:
        platform = 'gitcode'
        token = settings.gitcode_token
    else:
        raise ValueError("Unsupported platform")

    # 提取路径参数
    path_parts = parsed.path.strip('/').split('/')
    if len(path_parts) < 2:
        raise ValueError("Invalid repository URL")

    owner, repo = path_parts[0], path_parts[1]

    # 处理可能存在的 .git 后缀
    if repo.endswith('.git'):
        repo = repo[:-4]

    return platform, token, owner, repo


def parse_clone_url(clone_url: str) -> tuple:
    """解析fork后的仓库URL，返回(平台, 拥有者, 仓库名)"""
    parsed = urlparse(clone_url)
    path = parsed.path.strip('/')

    # 分割路径部分
    path_parts = path.split('/')
    if len(path_parts) < 2:
        raise ValueError("Invalid clone URL")

    owner, repo = path_parts[0], path_parts[1]

    # 处理可能的.git后缀
    if repo.endswith('.git'):
        repo = repo[:-4]

    return owner, repo


def update_spec_file(repo_url, file_content):
    """
    更新指定仓库的.spec文件
    :param repo_url: 仓库URL
    :param file_content: 文件内容
    """
    platform, token, owner, repo = parse_repo_url(repo_url)
    service = ForkServiceFactory.get_service(platform, token)
    clone_url = service.create_fork(owner, repo)
    fork_owner, fork_repo = parse_clone_url(clone_url)
    file_path = f'{fork_repo}.spec'
    try:
        file_path, sha = service.submit_spec_file(
            fork_owner=fork_owner,
            fork_repo=repo,  # 假设仓库名不变
            content=file_content,
            file_path=file_path
        )
        print(f"文件已提交至: {file_path}")
        return clone_url, sha
    except Exception as e:
        print(f"提交失败: {str(e)}")


def comment_on_pr(repo_url, pr_num, comment):
    platform, token, owner, repo = parse_repo_url(repo_url)
    service = ForkServiceFactory.get_service(platform, token)
    try:
        service.comment_on_pr(
            owner=owner,
            repo=repo,
            pr_num=pr_num,
            comment=comment
        )
    except Exception as e:
        print(f"提交失败: {str(e)}")
