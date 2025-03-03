import logging
import requests

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class SiliconFlowChat:
    def __init__(self, api_key):
        self.api_key = api_key
        self.api_url = "https://api.siliconflow.cn/v1/chat/completions"  # 假设的接口地址
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

    def chat(self, messages, max_tokens=4096, temperature=0.1):
        """
        发送对话请求
        :param messages: prompt
        :param max_tokens: 生成的最大token数
        :param temperature: 生成多样性控制（0-1）
        :return: AI生成的回复
        """
        try:
            payload = {
                "model": "Qwen/Qwen2.5-Coder-32B-Instruct",  # 根据实际模型名称修改
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }

            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=payload,
                timeout=3000,  # 设置超时时间为30秒
            )

            if response.status_code == 200:
                res = response.json()
                ai_reply = res['choices'][0]['message']['content']
                return ai_reply
            else:
                return f"API请求失败，状态码：{response.status_code}，错误信息：{response.text}"

        except Exception as exp:
            return f"请求异常：{str(exp)}"

    def analyze_build_log(self, specContent, logContent):
        # 构建系统提示词
        system_prompt = """你是一个资深的RPM打包专家，请仔细分析提供的spec文件和构建日志，
    找出构建失败的原因，并给出修正后的完整spec文件内容。保持原有注释和结构，只修改必要部分。"""

        # 构建用户提示词
        user_prompt = f"""请根据以下构建日志分析spec文件需要修改的地方，并返回修正后的完整spec文件内容：
    
    === SPEC文件内容 ===
    {specContent}
    
    === 构建日志 ===
    {logContent}
    
    请按以下格式响应：
    1. 首先用中文简要说明需要修改的原因
    2. 然后输出修改后的完整spec文件内容，用```spec包裹
    3. 不要包含其他无关内容"""

        # 调用API
        response = self.chat(messages=[{"role": "system", "content": system_prompt},
                                       {"role": "user", "content": user_prompt}])
        if "```spec" in response:
            new_spec = response.split("```spec")[1].split("```")[0].strip()
            return new_spec
        else:
            return response
