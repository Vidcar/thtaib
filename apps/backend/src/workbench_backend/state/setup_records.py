"""Project bindings and setup versions in the existing application database."""

from __future__ import annotations

from workbench_backend.agents.setup_schemas import AgentSetupRecord, AgentSetupVersion, ProjectRecord, SetupConfiguration
from workbench_backend.errors import HarnessError

SETUP_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY, canonical_path TEXT NOT NULL UNIQUE, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_setups (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_setup_versions (
    id TEXT PRIMARY KEY, setup_id TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS setup_defaults (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
"""


class SetupStoreMixin:
    def list_projects(self) -> list[ProjectRecord]:
        with self._lock:
            return [ProjectRecord.model_validate_json(row[0]) for row in self._conn.execute("SELECT payload FROM projects ORDER BY rowid")]

    def get_project(self, project_id: str) -> ProjectRecord | None:
        with self._lock:
            row = self._conn.execute("SELECT payload FROM projects WHERE id=?", (project_id,)).fetchone()
        return ProjectRecord.model_validate_json(row[0]) if row else None

    def put_project(self, project: ProjectRecord) -> ProjectRecord:
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO projects(id,canonical_path,payload) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload", (project.id, project.canonical_path, project.model_dump_json()))
        return project

    def get_setup_defaults(self) -> SetupConfiguration:
        with self._lock:
            row = self._conn.execute("SELECT payload FROM setup_defaults WHERE id='application'").fetchone()
        return SetupConfiguration.model_validate_json(row[0]) if row else SetupConfiguration()

    def put_setup_defaults(self, value: SetupConfiguration) -> SetupConfiguration:
        with self._lock, self._conn:
            self._conn.execute("INSERT OR REPLACE INTO setup_defaults(id,payload) VALUES('application',?)", (value.model_dump_json(),))
        return value

    def list_agent_setups(self) -> list[AgentSetupRecord]:
        with self._lock:
            return [AgentSetupRecord.model_validate_json(row[0]) for row in self._conn.execute("SELECT payload FROM agent_setups ORDER BY rowid")]

    def get_agent_setup(self, setup_id: str) -> AgentSetupRecord | None:
        with self._lock:
            row = self._conn.execute("SELECT payload FROM agent_setups WHERE id=?", (setup_id,)).fetchone()
        return AgentSetupRecord.model_validate_json(row[0]) if row else None

    def get_agent_setup_version(self, version_id: str) -> AgentSetupVersion | None:
        with self._lock:
            row = self._conn.execute("SELECT payload FROM agent_setup_versions WHERE id=?", (version_id,)).fetchone()
        return AgentSetupVersion.model_validate_json(row[0]) if row else None

    def list_agent_setup_versions(self, setup_id: str) -> list[AgentSetupVersion]:
        with self._lock:
            rows = self._conn.execute("SELECT payload FROM agent_setup_versions WHERE setup_id=? ORDER BY rowid", (setup_id,)).fetchall()
        return [AgentSetupVersion.model_validate_json(row[0]) for row in rows]

    def save_agent_setup(self, record: AgentSetupRecord, version: AgentSetupVersion | None = None, *, base_version: str | None = None) -> None:
        with self._lock, self._conn:
            # BEGIN IMMEDIATE makes version comparison and append atomic across connections.
            self._conn.execute("BEGIN IMMEDIATE")
            current = self.get_agent_setup(record.id)
            if base_version is not None and current is not None and not current.active:
                raise HarnessError("This agent setup was removed. Reload before saving.", code="agent_setup_inactive", status_code=409)
            if base_version is not None and (current is None or current.current_version_id != base_version):
                raise HarnessError("This agent was edited elsewhere. Reload before saving.", code="agent_setup_conflict", status_code=409)
            if version is not None:
                self._conn.execute("INSERT INTO agent_setup_versions(id,setup_id,payload) VALUES(?,?,?)", (version.id, version.setup_id, version.model_dump_json()))
            self._conn.execute("INSERT OR REPLACE INTO agent_setups(id,payload) VALUES(?,?)", (record.id, record.model_dump_json()))
