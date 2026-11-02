"""
生成零售数据集：门店 / 商品 / 订单 / 明细。
固定随机种子，重复运行得到同一份数据。
用法：python scripts/generate_data.py
"""

import sqlite3
from pathlib import Path

