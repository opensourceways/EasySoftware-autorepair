import requests


class BuildLogFetcher:
    @staticmethod
    def get_build_log(url):
        try:
            # 发送GET请求
            response = requests.get(url)

            # 检查请求是否成功
            response.raise_for_status()

            # 将响应内容按行分割
            lines = response.text.splitlines()

            # 只保留最后500行
            last_500_lines = lines[-500:]

            # 将行列表重新组合为字符串
            return "\n".join(last_500_lines)
        except requests.exceptions.RequestException as e:
            # 处理请求异常
            print(f"Error fetching URL: {e}")
            return None


get_build_log = BuildLogFetcher.get_build_log
