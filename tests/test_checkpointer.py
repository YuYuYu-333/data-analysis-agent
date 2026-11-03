"""
检查点：同一 thread 跨调用保留状态.
"""

import asyncio
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.checkpointer import build_sqlite_checkpointer

class State(TypedDict, total=False):
    x: int
    seen: list[int]


def _build(checkpointer):
    def node(state: State) -> dict:
        return {
            "x": state["x"] + 1,
            "seen": (state.get("seen") or []) + [state["x"]],
        }

    builder = StateGraph(State)
    builder.add_node("n", node)
    builder.add_edge(START, "n")
    builder.add_edge("n", END)
    return builder.compile(checkpointer=checkpointer)


def test_checkpointer_persists_state(tmp_path):
    async def run():
        saver, conn = await build_sqlite_checkpointer(tmp_path / "checkpoints.db")
        try:
            graph = _build(saver)
            config = {"configurable": {"thread_id": "t1"}}

            first = await graph.ainvoke({"x": 1, "seen": []}, config=config)
            second = await graph.ainvoke({"x": 10}, config=config)

            assert first["x"] == 2
            assert second["x"] == 11
            assert second["seen"] == [1, 10]
        finally:
            await conn.close()

    asyncio.run(run())