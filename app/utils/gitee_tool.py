# 标准库
import json
import logging
import os
import tarfile
import tempfile
from urllib.parse import urlparse

# 第三方库
import requests


GITEE_API = "https://gitee.com/api/v5"
logger = logging.getLogger(__name__)


def parse_pr_url(pr_url):
    """解析Gitee PR链接"""
    path = urlparse(pr_url).path.strip('/').split('/')
    if len(path) < 3 or path[2] != 'pulls':
        raise ValueError("无效的Gitee PR链接格式")
    return path[0], path[1], path[3]


def get_pr_files(owner, repo, pr_number, token=None):
    """获取新增/修改的压缩文件"""
    params = {'access_token': token} if token else {}
    url = f"{GITEE_API}/repos/{owner}/{repo}/pulls/{pr_number}/files"

    response = requests.get(url, params=params)
    response.raise_for_status()

    valid_files = []
    for f in response.json():
        # 只处理新增和修改的压缩文件
        if f.get('status') in ['added'] and f.get('filename', '').endswith(('.tar.gz', '.gem')):
            valid_files.append((
                f['filename'],
                f['raw_url']
            ))
    return valid_files


def analyze_compressed_file(file_path):
    """分析压缩文件结构（返回可排序的路径字符串）"""

    def get_sorted_paths(members):
        return sorted([m.name for m in members if m.name])

    if file_path.endswith('.gem'):
        with tarfile.open(file_path, 'r:*') as gem:
            data_tar = next((m for m in gem if m.name == 'data.tar.gz'), None)
            if not data_tar:
                raise ValueError("gem文件中缺少data.tar.gz")

            data = gem.extractfile(data_tar)
            with tarfile.open(fileobj=data, mode='r:*') as inner_tar:
                return get_sorted_paths(inner_tar.getmembers())

    with tarfile.open(file_path, 'r:*') as tar:
        return get_sorted_paths(tar.getmembers())


def download_gitee_file(raw_url, token=None):
    """下载Gitee原始文件"""
    params = {'access_token': token} if token else {}
    parsed = urlparse(raw_url)
    new_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    response = requests.get(new_url, params=params, stream=True)
    response.raise_for_status()

    _, ext = os.path.splitext(raw_url)
    fd, path = tempfile.mkstemp(suffix=ext)

    with os.fdopen(fd, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    return path


def build_directory_tree(file_list):
    """构建目录树结构"""
    tree = {}
    for path in file_list:
        current = tree
        parts = path.split('/')
        for part in parts:
            if part:  # 过滤空字符串
                if part not in current:
                    current[part] = {}
                current = current[part]
    return tree


def generate_json_tree(tree):
    """生成带类型标识的JSON结构"""

    def convert(node):
        children = {}
        for name, child_node in node.items():
            if child_node:  # 目录
                children[name] = {
                    "type": "directory",
                    "children": convert(child_node)
                }
            else:  # 文件
                children[name] = {"type": "file"}
        return children

    return {
        "type": "root",
        "children": convert(tree)
    }


def get_dir_json(pr_url, token=None):
    try:
        owner, repo, pr_number = parse_pr_url(pr_url)
        files = get_pr_files(owner, repo, pr_number, token)

        if not files:
            logger.info("该PR中没有新增的压缩文件")
            return

        logger.info(f"找到{len(files)}个压缩文件:")
        for i, (filename, _) in enumerate(files, 1):
            logger.info(f"{i}. {filename}")

        for filename, raw_url in files:
            logger.info(f"\n分析文件: {filename}")
            temp_file = None

            try:
                temp_file = download_gitee_file(raw_url, token)
                structure = analyze_compressed_file(temp_file)

                dir_tree = build_directory_tree(structure)
                json_output = generate_json_tree(dir_tree)

                logger.info("\nJSON格式目录结构:")
                logger.info((json.dumps(json_output, indent=2, ensure_ascii=False)))

            except Exception as e:
                logger.info(f"分析失败: {str(e)}")
            finally:
                if temp_file and os.path.exists(temp_file):
                    os.remove(temp_file)

    except Exception as e:
        logger.info(f"发生错误: {str(e)}")
