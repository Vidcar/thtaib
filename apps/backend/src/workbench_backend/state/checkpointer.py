"""LangGraph SQLite checkpointer factory.

The checkpointer owns ``checkpoints.sqlite``. Application code must not execute
SQL against this file or mutate its private tables. Linkage is by checkpoint
id, recorded in ``application.sqlite``.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from workbench_backend.paths import CHECKPOINTS_DB_NAME

_HOLDERS: dict[str, tuple[sqlite3.Connection, SqliteSaver]] = {}
_LOCK = threading.Lock()


def conversation_state(path: Path, thread_id: str) -> dict:
    """Read retained messages through a compiled graph's public state API only.

    This projection is never invoked: Deep Agents remains the execution owner.
    Its state schema preserves upstream compaction metadata for preflight.
    """
    from deepagents.middleware.summarization import SummarizationState
    from deepagents.graph import DeepAgentState
    from langgraph.graph import StateGraph, START, END
    class ConversationState(SummarizationState, DeepAgentState):
        pass
    graph = StateGraph(ConversationState)
    graph.add_node("read_only_projection", lambda state: {})
    graph.add_edge(START, "read_only_projection")
    graph.add_edge("read_only_projection", END)
    compiled = graph.compile(checkpointer=open_sqlite_checkpointer(path))
    return dict(compiled.get_state({"configurable": {"thread_id": thread_id}}).values or {})


def open_sqlite_checkpointer(path: Path) -> SqliteSaver:
    """Return the LangGraph saver for ``checkpoints.sqlite``.

    This is the only module that opens the checkpointer database. Callers must
    use public graph APIs (``get_state`` / ``get_state_history``) to read
    checkpoint ids.
    """

    resolved = path.expanduser().resolve()
    if resolved.name != CHECKPOINTS_DB_NAME:
        raise ValueError(
            "Checkpointer path must be checkpoints.sqlite under the product root."
        )
    resolved.parent.mkdir(parents=True, exist_ok=True)
    key = str(resolved)
    with _LOCK:
        holder = _HOLDERS.get(key)
        if holder is not None:
            return holder[1]
        conn = sqlite3.connect(key, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        saver = SqliteSaver(conn)
        saver.setup()
        _HOLDERS[key] = (conn, saver)
        return saver


def close_sqlite_checkpointer(path: Path) -> None:
    """Close the cached saver for ``path``, if this process opened it."""
    resolved = path.expanduser().resolve()
    _close_holder(str(resolved))


def close_all_sqlite_checkpointers() -> None:
    """Close every cached checkpointer connection owned by this process."""
    with _LOCK:
        keys = list(_HOLDERS)
    for key in keys:
        _close_holder(key)


def _close_holder(key: str) -> None:
    with _LOCK:
        holder = _HOLDERS.pop(key, None)
    if holder is None:
        return
    conn, _saver = holder
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.commit()
    except sqlite3.Error:
        pass
    conn.close()


def checkpoint_ids_from_graph(agent: object, config: dict[str, object]) -> list[str]:
    """Collect checkpoint ids via LangGraph public APIs only."""

    ids: list[str] = []
    history = getattr(agent, "get_state_history", None)
    if callable(history):
        for snapshot in history(config):
            cid = _checkpoint_id(snapshot)
            if cid:
                ids.append(cid)
    if not ids:
        get_state = getattr(agent, "get_state", None)
        if callable(get_state):
            cid = _checkpoint_id(get_state(config))
            if cid:
                ids.append(cid)
    seen: set[str] = set()
    unique: list[str] = []
    for item in ids:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def _checkpoint_id(snapshot: object) -> str | None:
    config = getattr(snapshot, "config", None)
    if not isinstance(config, dict):
        return None
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        return None
    value = configurable.get("checkpoint_id")
    if value is None:
        return None
    text = str(value).strip()
    return text or None
