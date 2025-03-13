import requests


class SpecFetcher:
    @staticmethod
    def get_spec_content(owner, repo, pr_number, file_path, token=None):
        # Gitee API 基础地址
        base_url = "https://gitee.com/api/v5/repos"
        # 构造 PR 文件列表请求 URL（token 通过 URL 参数传递）
        pr_files_url = f"{base_url}/{owner}/{repo}/pulls/{pr_number}/files"
        params = {"access_token": token} if token else {}

        try:
            # 获取 PR 文件列表
            response = requests.get(pr_files_url, params=params)
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


get_spec_content = SpecFetcher.get_spec_content
