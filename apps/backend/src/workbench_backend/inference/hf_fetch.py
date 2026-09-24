"""huggingface_hub fetch boundary. Downloads only; it does not start inference."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
import fnmatch
import hashlib
import json
import re
from itertools import islice
import httpx
from urllib.parse import urlparse, unquote

from huggingface_hub import HfApi, hf_hub_download, snapshot_download
from huggingface_hub.errors import GatedRepoError, HfHubHTTPError, OfflineModeIsEnabled

from workbench_backend.errors import ManagerError
from workbench_backend.inference.schemas import HubRepository, HubSearchResult, HubSource, HubVariant

PUBLISHER_DIR = ".workbench-publisher"
REPOSITORY_TEMPLATE_DIR = ".workbench-repository-template"
CONFIG_NAMES = frozenset({"config.json", "generation_config.json", "tokenizer_config.json", "tokenizer.json", "chat_template.jinja"})


def _access_error(exc: Exception) -> ManagerError:
    if isinstance(exc, GatedRepoError):
        return ManagerError("This repository is gated. Accept its publisher's terms and configure Hugging Face access on this machine, then retry.", code="hf_gated", status_code=400)
    if isinstance(exc, (OfflineModeIsEnabled, httpx.TransportError)):
        return ManagerError("Hugging Face cannot be reached. Check your connection and offline-mode setting, then retry.", code="hf_offline", status_code=503)
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status == 401:
        return ManagerError("Hugging Face requires valid access credentials for this request. Configure or renew your local Hugging Face login, then retry.", code="hf_authentication", status_code=400)
    if status in {403, 404}:
        return ManagerError("This repository or revision is unavailable to your account. Check its name and your access, then retry.", code="hf_inaccessible", status_code=400)
    return ManagerError("Hugging Face could not complete the request. Try again later.", code="hf_service", status_code=502)


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
    siblings = {item.rfilename: item for item in getattr(info, "siblings", [])}
    files = {name: getattr(item, "size", None) for name, item in siblings.items()}
    groups: dict[str, list[str]] = {}
    auxiliary_groups: dict[str, list[str]] = {}
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
                auxiliary = (path.parts[0].casefold() == "mtp" or path.name.casefold().startswith("mtp-")
                             or re.match(r"(?i)^imatrix(?:[-_.]|$)", path.name) is not None)
                (auxiliary_groups if auxiliary else groups).setdefault(group, []).append(name)
        elif path.name.lower() in {"readme.md", ".src_sha", *CONFIG_NAMES}:
            guidance.append(name)
    def grouped_variants(grouped: dict[str, list[str]]) -> list[HubVariant]:
        result = []
        for name, names in grouped.items():
            matches = [re.search(r"-(\d{5})-of-(\d{5})\.gguf$", f, re.I) for f in names]
            complete = True
            if any(matches):
                totals = {int(m[2]) for m in matches if m}
                complete = len(totals) == 1 and all(matches)
                if complete:
                    total = next(iter(totals))
                    complete = {int(m[1]) for m in matches if m} == set(range(1, total + 1))
            size = sum(files[f] for f in names) if all(files[f] is not None for f in names) else None
            result.append(HubVariant(name=name, files=names, size_bytes=size, complete=complete))
        return result

    variants = grouped_variants(groups)
    auxiliary_ggufs = grouped_variants(auxiliary_groups)
    warnings = ["File size is disk usage, not a RAM/VRAM estimate. Runtime support depends on architecture, template and configuration."]
    if projectors:
        warnings.append("Projector compatibility is not established by its filename. Check publisher guidance and select explicitly, or choose text-only.")
    if auxiliary_ggufs:
        warnings.append("MTP and imatrix GGUF files are listed separately; they are not selectable primary model weights.")
    if not variants:
        warnings.append("No GGUF weights found. This execution path uses llama.cpp; other formats need a separate adapter.")
    return HubRepository(
        repo_id=repo_id,
        resolved_revision=str(sha),
        variants=variants,
        projectors=projectors,
        auxiliary_ggufs=auxiliary_ggufs,
        guidance_files=guidance,
        warnings=warnings,
        file_sha256={name: _sibling_sha256(item) for name, item in siblings.items()},
        file_sizes=files,
    )


def _sibling_sha256(item: object) -> str | None:
    lfs = getattr(item, "lfs", None)
    if isinstance(lfs, dict):
        digest = lfs.get("sha256")
    else:
        digest = getattr(lfs, "sha256", None)
    if isinstance(digest, str) and re.fullmatch(r"[0-9a-fA-F]{64}", digest):
        return digest.lower()
    return None


@dataclass(frozen=True)
class HuggingFaceDownload:
    repo_id: str
    requested_revision: str
    resolved_revision: str
    local_dir: Path
    expected_sizes: dict[str, int | None] = field(default_factory=dict)
    expected_sha256: dict[str, str | None] = field(default_factory=dict)
    source_repo_id: str | None = None
    source_revision: str | None = None
    source_files: list[str] = field(default_factory=list)


class HuggingFaceFetcher:
    def search(self, query: str, limit: int = 20) -> list[HubSearchResult]:
        value = query.strip()
        if not value:
            raise ManagerError("Enter a model search query.", code="hf_search_query", status_code=400)
        limit = max(1, min(limit, 50))
        try:
            results = list(islice(HfApi().list_models(search=value, limit=limit, sort="downloads"), limit))
        except (HfHubHTTPError, httpx.TransportError, OfflineModeIsEnabled) as exc:
            raise _access_error(exc) from exc
        return [
            HubSearchResult(
                repo_id=str(getattr(item, "modelId", "") or getattr(item, "id", "")),
                downloads=getattr(item, "downloads", None),
                likes=getattr(item, "likes", None),
            )
            for item in results
            if getattr(item, "modelId", None) or getattr(item, "id", None)
        ]

    def inspect(self, *, repo_id: str, revision: str = "main") -> HubRepository:
        repo_id = repository_id(repo_id)
        try:
            info = HfApi().model_info(repo_id=repo_id, revision=revision or "main", files_metadata=True)
        except (HfHubHTTPError, httpx.TransportError, OfflineModeIsEnabled) as exc:
            raise _access_error(exc) from exc
        listing = describe_repository(repo_id, info)
        if listing.variants:
            listing.source = self._verified_source(listing, info)
        else:
            listing.gguf_candidates = self._gguf_candidates(listing.repo_id)
        return listing

    def _gguf_candidates(self, source_repo_id: str) -> list[HubSearchResult]:
        name = source_repo_id.split("/", 1)[1]
        try:
            matches = HfApi().list_models(search=name, filter="gguf", sort="downloads", limit=50, cardData=True)
            candidates = [item for item in matches if _base_model(getattr(item, "card_data", None)) == source_repo_id]
        except (HfHubHTTPError, httpx.TransportError, OfflineModeIsEnabled) as exc:
            raise _access_error(exc) from exc
        return [HubSearchResult(repo_id=str(getattr(item, "modelId", "") or getattr(item, "id", "")),
            downloads=getattr(item, "downloads", None), likes=getattr(item, "likes", None))
            for item in candidates[:12] if getattr(item, "modelId", None) or getattr(item, "id", None)]

    def _verified_source(self, listing: HubRepository, info: object) -> HubSource | None:
        base_model = _base_model(getattr(info, "card_data", None))
        if not base_model or base_model == listing.repo_id:
            return None
        source = HubSource(repo_id=base_model, note="Conversion source commit could not be verified.")
        if ".src_sha" not in listing.file_sizes:
            return source
        try:
            marker = Path(hf_hub_download(repo_id=listing.repo_id, filename=".src_sha",
                revision=listing.resolved_revision)).read_text(encoding="utf-8")
            match = re.search(r"(?im)^PRIMARY=([0-9a-f]{40})\s*$", marker)
            if match is None:
                return source
            source_info = HfApi().model_info(repo_id=base_model, revision=match[1], files_metadata=True)
            source_listing = describe_repository(base_model, source_info)
        except (HfHubHTTPError, httpx.TransportError, OfflineModeIsEnabled, OSError, UnicodeError, ManagerError):
            return source
        if source_listing.resolved_revision.lower() != match[1].lower():
            return source
        return HubSource(repo_id=base_model, resolved_revision=source_listing.resolved_revision,
            verified=True, note="Conversion marker matches this publisher commit.",
            guidance_files=[name for name in source_listing.guidance_files if name in CONFIG_NAMES])

    def download(
        self,
        *,
        repo_id: str,
        revision: str,
        dest: Path,
        allow_patterns: list[str] | None,
        force_download: bool = False,
    ) -> HuggingFaceDownload:
        listing = self.inspect(repo_id=repo_id, revision=revision)
        repo_id, resolved = listing.repo_id, listing.resolved_revision
        available = [f for v in listing.variants + listing.projectors for f in v.files] + listing.guidance_files
        files = listing.file_sizes
        selected = {f for f in available if allow_patterns is None or any(fnmatch.fnmatchcase(f, p) for p in allow_patterns)}
        auxiliary_selected = {f for variant in listing.auxiliary_ggufs for f in variant.files
                              if allow_patterns is None or any(fnmatch.fnmatchcase(f, p) for p in allow_patterns)}
        if auxiliary_selected:
            raise ManagerError("Selected auxiliary GGUF files cannot be used as primary weights.", code="hf_auxiliary_selection", status_code=400)
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
        if any(name == prefix or name.startswith(prefix + "/")
            for name in listing.file_sizes for prefix in (PUBLISHER_DIR, REPOSITORY_TEMPLATE_DIR)):
            raise ManagerError("The repository uses a reserved configuration path.", code="hf_file_path_collision", status_code=400)
        # A moving branch may resolve to a different commit on retry. Keep its
        # upstream resume metadata separate so removed files cannot leak into
        # the newly selected bundle.
        dest = dest / resolved
        dest.mkdir(parents=True, exist_ok=True)
        snapshot_download(
            repo_id=repo_id,
            revision=resolved,
            local_dir=str(dest),
            force_download=force_download,
            allow_patterns=[f.replace("[", "[[]").replace("?", "[?]").replace("*", "[*]") for f in sorted(selected)],
        )
        source_files: list[str] = []
        expected_sizes = {name: files.get(name) for name in selected}
        expected_sha256 = {name: listing.file_sha256.get(name) for name in selected}
        _materialize_tokenizer_template(dest, selected, REPOSITORY_TEMPLATE_DIR,
            expected_sizes, expected_sha256)
        source = listing.source
        if source is not None and source.verified and source.resolved_revision:
            pinned_source = describe_repository(source.repo_id, HfApi().model_info(
                repo_id=source.repo_id, revision=source.resolved_revision, files_metadata=True))
            if pinned_source.resolved_revision != source.resolved_revision:
                raise ManagerError("Publisher source changed during selection.", code="hf_source_revision", status_code=409)
            source_files = [name for name in source.guidance_files if name in CONFIG_NAMES]
            if source_files:
                snapshot_download(repo_id=source.repo_id, revision=source.resolved_revision,
                    local_dir=str(dest / PUBLISHER_DIR), force_download=force_download,
                    allow_patterns=sorted(source_files))
                for name in source_files:
                    bundled_name = f"{PUBLISHER_DIR}/{name}"
                    expected_sizes[bundled_name] = pinned_source.file_sizes.get(name)
                    expected_sha256[bundled_name] = pinned_source.file_sha256.get(name)
                _materialize_tokenizer_template(dest / PUBLISHER_DIR, set(source_files),
                    PUBLISHER_DIR, expected_sizes, expected_sha256, root=dest)
        return HuggingFaceDownload(
            repo_id=repo_id,
            requested_revision=revision,
            resolved_revision=resolved,
            local_dir=dest,
            expected_sizes=expected_sizes,
            expected_sha256=expected_sha256,
            source_repo_id=source.repo_id if source and source.verified else None,
            source_revision=source.resolved_revision if source and source.verified else None,
            source_files=source_files,
        )


def _base_model(card_data: object) -> str | None:
    raw = card_data.get("base_model") if isinstance(card_data, dict) else getattr(card_data, "base_model", None)
    values = raw if isinstance(raw, list) else [raw]
    candidates: set[str] = set()
    for value in values:
        if isinstance(value, str):
            try:
                candidates.add(repository_id(value))
            except ManagerError:
                continue
    return next(iter(candidates)) if len(candidates) == 1 else None


def _materialize_tokenizer_template(directory: Path, selected: set[str], namespace: str,
    expected_sizes: dict[str, int | None], expected_sha256: dict[str, str | None],
    *, root: Path | None = None) -> None:
    if "chat_template.jinja" in selected or "tokenizer_config.json" not in selected:
        return
    try:
        config = json.loads((directory / "tokenizer_config.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return
    raw = config.get("chat_template") if isinstance(config, dict) else None
    if isinstance(raw, dict):
        raw = raw.get("default")
    elif isinstance(raw, list):
        raw = next((item.get("template") for item in raw if isinstance(item, dict)
            and item.get("name") == "default"), None)
    if not isinstance(raw, str) or not raw.strip():
        return
    destination = (root or directory) / namespace / "chat_template.from-tokenizer.jinja"
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = raw.encode("utf-8")
    destination.write_bytes(payload)
    relative = f"{namespace}/chat_template.from-tokenizer.jinja"
    expected_sizes[relative] = len(payload)
    expected_sha256[relative] = hashlib.sha256(payload).hexdigest()
