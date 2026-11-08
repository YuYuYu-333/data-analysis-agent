# 接口

八个端点。README 里留了端点表、状态码和 `degraded` 契约；这里放请求 / 响应示例、字段含义和 SSE 事件格式。

## 端点

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| `GET` | `/` | 无 | 单页 UI |
| `POST` | `/demo/analyze` | 无 | 公开演示，每 IP 每分钟 5 次 |
| `POST` | `/analyze` | `X-API-Key` | 正式接口，每分钟 30 次（单 key，全局计数） |
| `POST` | `/demo/analyze/stream` | 无 | 同上，SSE 逐节点下发进度 |
| `POST` | `/analyze/stream` | `X-API-Key` | 同上，SSE |
| `GET` | `/health` | 无 | 进程存活，不检查依赖 |
| `GET` | `/ready` | 无 | checkpointer 与 MCP 是否就绪，不可用时 503 |
| `GET` | `/metrics` | 无 | Prometheus 文本格式 |

## POST /analyze

请求：

```json
{ "question": "2026年9月华东大区的销售额是多少？", "session_id": null }
```

- `question`：1–500 字
- `session_id`：不传则新建；传回同一个即可继续追问。它就是 LangGraph 的 `thread_id`

响应：

```json
{
  "session_id": "3f9c8a...",
  "answer": "2026年9月华东大区的销售额是24884.15。",
  "columns": ["sales_amount"],
  "rows": [[24884.15]],
  "row_count": 1,
  "truncated": false,
  "citations": [{"value": 24884.15, "row": 0, "column": "sales_amount"}],
  "attempts": 1,
  "degraded": false,
  "degrade_reason": null,
  "trace": null
}
```

| 字段 | 说明 |
|---|---|
| `session_id` | 不传则新建；传回同一个即可继续追问 |
| `citations` | 每个数字来自第几行、哪一列；降级时为空 |
| `degraded` | `answer` 不能再当结论用，见 `degrade_reason` |
| `degrade_reason` | `citations` / `answer_llm` / `give_up`，见下 |
| `truncated` | 结果超过 1000 行，只返回前 1000 |
| `trace` | 仅 `DEBUG=1` 时返回，每个节点的执行轨迹 |

### `degraded` 的三种原因

| 值 | 发生了什么 | `answer` 里是什么 |
|---|---|---|
| `citations` | 回答里有数字在结果集里找不到出处 | 通用说明 + 完整表格 |
| `answer_llm` | 写结论的模型调用失败 | 完整表格 |
| `give_up` | 三次 SQL 都失败 | 「查不出来: <数据库原始错误>」 |

三种情况对客户端的意义完全不同：前两种**有数据**，只是没有自然语言结论；第三种**没有数据**，是一句错误。只看 `degraded` 无法区分，必须读 `degrade_reason`。

## 流式接口

`/analyze/stream` 与 `/demo/analyze/stream` 返回 `text/event-stream`，每个事件是一个 `data:` 帧：

```
data: {"type": "step", "step": "generate_sql", "label": "生成 SQL"}

data: {"type": "final", ...与 /analyze 响应体相同的字段...}
```

- `step`：每进入一个节点发一次，`label` 是给用户看的中文名
- `final`：结束时发一次，字段与 `/analyze` 的响应体一致
- `error`：流中途出现未预期异常时发一次，带 `detail`

同一个 `session_id` 的请求串行执行；流断开时 `async with` 的 `finally` 会释放会话锁。

## 状态码

| 码 | 什么时候出现 |
|---|---|
| `200` | 正常返回 |
| `401` | API key 缺失或错误 |
| `422` | 问题为空或超过 500 字 |
| `429` | 超过每分钟请求上限 |
| `503` | 未配置 `API_KEY`；或 `/ready` 检测到依赖不可用 |
| `500` | 未预期异常（日志带 `request_id`，不回内部细节） |

每个响应都带 `X-Request-Id`，和日志里的 `request_id` 是同一个值。
