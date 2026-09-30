"""Advisory memory predictions at the existing inference boundary.

Remote inspection reads bounded prefixes to inspect a GGUF directory. A small
file may include initial tensor bytes; transfers are capped regardless of size.
Installed previews use cached directory facts. The pinned native helper runs
only for an explicit check. Neither path establishes residency or changes settings.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
import json
import math
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import threading
import time
from itertools import islice
from typing import Any

import httpx
from gguf.constants import GGMLQuantizationType, GGML_QUANT_SIZES
from huggingface_hub import get_token, hf_hub_url

from workbench_backend.errors import ManagerError
from workbench_backend.inference.bundles import mmproj_companion, collect_bundle_files, validate_bundle_selection, is_under
from workbench_backend.inference.configurations import loading_startup_settings, loaded_model_identity
from workbench_backend.inference.hardware import HardwareObserver
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.inspect import (GgufFields, IncompleteMetadata, MAX_METADATA_BYTES,
    parse_gguf_directory, read_gguf_directory)
from workbench_backend.inference.inspection_cache import bundle_identity
from workbench_backend.inference.native_memory import COMMIT, PROTOCOL, preview_environment, require_planner
from workbench_backend.inference.schemas import ModelEstimateRequest, ModelMemoryEstimate, ResourceUsage
from workbench_backend.inference.settings import resolve_bags, startup_cli_args

MAX_METADATA_REQUESTS = 16
METADATA_DEADLINE = 15.0
NATIVE_DEADLINE = 15.0
MAX_NATIVE_OUTPUT = 256 * 1024
DENSE_ARCHITECTURES = frozenset({"llama", "qwen2", "qwen3"})
HYBRID_ARCHITECTURES = frozenset({"qwen35", "qwen35moe", "qwen3next"})



def dense_kv_bytes(fields: dict[str, Any], context: int, key_type: str, value_type: str) -> int | None:
    architecture = fields.get("general.architecture")
    if architecture not in DENSE_ARCHITECTURES or not 0 < context <= 2**32:
        return None
    prefix = f"{architecture}."
    for key, value in fields.items():
        if not ("sliding_window" in key or ".ssm." in key
                or "nextn_predict" in key or "kv_lora" in key or "recurrent" in key):
            continue
        # Presence with unknown or array-valued metadata cannot prove a dense
        # per-layer cache. Only an explicit numeric zero/false disables it.
        if value is not False and not (type(value) in {int, float} and value == 0):
            return None
    layers = _positive(fields.get(prefix + "block_count"))
    if layers is None:
        return None
    try:
        return sum(_attention_bytes(fields, layer, context, key_type, value_type) for layer in range(layers))
    except (KeyError, ValueError, TypeError):
        return None


def _positive(value: Any, *, zero: bool = False) -> int | None:
    return value if type(value) is int and (0 if zero else 1) <= value <= 2**20 else None


def _layer_value(fields: dict[str, Any], key: str, layer: int) -> int | None:
    value = fields.get(f"{fields.get('general.architecture')}.{key}")
    if isinstance(value, list):
        value = value[layer] if layer < len(value) else None
    return _positive(value, zero=True)


def _row_bytes(width: int, precision: str) -> int:
    block, size = GGML_QUANT_SIZES[GGMLQuantizationType[precision.upper()]]
    if width % block:
        raise ValueError("Unsupported cache block layout")
    return width // block * size


def _attention_bytes(fields, layer, context, key_type, value_type, *, v_trans=False) -> int:
    heads = _layer_value(fields, "attention.head_count", layer)
    kv_heads = _layer_value(fields, "attention.head_count_kv", layer)
    if kv_heads == 0:
        return 0
    embedding = _layer_value(fields, "embedding_length", layer)
    inferred = embedding // heads if embedding and heads and embedding % heads == 0 else None
    key_dim = _layer_value(fields, "attention.key_length", layer) or inferred
    value_dim = _layer_value(fields, "attention.value_length", layer) or inferred
    if not kv_heads or not key_dim or not value_dim:
        raise ValueError("Attention cache dimensions are unavailable.")
    value_width = kv_heads * value_dim
    if v_trans:
        layers = _positive(fields.get(f"{fields.get('general.architecture')}.block_count"))
        if layers is None:
            raise ValueError("Layer count is unavailable.")
        widths = []
        for index in range(layers):
            count = _layer_value(fields, "attention.head_count_kv", index)
            dim = _layer_value(fields, "attention.value_length", index) or inferred
            if count is None or dim is None:
                raise ValueError("Variable value cache dimensions are unavailable.")
            widths.append(count * dim)
        value_width = max(widths)
    return context * (_row_bytes(kv_heads * key_dim, key_type) + _row_bytes(value_width, value_type))


@dataclass
class CacheProjection:
    attention: dict[int, int] = field(default_factory=dict)
    recurrent: dict[int, int] = field(default_factory=dict)
    attention_known: bool = True
    recurrent_known: bool = True
    unknown: list[str] = field(default_factory=list)

    @property
    def total(self) -> int | None:
        return (sum(self.attention.values()) + sum(self.recurrent.values())
                if self.attention_known and self.recurrent_known else None)


def cache_projection(fields, context, key_type="f16", value_type="f16", *, parallel=4,
                     rollback=0, mtp=False, flash_attention="auto") -> CacheProjection:
    """Pinned b11045 tensor shapes; compute/driver allocation remains unknown.

    See src/{llama-kv-cache,llama-memory-recurrent,llama-hparams}.cpp and
    src/models/qwen35.cpp at ggml-org/llama.cpp's b11045 tag.
    """
    result = CacheProjection()
    arch = fields.get("general.architecture")
    layers = _positive(fields.get(f"{arch}.block_count"))
    nextn = _positive(fields.get(f"{arch}.nextn_predict_layers", 0), zero=True)
    if arch not in DENSE_ARCHITECTURES | HYBRID_ARCHITECTURES or not layers or nextn is None or nextn > layers:
        result.attention_known = result.recurrent_known = False
        result.unknown.append("Cache and model state projection is unavailable for this architecture.")
        return result
    trunk = layers - nextn
    if mtp:
        if not nextn:
            result.attention_known = False
            result.unknown.append("MTP attention layers are not reported by this model.")
            return result
        attention_layers, recurrent_layers = list(range(trunk, layers)), []
    elif arch in HYBRID_ARCHITECTURES:
        mask = fields.get(f"{arch}.attention.recurrent_layers")
        if mask is None:
            interval = _positive(fields.get(f"{arch}.full_attention_interval", 4))
            mask = [(index + 1) % interval != 0 for index in range(layers)] if interval else None
        elif type(mask) in {int, bool}:
            mask = [mask] * layers
        if (not isinstance(mask, list) or len(mask) != layers
                or any(type(value) not in {bool, int} or value not in {False, True} for value in mask)):
            result.attention_known = result.recurrent_known = False
            result.unknown.append("The model's recurrent layer layout is unavailable.")
            return result
        recurrent_layers = [index for index in range(trunk) if mask[index]]
        attention_layers = [index for index in range(trunk) if not mask[index]]
    else:
        if dense_kv_bytes(fields, 1, key_type, value_type) is None:
            result.attention_known = False
            result.unknown.append("The model's dense cache dimensions/layout are unavailable.")
            return result
        attention_layers, recurrent_layers = list(range(trunk)), []
    sliding = fields.get(f"{arch}.attention.sliding_window", 0)
    if sliding not in (0, False, None):
        result.attention_known = False
        result.unknown.append("Sliding-window cache allocation is not included in this metadata projection.")
    elif type(context) is not int or context <= 0:
        result.attention_known = False
        result.unknown.append("Automatic context allocation requires a known model maximum or a native check.")
    else:
        for layer in attention_layers:
            try:
                result.attention[layer] = _attention_bytes(fields, layer, context, key_type, value_type,
                    v_trans=flash_attention == "off")
            except (KeyError, TypeError, ValueError):
                result.attention_known = False
                result.unknown.append(f"Attention cache dimensions/type are unavailable for layer {layer}.")
    if recurrent_layers:
        conv = _positive(fields.get(f"{arch}.ssm.conv_kernel"))
        inner = _positive(fields.get(f"{arch}.ssm.inner_size"))
        state = _positive(fields.get(f"{arch}.ssm.state_size"))
        groups = _positive(fields.get(f"{arch}.ssm.group_count"))
        if None in (conv, inner, state, groups):
            result.recurrent_known = False
            result.unknown.append("Recurrent state dimensions are unavailable; attention bytes remain known.")
        else:
            # Native recurrent R/S are f32 independent of requested K/V precision.
            rows = max(1, parallel) * (1 + rollback)
            per_layer = ((conv - 1) * (inner + 2 * groups * state) + state * inner) * 4 * rows
            result.recurrent = {layer: per_layer for layer in recurrent_layers}
    return result


def _bounded_native(args: list[str], timeout: float = NATIVE_DEADLINE) -> str:
    """Drain both pipes with a shared cap; no log files or service process."""
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=preview_environment(), cwd=Path(args[0]).resolve().parent,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    output: list[bytes] = []
    stderr: list[bytes] = []
    count = 0
    exceeded = threading.Event()
    lock = threading.Lock()
    def drain(pipe, target):
        nonlocal count
        try:
            while chunk := pipe.read(4096):
                with lock:
                    count += len(chunk)
                    if count > MAX_NATIVE_OUTPUT:
                        exceeded.set()
                        process.kill()
                        return
                    target.append(chunk)
        finally:
            pipe.close()
    threads = [threading.Thread(target=drain, args=(process.stdout, output), daemon=True),
               threading.Thread(target=drain, args=(process.stderr, stderr), daemon=True)]
    for thread in threads:
        thread.start()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)
        raise ValueError("Native prediction exceeded its time budget") from None
    finally:
        for thread in threads:
            thread.join(timeout=2)
    if exceeded.is_set() or process.returncode:
        raise ValueError("Native memory prediction is unavailable for these settings")
    return b"".join(output).decode("utf-8", errors="replace")


class MemoryEstimator:
    def __init__(self, manager) -> None:
        self.manager = manager
        self.hardware = HardwareObserver()
        self._metadata: OrderedDict[str, tuple[dict[str, Any], int | None]] = OrderedDict()
        self._metadata_failures: OrderedDict[str, str] = OrderedDict()
        self._repositories: OrderedDict[str, Any] = OrderedDict()
        self._native: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._lock = threading.Lock()
        self._worker = threading.Lock()

    def estimate(self, request: ModelEstimateRequest) -> ModelMemoryEstimate:
        started = time.perf_counter()
        bags = resolve_bags(startup=request.startup)
        if bags.startup.unsupported:
            raise ManagerError("Check the selected launch settings.", code="estimate_settings", status_code=400)
        hardware = self.hardware.observe(refresh=request.refresh)
        if sum(bool(item) for item in (request.bundle_id, request.repo_id, request.source_path)) != 1:
            raise ManagerError("Choose one installed model, repository selection or local source.", code="estimate_selection", status_code=400)
        if request.method == "native" and not request.bundle_id:
            raise ManagerError("Native checking requires an installed model; Choose uses read-only metadata.", code="estimate_selection", status_code=400)
        identity = request.bundle_id or request.source_path or f"{request.repo_id}@{request.revision}:{','.join(request.primary_files)}"
        result = ModelMemoryEstimate(source_identity=identity, estimated_at=utc_now(), hardware=hardware,
            basis=request.basis, selected_startup=dict(request.startup), evaluated_startup=dict(request.startup))
        self._set_budgets(result)
        fields = GgufFields()
        projector_fields: GgufFields | None = None
        draft_fields: GgufFields | None = None
        if request.bundle_id:
            fields, projector_fields, draft_fields = self._estimate_installed_bundle(request, bags, result)
        elif request.repo_id:
            fields, projector_fields, draft_fields = self._estimate_repository_files(request, bags, result)
        elif request.source_path:
            fields, projector_fields, draft_fields = self._estimate_local_source(request, bags, result)
        else:
            raise ManagerError("Choose an installed model or exact repository files.", code="estimate_selection", status_code=400)
        result.builtin_mtp = self._builtin_mtp(fields)
        result.advertised_modalities = self._advertised_modalities(fields)
        if result.source != "native_prediction":
            self._metadata_prediction(fields, bags.startup.applied, result,
                                      projector_fields=projector_fields, draft_fields=draft_fields)
        result.unknown_reasons.extend(hardware.reasons)
        result.unknown_reasons = list(dict.fromkeys(result.unknown_reasons))
        result.calculation_ms = round((time.perf_counter() - started) * 1000, 3)
        return result

    @staticmethod
    def _set_budgets(result):
        capacity = result.basis == "capacity"
        result.gpu_headroom_bytes = 1024**3 if capacity else 0
        result.ram_headroom_bytes = 2 * 1024**3 if capacity else 0
        for device in result.hardware.gpu_devices:
            raw = device.total_bytes if capacity else device.available_bytes
            result.gpu_budget_bytes[device.id] = max(0, raw - result.gpu_headroom_bytes) if raw is not None else None
        raw = result.hardware.ram_total_bytes if capacity else result.hardware.ram_available_bytes
        result.ram_budget_bytes = max(0, raw - result.ram_headroom_bytes) if raw is not None else None
        if capacity:
            result.assumptions.append("Discovery uses physical capacity with 1 GiB GPU and 2 GiB RAM headroom; current loaded models are excluded.")

    def _estimate_local_source(self, request, bags, result):
        source = Path(request.source_path).expanduser().resolve()
        if source.is_dir():
            candidates = list(islice((path for path in source.rglob("*") if path.is_file()
                and ".cache" not in path.relative_to(source).parts), 257))
        else:
            candidates = collect_bundle_files(source)
        if len(candidates) > 256:
            raise ManagerError("Choose a smaller local folder or one complete model selection.", code="estimate_selection", status_code=400)
        if source.is_dir() and any(not is_under(path, source) for path in candidates):
            raise ManagerError("Local preview cannot follow files outside the chosen folder.", code="estimate_selection", status_code=400)
        # Optional explicit members are restricted to this local selection; do
        # not turn a preview into a general host-file reader.
        if request.primary_files or request.projector_files:
            root = source if source.is_dir() else source.parent
            selected = [((root / name).resolve()) for name in request.primary_files + request.projector_files]
            if any(not is_under(path, root) or path not in candidates for path in selected):
                raise ManagerError("Choose files belonging to the local source.", code="estimate_selection", status_code=400)
            candidates = selected
        primaries, shards, companions = validate_bundle_selection(candidates)
        if not primaries:
            raise ManagerError("Choose a complete GGUF weights selection.", code="estimate_selection", status_code=400)
        projectors = [path for path in companions if path.suffix.casefold() == ".gguf"]
        result.source_identity = str(source)
        result.model_disk_bytes = sum(path.stat().st_size for path in primaries + shards)
        result.projector_disk_bytes = sum(path.stat().st_size for path in projectors)
        fields = GgufFields()
        try:
            for index, path in enumerate(primaries + shards):
                part, _ = self._local_directory(path, refresh=request.refresh)
                if index == 0:
                    fields = part
                else:
                    fields.tensors += part.tensors
            result.weights_bytes = self._weight_bytes(fields, bags.startup.applied)
        except (OSError, ValueError, ManagerError) as exc:
            result.unknown_reasons.append(f"Local model metadata is unavailable: {getattr(exc, 'message', str(exc))}")
        projector_fields = None
        if projectors:
            try:
                projector_fields, result.projector_bytes = self._local_directory(projectors[0], refresh=request.refresh)
            except (OSError, ValueError, ManagerError) as exc:
                result.unknown_reasons.append(f"Projector metadata is unavailable: {getattr(exc, 'message', str(exc))}")
        else:
            result.projector_bytes = 0
        return fields, projector_fields, self._installed_draft_fields(bags, request, result)

    def _estimate_installed_bundle(self, request, bags, result):
        bundle = self.manager.store.get_bundle(request.bundle_id)
        if bundle is None:
            raise ManagerError("Unknown bundle", code="bundle_missing", status_code=404)
        primaries = [item for item in bundle.files if item.name.lower().endswith(".gguf")
            and item.role.value in {"primary_weights", "shard"}]
        result.model_disk_bytes = sum(item.size_bytes for item in primaries)
        projector = mmproj_companion(bundle)
        result.projector_disk_bytes = projector.size_bytes if projector else 0
        fields = self._installed_primary_fields(primaries, request, bags, result)
        projector_fields = self._installed_projector_fields(projector, request, result)
        draft_fields = self._installed_draft_fields(bags, request, result)
        self._apply_explicit_native_check(bundle, request, result)
        self._attach_observed_runtime(bundle, bags, result)
        return fields, projector_fields, draft_fields

    def _installed_primary_fields(self, primaries, request, bags, result):
        fields = GgufFields()
        try:
            for index, primary in enumerate(primaries):
                if Path(primary.path).stat().st_size != primary.size_bytes:
                    raise ValueError("Model files changed; known disk totals may be out of date. Verify the model in Files.")
                shard_fields, _ = self._local_directory(Path(primary.path), refresh=request.refresh)
                if index == 0:
                    fields = shard_fields
                else:
                    fields.tensors += shard_fields.tensors
            result.weights_bytes = self._weight_bytes(fields, bags.startup.applied)
            result.architecture = fields.get("general.architecture")
            maximum = fields.get(f"{result.architecture}.context_length")
            result.context_maximum = maximum if isinstance(maximum, int) and 0 < maximum < 2**32 else None
        except (OSError, ValueError, ManagerError) as exc:
            result.unknown_reasons.append(str(exc) if not isinstance(exc, ManagerError) else exc.message)
        return fields

    def _installed_projector_fields(self, projector, request, result):
        if projector:
            try:
                projector_fields, result.projector_bytes = self._local_directory(Path(projector.path), refresh=request.refresh)
                return projector_fields
            except (OSError, ValueError, ManagerError) as exc:
                result.unknown_reasons.append(f"Projector metadata is unavailable: {getattr(exc, 'message', str(exc))}")
                return None
        result.projector_bytes = 0
        return None

    def _installed_draft_fields(self, bags, request, result):
        draft_fields = None
        draft_path = bags.startup.applied.get("spec_draft_model")
        if draft_path and self._spec_modes(bags.startup.applied) - {"none"}:
            try:
                draft_fields, _ = self._local_directory(Path(draft_path), refresh=request.refresh)
            except (OSError, ValueError, ManagerError) as exc:
                result.unknown_reasons.append(f"Draft metadata is unavailable: {getattr(exc, 'message', str(exc))}")
        return draft_fields

    def _apply_explicit_native_check(self, bundle, request, result):
        if request.method == "native":
            # A metadata-reader failure cannot disable an explicit native check.
            try:
                self._native_prediction(bundle, request, result)
            except (OSError, ValueError, ManagerError) as exc:
                result.completeness = "unavailable"
                result.unknown_reasons.append(str(exc) if not isinstance(exc, ManagerError) else exc.message)

    def _attach_observed_runtime(self, bundle, bags, result):
        # A different setup, slot policy or cache on the same weights is
        # not an observation of this candidate. Response choices are absent
        # from the canonical native residency identity.
        plan_identity = loaded_model_identity(self.manager.runtime.current(), bundle, bags, hash_external=False)
        result.plan_identity = plan_identity
        try:
            verification = json.loads(self.manager.store.get_setting(f"model-verification:{bundle.id}") or "null")
            observed_files_match = (isinstance(verification, dict) and verification.get("matches") is True
                                    and verification.get("identity") == bundle_identity(bundle))
        except (OSError, ValueError):
            observed_files_match = False
        live = next((item for item in self.manager.store.list_deployments() if plan_identity is not None
            and observed_files_match
            and item.bundle_id == bundle.id
            and item.status.value == "running" and item.health and item.health.healthy
            and item.loaded_model_identity == plan_identity), None)
        if live:
            usage = live.resource_usage
            if live.router_preset_id is not None:
                # Routed deployments own the shared parent process. Its RSS
                # does not measure this model's unrecorded native child.
                usage = ResourceUsage(available=False,
                    reason="Model process RAM is unavailable; the recorded process usage belongs to the shared router.")
            result.observed_runtime = {"deployment_id": live.id, "observed_at": live.updated_at,
                "plan_identity": plan_identity, "kind": "observed",
                "startup": live.applied_startup, "resource_usage": usage.model_dump(mode="json") if usage else None}

    def _estimate_repository_files(self, request, bags, result):
        listing = self._repository_listing(request)
        variant, projector = self._selected_repository_variant(listing, request, result)
        fields = self._remote_weight_fields(listing, variant, request, result)
        projector_fields = self._remote_projector_fields(listing, projector, request, result)
        draft_fields = self._apply_remote_draft_weights(listing, bags, request, result, fields)
        return fields, projector_fields, draft_fields

    def _repository_listing(self, request):
        repository_key = f"{request.repo_id}@{request.revision}"
        with self._lock:
            listing = self._repositories.get(repository_key) if re.fullmatch(r"[a-fA-F0-9]{40}", request.revision) else None
        if listing is None or request.refresh:
            listing = self.manager.bundles.hf.inspect(repo_id=request.repo_id, revision=request.revision)
            with self._lock:
                self._repositories[f"{listing.repo_id}@{listing.resolved_revision}"] = listing
                while len(self._repositories) > 32:
                    self._repositories.popitem(last=False)
        return listing

    def _selected_repository_variant(self, listing, request, result):
        variant = next((item for item in listing.variants if set(item.files) == set(request.primary_files) and item.complete), None)
        projector = next((item for item in listing.projectors if set(item.files) == set(request.projector_files) and item.complete), None)
        if not variant or (request.projector_files and projector is None):
            raise ManagerError("Choose one complete model and at most one complete projector.", code="estimate_selection", status_code=400)
        result.source_identity = f"{listing.repo_id}@{listing.resolved_revision}:{','.join(variant.files)}"
        result.model_disk_bytes = variant.size_bytes
        result.projector_disk_bytes = projector.size_bytes if projector else 0
        return variant, projector

    def _remote_weight_fields(self, listing, variant, request, result):
        fields = GgufFields()
        try:
            fields, weights = self._remote_directories(listing.repo_id, listing.resolved_revision, variant.files, request.refresh)
            result.weights_bytes = weights
        except (ValueError, OSError, httpx.HTTPError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) else "Bounded remote GGUF metadata is unavailable."
            result.unknown_reasons.append(reason)
            with self._lock:
                self._metadata_failures[result.source_identity] = reason
                while len(self._metadata_failures) > 32:
                    self._metadata_failures.popitem(last=False)
        return fields

    def _remote_projector_fields(self, listing, projector, request, result):
        projector_fields = None
        if projector:
            try:
                projector_fields, result.projector_bytes = self._remote_directories(listing.repo_id,
                    listing.resolved_revision, projector.files, request.refresh)
            except (ValueError, OSError, httpx.HTTPError) as exc:
                result.unknown_reasons.append("Bounded projector metadata is unavailable.")
            result.unknown_reasons.append("Vision runtime/compute allocation is unknown before loading.")
            return projector_fields
        result.projector_bytes = 0
        return None

    def _apply_remote_draft_weights(self, listing, bags, request, result, fields):
        verified, draft_by_name = self._verified_mtp_files(listing, request.refresh)
        result.mtp_draft_files = verified
        selected_draft = str(bags.startup.applied.get("spec_draft_model") or "")
        draft_fields = None
        if selected_draft in draft_by_name:
            draft_fields = draft_by_name[selected_draft]
        result.weights_bytes = self._weight_bytes(fields, bags.startup.applied) if fields.tensors else result.weights_bytes
        if request.method == "native":
            result.unknown_reasons.append("Native checking is available after the selected model is installed.")
        return draft_fields

    @staticmethod
    def _local_directory(path: Path, *, refresh: bool = False):
        return read_gguf_directory(path, refresh=refresh)

    def _remote_directories(self, repo: str, revision: str, files: list[str], refresh: bool):
        key = f"{repo}@{revision}:{','.join(files)}"
        with self._lock:
            cached = self._metadata.get(key)
            failure = self._metadata_failures.get(key)
        if failure and not refresh:
            raise ValueError(failure)
        if cached and not refresh:
            return cached
        budget, requests = MAX_METADATA_BYTES, MAX_METADATA_REQUESTS
        deadline = time.monotonic() + METADATA_DEADLINE
        first_fields = GgufFields()
        weight_total: int | None = 0
        token = get_token()
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(5, connect=3)) as client:
            for index, file in enumerate(files):
                payload = bytearray()
                while True:
                    if budget <= 0 or requests <= 0 or time.monotonic() >= deadline:
                        raise ValueError("GGUF metadata exceeded the bounded inspection budget.")
                    size = min(1024 * 1024, budget)
                    start, end = len(payload), len(payload) + size - 1
                    url = hf_hub_url(repo_id=repo, filename=file, revision=revision)
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ValueError("GGUF metadata exceeded the bounded inspection budget.")
                    timeout = httpx.Timeout(remaining, connect=min(3.0, remaining), read=min(5.0, remaining))
                    with client.stream("GET", url, headers={**headers, "Range": f"bytes={start}-{end}"}, timeout=timeout) as response:
                        content_range = response.headers.get("content-range", "")
                        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range)
                        if response.status_code != 206 or not match or int(match[1]) != start or int(match[2]) > end:
                            raise ValueError("The repository did not support bounded GGUF metadata ranges.")
                        received = 0
                        for chunk in response.iter_bytes(chunk_size=65536):
                            if time.monotonic() >= deadline or received + len(chunk) > size:
                                raise ValueError("GGUF metadata exceeded the bounded inspection budget.")
                            payload.extend(chunk)
                            received += len(chunk)
                        if received != int(match[2]) - start + 1:
                            raise ValueError("The GGUF metadata range was incomplete.")
                        budget -= received
                        requests -= 1
                    try:
                        fields, weights = parse_gguf_directory(bytes(payload))
                        if index == 0:
                            first_fields = fields
                        else:
                            first_fields.tensors += fields.tensors
                        weight_total = weight_total + weights if weight_total is not None and weights is not None else None
                        break
                    except IncompleteMetadata:
                        if int(match[2]) + 1 >= int(match[3]):
                            raise ValueError("The GGUF directory is incomplete.") from None
        result = first_fields, weight_total
        with self._lock:
            self._metadata[key] = result
            self._metadata_failures.pop(key, None)
            while len(self._metadata) > 32:
                self._metadata.popitem(last=False)
        return result

    @staticmethod
    def _spec_modes(applied):
        raw = applied.get("spec_type", "none")
        return set(raw if isinstance(raw, list) else str(raw).split(","))

    @staticmethod
    def _builtin_mtp(fields) -> bool:
        return any(getattr(tensor, "name", "").endswith(".nextn.eh_proj.weight") for tensor in getattr(fields, "tensors", ()))

    @staticmethod
    def _has_nextn_tensor(fields) -> bool:
        return any(".nextn." in getattr(tensor, "name", "") for tensor in getattr(fields, "tensors", ()))

    @staticmethod
    def _is_mtp_candidate(name: str) -> bool:
        path = PurePosixPath(name)
        return bool(path.name) and (bool(path.parts) and path.parts[0].casefold() == "mtp" or path.name.casefold().startswith("mtp-"))

    @staticmethod
    def _advertised_modalities(fields) -> list[str]:
        names = [str(key).casefold() for key in fields]
        found: list[str] = []
        if any(key.startswith("clip.") or ".vision" in key or key.startswith("vision.") for key in names):
            found.append("image")
        if any(".video" in key or key.startswith("video.") for key in names):
            found.append("video")
        architecture = str(fields.get("general.architecture") or "").casefold()
        if architecture == "whisper" or any(key.startswith("audio.") or ".audio" in key for key in names):
            found.append("audio")
        return found

    def _verified_mtp_files(self, listing, refresh: bool) -> tuple[list[str], dict[str, Any]]:
        """Range-read MTP-named auxiliaries and keep those whose header has a NextN tensor."""
        verified: list[str] = []
        fields_by_name: dict[str, Any] = {}
        for item in getattr(listing, "auxiliary_ggufs", ()) or ():
            names = list(getattr(item, "files", ()) or ())
            if not names or not getattr(item, "complete", True) or not any(self._is_mtp_candidate(name) for name in names):
                continue
            try:
                draft_fields, _ = self._remote_directories(listing.repo_id, listing.resolved_revision, names, refresh)
            except (ValueError, OSError, httpx.HTTPError):
                continue
            if not self._has_nextn_tensor(draft_fields):
                continue
            for name in names:
                verified.append(name)
                fields_by_name[name] = draft_fields
        return verified, fields_by_name

    @staticmethod
    def _nextn_trunk(fields) -> int | None:
        architecture = fields.get("general.architecture")
        layers = _positive(fields.get(f"{architecture}.block_count"))
        nextn = _positive(fields.get(f"{architecture}.nextn_predict_layers", 0), zero=True)
        if not layers or nextn is None or nextn > layers:
            return None
        return layers - nextn

    @staticmethod
    def _embedded_nextn(name: str, trunk: int | None) -> bool:
        if ".nextn." in name:
            return True
        match = re.match(r"^blk\.(\d+)\.", name)
        return trunk is not None and match is not None and int(match[1]) >= trunk

    @staticmethod
    def _selected_tensors(fields, applied, *, keep_embedded_mtp: bool | None = None):
        tensors = getattr(fields, "tensors", ())
        if keep_embedded_mtp is None:
            keep_embedded_mtp = ("draft-mtp" in MemoryEstimator._spec_modes(applied)
                                 and not applied.get("spec_draft_model"))
        if keep_embedded_mtp:
            return tensors
        trunk = MemoryEstimator._nextn_trunk(fields)
        return tuple(tensor for tensor in tensors if not MemoryEstimator._embedded_nextn(tensor.name, trunk))

    @staticmethod
    def _weight_bytes(fields, applied, *, keep_embedded_mtp: bool | None = None):
        tensors = MemoryEstimator._selected_tensors(fields, applied, keep_embedded_mtp=keep_embedded_mtp)
        return sum(tensor.n_bytes for tensor in tensors) if tensors and all(tensor.n_bytes is not None for tensor in tensors) else None

    @staticmethod
    def _pool(fields, applied, result):
        parallel = applied.get("parallel", -1)
        automatic = parallel is None or parallel == -1
        parallel = 4 if automatic else max(1, parallel)
        unified = True if automatic else applied.get("kv_unified", False)
        context = applied.get("ctx_size")
        cap = applied.get("kv_unified_per_slot", 0)
        if not context:
            context = parallel * cap if cap else result.context_maximum
            if context:
                result.assumptions.append("Automatic context preview precedes native memory fitting and may differ when loaded.")
        if context:
            context = math.ceil(context / 256) * 256
            per_slot = context if unified else math.ceil((context // parallel) / 256) * 256
            context = per_slot if unified else per_slot * parallel
            result.effective_context = context
            result.effective_context_per_slot = min(per_slot, result.context_maximum or per_slot, cap or per_slot)
            result.evaluated_startup.update(ctx_size=context)
        result.effective_parallel, result.kv_unified = parallel, unified
        result.evaluated_startup.update(parallel=parallel, kv_unified=unified)
        if unified and parallel > 1:
            result.assumptions.append("Simultaneous requests share the total context pool; each slot's maximum is not a separate reservation.")
        return context, parallel

    def _metadata_prediction(self, fields, applied, result, *, projector_fields=None, draft_fields=None):
        if not result.gpu_budget_bytes:
            self._set_budgets(result)
        if result.projector_disk_bytes == 0 and result.projector_bytes is None:
            result.projector_bytes = 0
        architecture = fields.get("general.architecture")
        result.architecture = architecture if isinstance(architecture, str) else None
        maximum = fields.get(f"{architecture}.context_length")
        result.context_maximum = maximum if isinstance(maximum, int) and 0 < maximum < 2**32 else None
        context, parallel = self._pool(fields, applied, result)
        modes = self._spec_modes(applied)
        rollback = applied.get("spec_draft_n_max", 3) if modes & {"draft-mtp", "draft-eagle3", "draft-dflash", "draft-dspark"} else 0
        projection = self._apply_selected_cache(fields, applied, result, context, parallel, rollback)
        speculative = self._include_mtp_or_draft(fields, applied, result, context, parallel, modes, draft_fields)
        self._metadata_placement(fields, applied, projection, speculative, result,
                                 projector_fields=projector_fields, draft_fields=draft_fields)

    def _apply_selected_cache(self, fields, applied, result, context, parallel, rollback):
        projection = cache_projection(fields, context, applied.get("cache_type_k", "f16"), applied.get("cache_type_v", "f16"),
            parallel=parallel, rollback=rollback, flash_attention=applied.get("flash_attn", "auto"))
        result.attention_cache_bytes = sum(projection.attention.values()) if projection.attention_known else None
        result.recurrent_state_bytes = sum(projection.recurrent.values()) if projection.recurrent_known else None
        result.kv_bytes = projection.total
        result.unknown_reasons.extend(projection.unknown)
        result.unknown_reasons.append("Runtime/compute overhead is unknown until a matching native prediction or load.")
        result.assumptions.append("Metadata totals are known weight/cache components; native buffers, compute, driver and host-cache overhead remain excluded.")
        if result.recurrent_state_bytes:
            result.assumptions.append("Recurrent state uses native f32 tensors per simultaneous request and speculative rollback snapshot, independent of K/V precision.")
        return projection

    def _include_mtp_or_draft(self, fields, applied, result, context, parallel, modes, draft_fields):
        speculative = CacheProjection()
        draft_weights = 0
        if "draft-mtp" in modes and not applied.get("spec_draft_model"):
            speculative = cache_projection(fields, context, applied.get("spec_draft_cache_type_k", "f16"),
                applied.get("spec_draft_cache_type_v", "f16"), parallel=parallel, mtp=True,
                flash_attention=applied.get("flash_attn", "auto"))
            result.speculation_bytes = speculative.total
            result.assumptions.append("MTP shares the loaded target weights; its dense cache is additional and shared weights are counted once.")
        elif modes - {"none"}:
            if draft_fields is None:
                speculative.attention_known = speculative.recurrent_known = False
                result.speculation_bytes = None
                result.unknown_reasons.append("The selected speculative allocation is unavailable; target components remain known.")
            else:
                draft_weights = self._weight_bytes(draft_fields, applied, keep_embedded_mtp=True)
                if modes & {"draft-eagle3", "draft-dflash", "draft-dspark"}:
                    speculative.attention_known = speculative.recurrent_known = False
                    speculative.unknown.append("Specialist draft cache geometry is unavailable; its weight bytes remain known.")
                else:
                    speculative = cache_projection(draft_fields, context, applied.get("spec_draft_cache_type_k", "f16"),
                        applied.get("spec_draft_cache_type_v", "f16"), parallel=parallel, mtp="draft-mtp" in modes,
                        flash_attention=applied.get("flash_attn", "auto"))
                result.speculation_bytes = draft_weights + speculative.total if draft_weights is not None and speculative.total is not None else None
        else:
            result.speculation_bytes = 0
        result.unknown_reasons.extend(speculative.unknown)
        if speculative.total is not None and result.kv_bytes is not None:
            result.kv_bytes += speculative.total
        elif speculative.total is None:
            result.kv_bytes = None
        if draft_weights is None:
            result.weights_bytes = None
        elif draft_weights and result.weights_bytes is not None:
            result.weights_bytes += draft_weights
        return speculative

    def _metadata_placement(self, fields, applied, projection, speculative, result, *, projector_fields, draft_fields):
        rows, single_gpu, total_layers, requested, offload, placement_known = self._device_placement(fields, applied, result)
        tensors = self._place_target_weights(rows, fields, applied, result, count=offload, layers=total_layers, requested=requested,
            placement_known=placement_known, single_gpu=single_gpu)
        self._place_target_caches(rows, projection, count=offload, layers=total_layers, applied=applied,
            placement_known=placement_known, single_gpu=single_gpu)
        if draft_fields is None:
            self._place_speculative_attention(rows, speculative, count=offload, layers=total_layers, applied=applied,
                placement_known=placement_known, single_gpu=single_gpu)
        if draft_fields is not None:
            self._place_separate_draft(rows, draft_fields, applied, speculative, result,
                placement_known=placement_known, single_gpu=single_gpu)
        self._place_projector(rows, result, applied, single_gpu)
        self._finalize_device_rows(rows, result, speculative, placement_known)
        self._assign_gpu_ram(rows, result, placement_known=placement_known, tensors=tensors, requested=requested, applied=applied)
        if not tensors and type(requested) is int and requested > 0:
            result.unknown_reasons.append("Explicit layer placement requires the model's tensor names; weight placement is unavailable.")
        self._context_upper_bound(fields, applied, projection, result, rows, single_gpu, requested, tensors)

    def _device_placement(self, fields, applied, result):
        rows = {"Host": {"id": "Host", "name": "RAM", "weights_bytes": 0, "attention_cache_bytes": 0,
                         "recurrent_state_bytes": 0, "projector_bytes": 0, "speculation_bytes": 0}}
        devices = result.hardware.gpu_devices
        single_gpu = devices[0] if len(devices) == 1 else None
        if single_gpu:
            rows[single_gpu.id] = {**rows["Host"], "id": single_gpu.id, "name": single_gpu.name}
        total_layers = _positive(fields.get(f"{fields.get('general.architecture')}.block_count"))
        requested = applied.get("n_gpu_layers", "auto")
        auto = requested in {None, -1, "auto"}
        offload = total_layers + 1 if total_layers and (auto or requested == "all") else requested
        placement_known = type(offload) is int and total_layers is not None and (offload == 0 or single_gpu is not None)
        if auto:
            result.assumptions.append("Automatic placement preview assumes all eligible layers on one GPU; native fitting may place some in RAM.")
        if not placement_known:
            result.unknown_reasons.append("Device placement is unavailable or uses multiple GPUs; their budgets are not pooled.")
        return rows, single_gpu, total_layers, requested, offload, placement_known

    def _layer_device(self, layer, *, count, layers, applied, placement_known, single_gpu, cache=False):
        if cache and not applied.get("kv_offload", True) or count == 0:
            return "Host"
        if not placement_known or type(count) is not int or layers is None:
            return None
        return single_gpu.id if layer >= max(layers + 1 - count, 0) and count > 0 else "Host"

    def _place_weight_tensor(self, rows, tensor, *, count, layers, applied, placement_known, single_gpu):
        if tensor.n_bytes is None:
            return
        match = re.match(r"^blk\.(\d+)\.", tensor.name)
        target = (self._layer_device(int(match[1]), count=count, layers=layers, applied=applied, placement_known=placement_known, single_gpu=single_gpu) if match
            else self._layer_device(layers, count=count, layers=layers, applied=applied, placement_known=placement_known, single_gpu=single_gpu) if layers is not None and tensor.name.startswith(("output.", "output_norm."))
            else "Host")
        if target is not None:
            rows[target]["weights_bytes"] += tensor.n_bytes

    def _place_target_weights(self, rows, fields, applied, result, *, count, layers, requested, placement_known, single_gpu):
        tensors = self._selected_tensors(fields, applied)
        for tensor in tensors:
            self._place_weight_tensor(rows, tensor, count=count, layers=layers, applied=applied,
                placement_known=placement_known, single_gpu=single_gpu)
        if not tensors and result.weights_bytes is not None and requested == 0:
            rows["Host"]["weights_bytes"] = result.weights_bytes
        return tensors

    def _place_target_caches(self, rows, projection, *, count, layers, applied, placement_known, single_gpu):
        for kind, allocations in (("attention_cache_bytes", projection.attention), ("recurrent_state_bytes", projection.recurrent)):
            for layer, size in allocations.items():
                target = self._layer_device(layer, count=count, layers=layers, cache=True, applied=applied,
                    placement_known=placement_known, single_gpu=single_gpu)
                if target is not None:
                    rows[target][kind] += size

    def _place_speculative_attention(self, rows, speculative, *, count, layers, applied, placement_known, single_gpu):
        for layer, size in speculative.attention.items():
            target = self._layer_device(layer, count=count, layers=layers, cache=True, applied=applied,
                placement_known=placement_known, single_gpu=single_gpu)
            if target is not None:
                rows[target]["attention_cache_bytes"] += size
                rows[target]["speculation_bytes"] += size

    def _place_separate_draft(self, rows, draft_fields, applied, speculative, result, *, placement_known, single_gpu):
        draft_layers = _positive(draft_fields.get(f"{draft_fields.get('general.architecture')}.block_count"))
        draft_count = applied.get("spec_draft_ngl", "auto")
        if draft_count in {None, -1, "auto", "all"}:
            draft_count = draft_layers + 1 if draft_layers else None
        for tensor in self._selected_tensors(draft_fields, applied, keep_embedded_mtp=True):
            self._place_weight_tensor(rows, tensor, count=draft_count, layers=draft_layers, applied=applied,
                placement_known=placement_known, single_gpu=single_gpu)
        self._place_speculative_attention(rows, speculative, count=draft_count, layers=draft_layers, applied=applied,
            placement_known=placement_known, single_gpu=single_gpu)
        for layer, size in speculative.recurrent.items():
            target = self._layer_device(layer, count=draft_count, layers=draft_layers, cache=True, applied=applied,
                placement_known=placement_known, single_gpu=single_gpu)
            if target is not None:
                rows[target]["recurrent_state_bytes"] += size
        result.unknown_reasons.append("Separate draft placement/compute is approximate and may differ after native fitting.")

    def _place_projector(self, rows, result, applied, single_gpu):
        if result.projector_bytes is not None and (not applied.get("mmproj_use_gpu", True) or single_gpu or result.projector_bytes == 0):
            target = single_gpu.id if applied.get("mmproj_use_gpu", True) and single_gpu else "Host"
            rows[target]["projector_bytes"] = result.projector_bytes
            if result.projector_bytes:
                result.assumptions.append("Projector tensor bytes are a component estimate; native vision buffers/compute remain unknown.")

    def _finalize_device_rows(self, rows, result, speculative, placement_known):
        for row in rows.values():
            row["kv_bytes"] = row["attention_cache_bytes"] + row["recurrent_state_bytes"]
            row["runtime_overhead_bytes"] = row["total_bytes"] = None
            row["known_total_bytes"] = row["weights_bytes"] + row["kv_bytes"] + row["projector_bytes"]
            row["lower_bound"] = True
            row["known_weights_bytes"] = row["weights_bytes"]
            row["known_attention_cache_bytes"] = row["attention_cache_bytes"]
            row["known_recurrent_state_bytes"] = row["recurrent_state_bytes"]
            if result.weights_bytes is None or not placement_known:
                row["weights_bytes"] = None
            if result.attention_cache_bytes is None or not speculative.attention_known or not placement_known:
                row["attention_cache_bytes"] = None
            if result.recurrent_state_bytes is None or not speculative.recurrent_known or not placement_known:
                row["recurrent_state_bytes"] = None
            if result.kv_bytes is None or not placement_known:
                row["kv_bytes"] = None
            if result.projector_bytes is None:
                row["projector_bytes"] = None

    def _assign_gpu_ram(self, rows, result, *, placement_known, tensors, requested, applied):
        result.devices = list(rows.values())
        selected_components_known = (result.weights_bytes is not None and result.kv_bytes is not None
                                     and result.projector_bytes is not None and result.speculation_bytes is not None)
        if placement_known and selected_components_known:
            result.gpu_bytes = sum(row["known_total_bytes"] for row in result.devices if row["id"] != "Host")
            result.ram_bytes = rows["Host"]["known_total_bytes"]
            if not tensors and requested != 0:
                result.gpu_bytes = None
                result.ram_bytes = rows["Host"]["kv_bytes"] if not applied.get("kv_offload", True) else None

    def _context_upper_bound(self, fields, applied, projection, result, rows, single_gpu, requested, tensors):
        if (single_gpu and not result.hardware.stale and requested in {None, -1, "auto", "all"}
                and result.weights_bytes is not None and result.projector_disk_bytes == 0
                and result.speculation_bytes == 0 and applied.get("kv_offload", True)
                and projection.total is not None):
            available = result.gpu_budget_bytes.get(single_gpu.id)
            one_token = cache_projection(fields, 1, applied.get("cache_type_k", "f16"), applied.get("cache_type_v", "f16"),
                parallel=result.effective_parallel, flash_attention=applied.get("flash_attn", "auto"))
            rate = sum(one_token.attention.values()) if one_token.attention_known else None
            if available is not None and rate:
                gpu_row = rows[single_gpu.id]
                weights = gpu_row["known_weights_bytes"] if tensors else result.weights_bytes
                state = gpu_row["known_recurrent_state_bytes"]
                marker = max(0, (available - weights - state) // rate)
                result.context_marker = min(marker, result.context_maximum) if result.context_maximum else marker
                result.context_marker_kind = "upper_bound"
                result.assumptions.append("Context marker assumes all eligible layers on this GPU and excludes unknown overhead; it does not verify a fit.")

    def _native_prediction(self, bundle, request, result):
        manifest, executable, bags, selected, projector, identities = self._prepare_native_planner(bundle, request)
        key = json.dumps([manifest.executable, manifest.sha256, manifest.memory_planner_sha256,
                          manifest.memory_planner_native_fingerprint, identities, selected], sort_keys=True)
        with self._lock:
            cached = self._native.get(key)
        if cached and not request.refresh and time.monotonic() - cached[0] < 30:
            prediction = cached[1]
        else:
            if not self._worker.acquire(timeout=0.1):
                raise ValueError("Native memory prediction is busy; retry shortly.")
            try:
                if not bundle.primary_path:
                    raise ValueError("The model's primary GGUF is unavailable; its allocation is unknown.")
                arguments = [str(executable), "-m", bundle.primary_path, *startup_cli_args(selected)]
                if projector:
                    arguments.extend(["--mmproj", projector.path])
                prediction = self._validate_native(json.loads(_bounded_native(arguments)), manifest)
                prediction["evaluated_startup"] = {**selected, **prediction["evaluated_startup"]}
                prediction["estimated_at"] = utc_now()
                with self._lock:
                    self._native[key] = time.monotonic(), prediction
                    while len(self._native) > 32:
                        self._native.popitem(last=False)
            finally:
                self._worker.release()
        self._apply_native_prediction(result, prediction, manifest, bundle, bags, selected)

    def _prepare_native_planner(self, bundle, request):
        manifest = self.manager.runtime.current()
        executable = require_planner(manifest)
        bags = resolve_bags(startup=request.startup)
        selected = loading_startup_settings(bags)
        # Operational endpoints and aliases cannot affect allocation. They are
        # neither needed nor passed to the subprocess's real server parser.
        for key in ("host", "port", "alias"):
            selected.pop(key, None)
        identities = []
        projector = mmproj_companion(bundle)
        selected_artifacts = [file for file in bundle.files if file.name.lower().endswith(".gguf")
                              and file.role.value in {"primary_weights", "shard"}]
        if projector:
            selected_artifacts.append(projector)
        for file in {item.path: item for item in selected_artifacts}.values():
            stat = Path(file.path).stat()
            if stat.st_size != file.size_bytes:
                raise ValueError("Model files changed; verify them in Models before predicting memory.")
            identities.append((file.path, file.size_bytes, file.sha256, stat.st_mtime_ns))
        draft = selected.get("spec_draft_model")
        if draft:
            from workbench_backend.inference.hashes import _cache_key
            path = Path(draft)
            if not path.is_file():
                raise ValueError("The selected draft model is unavailable; its allocation is unknown.")
            stat = path.stat()
            identities.append(_cache_key(path))
        return manifest, executable, bags, selected, projector, identities

    @staticmethod
    def _apply_native_prediction(result, prediction, manifest, bundle, bags, selected):
        result.source = "native_prediction"
        result.estimated_at = prediction["estimated_at"]
        result.evaluated_startup = prediction["evaluated_startup"]
        result.devices = prediction["devices"]
        result.completeness = prediction["completeness"]
        for key in ("effective_context", "effective_context_per_slot", "effective_parallel", "kv_unified", "context_maximum"):
            setattr(result, key, prediction[key])
        result.plan_identity = loaded_model_identity(manifest, bundle, bags, hash_external=False)
        result.weights_bytes = sum(row["weights_bytes"] for row in result.devices)
        result.kv_bytes = sum(row["kv_bytes"] for row in result.devices)
        result.runtime_overhead_bytes = sum(row["runtime_overhead_bytes"] for row in result.devices)
        projector_measured = prediction["components"]["projector"] != "unavailable"
        speculation_measured = prediction["components"]["speculation"] != "unavailable"
        result.projector_bytes = sum(row["projector_bytes"] for row in result.devices) if projector_measured else None
        result.speculation_bytes = sum(row["speculation_bytes"] for row in result.devices) if speculation_measured else None
        # Failed speculation must not erase measured target components. Native
        # total_bytes remains unknown while the target's rows stay inspectable.
        if result.completeness == "complete":
            result.gpu_bytes = sum(row["total_bytes"] for row in result.devices if row["id"] != "Host")
            result.ram_bytes = sum(row["total_bytes"] for row in result.devices if row["id"] == "Host")
        else:
            result.gpu_bytes = result.ram_bytes = None
        result.unknown_reasons.extend(prediction["unknown_reasons"])
        result.assumptions.append("Estimated with the exact pinned native no-allocation APIs; actual loaded allocation remains authoritative.")
        result.assumptions.append("Native context memory includes KV cache and architecture-specific state; compute excludes unknown driver overhead.")
        result.unknown_reasons.append("Dynamic driver, operating-system, host output-buffer and prompt-cache memory is not included in the native allocation estimate.")
        if result.kv_unified and result.effective_parallel > 1:
            result.assumptions.append("Simultaneous requests share the total context pool; the per-chat maximum is not reserved for every slot.")
        if result.evaluated_startup != selected:
            result.assumptions.append("Automatic placement/context were evaluated hypothetically; your requested settings remain unchanged.")
            if "ctx_size" not in selected and result.completeness == "complete":
                result.context_marker = result.effective_context_per_slot
                result.context_marker_kind = "native_prediction"

    @staticmethod
    def _validate_native(payload, manifest):
        MemoryEstimator._validate_native_protocol(payload, manifest)
        rows = MemoryEstimator._validate_native_host_row(payload)
        components = MemoryEstimator._validate_native_component_status(payload)
        MemoryEstimator._validate_native_device_rows(rows, components)
        for key in ("effective_context", "effective_context_per_slot", "effective_parallel", "context_maximum"):
            if type(payload.get(key)) is not int or not 0 < payload[key] < 2**32:
                raise ValueError("The native context capacity is invalid.")
        if type(payload.get("kv_unified")) is not bool:
            raise ValueError("The native context policy is invalid.")
        if payload["effective_context_per_slot"] > min(payload["effective_context"], payload["context_maximum"]):
            raise ValueError("The native per-chat capacity exceeds the available context pool.")
        if payload["completeness"] == "complete" and "unavailable" in components.values():
            raise ValueError("The native allocation result incorrectly marks unknown memory as complete.")
        if not isinstance(payload.get("unknown_reasons"), list) or any(not isinstance(reason, str) for reason in payload["unknown_reasons"]):
            raise ValueError("The native allocation diagnostics are invalid.")
        return payload

    @staticmethod
    def _validate_native_protocol(payload, manifest):
        if (not isinstance(payload, dict) or payload.get("protocol") != PROTOCOL
                or payload.get("native_build") != 11045 or payload.get("native_commit") != COMMIT
                or payload.get("native_fingerprint") != manifest.memory_planner_native_fingerprint
                or payload.get("completeness") not in {"complete", "partial"}):
            raise ValueError("The native allocation result does not match the selected runtime.")

    @staticmethod
    def _validate_native_host_row(payload):
        rows = payload.get("devices")
        if not isinstance(rows, list) or not rows or not any(row.get("id") == "Host" for row in rows if isinstance(row, dict)):
            raise ValueError("The native allocation result contains no usable device breakdown.")
        return rows

    @staticmethod
    def _validate_native_component_status(payload):
        components = payload.get("components")
        if (not isinstance(payload.get("evaluated_startup"), dict) or not isinstance(components, dict)
                or components.get("target") != "measured" or any(components.get(key) not in
                    {"measured", "not_selected", "unavailable"} for key in ("projector", "speculation"))):
            raise ValueError("The native component allocation status is invalid.")
        return components

    @staticmethod
    def _validate_native_device_rows(rows, components):
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                raise ValueError("The native allocation device breakdown is invalid.")
            for key in ("weights_bytes", "kv_bytes", "runtime_overhead_bytes", "projector_bytes", "speculation_bytes", "total_bytes"):
                unknown = ((key == "projector_bytes" and components["projector"] == "unavailable") or
                           (key == "speculation_bytes" and components["speculation"] == "unavailable") or
                           (key == "total_bytes" and "unavailable" in components.values()))
                if unknown and row.get(key) is None:
                    continue
                if unknown:
                    raise ValueError("The native allocation result incorrectly assigns a number to unknown memory.")
                if type(row.get(key)) is not int or not 0 <= row[key] < 2**63:
                    raise ValueError("The native allocation device breakdown is invalid.")
            if row["total_bytes"] is not None and row["total_bytes"] != sum(row[key] for key in ("weights_bytes", "kv_bytes", "runtime_overhead_bytes", "projector_bytes")):
                raise ValueError("The native allocation totals are inconsistent.")
