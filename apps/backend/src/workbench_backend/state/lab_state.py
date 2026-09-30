"""Lab application rows; the shared ApplicationStore owns the connection."""

from __future__ import annotations

from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.lab.workbench_schemas import LabChallenge, LabRun

LAB_SCHEMA = """
CREATE TABLE IF NOT EXISTS lab_runs (
    id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lab_challenges (
    id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lab_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class LabStateStoreMixin:
    def list_lab_runs(self) -> list[LabRun]:
        with self._lock:
            rows = self._conn.execute("SELECT payload FROM lab_runs ORDER BY created_at DESC, id DESC").fetchall()
        return [LabRun.model_validate_json(row[0]) for row in rows]

    def get_lab_run(self, run_id: str) -> LabRun | None:
        with self._lock:
            row = self._conn.execute("SELECT payload FROM lab_runs WHERE id=?", (run_id,)).fetchone()
        return LabRun.model_validate_json(row[0]) if row else None

    def put_lab_run(self, run: LabRun) -> LabRun:
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO lab_runs VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at",
                               (run.id, run.model_dump_json(), run.created_at, run.updated_at))
        return run

    def delete_lab_run(self, run_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM lab_runs WHERE id=?", (run_id,))

    def list_lab_challenges(self) -> list[LabChallenge]:
        with self._lock, self._conn:
            seeded = self._conn.execute("SELECT value FROM lab_state WHERE key='challenges_seeded'").fetchone()
            if seeded is None:
                if not self._conn.execute("SELECT 1 FROM lab_challenges LIMIT 1").fetchone():
                    now = utc_now()
                    challenge = LabChallenge(id=new_id("challenge"), name="Echo a code",
                        task="Call echo with the text lab-echo-ok, then include lab-echo-ok in your answer.",
                        required_text="lab-echo-ok", required_tool="echo", created_at=now, updated_at=now)
                    self._conn.execute("INSERT INTO lab_challenges VALUES (?,?,?,?)",
                        (challenge.id, challenge.model_dump_json(), now, now))
                self._conn.execute("INSERT INTO lab_state VALUES ('challenges_seeded','1')")
            rows = self._conn.execute("SELECT payload FROM lab_challenges ORDER BY created_at, id").fetchall()
        return [LabChallenge.model_validate_json(row[0]) for row in rows]

    def put_lab_challenge(self, challenge: LabChallenge) -> LabChallenge:
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO lab_challenges VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at",
                (challenge.id, challenge.model_dump_json(), challenge.created_at, challenge.updated_at))
        return challenge

    def delete_lab_challenge(self, challenge_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM lab_challenges WHERE id=?", (challenge_id,))
