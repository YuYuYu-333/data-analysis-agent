"""
图：SQL 抽取、路由和答案格式化（不调模型）。
"""

import asyncio
from types import SimpleNamespace

import app.graph as graph_module
from langgraph.checkpoint.memory import MemorySaver

from app.graph import _extract_sql, route, verify_citations


def test_extract_sql_plain():
    assert _extract_sql("SELECT 1") == "SELECT 1"


def test_extract_sql_code_fence():
    assert _extract_sql("```sql\nSELECT 1\n```") == "SELECT 1"


def test_extract_sql_with_explanation():
    assert _extract_sql("这是查询：\nSELECT 1;") == "SELECT 1;"


def test_route_retry():
    assert route({"error": "bad", "attempts": 1}) == "retry"


def test_route_give_up():
    assert route({"error": "bad", "attempts": 3}) == "give_up"


def test_route_answer():
    assert route({"error": None, "attempts": 1}) == "answer"


def test_verify_citations_ok():
    result = verify_citations({
        "columns": ["sales"],
        "rows": [[12345.67]],
        "answer": "销售额为 12345.67 元。",
        "question": "销售额是多少？",
    })
    assert result["degraded"] is False
    assert len(result["citations"]) == 1


def test_verify_citations_degrades_on_fake_number():
    result = verify_citations({
        "columns": ["sales"],
        "rows": [[12345.67]],
        "answer": "销售额为 999.00 元。",
        "question": "销售额是多少？",
    })
    assert result["degraded"] is True
    assert result["answer"].startswith("sales")


def test_verify_citations_skips_when_no_rows():
    result = verify_citations({"columns": ["n"], "rows": [], "answer": "没有查到符合条件的数据。"})
    assert result["degraded"] is False


def test_verify_citations_keeps_existing_degraded():
    """build_answer 已经降级时，溯源不能把它改回 False"""
    result = verify_citations({
        "columns": ["sales"],
        "rows": [[12345.67]],
        "answer": "sales\n12345.67",
        "question": "销售额是多少？",
        "degraded": True,
    })
    assert result["degraded"] is True


def test_state_resets_between_turns(monkeypatch):
    """同一个 thread 的第二轮，tokens 和 trace 都从空开始"""

    async def fake_schema(state):
        return {"schema_context": "", "trace": [*(state.get("trace") or []), "schema"]}

    async def fake_sql(state):
        return {
            "sql": "SELECT 1", "attempts": 1,
            "trace": [*(state.get("trace") or []), "sql"],
            "tokens": (state.get("tokens") or 0) + 7
        }

    async def fake_execute(state):
        return {
            "error": None, "columns": ["n"],
            "rows": [[1]], "truncated": False,
            "trace": [*(state.get("trace") or []), "exec"]
        }

    async def fake_answer(state):
        return {
            "answer": "1",
            "raw_answer": "1",
            "citations": [],
            "degraded": False,
            "history": [],
            "trace": [*(state.get("trace") or []), "answer"],
            "tokens": (state.get("tokens") or 0) + 3
        }

    monkeypatch.setattr(graph_module, "retrieve_schema", fake_schema)
    monkeypatch.setattr(graph_module, "generate_sql", fake_sql)
    monkeypatch.setattr(graph_module, "execute_sql_node", fake_execute)
    monkeypatch.setattr(graph_module, "build_answer", fake_answer)

    graph = graph_module.build_graph(MemorySaver())
    config = {"configurable": {"thread_id": "t1"}}

    async def run():
        first = await graph.ainvoke(graph_module._initial_state("q", "t1", "rag"), config)
        second = await graph.ainvoke(graph_module._initial_state("q", "t1", "rag"), config)
        return first, second

    first, second = asyncio.run(run())
    assert first["tokens"] == 10
    assert second["tokens"] == 10
    assert len(second["trace"]) == len(first["trace"])


def _capture_llm(monkeypatch, box):
    class Completions:
        async def create(self, **kwargs):
            box["text"] = kwargs["messages"][-1]["content"]
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="SELECT 1"))],
                usage=SimpleNamespace(total_tokens=1),
            )

    monkeypatch.setattr(
        graph_module, "chat_client",
        SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
    )


def test_first_attempt_has_no_final_hint(monkeypatch):
    box = {}
    _capture_llm(monkeypatch, box)
    asyncio.run(graph_module.generate_sql({"question": "q", "attempts": 0}))
    assert "第三次尝试" not in box["text"]


def test_final_attempt_changes_strategy(monkeypatch):
    box = {}
    _capture_llm(monkeypatch, box)
    asyncio.run(graph_module.generate_sql({"question": "q", "attempts": 2, "error": "no such column: x"}))
    assert "第三次尝试" in box["text"]


def test_columns_mode_has_no_core_metrics():
    context = graph_module._schema_context("columns", "")
    assert "sales_item.amount - sales_item.refund_amount" not in context
    assert "COUNT(DISTINCT" not in context


def test_rag_mode_always_carries_core_metrics():
    context = graph_module._schema_context("rag", "")
    assert "sales_item.amount - sales_item.refund_amount" in context
    assert "COUNT(DISTINCT" in context


def test_retrieved_chunks_append_to_core_metrics():
    context = graph_module._schema_context("rag", "### 9. 已知陷阱\n取消订单不计")
    assert "核心口径" in context
    assert "取消订单不计" in context
