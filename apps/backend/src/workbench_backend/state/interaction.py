"""Interaction projections and replay in the existing application database.

These are display records, never an execution/checkpointer authority. Native
events are retained verbatim after safe wire serialization; no block assembler
or graph executor lives here.
"""
from __future__ import annotations

import json
from typing import Any


INTERACTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS interaction_threads (
    id TEXT PRIMARY KEY,
    surface TEXT NOT NULL,
    conversation_id TEXT UNIQUE,
    graph_thread_id TEXT NOT NULL UNIQUE,
    run_id TEXT,
    seq INTEGER NOT NULL DEFAULT 0,
    snapshot TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS interaction_events (
    thread_id TEXT NOT NULL REFERENCES interaction_threads(id),
    seq INTEGER NOT NULL,
    payload TEXT NOT NULL,
    replaceable_measurement INTEGER NOT NULL DEFAULT 0,
    after_seq INTEGER NOT NULL,
    PRIMARY KEY(thread_id, seq)
);
"""


class InteractionStoreMixin:
    """Methods executed with ApplicationStore's connection and lock."""

    def _migrate_interaction_replay(self) -> None:
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(interaction_events)")}
        if "replaceable_measurement" not in columns:
            self._conn.execute("ALTER TABLE interaction_events ADD COLUMN replaceable_measurement INTEGER NOT NULL DEFAULT 0")
        if "after_seq" not in columns:
            self._conn.execute("ALTER TABLE interaction_events ADD COLUMN after_seq INTEGER NOT NULL DEFAULT 0")
            self._conn.execute("UPDATE interaction_events SET after_seq=seq-1")

    def register_interaction(self, thread_id: str, surface: str, graph_thread_id: str,
                             conversation_id: str | None, snapshot: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO interaction_threads(id,surface,graph_thread_id,conversation_id,snapshot) VALUES(?,?,?,?,?)",
                (thread_id, surface, graph_thread_id, conversation_id, json.dumps(snapshot)),
            )
            self._conn.commit()
            return self.get_interaction(thread_id) or self.interaction_for_graph(graph_thread_id)

    def get_interaction(self, thread_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM interaction_threads WHERE id=?", (thread_id,)).fetchone()
            return self._interaction_row(row)

    def interaction_for_graph(self, graph_thread_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM interaction_threads WHERE graph_thread_id=?", (graph_thread_id,)).fetchone()
            return self._interaction_row(row)

    @staticmethod
    def _interaction_row(row: Any) -> dict[str, Any] | None:
        if row is None:
            return None
        result = dict(row)
        result["snapshot"] = json.loads(result["snapshot"])
        return result

    def append_interaction(self, thread_id: str, events: list[dict[str, Any]], *,
                           snapshot: dict[str, Any] | None = None, run_id: str | None = None,
                           replaceable_measurement: bool = False) -> int:
        """Commit replay events and their matching snapshot/cursor atomically."""
        root_values = any(item.get("method") == "values" and not item.get("params", {}).get("namespace") for item in events)
        if replaceable_measurement and (len(events) != 1 or not root_values or snapshot is None):
            raise ValueError("Only a single measurement values snapshot can be replaceable.")
        with self._lock:
            row = self.get_interaction(thread_id)
            if row is None:
                raise KeyError(thread_id)
            seq = row["seq"]
            try:
                for original in events:
                    seq += 1
                    event = {**original, "type": "event", "seq": seq, "event_id": str(seq)}
                    self._conn.execute("INSERT INTO interaction_events(thread_id,seq,payload,replaceable_measurement,after_seq) VALUES(?,?,?,?,?)",
                                       (thread_id, seq, json.dumps(event), int(replaceable_measurement), seq - 1))
                if root_values:
                    # A newer complete values record supersedes only snapshots
                    # explicitly marked as transient measurements. Message,
                    # tool, lifecycle and final request records remain intact.
                    obsolete = self._conn.execute(
                        "SELECT seq,after_seq FROM interaction_events WHERE thread_id=? AND replaceable_measurement=1 AND seq<=? ORDER BY seq",
                        (thread_id, row["seq"]),
                    ).fetchall()
                    for old in obsolete:
                        successor = self._conn.execute(
                            "SELECT seq FROM interaction_events WHERE thread_id=? AND seq>? ORDER BY seq LIMIT 1",
                            (thread_id, old["seq"]),
                        ).fetchone()
                        self._conn.execute(
                            "UPDATE interaction_events SET after_seq=(SELECT after_seq FROM interaction_events WHERE thread_id=? AND seq=?) WHERE thread_id=? AND seq=? AND after_seq<=?",
                            (thread_id, old["seq"], thread_id, successor["seq"], old["seq"]),
                        )
                        self._conn.execute("DELETE FROM interaction_events WHERE thread_id=? AND seq=?", (thread_id, old["seq"]))
                if snapshot is None:
                    self._conn.execute("UPDATE interaction_threads SET seq=?,run_id=? WHERE id=?",
                                       (seq, run_id or row["run_id"], thread_id))
                else:
                    self._conn.execute("UPDATE interaction_threads SET seq=?,snapshot=?,run_id=? WHERE id=?",
                                       (seq, json.dumps(snapshot), run_id or row["run_id"], thread_id))
                self._conn.commit()
            except BaseException:
                self._conn.rollback()
                raise
            return seq

    def interaction_events_after(self, thread_id: str, since: int, limit: int = 128) -> list[dict[str, Any]]:
        """Read a bounded page; a slow observer never accumulates RAM backlog."""
        with self._lock:
            rows = self._conn.execute("SELECT payload FROM interaction_events WHERE thread_id=? AND seq>? ORDER BY seq LIMIT ?",
                                     (thread_id, since, min(limit, 128))).fetchall()
            return [json.loads(row["payload"]) for row in rows]

    def interaction_range(self, thread_id: str) -> tuple[int, int]:
        with self._lock:
            row = self._conn.execute("SELECT MIN(seq) AS first,MAX(seq) AS last FROM interaction_events WHERE thread_id=?", (thread_id,)).fetchone()
            return int(row["first"] or 0), int(row["last"] or 0)

    def interaction_page(self, thread_id: str, since: int) -> tuple[list[dict[str, Any]], int, bool]:
        """Read the replay page and its high-water mark in one lock scope."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq,payload,after_seq FROM interaction_events WHERE thread_id=? AND seq>? ORDER BY seq LIMIT 128",
                (thread_id, since),
            ).fetchall()
            cursor, gap = since, False
            for row in rows:
                # after_seq can precede seq-1 only when this transaction owner
                # discarded obsolete measurements. Other missing events still
                # cause the normal saved-state recovery, never silent loss.
                gap = gap or row["after_seq"] > cursor
                cursor = row["seq"]
            page = [json.loads(row["payload"]) for row in rows]
            binding = self.get_interaction(thread_id)
            high_water = binding["seq"] if binding else 0
            return page, high_water, gap or since > high_water or (not page and since < high_water)
