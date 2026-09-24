"""Interaction projections and replay in the existing application database.

These are display records, never an execution/checkpointer authority. Native
events are retained verbatim after safe wire serialization; no block assembler
or graph executor lives here.
"""
from __future__ import annotations

import json
from typing import Any

from workbench_backend.contracts.lifecycle import LIVE_RUN_LIFECYCLE_STATUSES
from workbench_backend.interaction.projection import compact_finished_message_deltas

_LIVE_RUN_STATUS = {item.value for item in LIVE_RUN_LIFECYCLE_STATUSES}


INTERACTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS interaction_threads (
    id TEXT PRIMARY KEY,
    surface TEXT NOT NULL,
    conversation_id TEXT UNIQUE,
    graph_thread_id TEXT NOT NULL UNIQUE,
    run_id TEXT,
    seq INTEGER NOT NULL DEFAULT 0,
    snapshot TEXT NOT NULL DEFAULT '{}',
    full_values_seq INTEGER NOT NULL DEFAULT 0,
    display_cutover_seq INTEGER NOT NULL DEFAULT 0,
    projected_status TEXT,
    compacted_through_seq INTEGER NOT NULL DEFAULT 0,
    history_unavailable INTEGER NOT NULL DEFAULT 0
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
        thread_columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(interaction_threads)")}
        if "full_values_seq" not in thread_columns:
            self._conn.execute("ALTER TABLE interaction_threads ADD COLUMN full_values_seq INTEGER NOT NULL DEFAULT 0")
        if "display_cutover_seq" not in thread_columns:
            self._conn.execute("ALTER TABLE interaction_threads ADD COLUMN display_cutover_seq INTEGER NOT NULL DEFAULT 0")
            self._conn.execute("""UPDATE interaction_threads
                                  SET display_cutover_seq=COALESCE(json_extract(snapshot, '$.workbench.display_cutover_seq'), 0)""")
        if "projected_status" not in thread_columns:
            self._conn.execute("ALTER TABLE interaction_threads ADD COLUMN projected_status TEXT")
            self._conn.execute("""UPDATE interaction_threads
                                  SET projected_status=json_extract(snapshot, '$.workbench.run.status')""")
        if "compacted_through_seq" not in thread_columns:
            self._conn.execute("ALTER TABLE interaction_threads ADD COLUMN compacted_through_seq INTEGER NOT NULL DEFAULT 0")
        detect_legacy_gaps = "history_unavailable" not in thread_columns
        if detect_legacy_gaps:
            self._conn.execute("ALTER TABLE interaction_threads ADD COLUMN history_unavailable INTEGER NOT NULL DEFAULT 0")
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(interaction_events)")}
        if "replaceable_measurement" not in columns:
            self._conn.execute("ALTER TABLE interaction_events ADD COLUMN replaceable_measurement INTEGER NOT NULL DEFAULT 0")
        if "after_seq" not in columns:
            self._conn.execute("ALTER TABLE interaction_events ADD COLUMN after_seq INTEGER NOT NULL DEFAULT 0")
            self._conn.execute("UPDATE interaction_events SET after_seq=seq-1")
        if detect_legacy_gaps:
            self._conn.execute("""WITH ordered AS (
                SELECT thread_id, seq, after_seq,
                       LAG(seq, 1, 0) OVER (PARTITION BY thread_id ORDER BY seq) AS previous_seq
                FROM interaction_events
            )
            UPDATE interaction_threads SET history_unavailable=1
            WHERE id IN (SELECT thread_id FROM ordered WHERE after_seq > previous_seq)
               OR (seq > 0 AND NOT EXISTS (
                   SELECT 1 FROM interaction_events WHERE thread_id=interaction_threads.id
               ))""")

    def register_interaction(self, thread_id: str, surface: str, graph_thread_id: str,
                             conversation_id: str | None, snapshot: dict[str, Any]) -> dict[str, Any]:
        cutover, status = self._snapshot_stream_metadata(snapshot)
        with self._lock:
            self._conn.execute(
                """INSERT OR IGNORE INTO interaction_threads
                   (id,surface,graph_thread_id,conversation_id,snapshot,display_cutover_seq,projected_status)
                   VALUES(?,?,?,?,?,?,?)""",
                (thread_id, surface, graph_thread_id, conversation_id, json.dumps(snapshot), cutover, status),
            )
            self._conn.commit()
            return self.get_interaction(thread_id) or self.interaction_for_graph(graph_thread_id)

    def get_interaction(self, thread_id: str) -> dict[str, Any] | None:
        # Flush only from outside the store lock. A caller that already holds
        # it is inside append or a page read; flushing would take the projection
        # lock and can deadlock with the writer that is waiting for this lock.
        if not self._lock._is_owned():
            self._flush_interaction(thread_id)
        with self._lock:
            row = self._conn.execute("SELECT * FROM interaction_threads WHERE id=?", (thread_id,)).fetchone()
            return self._interaction_row(row)

    def interaction_for_graph(self, graph_thread_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM interaction_threads WHERE graph_thread_id=?", (graph_thread_id,)).fetchone()
            return self._interaction_row(row)

    def interaction_id_for_graph(self, graph_thread_id: str) -> str | None:
        """Resolve a native event's display owner without decoding its archive."""
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM interaction_threads WHERE graph_thread_id=?", (graph_thread_id,)
            ).fetchone()
            return str(row["id"]) if row is not None else None

    @staticmethod
    def _interaction_row(row: Any) -> dict[str, Any] | None:
        if row is None:
            return None
        result = dict(row)
        result["snapshot"] = json.loads(result["snapshot"])
        return result

    @staticmethod
    def _snapshot_stream_metadata(snapshot: dict[str, Any]) -> tuple[int, str | None]:
        workbench = snapshot.get("workbench") or {}
        cutover = workbench.get("display_cutover_seq", 0)
        run = workbench.get("run") or {}
        status = run.get("status") if isinstance(run, dict) else None
        valid_cutover = cutover if isinstance(cutover, int) and not isinstance(cutover, bool) and cutover >= 0 else 0
        return valid_cutover, status if isinstance(status, str) else None

    def interaction_stream_metadata(self, thread_id: str) -> tuple[int, int, str | None, str | None]:
        """Read display and durable run state without decoding the transcript."""
        self._flush_interaction(thread_id)
        with self._lock:
            row = self._conn.execute(
                """SELECT i.seq,i.display_cutover_seq,i.projected_status,r.status AS durable_status
                   FROM interaction_threads AS i LEFT JOIN runs AS r ON r.id=i.run_id WHERE i.id=?""",
                (thread_id,),
            ).fetchone()
        if row is None:
            raise KeyError(thread_id)
        return int(row["seq"]), int(row["display_cutover_seq"]), row["projected_status"], row["durable_status"]

    def interaction_history_unavailable(self, thread_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT history_unavailable FROM interaction_threads WHERE id=?", (thread_id,)
            ).fetchone()
            return bool(row["history_unavailable"]) if row is not None else False

    def append_interaction(self, thread_id: str, events: list[dict[str, Any]], *,
                           snapshot: dict[str, Any] | None = None, run_id: str | None = None,
                           replaceable_measurement: bool = False) -> int:
        """Commit replay events and their matching snapshot/cursor atomically."""
        root_values = any(item.get("method") == "values" and not item.get("params", {}).get("namespace") for item in events)
        if replaceable_measurement and (len(events) != 1 or not root_values or snapshot is None):
            raise ValueError("Only a single measurement values snapshot can be replaceable.")
        with self._lock:
            row = self._conn.execute(
                "SELECT seq,run_id,full_values_seq FROM interaction_threads WHERE id=?", (thread_id,)
            ).fetchone()
            if row is None:
                raise KeyError(thread_id)
            seq = row["seq"]
            full_values: list[int] = []
            try:
                for original in events:
                    seq += 1
                    event = {**original, "type": "event", "seq": seq, "event_id": str(seq)}
                    self._conn.execute("INSERT INTO interaction_events(thread_id,seq,payload,replaceable_measurement,after_seq) VALUES(?,?,?,?,?)",
                                       (thread_id, seq, json.dumps(event), int(replaceable_measurement), seq - 1))
                    if (not replaceable_measurement and original.get("method") == "values" and
                            not original.get("params", {}).get("namespace") and
                            not original.get("params", {}).get("measurement")):
                        full_values.append(seq)
                if root_values:
                    # A newer complete values record supersedes only snapshots
                    # explicitly marked as transient measurements. Message,
                    # tool, lifecycle and final request records remain intact.
                    obsolete = self._conn.execute(
                        "SELECT seq FROM interaction_events WHERE thread_id=? AND replaceable_measurement=1 AND seq<=? ORDER BY seq",
                        (thread_id, row["seq"]),
                    ).fetchall()
                    for old in obsolete:
                        self._remove_replay_event(thread_id, old["seq"])
                if full_values:
                    # A complete values frame carries the accumulated saved
                    # snapshot. Keep its newest copy; native message/tool deltas
                    # still supply any live partial and resume detail.
                    if row["full_values_seq"]:
                        obsolete_full = [row["full_values_seq"], *full_values[:-1]]
                    else:
                        # Existing databases had no full-values cursor. Compact
                        # their older copies once, on the next complete frame.
                        obsolete_full = self._conn.execute(
                            """SELECT seq FROM interaction_events
                               WHERE thread_id=? AND seq<?
                                 AND replaceable_measurement=0
                                 AND json_extract(payload, '$.method')='values'
                                 AND json_extract(payload, '$.params.namespace')='[]'
                                 AND COALESCE(json_extract(payload, '$.params.measurement'),0)=0
                               ORDER BY seq""",
                            (thread_id, full_values[-1]),
                        )
                        obsolete_full = [old["seq"] for old in obsolete_full]
                    for old_seq in obsolete_full:
                        self._remove_replay_event(thread_id, old_seq)
                if snapshot is None:
                    self._conn.execute("UPDATE interaction_threads SET seq=?,run_id=?,full_values_seq=? WHERE id=?",
                                       (seq, run_id or row["run_id"], full_values[-1] if full_values else row["full_values_seq"], thread_id))
                else:
                    cutover, status = self._snapshot_stream_metadata(snapshot)
                    self._conn.execute("""UPDATE interaction_threads SET seq=?,snapshot=?,run_id=?,full_values_seq=?,
                                         display_cutover_seq=?,projected_status=? WHERE id=?""",
                                       (seq, json.dumps(snapshot), run_id or row["run_id"], full_values[-1] if full_values else row["full_values_seq"], cutover, status, thread_id))
                self._conn.commit()
            except BaseException:
                self._conn.rollback()
                raise
            return seq

    def _remove_replay_event(self, thread_id: str, seq: int) -> None:
        current = self._conn.execute(
            "SELECT after_seq FROM interaction_events WHERE thread_id=? AND seq=?",
            (thread_id, seq),
        ).fetchone()
        if current is None:
            return
        successor = self._conn.execute(
            "SELECT seq FROM interaction_events WHERE thread_id=? AND seq>? ORDER BY seq LIMIT 1",
            (thread_id, seq),
        ).fetchone()
        if successor is not None:
            # Preserve an existing real gap; bridge only the row we deliberately
            # removed so an ordinary reconnect does not claim data was lost.
            self._conn.execute(
                "UPDATE interaction_events SET after_seq=? WHERE thread_id=? AND seq=? AND after_seq<=?",
                (current["after_seq"], thread_id, successor["seq"], seq),
            )
        self._conn.execute("DELETE FROM interaction_events WHERE thread_id=? AND seq=?", (thread_id, seq))

    def discard_finished_token_log(self, thread_id: str) -> int:
        """Compact only finished message deltas after the run settles.

        The retained final block occupies an original event position. Tool,
        lifecycle, nested, and unfinished message records retain their order.
        """

        with self._lock:
            row = self._conn.execute(
                "SELECT run_id, projected_status, seq, compacted_through_seq FROM interaction_threads WHERE id = ?",
                (thread_id,),
            ).fetchone()
            if row is None:
                return 0
            # The run commit precedes the terminal interaction snapshot. Until
            # that snapshot is published, token rows may be its only answer.
            if row["projected_status"] in _LIVE_RUN_STATUS:
                return 0
            if row["run_id"]:
                status = self._conn.execute(
                    "SELECT status FROM runs WHERE id = ?",
                    (row["run_id"],),
                ).fetchone()
                if status is not None and status["status"] in _LIVE_RUN_STATUS:
                    return 0
            through = int(row["seq"])
            if through <= int(row["compacted_through_seq"]):
                return 0
            messages = self._conn.execute(
                """SELECT payload FROM interaction_events
                   WHERE thread_id=? AND seq>? AND seq<=?
                     AND json_extract(payload, '$.method')='messages'
                   ORDER BY seq""",
                (thread_id, row["compacted_through_seq"], through),
            ).fetchall()
            replacements, deletions = compact_finished_message_deltas(
                thread_id, [json.loads(item["payload"]) for item in messages],
            )
            try:
                for seq, replacement in replacements.items():
                    self._conn.execute(
                        "UPDATE interaction_events SET payload=? WHERE thread_id=? AND seq=?",
                        (json.dumps(replacement), thread_id, seq),
                    )
                if deletions:
                    # Follow only predecessor links we deliberately remove.
                    # A missing native event has no such link and remains a gap.
                    resolved_after: dict[int, int] = {}
                    affected = self._conn.execute(
                        """SELECT seq,after_seq FROM interaction_events
                           WHERE thread_id=? AND seq>=? AND seq<=? ORDER BY seq""",
                        (thread_id, min(deletions), through),
                    ).fetchall()
                    for item in affected:
                        seq, after = int(item["seq"]), int(item["after_seq"])
                        bridged = resolved_after.get(after, after)
                        if seq in deletions:
                            resolved_after[seq] = bridged
                        elif bridged != after:
                            self._conn.execute(
                                "UPDATE interaction_events SET after_seq=? WHERE thread_id=? AND seq=?",
                                (bridged, thread_id, seq),
                            )
                    ordered = sorted(deletions)
                    for index in range(0, len(ordered), 400):
                        chunk = ordered[index:index + 400]
                        placeholders = ",".join("?" for _ in chunk)
                        self._conn.execute(
                            f"DELETE FROM interaction_events WHERE thread_id=? AND seq IN ({placeholders})",
                            (thread_id, *chunk),
                        )
                self._conn.execute(
                    "UPDATE interaction_threads SET compacted_through_seq=? WHERE id=?",
                    (through, thread_id),
                )
                self._conn.commit()
            except BaseException:
                self._conn.rollback()
                raise
            return len(deletions)

    def discard_finished_token_logs(self) -> int:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT interaction_threads.id AS id, runs.status AS status
                FROM interaction_threads
                LEFT JOIN runs ON runs.id = interaction_threads.run_id
                """
            ).fetchall()
        removed = 0
        for row in rows:
            if row["status"] in _LIVE_RUN_STATUS:
                continue
            removed += self.discard_finished_token_log(str(row["id"]))
        return removed

    def interaction_event_count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT count(*) AS n FROM interaction_events").fetchone()
        return int(row["n"] if row is not None else 0)

    def reclaim_unused_space(self) -> None:
        with self._lock:
            self._conn.execute("VACUUM")

    def interaction_events_after(self, thread_id: str, since: int, limit: int = 128) -> list[dict[str, Any]]:
        """Read a bounded page; a slow observer never accumulates RAM backlog."""
        self._flush_interaction(thread_id)
        with self._lock:
            rows = self._conn.execute("SELECT payload FROM interaction_events WHERE thread_id=? AND seq>? ORDER BY seq LIMIT ?",
                                     (thread_id, since, min(limit, 128))).fetchall()
            return [json.loads(row["payload"]) for row in rows]

    def interaction_range(self, thread_id: str) -> tuple[int, int]:
        with self._lock:
            row = self._conn.execute("SELECT MIN(seq) AS first,MAX(seq) AS last FROM interaction_events WHERE thread_id=?", (thread_id,)).fetchone()
            return int(row["first"] or 0), int(row["last"] or 0)

    def _flush_interaction(self, thread_id: str) -> None:
        hook = getattr(self, "before_interaction_read", None)
        if hook is not None:
            hook(thread_id)

    def interaction_page(self, thread_id: str, since: int) -> tuple[list[dict[str, Any]], int, bool]:
        """Read the replay page and its high-water mark in one lock scope."""
        self._flush_interaction(thread_id)
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
            latest = self._conn.execute("SELECT seq FROM interaction_threads WHERE id=?", (thread_id,)).fetchone()
            high_water = int(latest["seq"]) if latest else 0
            return page, high_water, gap or since > high_water or (not page and since < high_water)
