import logging
import requests

from app.config import settings

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

    def chat(self, messages, max_tokens=settings.model_max_tokens, temperature=settings.model_temperature):
        """
        发送对话请求
        :param messages: prompt
        :param max_tokens: 生成的最大token数
        :param temperature: 生成多样性控制（0-1）
        :return: AI生成的回复
        """
        try:
            payload = {
                "model": settings.ai_model,  # 根据实际模型名称修改
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

    def analyze_build_log(self, repo, specContent, logContent):
        # 调用API
        response = self.chat(messages=[{"role": "system", "content": settings.system_prompt},
                                       {"role": "user",
                                        "content": settings.user_prompt.format(specContent=specContent,
                                                                               logContent=logContent)}])
        if "```spec" in response:
            new_spec = response.split("```spec")[1].split("```")[0].strip()
            return new_spec
        else:
            return response
