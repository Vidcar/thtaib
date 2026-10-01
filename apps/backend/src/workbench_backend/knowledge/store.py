"""Append-only knowledge versions under the application knowledge directory."""

from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
import tempfile
import time

from pydantic import TypeAdapter

from workbench_backend.knowledge.schemas import (
    ContextCaptureSettings,
    KnowledgeConfig,
    KnowledgeEntry,
    KnowledgeVersion,
    KnowledgeProposal,
    SkillResource,
)
from workbench_backend.paths import WorkbenchPaths


class KnowledgeStore:
    def __init__(self, paths: WorkbenchPaths) -> None:
        self.paths = paths.ensure()
        self.root = self.paths.knowledge
        self.root.mkdir(parents=True, exist_ok=True)
        self.entries_path = self.root / "entries.json"
        self.versions_dir = self.root / "versions"
        self.config_path = self.root / "config.json"
        self.proposals_dir = self.root / "proposals"
        self.versions_dir.mkdir(parents=True, exist_ok=True)
        self.proposals_dir.mkdir(parents=True, exist_ok=True)

    def read_config(self) -> KnowledgeConfig:
        if not self.config_path.is_file():
            # Concurrent initial readers must not publish defaults over
            # another caller's newly saved choices.
            return KnowledgeConfig()
        config = KnowledgeConfig.model_validate_json(self.config_path.read_text(encoding="utf-8"))
        # A saved redaction choice must not revive a stored request policy.
        return config.model_copy(update={"context_captures": ContextCaptureSettings()})

    def write_config(self, config: KnowledgeConfig) -> KnowledgeConfig:
        stored = config.model_copy(update={"context_captures": ContextCaptureSettings()})
        self._write_json(self.config_path, stored.model_dump(mode="json"))
        return stored

    def list_entries(self) -> list[KnowledgeEntry]:
        return self._read_list(self.entries_path, KnowledgeEntry)

    def get_entry(self, entry_id: str) -> KnowledgeEntry | None:
        return next((item for item in self.list_entries() if item.id == entry_id), None)

    def put_entry(self, entry: KnowledgeEntry) -> KnowledgeEntry:
        items = self.list_entries()
        next_items: list[KnowledgeEntry] = []
        replaced = False
        for existing in items:
            if existing.id == entry.id:
                next_items.append(entry)
                replaced = True
            else:
                next_items.append(existing)
        if not replaced:
            next_items.append(entry)
        self._write_json(self.entries_path, [item.model_dump(mode="json") for item in next_items])
        return entry

    def append_version(self, version: KnowledgeVersion) -> KnowledgeVersion:
        path = self.versions_dir / f"{version.id}.json"
        if path.exists():
            raise FileExistsError(version.id)
        self._write_json(path, version.model_dump(mode="json"))
        return version

    def get_version(self, version_id: str) -> KnowledgeVersion | None:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", version_id):
            return None
        path = self.versions_dir / f"{version_id}.json"
        if not path.is_file():
            return None
        return KnowledgeVersion.model_validate_json(path.read_text(encoding="utf-8"))

    def list_versions(self, entry_id: str) -> list[KnowledgeVersion]:
        versions = [
            KnowledgeVersion.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self.versions_dir.glob("knv_*.json"))
        ]
        return [item for item in versions if item.entry_id == entry_id]

    def retain_resource(self, relative_path: str, data: bytes) -> SkillResource:
        digest = hashlib.sha256(data).hexdigest()
        root = self.root / "resources"
        root.mkdir(exist_ok=True)
        target = root / digest
        if not target.is_file():
            temporary = target.with_suffix(".tmp")
            temporary.write_bytes(data)
            temporary.replace(target)
        return SkillResource(path=relative_path, sha256=digest, size_bytes=len(data))

    def read_resource(self, resource: SkillResource) -> bytes:
        if not re.fullmatch(r"[a-f0-9]{64}", resource.sha256):
            raise ValueError("Invalid retained resource digest")
        data = (self.root / "resources" / resource.sha256).read_bytes()
        if len(data) != resource.size_bytes or hashlib.sha256(data).hexdigest() != resource.sha256:
            raise ValueError("The retained skill resource no longer matches its version")
        return data

    def put_proposal(self, proposal: KnowledgeProposal) -> KnowledgeProposal:
        self._write_json(self.proposals_dir / f"{proposal.id}.json", proposal.model_dump(mode="json"))
        return proposal

    def get_proposal(self, proposal_id: str) -> KnowledgeProposal | None:
        if Path(proposal_id).name != proposal_id:
            return None
        path = self.proposals_dir / f"{proposal_id}.json"
        return KnowledgeProposal.model_validate_json(path.read_text(encoding="utf-8")) if path.is_file() else None

    def list_proposals(self) -> list[KnowledgeProposal]:
        return [KnowledgeProposal.model_validate_json(p.read_text(encoding="utf-8")) for p in sorted(self.proposals_dir.glob("proposal_*.json"))]

    def _read_list(self, path: Path, model: type[KnowledgeEntry]) -> list[KnowledgeEntry]:
        if not path.is_file():
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
        return TypeAdapter(list[model]).validate_python(raw)

    def _write_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(payload, indent=2)
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                    prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
                tmp = Path(handle.name)
                handle.write(data)
            # Windows requires the temporary handle to close before replacing.
            # Each writer owns its temporary file; readers see a whole record.
            for attempt in range(10):
                try:
                    tmp.replace(path)
                    break
                except PermissionError as exc:
                    # Concurrent replacement/read handles can briefly block a
                    # Windows rename. Real permission failures still surface.
                    if getattr(exc, "winerror", None) not in {5, 32, 33} or attempt == 9:
                        raise
                    time.sleep(0.005)
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
