"""
模型客户端：集中创建，其他模块只
import，不自己创建。
DeepSeek 负责对话 / SQL；SiliconFlow 负责
schema embedding。
"""

from openai import AsyncOpenAI, OpenAI

from app.config import DEEPSEEK_API_KEY, SILICONFLOW_API_KEY

CHAT_MODEL = "deepseek-flash"
EMBED_MODEL = "BAAI/bge-m3"

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"

chat_client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL,
    timeout=30.0,
    max_retries=2,
)

embed_client = OpenAI(
    api_key=SILICONFLOW_API_KEY,
    base_url=SILICONFLOW_BASE_URL,
    timeout=15.0,
    max_retries=2,
)
