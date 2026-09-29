"""Run checkpoint linkage must stop at the pre-run history boundary."""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from workbench_backend.state.checkpointer import (
    CheckpointReadError,
    acheckpoint_ids_from_graph,
    checkpoint_head_id,
)


class PagedGraph:
    def __init__(self, count: int) -> None:
        self.history = [SimpleNamespace(config={"configurable": {"checkpoint_id": str(i)}})
                        for i in range(count, 0, -1)]
        self.calls: list[tuple[str | None, int]] = []

    async def aget_state_history(self, _config, *, before=None, limit=None):
        previous = before["configurable"]["checkpoint_id"] if before else None
        self.calls.append((previous, limit))
        start = next((index + 1 for index, snapshot in enumerate(self.history)
                      if snapshot.config["configurable"]["checkpoint_id"] == previous), 0)
        for snapshot in self.history[start:start + limit]:
            yield snapshot

    async def aget_state(self, _config):
        return self.history[0]


class CheckpointPaginationTests(unittest.TestCase):
    def test_pre_run_anchor_is_exclusive_and_older_pages_are_not_scanned(self) -> None:
        graph = PagedGraph(150)
        ids = asyncio.run(acheckpoint_ids_from_graph(graph, {}, stop_at_id="75"))
        self.assertEqual(ids, [str(i) for i in range(150, 75, -1)])
        self.assertEqual(graph.calls, [(None, 64), ("87", 64)])

    def test_missing_anchor_cannot_link_older_runs(self) -> None:
        graph = PagedGraph(2)
        with self.assertRaisesRegex(ValueError, "Pre-run checkpoint missing"):
            asyncio.run(acheckpoint_ids_from_graph(graph, {}, stop_at_id="missing"))


class CheckpointHeadTests(unittest.TestCase):
    def test_saved_snapshot_returns_its_checkpoint_id(self) -> None:
        snapshot = SimpleNamespace(config={"configurable": {"checkpoint_id": "cp-9"}})
        with patch("workbench_backend.state.checkpointer.checkpoint_history", return_value=[snapshot]):
            self.assertEqual(checkpoint_head_id(Path("checkpoints.sqlite"), "thread-1"), "cp-9")

    def test_empty_history_returns_none(self) -> None:
        with patch("workbench_backend.state.checkpointer.checkpoint_history", return_value=[]):
            self.assertIsNone(checkpoint_head_id(Path("checkpoints.sqlite"), "thread-1"))

    def test_snapshot_without_identity_raises(self) -> None:
        snapshot = SimpleNamespace(config={"configurable": {}})
        with patch("workbench_backend.state.checkpointer.checkpoint_history", return_value=[snapshot]):
            with self.assertRaisesRegex(CheckpointReadError, "has no identity"):
                checkpoint_head_id(Path("checkpoints.sqlite"), "thread-1")

    def test_unreadable_history_raises_with_cause(self) -> None:
        disk = OSError("disk")
        with patch("workbench_backend.state.checkpointer.checkpoint_history", side_effect=disk):
            with self.assertRaisesRegex(CheckpointReadError, "could not be read: disk") as caught:
                checkpoint_head_id(Path("checkpoints.sqlite"), "thread-1")
        self.assertIs(caught.exception.__cause__, disk)

    def test_whitespace_checkpoint_id_is_returned_unchanged(self) -> None:
        snapshot = SimpleNamespace(config={"configurable": {"checkpoint_id": " "}})
        with patch("workbench_backend.state.checkpointer.checkpoint_history", return_value=[snapshot]):
            self.assertEqual(checkpoint_head_id(Path("checkpoints.sqlite"), "thread-1"), " ")


if __name__ == "__main__":
    unittest.main()
