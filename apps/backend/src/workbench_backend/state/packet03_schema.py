"""Packet 03 tables in the existing application SQLite authority."""

PREFERENCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS presentation_preferences (
    id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS permission_grants (
    id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS attention_receipts (
    identity TEXT PRIMARY KEY, notified_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS restored_roots (
    root TEXT PRIMARY KEY, backup_id TEXT NOT NULL, restored_at TEXT NOT NULL);
"""

ASSET_SCHEMA = """
CREATE TABLE IF NOT EXISTS retained_assets (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    content BLOB NOT NULL,
    origin TEXT NOT NULL,
    session_id TEXT NOT NULL,
    project_path TEXT,
    sha256 TEXT NOT NULL,
    deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS retained_asset_consumers (
    asset_id TEXT NOT NULL,
    consumer_kind TEXT NOT NULL,
    consumer_id TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (asset_id, consumer_kind, consumer_id),
    FOREIGN KEY(asset_id) REFERENCES retained_assets(id)
);
"""
