"""
集中配置：所有环境变量只在这里读，其他模块不碰 os.environ。
缺少必需项时在 import 阶段就报错，不要等到第一个请求。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY")

# 可选
CHECKPOINT_DB = Path(os.getenv("CHECKPOINT_DB") or ROOT / "data" / "checkpoints.db")
DATABASE_URL = os.getenv("DATABASE_URL")

# 服务层
API_KEY = os.getenv("API_KEY")
DEBUG = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")


def _require(name: str, value: str | None) -> None:
    if not value:
        raise RuntimeError(f"缺少环境变量 {name}. 请复制.env.example 为 .env 并填写")


_require("DEEPSEEK_API_KEY", DEEPSEEK_API_KEY)
_require("SILICONFLOW_API_KEY", SILICONFLOW_API_KEY)
