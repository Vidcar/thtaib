"""ApplicationStore-backed retained asset persistence."""

from __future__ import annotations

import sqlite3

from workbench_backend.assets.schemas import RetainedAsset
from workbench_backend.state.store import ApplicationStore


class RetainedAssetStore:
    """Uses the existing application.sqlite connection and lock."""

    def __init__(self, app_store: ApplicationStore) -> None:
        self.app_store = app_store

    def put(self, asset: RetainedAsset, content: bytes) -> RetainedAsset:
        with self.app_store._lock:
            self.app_store._conn.execute(
                """
                INSERT INTO retained_assets(
                    id, payload, content, origin, session_id, project_path, sha256, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload=excluded.payload,
                    content=excluded.content,
                    origin=excluded.origin,
                    session_id=excluded.session_id,
                    project_path=excluded.project_path,
                    sha256=excluded.sha256,
                    deleted_at=excluded.deleted_at
                """,
                (
                    asset.id,
                    asset.model_dump_json(),
                    sqlite3.Binary(content),
                    asset.origin.value,
                    asset.session_id,
                    asset.project_path,
                    asset.sha256,
                    asset.deleted_at,
                ),
            )
            self.app_store._conn.commit()
        return asset

    def get(self, asset_id: str) -> tuple[RetainedAsset, bytes] | None:
        with self.app_store._lock:
            row = self.app_store._conn.execute(
                "SELECT payload, content FROM retained_assets WHERE id = ?",
                (asset_id,),
            ).fetchone()
        if row is None:
            return None
        return RetainedAsset.model_validate_json(row["payload"]), bytes(row["content"])

    def list(
        self,
        *,
        session_id: str | None = None,
        project_path: str | None = None,
        origin: str | None = None,
        include_deleted: bool = False,
    ) -> list[RetainedAsset]:
        clauses: list[str] = []
        params: list[object] = []
        availability: list[str] = []
        if session_id is not None:
            availability.append(
                """
                (
                    session_id = ?
                    OR EXISTS (
                        SELECT 1 FROM retained_asset_consumers rac
                        WHERE rac.asset_id = retained_assets.id
                        AND rac.consumer_kind = 'session'
                        AND rac.consumer_id = ?
                    )
                )
                """
            )
            params.extend([session_id, session_id])
        if project_path is not None:
            availability.append("project_path = ?")
            params.append(project_path)
        if availability:
            clauses.append("(" + " OR ".join(availability) + ")")
        if origin is not None:
            clauses.append("origin = ?")
            params.append(origin)
        if not include_deleted:
            clauses.append("deleted_at IS NULL")
        sql = "SELECT payload FROM retained_assets"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY json_extract(payload, '$.observed_at'), id"
        with self.app_store._lock:
            rows = self.app_store._conn.execute(sql, params).fetchall()
        return [RetainedAsset.model_validate_json(row["payload"]) for row in rows]

    def add_consumer(self, asset_id: str, *, kind: str, consumer_id: str, recorded_at: str) -> None:
        with self.app_store._lock:
            self.app_store._conn.execute(
                """
                INSERT OR IGNORE INTO retained_asset_consumers(
                    asset_id, consumer_kind, consumer_id, recorded_at
                ) VALUES (?, ?, ?, ?)
                """,
                (asset_id, kind, consumer_id, recorded_at),
            )
            self.app_store._conn.commit()

    def consumers(self, asset_ids: list[str] | None = None) -> dict[str, list[dict[str, str]]]:
        clauses: list[str] = []
        params: list[object] = []
        if asset_ids:
            placeholders = ",".join("?" for _ in asset_ids)
            clauses.append(f"asset_id IN ({placeholders})")
            params.extend(asset_ids)
        sql = "SELECT asset_id, consumer_kind, consumer_id FROM retained_asset_consumers"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY asset_id, consumer_kind, consumer_id"
        result: dict[str, list[dict[str, str]]] = {}
        with self.app_store._lock:
            rows = self.app_store._conn.execute(sql, params).fetchall()
        for row in rows:
            result.setdefault(str(row["asset_id"]), []).append(
                {
                    "kind": str(row["consumer_kind"]),
                    "id": str(row["consumer_id"]),
                }
            )
        return result

    def asset_ids_for_consumer(self, *, kind: str, consumer_id: str) -> list[str]:
        with self.app_store._lock:
            rows = self.app_store._conn.execute(
                """
                SELECT asset_id FROM retained_asset_consumers
                WHERE consumer_kind = ? AND consumer_id = ?
                ORDER BY recorded_at, asset_id
                """,
                (kind, consumer_id),
            ).fetchall()
        return [str(row["asset_id"]) for row in rows]

    def has_consumer(self, asset_id: str, *, kind: str, consumer_id: str) -> bool:
        with self.app_store._lock:
            row = self.app_store._conn.execute(
                """
                SELECT 1 FROM retained_asset_consumers
                WHERE asset_id = ? AND consumer_kind = ? AND consumer_id = ?
                """,
                (asset_id, kind, consumer_id),
            ).fetchone()
        return row is not None

    def delete_consumers(self, asset_id: str, consumers: list[dict[str, str]]) -> None:
        if not consumers:
            return
        with self.app_store._lock:
            for consumer in consumers:
                self.app_store._conn.execute(
                    """
                    DELETE FROM retained_asset_consumers
                    WHERE asset_id = ? AND consumer_kind = ? AND consumer_id = ?
                    """,
                    (asset_id, consumer["kind"], consumer["id"]),
                )
            self.app_store._conn.commit()

    def mark_deleted(self, asset_id: str, deleted_at: str) -> RetainedAsset | None:
        loaded = self.get(asset_id)
        if loaded is None:
            return None
        asset, _ = loaded
        asset = asset.model_copy(update={"deleted_at": deleted_at})
        self.put(asset, b"")
        return asset
