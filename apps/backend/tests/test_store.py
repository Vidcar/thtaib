"""RecordStore JSON write behavior."""

from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from workbench_backend.inference.schemas import BundleSourceKind, ImportJob, ImportStatus
from workbench_backend.inference.store import RecordStore
from workbench_backend.paths import WorkbenchPaths


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = WorkbenchPaths(Path(self.tmp.name)).ensure()
        self.store = RecordStore(self.paths)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_parallel_upserts_keep_all_records_and_leave_no_shared_tmp(self) -> None:
        def write(index: int) -> None:
            self.store.put_job(
                ImportJob(
                    id=f"job-{index}",
                    kind=BundleSourceKind.local,
                    status=ImportStatus.complete,
                    created_at="2026-09-20T00:00:00Z",
                )
            )

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(write, range(40)))

        self.assertEqual({job.id for job in self.store.list_jobs()}, {f"job-{index}" for index in range(40)})
        self.assertEqual(list(self.paths.state.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
