import time

import requests
from . import euler_api
from ..config import settings


def get_request_headers():
    token = euler_api.get_token()
    if not token:
        return {}

    return {
        "Authorization": token
    }


def add_software_package(project, software_name, software_desc, software_repo_url, software_branch="master"):
    api_url = f"https://eulermaker.compass-ci.openeuler.openatom.cn/api/api/os/{project}"
    body = {"package_repos+": [
        {
            "spec_name": software_name,
            "spec_url": software_repo_url,
            "spec_branch": software_branch,
            "spec_description": software_desc
        }
    ]}
    try:
        response = requests.put(
            api_url,
            json=body,  # 自动设置headers的Content-Type
            headers=get_request_headers(),
            timeout=50
        )
        response.raise_for_status()  # 自动抛出HTTP错误
    except requests.exceptions.RequestException as e:
        print("请求失败:", e)


def add_build_target(project, software_package, os_variant, architecture, ground_projects, flag_build=True,
                     flag_publish=True):
    api_url = f"https://eulermaker.compass-ci.openeuler.openatom.cn/api/api/os/{project}"
    body = {"package_overrides": {software_package: {"build_targets+": [
        {"os_variant": os_variant, "architecture": architecture,
         "ground_projects": ground_projects, "flags": {"build": flag_build, "publish": flag_publish}}]}}}
    try:
        response = requests.put(
            api_url,
            json=body,  # 自动设置headers的Content-Type
            headers=get_request_headers(),
            timeout=50
        )
        response.raise_for_status()  # 自动抛出HTTP错误
    except requests.exceptions.RequestException as e:
        print("请求失败:", e)


def start_build_single(project, software_package):
    api_url = f"https://eulermaker.compass-ci.openeuler.openatom.cn/api/api/os/{project}/build_single"
    body = {"packages": software_package}
    try:
        response = requests.post(
            api_url,
            json=body,  # 自动设置headers的Content-Type
            headers=get_request_headers(),
            timeout=50
        )
        response.raise_for_status()  # 自动抛出HTTP错误
        data = response.json()
    except requests.exceptions.RequestException as e:
        print("请求失败:", e)


def get_build_id(os_project, packages):
    api_url = "https://eulermaker.compass-ci.openeuler.openatom.cn/api/data-api/search"
    body = {"index": "builds", "query": {"query": {"bool": {
        "must": [{"term": {"packages": packages}}, {"term": {"os_project": os_project}}]}},
        "size": 0, "aggs": {
            "group_by_architecture": {"terms": {"field": "build_target.architecture"}, "aggs": {
                "group_by_os_variant": {"terms": {"field": "build_target.os_variant"}, "aggs": {"latest_build_info": {
                    "top_hits": {"size": 1,
                                 "_source": ["build_target", "build_id", "create_time", "packages", "os_project",
                                             "status", "build_packages"],
                                 "sort": [{"create_time": {"order": "desc"}}]}}}}}}}}}
    try:
        response = requests.post(
            api_url,
            json=body,  # 自动设置headers的Content-Type
            timeout=50
        )
        response.raise_for_status()  # 自动抛出HTTP错误
        data = response.json()
        hits = data['aggregations']['group_by_architecture']['buckets'][0]['group_by_os_variant']['buckets'][0][
            'latest_build_info']['hits']['hits']
        for hit in hits:
            build_id = hit['_source']['build_id']
            return build_id
    except requests.exceptions.RequestException as e:
        print("请求失败:", e)


def get_job_id(os_project, packages):
    api_url = "https://eulermaker.compass-ci.openeuler.openatom.cn/api/data-api/search"
    build_id = get_build_id(os_project, packages)
    body = {"index": "jobs", "query": {"_source": [""], "query": {"bool": {
        "must": [{"term": {"os_project": os_project}}, {"term": {"package": packages}},
                 {"term": {"build_id": build_id}}]}}}}
    try:
        response = requests.post(
            api_url,
            json=body,  # 自动设置headers的Content-Type
            timeout=50
        )
        response.raise_for_status()  # 自动抛出HTTP错误
        data = response.json()
        hit = data['hits']['hits'][0]  # 获取第一个匹配项
        id_value = hit['_id']
        return id_value
    except requests.exceptions.RequestException as e:
        print("请求失败:", e)


def get_result_root(job_id):
    api_url = "https://eulermaker.compass-ci.openeuler.openatom.cn/api/data-api/search"
    body = {"index": "jobs",
            "query": {"size": 1, "_source": ["os_arch", "job_stage", "result_root", "job_health", "job_state"],
                      "query": {"match": {"id": job_id}}}}
    try:
        response = requests.post(
            api_url,
            json=body,  # 自动设置headers的Content-Type
            timeout=50
        )
        response.raise_for_status()  # 自动抛出HTTP错误
        data = response.json()
        hit = data['hits']['hits'][0]  # 获取第一个匹配项
        result_root = hit['_source']['result_root']
        return result_root
    except requests.exceptions.RequestException as e:
        print("请求失败:", e)


def get_log_url(result_root):
    return f"https://eulermaker.compass-ci.openeuler.openatom.cn/api/{result_root}/dmesg"


def get_job_build_status(os_project, packages):
    build_id = get_build_id(os_project, packages)
    print("the build id is ", build_id)
    api_url = "https://eulermaker.compass-ci.openeuler.openatom.cn/api/data-api/search"
    max_retries = 20  # 最大轮询次数
    retry_interval = 30  # 轮询间隔时间（秒）

    # 查询特定 build_id 的请求体
    query_body = {
        "index": "builds",
        "query": {
            "size": 1,
            "_source": ["build_id", "status"],
            "query": {"term": {"build_id": build_id}}
        }
    }
    for _ in range(max_retries):
        try:
            response = requests.post(api_url, json=query_body, timeout=50)
            response.raise_for_status()
            data = response.json()

            if data['hits']['hits']:
                current_status = data['hits']['hits'][0]['_source']['status']
                if current_status == 201:
                    return True
                elif current_status == 202:
                    return False

            # 如果未返回有效状态，继续轮询
            time.sleep(retry_interval)

        except requests.exceptions.RequestException as e:
            print("轮询请求失败:", e)
            time.sleep(retry_interval)  # 失败后等待再重试

    # 轮询结束后仍未得到结果
    print("轮询超时，未获取到最终状态")
    return None
