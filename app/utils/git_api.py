import os
import shutil
import stat
import subprocess
from abc import ABC, abstractmethod
from base64 import b64encode
from urllib.parse import urlparse
from app.config import settings
import requests
import logging

from app.utils.client import api_client

logger = logging.getLogger("git_api")


# 抽象接口层
class ForkServiceInterface(ABC):
    @abstractmethod
    def create_fork(self, owner, repo, pr_num):
        pass

    @abstractmethod
    def submit_spec_file(self, fork_owner, fork_repo, content, file_path, branch="master"):
        pass

    @abstractmethod
    def comment_on_pr(self, owner, repo, pr_number, comment):
        pass

    @abstractmethod
    def get_spec_content(self, owner, repo, pr_number, file_path, token=None):
        pass


# 平台具体实现层
class GiteeForkService(ForkServiceInterface):
    def __init__(self, token):
        self.client = api_client.ApiClient("gitee", token)
        self.current_user = self._get_current_user()

    def _get_current_user(self):
        """获取当前认证用户信息"""
        response = self.client.get("/user")
        if response.status_code == 200:
            return response.json()["login"]
        raise Exception(f"Failed to get user info: {response.text}")

    def _check_repo_exists(self, repo):
        """检查当前用户是否有指定仓库"""
        response = self.client.get(f"/repos/{self.current_user}/{repo}")
        return response.status_code == 200

    def _get_default_branch(self, repo):
        """获取仓库的默认分支名称"""
        response = self.client.get(f"/repos/{self.current_user}/{repo}")
        if response.status_code == 200:
            return response.json().get("default_branch", "master")
        return "master"

    def _get_branch_sha(self, repo, branch):
        """获取指定分支的SHA"""
        response = self.client.get(f"/repos/{self.current_user}/{repo}/branches/{branch}")
        if response.status_code == 200:
            return response.json()["commit"]["sha"]
        return None

    def _create_branch(self, repo, branch_name):
        # 先检查分支是否存在
        check_url = f"/repos/{self.current_user}/{repo}/branches/{branch_name}"
        check_response = self.client.get(check_url)

        # 分支已存在时跳过创建
        if check_response.status_code == 200:
            print(f"Branch {branch_name} already exists in {self.current_user}/{repo}.")
            return
        data = {
                "access_token": settings.gitee_token,
                "branch_name": branch_name,
                "refs": "master"
            }
        response = self.client.post(f"/repos/{self.current_user}/{repo}/branches", data=data)
        if response.status_code != 201:
            raise Exception(f"Failed to create branch {branch_name}: {response.json()}")
        print(f"Branch {branch_name} created successfully in {self.current_user}/{repo}.")

    def create_fork(self, owner, repo, branch):
        # 检查当前用户是否已有仓库
        if not self._check_repo_exists(repo):
            # 创建fork
            response = self.client.post(f"/repos/{owner}/{repo}/forks")
            if response.status_code != 201:
                raise Exception(f"Gitee fork failed: {response.json()}")
            print(f"Forked repository {self.current_user}/{repo} created.")

        # 创建新分支
        self._create_branch(repo, branch)

        # 返回新分支的URL
        return f"https://gitee.com/{self.current_user}/{repo}.git"

    def get_file_sha(self, owner, repo, file_path, branch="master"):
        response = self.client.get(f"/repos/{owner}/{repo}/contents/{file_path}?ref={branch}")
        if response.status_code == 200:
            return response.json()["sha"]

        return None

    def submit_spec_file(self, fork_owner, fork_repo, content, file_path, branch="master"):
        # 获取 SHA 值
        sha = self.get_file_sha(fork_owner, fork_repo, file_path, branch)
        data = {
            "content": b64encode(content.encode()).decode(),
            "message": "Add spec file",
            "branch": branch,
            "sha": sha
        }
        response = self.client.put(f"/repos/{fork_owner}/{fork_repo}/contents/{file_path}", data)
        if response.status_code == 200:
            return response.json()["content"]["path"], response.json()["commit"]["sha"]
        raise Exception(f"Gitee提交失败: {response.status_code} {response.text}")

    def comment_on_pr(self, owner, repo, pr_num, comment):
        data = {
            "body": comment
        }
        try:
            # 评论 PR
            response = self.client.post(f"/repos/{owner}/{repo}/pulls/{pr_num}/comments", data)
            response.raise_for_status()  # 检查是否成功
        except requests.exceptions.RequestException as e:
            print("评论 PR 失败:", e)

    def get_spec_content(self, owner, repo, pr_number, file_path, token=None):
        params = {"access_token": token}
        try:
            # 获取 PR 文件列表
            response = self.client.get(f"/repos/{owner}/{repo}/pulls/{pr_number}/files")
            response.raise_for_status()
            files = response.json()

            target_file = next((f for f in files if f["filename"] == file_path), None)
            if not target_file:
                print(f"文件 {file_path} 未在 PR 中找到")
                return None
            raw_response = requests.get(target_file['raw_url'], params=params)
            raw_response.raise_for_status()
            return raw_response.text
        except requests.exceptions.RequestException as e:
            print(f"API 请求失败: {e}")
            return None


class GitHubForkService(ForkServiceInterface):
    def __init__(self, token):
        self.client = api_client.ApiClient("github", token)

    def create_fork(self, owner, repo, pr_num):
        response = self.client.post(f"/repos/{owner}/{repo}/forks")
        if response.status_code == 202:
            return response.json()["clone_url"]
        raise Exception(f"GitHub fork failed: {response.json()}")

    def submit_spec_file(self, fork_owner, fork_repo, content, file_path, branch="main"):
        data = {
            "message": "Add spec file",
            "content": b64encode(content.encode()).decode(),
            "branch": branch
        }
        response = self.client.put(f"/repos/{fork_owner}/{fork_repo}/contents/{file_path}", data)
        if response.status_code == 201:
            return response.json()["content"]["path"]
        raise Exception(f"GitHub提交失败: {response.status_code} {response.text}")

    def comment_on_pr(self, owner, repo, pr_num, comment):
        pass

    def get_spec_content(self, owner, repo, pr_number, file_path, token=None):
        pass


class GitCodeForkService(ForkServiceInterface):
    def __init__(self, token):
        self.client = api_client.ApiClient("gitcode", token)
        self.base_url = "https://api.gitcode.com/api/v5"
        self.token = token

    def create_fork(self, owner, repo, pr_num):
        # 过滤空值参数
        response = self.client.post(
            f"/repos/{owner}/{repo}/forks",
        )
        if response.status_code == 200:
            return f"https://gitcode.com/{response.json()['full_name']}"
        raise Exception(f"GitCode fork失败: {response.status_code} {response.text}")

    def submit_spec_file(self, fork_owner, fork_repo, content, file_path, branch="main"):
        data = {
            "content": b64encode(content.encode()).decode(),
            "message": "Add spec file",
            "branch": branch
        }

        response = self.client.post(f"/repos/{fork_owner}/{fork_repo}/contents/{file_path}", data)
        if response.status_code == 201:
            return response.json()["path"]
        raise Exception(f"GitCode提交失败: {response.status_code} {response.text}")

    def comment_on_pr(self, owner, repo, pr_num, comment):
        pass

    def get_spec_content(self, owner, repo, pr_number, file_path, token=None):
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


def update_spec_file(service, owner, repo, file_content, branch):
    """
    更新指定仓库的.spec文件
    :param branch:
    :param repo:
    :param owner:
    :param service:
    :param file_content: 文件内容
    """
    clone_url = service.create_fork(owner, repo, branch)
    fork_owner, fork_repo = parse_clone_url(clone_url)
    file_path = f'{repo}.spec'
    try:
        file_path, sha = service.submit_spec_file(
            fork_owner=fork_owner,
            fork_repo=repo,  # 假设仓库名不变
            content=file_content,
            file_path=file_path,
            branch=branch,
        )
        print(f"文件已提交至: {file_path}")
        return clone_url, sha, branch
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


def get_spec_content(repo_url, pr_number, file_path):
    platform, token, owner, repo = parse_repo_url(repo_url)
    service = ForkServiceFactory.get_service(platform, token)
    return service.get_spec_content(owner, repo, pr_number, file_path, token)


def check_and_push(repo_url, new_content, pr_num):
    temp_dir = "temp_repo_to_amend_push"
    platform, token, owner, repo = parse_repo_url(repo_url)
    service = ForkServiceFactory.get_service(platform, token)
    branch = 'master'
    if service.current_user != owner:
        branch = f'repair-{pr_num}'
        update_spec_file(service, owner, repo, new_content, branch)
    else:
        file_path = f'{repo}.spec'
        try:
            authed_repo_url = f"https://{service.current_user}:{token}@gitee.com/{owner}/{repo}.git"

            subprocess.run(["git", "clone", authed_repo_url, temp_dir], check=True)

            with open(os.path.join(temp_dir, file_path), "w", encoding="utf-8") as f:
                f.write(new_content)

            subprocess.run(["git", "add", file_path], cwd=temp_dir, check=True)
            subprocess.run(["git", "commit", "--amend", "--no-edit"], cwd=temp_dir, check=True)
            subprocess.run(["git", "push", "origin", branch, "--force"], cwd=temp_dir, check=True)

        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, onerror=force_remove_readonly)


def force_remove_readonly(func, path, _):
    os.chmod(path, stat.S_IWRITE)
    func(path)
