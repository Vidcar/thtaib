"""huggingface_hub fetch boundary. Downloads only; it does not start inference."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download


@dataclass(frozen=True)
class HuggingFaceDownload:
    repo_id: str
    requested_revision: str
    resolved_revision: str
    local_dir: Path


class HuggingFaceFetcher:
    def download(
        self,
        *,
        repo_id: str,
        revision: str,
        dest: Path,
        allow_patterns: list[str] | None,
    ) -> HuggingFaceDownload:
        dest.mkdir(parents=True, exist_ok=True)
        api = HfApi()
        info = api.repo_info(repo_id=repo_id, revision=revision)
        resolved = str(getattr(info, "sha", None) or revision)
        snapshot_download(
            repo_id=repo_id,
            revision=resolved,
            local_dir=str(dest),
            allow_patterns=allow_patterns,
        )
        return HuggingFaceDownload(
            repo_id=repo_id,
            requested_revision=revision,
            resolved_revision=resolved,
            local_dir=dest,
        )
