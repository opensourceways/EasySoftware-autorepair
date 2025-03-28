import asyncio
import logging
import time
import httpx
import requests
from typing import Any, Dict, List, Optional
from requests.exceptions import RequestException
from . import euler_api

# 常量定义
logger = logging.getLogger(__name__)
BASE_API_URL = "https://eulermaker.compass-ci.openeuler.openatom.cn/api/api/os"
BASE_DATA_API_URL = "https://eulermaker.compass-ci.openeuler.openatom.cn/api/data-api"
REQUEST_TIMEOUT = 50
MAX_RETRIES = 3
RETRY_DELAY = 1


def _request_wrapper(
        method: str,
        url: str,
        retries: int = MAX_RETRIES,
        **kwargs
) -> Optional[requests.Response]:
    """统一封装的请求处理函数，支持重试机制"""
    headers = get_request_headers()
    kwargs.setdefault("headers", headers)
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)

    for attempt in range(retries):
        try:
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except RequestException as e:
            print(f"请求失败 (尝试 {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                print(f"最终请求失败: {url}")
                return None


def get_request_headers() -> Dict[str, str]:
    """获取带认证的请求头"""
    token = euler_api.get_token()
    if not token:
        raise ValueError("无法获取认证token")
    return {"Authorization": token, "Content-Type": "application/json"}


def add_software_package(
        project: str,
        software_name: str,
        software_desc: str,
        software_repo_url: str,
        software_branch: str = "master"
) -> bool:
    """添加软件包到指定项目"""
    url = f"{BASE_API_URL}/{project}"
    body = {
        "package_repos+": [{
            "spec_name": software_name,
            "spec_url": software_repo_url,
            "spec_branch": software_branch,
            "spec_description": software_desc
        }]
    }

    response = _request_wrapper("PUT", url, json=body)
    return response is not None and response.status_code == 200


def add_build_target(
        project: str,
        software_package: str,
        os_variant: str,
        architecture: str,
        ground_projects: List[str],
        flag_build: bool = True,
        flag_publish: bool = True
) -> bool:
    """添加构建目标到指定软件包"""
    url = f"{BASE_API_URL}/{project}"
    body = {
        "package_overrides": {
            software_package: {
                "build_targets+": [{
                    "os_variant": os_variant,
                    "architecture": architecture,
                    "ground_projects": ground_projects,
                    "flags": {
                        "build": flag_build,
                        "publish": flag_publish
                    }
                }]
            }
        }
    }

    response = _request_wrapper("PUT", url, json=body)
    return response is not None and response.status_code == 200


def start_build_single(project: str, software_package: str) -> Optional[str]:
    """启动单个软件包构建"""
    url = f"{BASE_API_URL}/{project}/build_single"
    body = {"packages": software_package}

    response = _request_wrapper("POST", url, json=body)
    if response:
        return response.json().get("build_id")
    return None


def _get_aggregation_value(data: Dict, keys: List[str]) -> Any:
    """安全获取聚合查询结果"""
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list) and isinstance(key, int):
            current = current[key] if len(current) > key else None
        else:
            return None
        if current is None:
            return None
    return current


def get_build_id(os_project: str, packages: str) -> Optional[str]:
    """获取指定项目的构建ID"""
    url = f"{BASE_DATA_API_URL}/search"
    body = {
        "index": "builds",
        "query": {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"packages": packages}},
                        {"term": {"os_project": os_project}}
                    ]
                }
            },
            "size": 0,
            "aggs": {
                "group_by_architecture": {
                    "terms": {"field": "build_target.architecture"},
                    "aggs": {
                        "group_by_os_variant": {
                            "terms": {"field": "build_target.os_variant"},
                            "aggs": {
                                "latest_build_info": {
                                    "top_hits": {
                                        "size": 1,
                                        "_source": ["build_id"],
                                        "sort": [{"create_time": "desc"}]
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    response = _request_wrapper("POST", url, json=body)
    if not response:
        return None

    data = response.json()
    # 安全解析聚合结果
    bucket_path = [
        "aggregations", "group_by_architecture", "buckets", 0,
        "group_by_os_variant", "buckets", 0,
        "latest_build_info", "hits", "hits", 0, "_source", "build_id"
    ]
    return _get_aggregation_value(data, bucket_path)


def get_job_id(os_project: str, packages: str) -> Optional[str]:
    """获取任务ID"""
    build_id = get_build_id(os_project, packages)
    if not build_id:
        return None

    url = f"{BASE_DATA_API_URL}/search"
    body = {
        "index": "jobs",
        "query": {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"os_project": os_project}},
                        {"term": {"package": packages}},
                        {"term": {"build_id": build_id}}
                    ]
                }
            },
            "_source": []
        }
    }

    response = _request_wrapper("POST", url, json=body)
    if not response:
        return None

    data = response.json()
    hits = data.get("hits", {}).get("hits", [])
    return hits[0].get("_id") if hits else None


def get_result_root(job_id: str) -> Optional[str]:
    """获取任务结果根目录"""
    url = f"{BASE_DATA_API_URL}/search"
    body = {
        "index": "jobs",
        "query": {
            "size": 1,
            "_source": ["result_root"],
            "query": {"match": {"id": job_id}}
        }
    }

    response = _request_wrapper("POST", url, json=body)
    if not response:
        return None

    data = response.json()
    hits = data.get("hits", {}).get("hits", [])
    return hits[0].get("_source", {}).get("result_root") if hits else None


def get_log_url(result_root: str) -> str:
    """构造日志URL"""
    return f"https://eulermaker.compass-ci.openseuler.openatom.cn/{result_root}/dmesg"


def get_build_log(url: str, lines: int = 200) -> Optional[str]:
    """获取指定行数的构建日志"""
    try:
        with requests.get(url, stream=True, timeout=REQUEST_TIMEOUT) as response:
            response.raise_for_status()

            # 流式读取最后N行
            buffer = []
            for line in response.iter_lines(decode_unicode=True):
                buffer.append(line)
                if len(buffer) > lines * 2:  # 保留缓冲避免精确截断
                    buffer = buffer[-lines:]

            return '\n'.join(buffer[-lines:])
    except RequestException as e:
        print(f"获取日志失败: {e}")
        return None


async def get_build_status(
        build_id: str,
        max_retries: int = 10,
        base_delay: float = 30.0
) -> Optional[Dict]:
    """异步优化版本"""
    api_url = "https://eulermaker.compass-ci.openseuler.openagent.cn/api/data-api/search"
    query_body = {
        "index": "builds",
        "query": {
            "size": 1,
            "_source": ["build_id", "status", "progress"],
            "query": {"term": {"build_id": build_id}}
        }
    }

    async with httpx.AsyncClient() as client:
        for attempt in range(1, max_retries + 1):
            try:
                response = await client.post(api_url, json=query_body, timeout=50)
                response.raise_for_status()
                data = response.json()

                if data.get('hits', {}).get('hits'):
                    return data['hits']['hits'][0]['_source']

                logger.warning(f"Empty response, attempt {attempt}/{max_retries}")
                await asyncio.sleep(base_delay * attempt)

            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                logger.error(f"Request failed: {str(e)}")
                if attempt == max_retries:
                    break
                await asyncio.sleep(base_delay * (attempt ** 2))
    return None
