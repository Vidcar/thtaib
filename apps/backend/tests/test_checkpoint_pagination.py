"""Run checkpoint linkage must stop at the pre-run history boundary."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
import unittest

from workbench_backend.state.checkpointer import acheckpoint_ids_from_graph


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


if __name__ == "__main__":
    unittest.main()
