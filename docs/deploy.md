# 部署到 Render

目标平台是 Render 免费层。仓库根目录的 `render.yaml` 就是 Blueprint，导入即用，不需要 Docker。

## 1. 导入 Blueprint

Render → **New → Blueprint** → 选这个仓库。`render.yaml` 里已经写好服务名、运行时、启动命令和 `TRUST_PROXY`。

## 2. 填环境变量

在 Dashboard 里填，**不要写进仓库**：

| 变量 | 说明 |
|---|---|
| `DEEPSEEK_API_KEY` | 生成 SQL 与结论 |
| `SILICONFLOW_API_KEY` | schema 向量化 + 重排 |
| `API_KEY` | `/analyze` 的请求密钥；不填则该接口 503，`/demo` 照常 |

`TRUST_PROXY=true` 已经写在 `render.yaml` 里（不是密钥，不用手填）。Render 前面有一层反向代理，不开它，限流拿到的全是代理的 IP，所有人共用一个桶。

## 3. 启动命令

```
python scripts/generate_data.py && uvicorn app.api:app --host 0.0.0.0 --port $PORT
```

**为什么必须先建库**：`retail.db` 是生成物、不进仓库，而容器每次重建都是干净的。不重建库，服务能起来，但一问就报错。数据库用固定种子生成，每次结果完全一致，所以重建是幂等的。

## 4. 验证

- `/health`：进程存活，不检查依赖
- `/ready`：checkpointer 与 MCP 是否就绪；不可用时返回 503，并在 `checks` 里指出是哪一项

## 免费层的两个已知现象

- **15 分钟无请求后休眠**，下次请求要等几十秒冷启动（含重新生成数据库 + 首次 embedding）
- **文件系统是临时的**：重启后检查点丢失，多轮会话从零开始

要持久化多轮会话，接 Neon Postgres 换 `PostgresSaver`；`DATABASE_URL` 已经在配置里预留。

## 冷启动失败的排查路径

实例在 Dashboard 显示 `Live`，但请求一直挂住、没有响应时：

1. **Logs → System logs**：看有没有新的 `Running 'uvicorn ...'`；没有就是实例没被拉起来。
2. **Application logs**：有 `Uvicorn running on ...` 才说明端口真的监听了。
3. 都没有就点 **Manual Deploy → Deploy latest commit**，重新拉起实例。

日志是单行 JSON，`request_id` 在每个请求的所有日志行里保持一致，可以直接按它串起一次请求。
