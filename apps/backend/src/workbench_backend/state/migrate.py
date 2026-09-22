"""One-shot JSON run/chat linkage → application.sqlite.

After cutover the application DB is the only system of record. Legacy JSON
files are archived and not updated. This is not a dual-write period and not
an exactly-once claim across databases and files.
"""

from __future__ import annotations

import json
from pathlib import Path

from workbench_backend.agents.schemas import AgentRun
from workbench_backend.chat.schemas import ChatConversation
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.store import ApplicationStore, json_chat_root, json_runs_root
from workbench_backend.state.chat_state import migrate_chat_identity_payload

CHAT_SOURCE = "state/chat"
RUNS_SOURCE = "state/runs"


def open_application_store(paths: WorkbenchPaths) -> ApplicationStore:
    """Open application.sqlite and migrate JSON run/chat linkage once."""

    store = ApplicationStore(paths)
    migrate_json_linkage(store)
    return store


def migrate_json_linkage(store: ApplicationStore) -> None:
    _migrate_chat(store)
    _migrate_runs(store)


def _migrate_chat(store: ApplicationStore) -> None:
    if store.migration_done(CHAT_SOURCE):
        return
    root = json_chat_root(store.paths)
    if root.is_dir():
        archived = root / "migrated"
        for path in sorted(root.glob("chat_*.json")):
            conversation = ChatConversation.model_validate(migrate_chat_identity_payload(json.loads(path.read_text(encoding="utf-8"))))
            if store.get_conversation(conversation.id) is None:
                store.put_conversation(conversation)
            _archive(path, archived)
    store.record_migration(CHAT_SOURCE, str(store.path))


def _migrate_runs(store: ApplicationStore) -> None:
    if store.migration_done(RUNS_SOURCE):
        return
    root = json_runs_root(store.paths)
    if root.is_dir():
        archived = root / "migrated"
        for path in sorted(root.glob("*.json")):
            raw = json.loads(path.read_text(encoding="utf-8"))
            run = AgentRun.model_validate(raw)
            if store.get_run(run.id) is None:
                store.put_run(run)
            _archive(path, archived)
    store.record_migration(RUNS_SOURCE, str(store.path))


def _archive(path: Path, archived: Path) -> None:
    archived.mkdir(parents=True, exist_ok=True)
    path.replace(archived / path.name)
