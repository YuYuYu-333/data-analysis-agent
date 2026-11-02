"""
生成零售数据集：门店 / 商品 / 订单 / 明细。
固定随机种子，重复运行得到同一份数据。
用法：python scripts/generate_data.py
"""

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

SEED = 42
ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "retail.db"

STORES = [
    ("S01", "上海徐汇店", "华东", "上海", "2023-03-15"),
    ("S02", "杭州西湖店", "华东", "杭州", "2022-09-01"),
    ("S03", "南京鼓楼店", "华东", "南京", "2021-06-20"),
    ("S04", "广州天河店", "华南", "广州", "2022-11-05"),
    ("S05", "深圳南山店", "华南", "深圳", "2023-01-10"),
    ("S06", "佛山禅城店", "华南", "佛山", "2021-12-18"),
    ("S07", "北京朝阳店", "华北", "北京", "2020-05-09"),
    ("S08", "天津和平店", "华北", "天津", "2022-07-22"),
    ("S09", "石家庄长安店", "华北", "石家庄", "2023-04-03"),
    ("S10", "成都锦江店", "西南", "成都", "2021-08-30"),
    ("S11", "重庆渝中店", "西南", "重庆", "2022-03-14"),
    ("S12", "昆明五华店", "西南", "昆明", "2023-06-01"),
]

PRODUCTS = {
    "饮料": [
        "矿泉水", "苏打水", "可乐", "雪碧",
        "橙汁", "苹果汁",
        "茉莉花茶", "绿茶", "咖啡", "牛奶",
        "酸奶", "豆奶",
    ],
    "零食": [
        "薯片", "饼干", "巧克力", "糖果",
        "坚果", "瓜子",
        "辣条", "海苔", "爆米花", "果冻",
        "牛肉干", "锅巴",
    ],
    "生鲜": [
        "鸡蛋", "猪肉", "鸡胸肉", "牛肉",
        "鲈鱼", "虾仁",
        "西红柿", "土豆", "苹果", "香蕉",
        "青菜", "豆腐",
    ],
    "日化": [
        "洗发水", "沐浴露", "牙膏", "牙刷",
        "洗衣液", "洗洁精",
        "纸巾", "湿巾", "香皂", "护手霜",
        "面膜", "防晒霜",
    ],
    "粮油": [
        "大米", "面粉", "花生油", "菜籽油",
        "橄榄油", "酱油",
        "醋", "盐", "白糖", "料酒", "蚝油",
        "淀粉",
    ],
}

PRICE_RANGES = {
    "饮料": (2.5, 15.0),
    "零食": (3.0, 25.0),
    "生鲜": (5.0, 60.0),
    "日化": (10.0, 80.0),
    "粮油": (8.0, 120.0),
}

ORDER_COUNT = 5000
CANCELLED_RATE = 0.05
REFUND_RATE = 0.08
ITEM_COUNT_WEIGHTS = [18, 30, 25, 17, 10]  # 1–5 条明细，平均约 2.7
QUANTITY_WEIGHTS = [50, 30, 15, 5]  # 每行 1–4 件
CHANNEL_WEIGHTS = [45, 55]  # 线上 / 线下


def create_tables(conn: sqlite3.Connection) -> None:
    """删除旧表,按 data/schema.md 建 4 张空表."""
    conn.executescript(
        """
        DROP TABLE IF EXISTS sales_item;
        DROP TABLE IF EXISTS sales_order;
        DROP TABLE IF EXISTS product;
        DROP TABLE IF EXISTS store;
        
        CREATE TABLE store (
              store_id   TEXT PRIMARY KEY,
              store_name TEXT NOT NULL,
              region     TEXT NOT NULL,
              city       TEXT NOT NULL,
              opened_at  TEXT NOT NULL
          );
        
        CREATE TABLE product (
              product_id   TEXT PRIMARY KEY,
              product_name TEXT NOT NULL,
              category     TEXT NOT NULL,
              list_price   REAL NOT NULL CHECK(list_price > 0)
          );
          
        CREATE TABLE sales_order (
              order_id        TEXT PRIMARY KEY,
              store_id        TEXT NOT NULL REFERENCES store(store_id),
              order_date      TEXT NOT NULL,
              channel         TEXT NOT NULL CHECK (channel IN ('线上', '线下')),
              status          TEXT NOT NULL CHECK (status IN ('completed', 'cancelled')),
              discount_amount REAL NOT NULL DEFAULT 0 CHECK (discount_amount >= 0)
          );  
          
        CREATE TABLE sales_item (
              item_id       TEXT PRIMARY KEY,
              order_id      TEXT NOT NULL REFERENCES sales_order(order_id),
              product_id    TEXT NOT NULL REFERENCES product(product_id),
              quantity      INTEGER NOT NULL CHECK (quantity >= 1),
              unit_price    REAL NOT NULL CHECK (unit_price >= 0),
              amount        REAL NOT NULL CHECK (amount >= 0),
              refunded      INTEGER NOT NULL DEFAULT 0 CHECK (refunded IN (0, 1)),
              refund_amount REAL NOT NULL DEFAULT 0 CHECK (refund_amount >= 0),
              CHECK (refund_amount <= amount),
              CHECK ((refunded = 0 AND refund_amount = 0) OR (refunded = 1 AND refund_amount > 0))
          );
        """
    )


def generate_stores(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO store (store_id, store_name, region, city, opened_at) "
        "VALUES (?, ?, ?, ?, ?)",
        STORES,
    )


def generate_products(conn: sqlite3.Connection) -> None:
    rows = []
    product_id = 1
    for category, names in PRODUCTS.items():
        low, high = PRICE_RANGES[category]
        for name in names:
            rows.append(
                (
                    f"P{product_id:02d}",
                    name,
                    category,
                    round(random.uniform(low, high), 2),
                )
            )
            product_id += 1
    conn.executemany(
        "INSERT INTO product (product_id, product_name, category, list_price) "
        "VALUES (?, ?, ?, ?)",
        rows,
    )


def generate_orders(conn: sqlite3.Connection) -> None:
    products = conn.execute("SELECT product_id, list_price FROM product ORDER BY product_id").fetchall()
    stores = [
        row[0] for row in conn.execute("SELECT store_id FROM store ORDER BY store_id")
    ]

    start = date(2026, 5, 1)
    days = (date(2026, 10, 31) - start).days + 1

    orders = []
    items = []
    item_id = 1

    for number in range(1, ORDER_COUNT + 1):
        order_id = f"O{number:06d}"
        store_id = random.choice(stores)
        order_date = (start + timedelta(days=random.randrange(days))).isoformat()
        channel = random.choices(["线上", "线下"], weights=CHANNEL_WEIGHTS)[0]
        cancelled = random.random() < CANCELLED_RATE
        status = "cancelled" if cancelled else "completed"

        original_total = 0.0
        amount_total = 0.0
        order_items = []

        item_count = random.choices([1, 2, 3, 4, 5], weights=ITEM_COUNT_WEIGHTS)[0]
        for _ in range(item_count):
            product_id, list_price = random.choice(products)
            quantity = random.choices([1, 2, 3, 4], weights=QUANTITY_WEIGHTS)[0]
            unit_price = round(list_price * random.uniform(0.80, 1.0), 2)
            amount = round(quantity * unit_price, 2)

            refunded = 0
            refund_amount = 0.0
            if not cancelled and random.random() < REFUND_RATE:
                refunded = 1
                refund_amount = min(
                    amount,
                    max(0.01, round(amount * random.uniform(0.3, 1.0), 2)),
                )

            original_total += quantity * list_price
            amount_total += amount
            order_items.append(
                (
                    f"I{item_id:07d}",
                    order_id,
                    product_id,
                    quantity,
                    unit_price,
                    amount,
                    refunded,
                    refund_amount,
                )
            )
            item_id += 1

        discount_amount = round(max(0.0, original_total - amount_total), 2)
        orders.append(
            (order_id, store_id, order_date, channel, status, discount_amount)
        )
        items.extend(order_items)

    conn.executemany(
        "INSERT INTO sales_order "
        "(order_id, store_id, order_date, channel, status, discount_amount) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        orders,
    )
    conn.executemany(
        "INSERT INTO sales_item "
        "(item_id, order_id, product_id, quantity, unit_price, amount, refunded, refund_amount) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        items,
    )


def main() -> None:
    random.seed(SEED)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('PRAGMA foreign_keys = ON;')
        create_tables(conn)
        generate_stores(conn)
        generate_products(conn)
        generate_orders(conn)
    print(f"数据生成完成: {DB_PATH}")


if __name__ == '__main__':
    main()
