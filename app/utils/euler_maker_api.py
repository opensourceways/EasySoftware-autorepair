import requests
import euler_api


def get_request_headers():
    token = euler_api.get_token()
    if not token:
        return {}

    return {
        "Authorization": token
    }


def add_software_package(project, software_name, software_desc, software_repo_url, software_branch):
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
        print("请求成功")
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
        print("请求成功")
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
        print(data)
        print("请求成功")
    except requests.exceptions.RequestException as e:
        print("请求失败:", e)


start_build_single("test-repair", "test")


def get_job_build_result(project, job_id):
    api_url = "https://eulermaker.compass-ci.openeuler.openatom.cn/api/data-api/search"
