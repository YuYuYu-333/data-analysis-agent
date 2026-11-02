# 零售数据仓库 · Schema 与指标口径

> 本文件是 Schema MCP Server 的检索语料，按 `##` / `###` 小节切块。
> 数据由 `scripts/generate_data.py` 生成（随机种子 42），`retail.db` 不提交仓库。
> 评测基准日 `as_of = 2026-10-31`：所有「本月 / 上月 / 本季度」都相对这一天，不随系统时间变化。

## 1. 数据概况

- 业务域：连锁零售（门店 + 商品 + 订单 + 明细）
- 规模：12 家门店、60 个商品、5000 条订单、约 13500 行明细
- 时间范围：`2026-05-01` 至 `2026-10-31`，共 6 个自然月
- 金额单位：人民币元（REAL）
- 数据性质：**合成数据**，固定种子可复现，不是真实业务数据

## 2. 表 store（门店）

| 字段 | 类型 | 含义 |
|---|---|---|
| store_id | TEXT | 门店编号，主键，格式 `S01`–`S12` |
| store_name | TEXT | 门店名称，例如「上海徐汇店」 |
| region | TEXT | 大区，取值见「枚举值」 |
| city | TEXT | 城市 |
| opened_at | TEXT | 开业日期，`YYYY-MM-DD`；所有门店都在 2026-05-01 之前开业 |

## 3. 表 product（商品）

| 字段 | 类型 | 含义 |
|---|---|---|
| product_id | TEXT | 商品编号，主键，格式 `P01`–`P60` |
| product_name | TEXT | 商品名称 |
| category | TEXT | 品类，5 种，见「枚举值」 |
| list_price | REAL | 标价（原价），单位元 |

## 4. 表 sales_order（订单头）

| 字段 | 类型 | 含义 |
|---|---|---|
| order_id | TEXT | 订单编号，主键，格式 `O000001` 起 |
| store_id | TEXT | 下单门店，关联 `store.store_id` |
| order_date | TEXT | 下单日期，`YYYY-MM-DD`，范围 2026-05-01 ~ 2026-10-31 |
| channel | TEXT | 渠道：`线上` / `线下` |
| status | TEXT | 状态：`completed`（已完成）/ `cancelled`（已取消） |
| discount_amount | REAL | 订单优惠总额 = Σ(明细数量 × 商品标价) − Σ(明细成交金额)；**只记录优惠了多少，不参与销售额口径**（见 8.1） |

## 5. 表 sales_item（订单明细）

| 字段 | 类型 | 含义 |
|---|---|---|
| item_id | TEXT | 明细编号，主键，格式 `I0000001` 起 |
| order_id | TEXT | 所属订单，关联 `sales_order.order_id` |
| product_id | TEXT | 商品，关联 `product.product_id` |
| quantity | INTEGER | 购买数量，≥ 1 |
| unit_price | REAL | 成交单价，单位元；**已含优惠，满足 `unit_price ≤ product.list_price`** |
| amount | REAL | 成交金额，等于 `quantity * unit_price` |
| refunded | INTEGER | 是否发生退款：`1` 是 / `0` 否；`refunded = 1` 当且仅当 `refund_amount > 0` |
| refund_amount | REAL | 退款金额，`0 ≤ refund_amount ≤ amount`；支持部分退款；无退款时为 `0`（不是 NULL） |

## 6. 枚举值

### 6.1 region（大区）

| 大区 | 城市（每城一店） |
|---|---|
| 华东 | 上海、杭州、南京 |
| 华南 | 广州、深圳、佛山 |
| 华北 | 北京、天津、石家庄 |
| 西南 | 成都、重庆、昆明 |

### 6.2 channel（渠道）

`线上`、`线下`

### 6.3 status（订单状态）

- `completed`：已完成，计入所有经营指标。
- `cancelled`：已取消；**它的明细仍然保留在 `sales_item` 中**，但不计入任何经营指标。

### 6.4 category（品类）

`饮料`、`零食`、`生鲜`、`日化`、`粮油`（每个品类 12 个商品）

### 6.5 refunded（退款标记）

`0` / `1`

## 7. 表关系

```
store 1 ──< sales_order 1 ──< sales_item >── 1 product
```

- `sales_order.store_id → store.store_id`
- `sales_item.order_id → sales_order.order_id`
- `sales_item.product_id → product.product_id`
- 一个订单只属于一家门店；一个订单有多条明细；一条明细只对应一个商品

## 8. 指标口径

> 口径必须唯一。同一个词不允许有两种算法。

### 8.1 销售额

**定义**：已完成订单的净成交金额，等于明细成交金额减去退款金额。

```sql
SUM(sales_item.amount - sales_item.refund_amount)
-- 仅统计 sales_order.status = 'completed' 的订单
```

**要点**：

- **只算 `completed`**；`cancelled` 订单的明细即使存在也不计。
- `discount_amount` **不再减一次**：`unit_price` 已经是成交价（已含优惠），再减就是重复扣减。
- 部分退款的明细，用 `amount - refund_amount` 得到净额。

### 8.2 订单数

**定义**：`COUNT(DISTINCT sales_order.order_id)`，仅统计 `completed` 订单。

**要点**：一个订单有多条明细，**不能** `COUNT(*)` 明细行，也**不能** `COUNT(order_id)` 不去重。

### 8.3 客单价

**定义**：销售额 / 订单数。

```sql
SUM(i.amount - i.refund_amount) / COUNT(DISTINCT o.order_id)
-- 分子分母都限定在同一范围（同一时间、同一门店 / 大区等）
```

**要点**：分母是**去重订单数**，不是明细行数。

### 8.4 退款率

**定义**：发生退款的明细行数 / 全部明细行数。

```sql
SUM(CASE WHEN i.refunded = 1 THEN 1 ELSE 0 END) * 1.0 / COUNT(*)
-- 仅统计 completed 订单的明细行
```

**要点**：

- 分母是**明细行**，不是订单数。
- 必须排除 `cancelled` 订单的明细，否则分母被无意义地放大。
- 分子按「明细行」计数：一条明细即使部分退款，也只算 1 行。

### 8.5 环比

**定义**：`(本期 - 上期) / 上期`；上期 = 前一个自然月；上期值为 0 或不存在时返回 NULL。

示例：`as_of = 2026-10-31` 时，「本月」= 2026-10，「上月」= 2026-09；9 月环比 8 月。

### 8.6 时间口径

- 所有指标都先按 `order_date` 过滤。
- `order_date` 是 TEXT，格式 `YYYY-MM-DD`；月份判断用 `substr(order_date, 1, 7) = '2026-09'` 或日期区间 `>= '2026-09-01' AND < '2026-10-01'`。
- **「上月」固定指 2026-09**（相对 `as_of`），不要用 `date('now')`，否则参考 SQL 会随时间失效。
- 数据从 2026-05 开始：5 月没有环比（上期不存在）。

## 9. 已知陷阱

1. **取消订单的明细还在表里**：任何经营指标都要 `JOIN sales_order` 并过滤 `status = 'completed'`，否则结果虚高。
2. **LEFT JOIN 放大行数**：订单头连明细再 `COUNT(*)` 或 `SUM(amount)`，会把订单级字段重复累加。订单级指标先在明细层聚合，或使用 `COUNT(DISTINCT order_id)`。
3. **客单价分母**：必须是去重订单数，不是明细行数。
4. **退款率分母**：是明细行数，不是订单数；且要排除 cancelled 订单。
5. **折扣不要重复扣**：`discount_amount` 是信息字段，销售额已经通过 `unit_price` 体现了优惠。
6. **部分退款**：`refund_amount` 可能小于 `amount`，不能把整行金额都减掉。
7. **日期是文本**：不要对 `order_date` 做数值运算；跨年时前缀匹配要小心。
8. **空值**：业务表没有 NULL；无退款时 `refund_amount = 0`，不要用 `IS NULL` 判断。

## 10. 数据分布（生成器的目标值）

- 订单状态：约 5% 为 `cancelled`
- 渠道：线上约 45%，线下约 55%
- 退款：`completed` 订单中约 8% 的明细行发生退款，以部分退款为主
- 订单日期在 6 个月内按天分布
- 每个订单 1–5 条明细，平均约 2.7 条

> 这些是生成目标，不是硬约束；参考 SQL 一律以 `retail.db` 的实际数据为准。
