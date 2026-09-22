"""Connection records and historical configuration in application.sqlite."""
import json
from workbench_backend.connections.schemas import ConnectionRecord
from workbench_backend.errors import HarnessError


class ConnectionStore:
    def __init__(self, application):
        self.application = application
        with application._lock, application._conn:
            application._conn.execute("CREATE TABLE IF NOT EXISTS connections (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            application._conn.execute("CREATE TABLE IF NOT EXISTS connection_versions (id TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(id,version))")

    def list(self):
        with self.application._lock:
            return [ConnectionRecord.model_validate_json(r[0]) for r in self.application._conn.execute("SELECT payload FROM connections ORDER BY id").fetchall()]

    def get(self, connection_id):
        with self.application._lock:
            row = self.application._conn.execute("SELECT payload FROM connections WHERE id=?", (connection_id,)).fetchone()
            return ConnectionRecord.model_validate_json(row[0]) if row else None

    def put(self, record, *, expected_version=None):
        with self.application._lock, self.application._conn:
            current = self.get(record.id)
            if expected_version is not None and (current is None or current.version != expected_version):
                raise HarnessError("This connection changed. Refresh it before saving.", code="connection_conflict", status_code=409)
            # Presence is resolved from the OS credential store, never durable truth.
            payload = record.model_dump(mode="json", exclude={"credential_present"})
            encoded = json.dumps(payload)
            self.application._conn.execute("INSERT OR REPLACE INTO connections VALUES (?,?)", (record.id, encoded))
            self.application._conn.execute("INSERT OR IGNORE INTO connection_versions VALUES (?,?,?)", (record.id, record.version, encoded))
        return record
