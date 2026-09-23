"""Application preferences and exact-action permission grants in the shared store."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from workbench_backend.inference.ids import new_id, utc_now


class PresentationPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    theme: Literal["system", "light", "dark"] = "system"
    detailed_streams: bool = False
    attention_notifications: bool = True
    success_notifications: bool = False


class PermissionGrant(BaseModel):
    id: str
    scope: Literal["session", "always"]
    thread_id: str | None = None
    project_path: str | None = None
    action: str
    arguments: dict
    created_at: str
    source_run_id: str


class PreferenceStore:
    def __init__(self, store):
        self.store = store

    def preferences(self) -> PresentationPreferences:
        with self.store._lock:
            row = self.store._conn.execute("SELECT payload FROM presentation_preferences WHERE id=1").fetchone()
        return PresentationPreferences.model_validate_json(row[0]) if row else PresentationPreferences()

    def save_preferences(self, value: PresentationPreferences) -> PresentationPreferences:
        with self.store._lock, self.store._conn:
            self.store._conn.execute("INSERT OR REPLACE INTO presentation_preferences VALUES(1, ?)", (value.model_dump_json(),))
        return value

    def update_preferences(self, patch: PresentationPreferences) -> PresentationPreferences:
        with self.store._lock, self.store._conn:
            value = self.preferences().model_copy(update=patch.model_dump(exclude_unset=True))
            self.store._conn.execute("INSERT OR REPLACE INTO presentation_preferences VALUES(1, ?)", (value.model_dump_json(),))
        return value

    def grants(self) -> list[PermissionGrant]:
        with self.store._lock:
            rows = self.store._conn.execute("SELECT payload FROM permission_grants ORDER BY id").fetchall()
        return [PermissionGrant.model_validate_json(row[0]) for row in rows]

    def revoke(self, grant_id: str) -> None:
        with self.store._lock, self.store._conn:
            self.store._conn.execute("DELETE FROM permission_grants WHERE id=?", (grant_id,))

    def notification_claim(self, identity: str) -> bool:
        with self.store._lock, self.store._conn:
            cursor = self.store._conn.execute("INSERT OR IGNORE INTO attention_receipts VALUES (?, ?)", (identity, utc_now()))
            return cursor.rowcount == 1

    def notification_sent(self, identity: str) -> bool:
        with self.store._lock:
            return self.store._conn.execute("SELECT 1 FROM attention_receipts WHERE identity=?", (identity,)).fetchone() is not None

    def dismiss_attention(self, identity: str) -> None:
        self._dismiss_keys([f"id:{identity}"])

    def dismiss_runs(self, run_ids: list[str]) -> None:
        self._dismiss_keys([f"run:{run_id}" for run_id in run_ids if run_id])

    def attention_hidden(self, identity: str, run_id: str) -> bool:
        with self.store._lock:
            row = self.store._conn.execute(
                "SELECT 1 FROM attention_dismissals WHERE key IN (?, ?) LIMIT 1",
                (f"id:{identity}", f"run:{run_id}"),
            ).fetchone()
        return row is not None

    def _dismiss_keys(self, keys: list[str]) -> None:
        if not keys:
            return
        now = utc_now()
        with self.store._lock, self.store._conn:
            self.store._conn.executemany(
                "INSERT OR REPLACE INTO attention_dismissals VALUES (?, ?)",
                [(key, now) for key in keys],
            )

    def allow(self, run, action, scope: Literal["session", "always"]) -> PermissionGrant:
        grant = PermissionGrant(id=new_id("grant"), scope=scope,
            thread_id=run.thread_id if scope == "session" else None,
            project_path=_project(run.project_path), action=action.name,
            arguments=action.args, created_at=utc_now(), source_run_id=run.id)
        if scope == "session" and not grant.thread_id:
            raise ValueError("A session grant requires a saved thread.")
        with self.store._lock, self.store._conn:
            self.store._conn.execute("INSERT INTO permission_grants VALUES(?, ?)", (grant.id, grant.model_dump_json()))
        return grant

    def matches(self, run, name: str, arguments: dict) -> bool:
        # Exact arguments deliberately avoid shell-prefix or inferred path grants.
        if name not in run.presented_tools or name not in run.enabled_tools:
            return False
        return any(grant.action == name and grant.arguments == arguments
            and grant.project_path == _project(run.project_path)
            and (grant.scope == "always" or grant.thread_id == run.thread_id)
            for grant in self.grants())


def _project(value: str | None) -> str | None:
    return str(Path(value).resolve()) if value else None
