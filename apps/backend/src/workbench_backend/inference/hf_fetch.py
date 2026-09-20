"""huggingface_hub fetch boundary. Downloads only; it does not start inference."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import fnmatch
import re
from urllib.parse import urlparse, unquote

from huggingface_hub import HfApi, snapshot_download
from huggingface_hub.errors import GatedRepoError, HfHubHTTPError

from workbench_backend.errors import ManagerError
from workbench_backend.inference.schemas import HubRepository, HubVariant


def repository_id(value: str) -> str:
    value = value.strip()
    if "://" in value:
        url = urlparse(value)
        if url.scheme != "https" or url.hostname != "huggingface.co":
            raise ManagerError("Use a huggingface.co model link or owner/repository.", code="hf_repository", status_code=400)
        value = "/".join(unquote(url.path).strip("/").split("/")[:2])
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", value):
        raise ManagerError("Use a model repository in owner/name form.", code="hf_repository", status_code=400)
    return value


def describe_repository(repo_id: str, info: object) -> HubRepository:
    sha = getattr(info, "sha", None)
    if not sha or not re.fullmatch(r"[0-9a-fA-F]{40}", str(sha)):
        raise ManagerError("Hugging Face did not return an immutable revision.", code="hf_revision", status_code=502)
    files = {item.rfilename: getattr(item, "size", None) for item in getattr(info, "siblings", [])}
    groups: dict[str, list[str]] = {}
    projectors: list[HubVariant] = []
    guidance: list[str] = []
    for name, size in sorted(files.items()):
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
            raise ManagerError("Repository contains an unsafe file path.", code="hf_file_path", status_code=400)
        if name.lower().endswith(".gguf"):
            if "mmproj" in path.name.lower() or "projector" in path.name.lower():
                projectors.append(HubVariant(name=name, files=[name], size_bytes=size))
            else:
                group = re.sub(r"-\d{5}-of-\d{5}\.gguf$", ".gguf", name, flags=re.I)
                groups.setdefault(group, []).append(name)
        elif path.name.lower() in {"readme.md", "config.json", "generation_config.json", "tokenizer_config.json", "chat_template.jinja"}:
            guidance.append(name)
    variants = []
    for name, names in groups.items():
        matches = [re.search(r"-(\d{5})-of-(\d{5})\.gguf$", f, re.I) for f in names]
        complete = True
        if any(matches):
            totals = {int(m[2]) for m in matches if m}
            complete = len(totals) == 1 and all(matches)
            if complete:
                total = next(iter(totals))
                complete = {int(m[1]) for m in matches if m} == set(range(1, total + 1))
        size = sum(files[f] for f in names) if all(files[f] is not None for f in names) else None
        variants.append(HubVariant(name=name, files=names, size_bytes=size, complete=complete))
    warnings = ["File size is disk usage, not a RAM/VRAM estimate. Runtime support depends on architecture, template and configuration."]
    if projectors:
        warnings.append("Projector compatibility is not established by its filename. Check publisher guidance and select explicitly, or choose text-only.")
    if not variants:
        warnings.append("No GGUF weights found. This execution path uses llama.cpp; other formats need a separate adapter.")
    return HubRepository(repo_id=repo_id, resolved_revision=str(sha), variants=variants, projectors=projectors, guidance_files=guidance, warnings=warnings)


@dataclass(frozen=True)
class HuggingFaceDownload:
    repo_id: str
    requested_revision: str
    resolved_revision: str
    local_dir: Path


class HuggingFaceFetcher:
    def inspect(self, *, repo_id: str, revision: str = "main") -> HubRepository:
        repo_id = repository_id(repo_id)
        try:
            info = HfApi().model_info(repo_id=repo_id, revision=revision or "main", files_metadata=True)
        except GatedRepoError as exc:
            raise ManagerError("This repository is gated. Accept its terms and configure Hugging Face access on this machine, then retry.", code="hf_gated", status_code=400) from exc
        except HfHubHTTPError as exc:
            raise ManagerError("Could not read this Hugging Face repository/revision. Check its name, access and connection.", code="hf_access", status_code=400) from exc
        return describe_repository(repo_id, info)

    def download(
        self,
        *,
        repo_id: str,
        revision: str,
        dest: Path,
        allow_patterns: list[str] | None,
    ) -> HuggingFaceDownload:
        listing = self.inspect(repo_id=repo_id, revision=revision)
        repo_id, resolved = listing.repo_id, listing.resolved_revision
        available = [f for v in listing.variants + listing.projectors for f in v.files] + listing.guidance_files
        selected = {f for f in available if allow_patterns is None or any(fnmatch.fnmatchcase(f, p) for p in allow_patterns)}
        if len({f.lower() for f in selected}) != len(selected):
            raise ManagerError(
                "Selected files include paths that differ only by case, which is unsafe on this platform.",
                code="hf_file_path_collision",
                status_code=400,
            )
        variants = [v for v in listing.variants if selected.intersection(v.files)]
        if len(variants) != 1 or not variants[0].complete or not set(variants[0].files).issubset(selected):
            raise ManagerError("Select exactly one complete GGUF variant, including every shard, before downloading.", code="hf_variant_selection", status_code=400)
        if sum(bool(selected.intersection(v.files)) for v in listing.projectors) > 1:
            raise ManagerError("Select one compatible projector or choose text-only before downloading.", code="hf_projector_selection", status_code=400)
        # A moving branch may resolve to a different commit on retry. Keep its
        # upstream resume metadata separate so removed files cannot leak into
        # the newly selected bundle.
        dest = dest / resolved
        dest.mkdir(parents=True, exist_ok=True)
        snapshot_download(
            repo_id=repo_id,
            revision=resolved,
            local_dir=str(dest),
            allow_patterns=[f.replace("[", "[[]").replace("?", "[?]").replace("*", "[*]") for f in sorted(selected)],
        )
        return HuggingFaceDownload(
            repo_id=repo_id,
            requested_revision=revision,
            resolved_revision=resolved,
            local_dir=dest,
        )
