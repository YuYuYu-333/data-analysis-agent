# 快速开始（完整版）

README 里只留最短路径。这里放每个变量的含义、测试与评测怎么跑、以及 Windows 上的几个坑。

## 环境

- Python 3.13（开发用 3.13.15，CI 在 Ubuntu + 3.13 上跑同一套）
- 不需要 Redis，也不需要数据库服务；`retail.db` 由脚本按固定种子生成
- 两个模型密钥：DeepSeek（生成 SQL 与结论）、SiliconFlow（schema 向量化与重排）

## 安装

```powershell
git clone https://github.com/YuYuYu-333/data-analysis-agent.git
cd data-analysis-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

首次执行报「禁止运行脚本」时，先放开当前会话的策略：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Linux / macOS：把激活命令换成 `source .venv/bin/activate`，路径分隔符换成 `/`。

## 配置 `.env`

```powershell
Copy-Item .env.example .env
```

| 变量 | 用途 | 必需 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 生成 SQL、写结论 | 是 |
| `SILICONFLOW_API_KEY` | schema 切片向量化（`BAAI/bge-m3`） | 是 |
| `API_KEY` | `/analyze` 的请求密钥；不填则该接口返回 503，`/demo` 不受影响 | 否 |
| `CHECKPOINT_DB` | 多轮检查点位置，默认 `data/checkpoints.db` | 否 |
| `DEBUG` | 设为 `1` 时响应里返回 `trace` | 否 |
| `TRUST_PROXY` | 部署在反向代理后面时设为 `1`，才会读 `X-Forwarded-For`（只取最后一跳） | 否 |

`.env` 在 `.gitignore` 里。密钥缺失时 `app/config.py` 在 **import 阶段**就抛 `RuntimeError`，不会等到第一个请求才发现。首尾两个变量不是必需项，判据在 README 的「设计决策 1」。

## 生成数据

```powershell
.venv\Scripts\python.exe scripts\generate_data.py
```

生成 `data/retail.db`：12 门店 / 60 商品 / 5000 订单 / 13572 明细，固定种子，重复运行结果完全一致。这个文件不进仓库。

## 启动

```powershell
.\scripts\start.ps1
```

脚本会先检查 `.venv`、`.env`、`data\retail.db` 三样东西，缺哪个就打印该跑的修复命令再退出——而不是让新人对着一个 import 栈发呆。

打开 <http://127.0.0.1:8000> 直接用页面问；接口文档在 `/docs`。

## 跑测试

```powershell
pytest
```

116 个测试，不调真实模型、不需要网络。CI 在干净的 Ubuntu + Python 3.13 上重跑同一套，跑之前先用固定种子生成 `retail.db`——`*.db` 不进仓库，不生成的话 5 条执行路径会一直 skip。

`config.py` 在 import 阶段校验密钥，所以没有 `.env` 会在收集阶段直接报错；用 `DEEPSEEK_API_KEY=dummy SILICONFLOW_API_KEY=dummy` 顶替也行，CI 就是这么跑的。

## 跑评测

```powershell
# 单轮：只给列名 / 只给口径 / 整份 schema 全塞 / 口径 + 检索
.venv\Scripts\python.exe -m eval.run_eval --mode columns --turns first
.venv\Scripts\python.exe -m eval.run_eval --mode core    --turns first
.venv\Scripts\python.exe -m eval.run_eval --mode full    --turns first
.venv\Scripts\python.exe -m eval.run_eval --mode rag     --turns first

# 多轮 50 轮
.venv\Scripts\python.exe -m eval.run_eval --mode rag --turns all

# 单会话排查
.venv\Scripts\python.exe -m eval.run_eval --mode rag --turns all --session E07

# 检索层评测（48 题，离线）
.venv\Scripts\python.exe -m eval.retrieval_eval
```

结果写进 `eval/raw-{mode}-{turns}-{session}.json`（不进仓库）。数字与分析见 README 的「评估」和 [report.md](../eval/report.md)。

## Windows 上的坑

- **执行策略**：见上面的 `Set-ExecutionPolicy -Scope Process`，只影响当前窗口。
- **路径**：PowerShell 里用反斜杠；bash 里用 `/`，两者都能跑。
- **MCP 子进程**：Windows 上退出时容易卡在 `process.wait()`，所以连接和关闭都放在同一个任务里（见 README 设计决策 3）。
