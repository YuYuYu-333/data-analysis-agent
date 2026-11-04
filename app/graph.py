"""
LangGraph 图：检索 schema → 生成 SQL → 执行 → 重试/出答案。
当前只做单轮；多轮和溯源在后续接。
"""

import re

from langgraph.graph import END, START, StateGraph

from app.answer import find_citations, format_table
from app.checkpointer import get_checkpointer, close_checkpointer
from app.llm import CHAT_MODEL, chat_client
from app.mcp_client import execute_sql as mcp_execute_sql
from app.mcp_client import search_schema
from app.state import AnalysisState

COLUMNS_ONLY = """
    store(store_id, store_name,region, city, opened_at)
    product(product_id, product_name, category, list_price)
    sales_order(order_id, store_id, order_date, channel, status, discount_amount)
    sales_item(item_id, order_id, product_id, quantity, unit_price, amount, refunded, refund_amount)
    """

SYSTEM_PROMPT = """你是 SQLite 数据分析助手. 根据给定的表结构和业务口径，把用户问题翻译成一条 SQLite 查询.
规则：
    1. 只输出 SQL，不要解释，不要 markdown 代码块。
    2. 只允许 SELECT 或 WITH 开头的只读查询。
    3. 如果提供了上次错误，根据错误修正，不要重复同一个错误。
    4. 结果列要有稳定排序；排名题用 ORDER BY 指标 DESC, 名称 ASC。
    5. 这是多轮对话：新问题没有重新限定时间时，必须沿用上一轮SQL 的时间范围；其他筛选条件（大区 / 渠道 / 品类 / 状态）同理，除非新问题明确改掉或扩大范围。
    """

ANSWER_PROMPT = """你是数据分析助手。根据查询结果，用一句中文回答用户的问题。
规则：
    1. 只使用查询结果里出现的数字，不要自己算新的数。
    2. 不要提"查询结果""表格"这些词，直接给结论。
    3. 结果有多行时，挑最关键的说明，不要逐行念。
    4. 一句话，不超过 80 字。
    """


def _extract_sql(text: str) -> str:
    """从模型输出里取出 SQL；兼容 ```sql 代码块和前后解释"""
    text = (text or "").strip()
    if "```" in text:
        for part in text.split("```"):
            part = part.strip()
            if part.lower().startswith("sql"):
                part = part[3:].strip()
            if part.upper().startswith(("SELECT", "WITH")):
                return part
    match = re.search(r"(?is)\b(SELECT|WITH)\b", text)
    if match:
        return text[match.start():].strip()
    return text


async def retrieve_schema(state: AnalysisState) -> dict:
    if state.get("schema_mode") == "columns":
        return {"schema_context": COLUMNS_ONLY, "trace": ["schema: columns only"]}

    try:
        result = await search_schema(state["question"], top_k=5)
        chunks = result.get("chunks", [])
        chunks_text = "\n\n".join(chunk["text"] for chunk in chunks)
        context = COLUMNS_ONLY + ("\n\n" + chunks_text if chunks_text else "")
        return {
            "schema_context": context,
            "trace": [f"schema: {len(chunks)} chunks"],
        }
    except Exception as exc:
        return {
            "schema_context": COLUMNS_ONLY,
            "trace": [f"schema error: {exc}"],
        }


async def generate_sql(state: AnalysisState) -> dict:
    attempts = state.get("attempts", 0) + 1
    history = state.get("history") or []
    history_text = "\n".join(f"- 问：{item['question']}\n SQL：{item['sql']}" for item in history[-2:]) or "无"

    prompt = f"""
    表结构与业务口径:{state.get('schema_context', '')}
    最近两轮（追问时默认继承它们的时间范围和筛选条件）：{history_text}
    上次 SQL 错误： {state.get('error') or '无'}
    用户问题：{state['question']}
    只输出一条 SQLite SQL.
    """

    try:
        response = await chat_client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
        )
        sql = _extract_sql(response.choices[0].message.content or "")
        return {
            "sql": sql,
            "attempts": attempts,
            "trace": [f"sql generated (attempt {attempts})"],
        }
    except Exception as exc:
        return {
            "sql": "",
            "attempts": attempts,
            "error": f"模型调用失败：{exc}",
            "trace": [f"llm error: {exc}"],
        }


async def execute_sql_node(state: AnalysisState) -> dict:
    try:
        result = await mcp_execute_sql(state.get("sql", ""))
    except Exception as exc:
        return {
            "error": f"数据库服务不可用：{exc}",
            "columns": None,
            "rows": None,
            "truncated": False,
            "trace": [f"mcp error: {exc}"],
        }
    if "error" in result:
        return {
            "error": result["error"],
            "columns": None,
            "rows": None,
            "truncated": False,
            "trace": [f"sql error: {result['error']}"],
        }
    return {
        "error": None,
        "columns": result["columns"],
        "rows": result["rows"],
        "truncated": result["truncated"],
        "trace": [f"sql ok: {result['row_count']} rows"],
    }


def route(state: AnalysisState) -> str:
    if state.get("error"):
        if state.get("attempts", 0) >= 3:
            return "give_up"
        return "retry"
    return "answer"


async def build_answer(state: AnalysisState) -> dict:
    columns = state.get("columns") or []
    rows = state.get("rows") or []

    history = list(state.get("history") or [])
    history.append({"question": state.get("question", ""), "sql": state.get("sql", "")})
    history = history[-2:]

    if not rows:
        return {
            "answer": "没有查到符合条件的数据。",
            "raw_answer": None,
            "citations": [],
            "degraded": False,
            "history": history,
            "trace": ["answer: empty result"],
        }

    table = format_table(columns, rows)
    prompt = f"""
    用户问题: {state['question']}
    查询结构: {table}
    """

    try:
        response = await chat_client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": ANSWER_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        answer = (response.choices[0].message.content or "").strip() or table
    except Exception as exc:
        return {
            "answer": table,
            "raw_answer": None,
            "citations": [],
            "degraded": True,
            "history": history,
            "trace": [f"answer llm error: {exc}"],
        }

    return {
        "answer": answer,
        "raw_answer": answer,
        "citations": [],
        "degraded": False,
        "history": history,
        "trace": ["answer generated"],
    }


def verify_citations(state: AnalysisState) -> dict:
    rows = state.get("rows") or []
    if not rows:
        return {"degraded": False, "trace": ["citations: no rows"]}

    columns = state.get("columns") or []
    citations, missing = find_citations(
        state.get("answer") or "",
        columns,
        rows,
        state.get("question", ""),
    )
    if missing:
        return {
            "answer": format_table(columns, rows),
            "citations": [],
            "degraded": True,
            "trace": [f"citations: {len(missing)} unmatched -> degraded"],
        }
    return {
        "citations": citations,
        "degraded": False,
        "trace": [f"citations: {len(citations)} ok"],
    }


def give_up(state: AnalysisState) -> dict:
    return {
        "answer": f"查不出来: {state.get('error') or '未知错误'}",
        "degraded": True,
        "trace": ["give up"]
    }


def build_graph(checkpointer=None):
    builder = StateGraph(AnalysisState)
    builder.add_node("retrieve_schema", retrieve_schema)
    builder.add_node("generate_sql", generate_sql)
    builder.add_node("execute_sql", execute_sql_node)
    builder.add_node("build_answer", build_answer)
    builder.add_node("verify_citations", verify_citations)
    builder.add_node("give_up", give_up)

    builder.add_edge(START, "retrieve_schema")
    builder.add_edge("retrieve_schema", "generate_sql")
    builder.add_edge("generate_sql", "execute_sql")
    builder.add_conditional_edges(
        "execute_sql",
        route,
        {
            "retry": "generate_sql",
            "answer": "build_answer",
            "give_up": "give_up",
        },
    )
    builder.add_edge("build_answer", "verify_citations")
    builder.add_edge("verify_citations", END)
    builder.add_edge("give_up", END)

    return builder.compile(checkpointer=checkpointer)


_graph = None


async def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph(await get_checkpointer())
    return _graph


async def analyze(question: str, session_id: str = "default", schema_mode: str = "rag") -> dict:
    state: AnalysisState = {
        "question": question,
        "session_id": session_id,
        "schema_mode": schema_mode,
        "attempts": 0,
        "error": None,
        "trace": [],
    }
    config = {"configurable": {"thread_id": session_id}}
    graph = await get_graph()
    return await graph.ainvoke(state, config=config)


if __name__ == '__main__':
    import asyncio


    async def _demo() -> None:
        try:
            first = await analyze("2026 年 9 月华东大区的销售额是多少？", session_id="demo")
            print("T1 sql:", first.get("sql"))
            print("T1 rows:", first.get("rows"))

            second = await analyze("那华南呢？", session_id="demo")
            print("T2 sql:", second.get("sql"))
            print("T2 rows:", second.get("rows"))
        finally:
            await close_checkpointer()


    asyncio.run(_demo())
