"""LangGraph SQLite checkpointer factory.

The checkpointer owns ``checkpoints.sqlite``. Application code must not execute
SQL against this file or mutate its private tables. Linkage is by checkpoint
id, recorded in ``application.sqlite``.
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from concurrent.futures import Future
from pathlib import Path
from typing import Any, Coroutine, TypeVar

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from workbench_backend.paths import CHECKPOINTS_DB_NAME

_HOLDERS: dict[str, _CheckpointOwner] = {}
_LOCK = threading.Lock()
T = TypeVar("T")


class _CheckpointOwner:
    """One loop for the shared graph driver, saver and loop-bound clients."""

    def __init__(self, path: Path) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._serve, name="workbench-agent-loop", daemon=True)
        self.thread.start()
        try:
            self.saver = self.submit(self._open(path)).result()
        except BaseException:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join()
            raise

    def _serve(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()
        self.loop.run_until_complete(self.loop.shutdown_asyncgens())
        self.loop.run_until_complete(self.loop.shutdown_default_executor())
        self.loop.close()

    async def _open(self, path: Path) -> AsyncSqliteSaver:
        conn = await aiosqlite.connect(str(path))
        try:
            saver = AsyncSqliteSaver(conn)
            await saver.setup()
            return saver
        except BaseException:
            await conn.close()
            raise

    def submit(self, coroutine: Coroutine[Any, Any, T]) -> Future[T]:
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop)

    def close(self) -> None:
        try:
            self.submit(self._close()).result()
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join()

    async def _close(self) -> None:
        # Harness shutdown settles owned graph tasks before this boundary.
        try:
            async with self.saver.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)"):
                pass
        finally:
            await self.saver.conn.close()


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


def open_sqlite_checkpointer(path: Path) -> AsyncSqliteSaver:
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
            return holder.saver
        holder = _CheckpointOwner(resolved)
        _HOLDERS[key] = holder
        return holder.saver


def submit_checkpoint_task(path: Path, coroutine: Coroutine[Any, Any, T]) -> Future[T]:
    """Schedule common execution on the saver's owning loop."""
    saver = open_sqlite_checkpointer(path)
    return asyncio.run_coroutine_threadsafe(coroutine, saver.loop)


def run_checkpoint_task(path: Path, coroutine: Coroutine[Any, Any, T]) -> T:
    """Bridge synchronous application entry points, never create a second driver."""
    saver = open_sqlite_checkpointer(path)
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None
    if current_loop is saver.loop:
        coroutine.close()
        raise RuntimeError("Checkpoint owner must await async graph operations directly.")
    return submit_checkpoint_task(path, coroutine).result()


def checkpoint_history(path: Path, config: dict, *, limit: int | None = None) -> list:
    """Materialize history on its owner; partial sync iteration leaks cursors."""
    saver = open_sqlite_checkpointer(path)
    async def read() -> list:
        return [item async for item in saver.alist(config, limit=limit)]
    return run_checkpoint_task(path, read())


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


def copy_checkpoints_for_backup(source: Path, destination: Path) -> None:
    """Copy ``checkpoints.sqlite`` through sqlite backup without private-table SQL."""

    resolved = source.expanduser().resolve()
    if resolved.name != CHECKPOINTS_DB_NAME:
        raise ValueError("Checkpointer backup source must be checkpoints.sqlite.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        holder = _HOLDERS.get(str(resolved))
    if holder is not None:
        async def backup() -> None:
            async with aiosqlite.connect(str(destination)) as target:
                await holder.saver.conn.backup(target)
        holder.submit(backup()).result()
        return
    if not resolved.exists():
        return
    src_conn = sqlite3.connect(str(resolved))
    dest_conn = sqlite3.connect(str(destination))
    try:
        src_conn.backup(dest_conn)
        dest_conn.commit()
    finally:
        dest_conn.close()
        src_conn.close()


def delete_checkpoint_thread(path: Path, thread_id: str) -> bool:
    """Delete one LangGraph thread through the saver API when supported."""

    saver = open_sqlite_checkpointer(path)
    delete_thread = getattr(saver, "delete_thread", None)
    if not callable(delete_thread):
        return False
    delete_thread(thread_id)
    return True


def _close_holder(key: str) -> None:
    with _LOCK:
        holder = _HOLDERS.pop(key, None)
    if holder is None:
        return
    holder.close()


async def acheckpoint_ids_from_graph(
    agent: object, config: dict[str, object], *, stop_at_id: str | None = None,
) -> list[str]:
    """Read this run's checkpoints, newest first, through bounded graph pages.

    ``stop_at_id`` is the checkpoint observed before the run began. It is
    exclusive, so linkage cannot accidentally claim earlier runs on a reused
    graph thread. LangGraph materializes each history query before yielding,
    hence the explicit page size matters even to an async consumer.
    """
    page_size = 64
    before: dict[str, object] | None = None
    ids: list[str] = []
    while True:
        page = [snapshot async for snapshot in agent.aget_state_history(
            config, before=before, limit=page_size,
        )]
        if not page:
            break
        for snapshot in page:
            checkpoint_id = _checkpoint_id(snapshot)
            if checkpoint_id == stop_at_id and stop_at_id is not None:
                return list(dict.fromkeys(ids))
            if checkpoint_id:
                ids.append(checkpoint_id)
        if len(page) < page_size:
            break
        next_before = getattr(page[-1], "config", None)
        if not isinstance(next_before, dict):
            raise ValueError("Checkpoint history page has no continuation config.")
        before = next_before
    if stop_at_id is not None:
        raise ValueError(f"Pre-run checkpoint {stop_at_id} is absent from graph history.")
    if not ids:
        latest = _checkpoint_id(await agent.aget_state(config))
        if latest:
            ids.append(latest)
    return list(dict.fromkeys(ids))


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
