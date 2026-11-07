"""
LangGraph 的状态定义。
trace / tokens
是每轮独立的普通字段，不是跨轮累加器：
每轮开头由 _initial_state
置空，节点自己把上一步的轨迹接上。
"""

from typing import TypedDict


class AnalysisState(TypedDict, total=False):
    question: str
    session_id: str
    schema_mode: str
    history: list[dict]
    schema_context: str
    sql: str
    error: str | None
    attempts: int
    columns: list[str] | None
    rows: list[list] | None
    truncated: bool
    answer: str | None
    raw_answer: str | None
    citations: list[dict]
    degraded: bool
    trace: list[str]
    tokens: int
