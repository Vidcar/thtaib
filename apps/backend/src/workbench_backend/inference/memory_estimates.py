"""Advisory memory predictions at the existing inference boundary.

Remote inspection reads bounded prefixes to inspect a GGUF directory. A small
file may include initial tensor bytes; transfers are capped regardless of size.
Installed predictions delegate allocation planning to the pinned native helper.
Neither path starts a deployment, rewrites settings or establishes residency.
"""
from __future__ import annotations

from collections import OrderedDict
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import sys
import threading
import time
from typing import Any

import httpx
from gguf.constants import GGMLQuantizationType, GGML_QUANT_SIZES
from huggingface_hub import get_token, hf_hub_url

from workbench_backend.errors import ManagerError
from workbench_backend.inference.bundles import mmproj_companion
from workbench_backend.inference.configurations import loading_startup_settings, loaded_model_identity
from workbench_backend.inference.hardware import HardwareObserver
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.native_memory import COMMIT, PROTOCOL, preview_environment, require_planner
from workbench_backend.inference.schemas import ModelEstimateRequest, ModelMemoryEstimate
from workbench_backend.inference.settings import resolve_bags, startup_cli_args

MAX_METADATA_BYTES = 16 * 1024 * 1024
MAX_METADATA_REQUESTS = 16
METADATA_DEADLINE = 15.0
NATIVE_DEADLINE = 15.0
MAX_NATIVE_OUTPUT = 256 * 1024
DENSE_ARCHITECTURES = frozenset({"llama", "qwen2", "qwen3"})


class IncompleteMetadata(ValueError):
    pass


def parse_gguf_directory(payload: bytes) -> tuple[dict[str, Any], int | None]:
    """Bounded structural inspection; use gguf's quant block sizes, not guessed bits."""
    offset = 0
    endian = "<"

    def take(size: int) -> bytes:
        nonlocal offset
        if size < 0 or size > MAX_METADATA_BYTES or offset + size > MAX_METADATA_BYTES:
            raise ValueError("GGUF metadata exceeds the inspection budget")
        if offset + size > len(payload):
            raise IncompleteMetadata("More GGUF metadata is required")
        result = payload[offset:offset + size]
        offset += size
        return result

    def number(fmt: str):
        return struct.unpack(endian + fmt, take(struct.calcsize(fmt)))[0]

    def string(*, keep: bool = True):
        size = number("Q")
        raw = take(size)
        return raw.decode("utf-8") if keep else None

    def value(kind: int, *, keep: bool = True):
        formats = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i", 6: "f", 7: "?", 10: "Q", 11: "q", 12: "d"}
        if kind in formats:
            result = number(formats[kind])
            return result if keep else None
        if kind == 8:
            return string(keep=keep)
        if kind == 9:
            element, count = number("I"), number("Q")
            if count > MAX_METADATA_BYTES or element == 9:
                raise ValueError("Unsupported GGUF metadata array")
            if element in formats:
                take(struct.calcsize(formats[element]) * count)
            else:
                for _ in range(count):
                    value(element, keep=False)
            return None  # variable per-layer layouts remain explicitly unsupported
        raise ValueError("Unknown GGUF metadata type")

    if take(4) != b"GGUF":
        raise ValueError("Not a GGUF file")
    raw_version = take(4)
    version = struct.unpack("<I", raw_version)[0]
    if version not in {2, 3}:
        endian = ">"
        version = struct.unpack(">I", raw_version)[0]
    if version not in {2, 3}:
        raise ValueError("Unsupported GGUF version")
    tensor_count, field_count = number("Q"), number("Q")
    if tensor_count > 1000000 or field_count > 1000000:
        raise ValueError("Invalid GGUF directory count")
    fields: dict[str, Any] = {}
    for _ in range(field_count):
        name = string()
        if len(name) > 1024:
            raise ValueError("Invalid GGUF metadata key")
        kind = number("I")
        keep = not name.startswith("tokenizer.")
        entry = value(kind, keep=keep)
        if keep:
            fields[name] = entry
    total = 0
    known = True
    for _ in range(tensor_count):
        string(keep=False)
        dimensions = number("I")
        if not 1 <= dimensions <= 4:
            raise ValueError("Invalid GGUF tensor dimensions")
        shape = [number("Q") for _ in range(dimensions)]
        kind, _tensor_offset = number("I"), number("Q")
        try:
            block, size = GGML_QUANT_SIZES[GGMLQuantizationType(kind)]
            elements = math.prod(shape)
            if any(not 0 < item <= 2**40 for item in shape) or shape[0] % block:
                raise ValueError("Unsupported tensor block layout")
            total += elements // block * size
        except (ValueError, KeyError):
            known = False
    return fields, total if known else None


def dense_kv_bytes(fields: dict[str, Any], context: int, key_type: str, value_type: str) -> int | None:
    architecture = fields.get("general.architecture")
    if architecture not in DENSE_ARCHITECTURES or not 0 < context <= 2**32:
        return None
    prefix = f"{architecture}."
    for key, value in fields.items():
        if not ("sliding_window" in key or ".ssm." in key or "expert_count" in key
                or "nextn_predict" in key or "kv_lora" in key or "recurrent" in key):
            continue
        # Presence with unknown or array-valued metadata cannot prove a dense
        # per-layer cache. Only an explicit numeric zero/false disables it.
        if value is not False and not (type(value) in {int, float} and value == 0):
            return None
    def positive(key: str) -> int | None:
        result = fields.get(prefix + key)
        return result if isinstance(result, int) and not isinstance(result, bool) and 0 < result <= 2**20 else None
    layers, heads, kv_heads = positive("block_count"), positive("attention.head_count"), positive("attention.head_count_kv")
    embedding = positive("embedding_length")
    if not layers or not heads or not kv_heads or not embedding or embedding % heads:
        return None
    key_dim = positive("attention.key_length") or embedding // heads
    value_dim = positive("attention.value_length") or embedding // heads
    def row_size(width: int, precision: str) -> int:
        block, size = GGML_QUANT_SIZES[GGMLQuantizationType[precision.upper()]]
        if width % block:
            raise ValueError("Unsupported cache block layout")
        return width // block * size
    try:
        return layers * context * (row_size(kv_heads * key_dim, key_type) + row_size(kv_heads * value_dim, value_type))
    except (KeyError, ValueError):
        return None


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
        bags = resolve_bags(startup=request.startup)
        if bags.startup.unsupported:
            raise ManagerError("Check the selected launch settings.", code="estimate_settings", status_code=400)
        hardware = self.hardware.observe(refresh=request.refresh)
        identity = request.bundle_id or f"{request.repo_id}@{request.revision}:{','.join(request.primary_files)}"
        result = ModelMemoryEstimate(source_identity=identity, estimated_at=utc_now(), hardware=hardware,
            selected_startup=dict(request.startup), evaluated_startup=dict(request.startup))
        fields: dict[str, Any] = {}
        if request.bundle_id:
            bundle = self.manager.get_bundle(request.bundle_id)
            primaries = [item for item in bundle.files if item.name.lower().endswith(".gguf")
                and item.role.value in {"primary_weights", "shard"}]
            result.model_disk_bytes = sum(item.size_bytes for item in primaries)
            projector = mmproj_companion(bundle)
            result.projector_disk_bytes = projector.size_bytes if projector else 0
            try:
                fields, weights = self._local_directory(Path(bundle.primary_path or ""))
                result.weights_bytes = weights if len(primaries) == 1 else None
                result.architecture = fields.get("general.architecture")
                maximum = fields.get(f"{result.architecture}.context_length")
                result.context_maximum = maximum if isinstance(maximum, int) and 0 < maximum < 2**32 else None
            except (OSError, ValueError, ManagerError) as exc:
                result.unknown_reasons.append(str(exc) if not isinstance(exc, ManagerError) else exc.message)
            # A directory larger than our metadata budget does not disable the
            # trusted native predictor, which owns its own bounded inspection.
            try:
                self._native_prediction(bundle, request, result)
            except (OSError, ValueError, ManagerError) as exc:
                result.completeness = "unavailable"
                result.unknown_reasons.append(str(exc) if not isinstance(exc, ManagerError) else exc.message)
            # A different setup, slot policy or cache on the same weights is
            # not an observation of this candidate. Response choices are absent
            # from the canonical native residency identity.
            plan_identity = loaded_model_identity(self.manager.runtime.current(), bundle, bags)
            result.plan_identity = plan_identity
            live = next((item for item in self.manager.store.list_deployments() if item.bundle_id == bundle.id
                and item.status.value == "running" and item.health and item.health.healthy
                and item.loaded_model_identity == plan_identity), None)
            if live:
                result.observed_runtime = {"deployment_id": live.id, "observed_at": live.updated_at,
                    "plan_identity": plan_identity, "kind": "observed",
                    "startup": live.applied_startup, "resource_usage": live.resource_usage.model_dump(mode="json") if live.resource_usage else None}
        elif request.repo_id:
            repository_key = f"{request.repo_id}@{request.revision}"
            with self._lock:
                listing = self._repositories.get(repository_key) if re.fullmatch(r"[a-fA-F0-9]{40}", request.revision) else None
            if listing is None or request.refresh:
                listing = self.manager.bundles.hf.inspect(repo_id=request.repo_id, revision=request.revision)
                with self._lock:
                    self._repositories[f"{listing.repo_id}@{listing.resolved_revision}"] = listing
                    while len(self._repositories) > 32:
                        self._repositories.popitem(last=False)
            variant = next((item for item in listing.variants if set(item.files) == set(request.primary_files) and item.complete), None)
            projector = next((item for item in listing.projectors if set(item.files) == set(request.projector_files) and item.complete), None)
            if not variant or (request.projector_files and projector is None):
                raise ManagerError("Choose one complete model and at most one complete projector.", code="estimate_selection", status_code=400)
            result.source_identity = f"{listing.repo_id}@{listing.resolved_revision}:{','.join(variant.files)}"
            result.model_disk_bytes = variant.size_bytes
            result.projector_disk_bytes = projector.size_bytes if projector else 0
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
            if projector:
                result.unknown_reasons.append("Vision runtime/compute allocation is unknown before loading.")
        else:
            raise ManagerError("Choose an installed model or exact repository files.", code="estimate_selection", status_code=400)
        if result.source != "native_prediction":
            self._metadata_prediction(fields, bags.startup.applied, result)
        result.unknown_reasons.extend(hardware.reasons)
        return result

    @staticmethod
    def _local_directory(path: Path):
        with path.open("rb") as handle:
            return parse_gguf_directory(handle.read(MAX_METADATA_BYTES))

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
        first_fields: dict[str, Any] = {}
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

    def _metadata_prediction(self, fields, applied, result):
        architecture = fields.get("general.architecture")
        result.architecture = architecture if isinstance(architecture, str) else None
        maximum = fields.get(f"{architecture}.context_length")
        result.context_maximum = maximum if isinstance(maximum, int) and 0 < maximum < 2**32 else None
        context = applied.get("ctx_size")
        if context:
            result.kv_bytes = dense_kv_bytes(fields, context, applied.get("cache_type_k", "f16"), applied.get("cache_type_v", "f16"))
        if result.kv_bytes is None:
            result.unknown_reasons.append("Cache projection is unavailable for this architecture or automatic context.")
        result.unknown_reasons.append("Runtime/compute overhead is unknown until a matching native prediction or load.")
        result.assumptions.append("Dense cache projection excludes allocation padding and runtime overhead; file bytes are shown separately.")
        if applied.get("kv_offload", True) is False and result.kv_bytes is not None:
            result.ram_bytes = result.kv_bytes
            result.assumptions.append("KV cache is requested in RAM; weights may still use the GPU.")
        if applied.get("n_gpu_layers") == 0 and result.weights_bytes is not None:
            result.ram_bytes = result.weights_bytes + (result.kv_bytes or 0)
            result.gpu_bytes = 0  # known model/cache lower bound, not driver/compute allocation
            result.assumptions.append("Weight layers and their cache are on CPU; RAM total excludes unknown compute overhead.")
        if len(result.hardware.gpu_devices) > 1:
            result.unknown_reasons.append("Device budgets are separate; automatic multi-GPU placement is unknown.")
        layers = applied.get("n_gpu_layers")
        full_gpu_candidate = layers in {None, -1, "auto"}
        if isinstance(layers, int) and layers > 0:
            result.unknown_reasons.append("Explicit layer placement requires native tensor placement; GPU/RAM weight allocation is unknown.")
        if len(result.hardware.gpu_devices) == 1 and not result.hardware.stale and result.weights_bytes is not None:
            available = result.hardware.gpu_devices[0].available_bytes
            per_token = dense_kv_bytes(fields, 1, applied.get("cache_type_k", "f16"), applied.get("cache_type_v", "f16"))
            if available is not None and per_token and applied.get("kv_offload", True) and result.projector_disk_bytes == 0 and full_gpu_candidate:
                result.context_marker = max(0, (available - result.weights_bytes) // per_token)
                if result.context_maximum:
                    result.context_marker = min(result.context_marker, result.context_maximum)
                result.context_marker_kind = "upper_bound"
                result.assumptions.append("Context marker assumes all weights and cache on this GPU and excludes unknown overhead.")
                if result.kv_bytes is not None:
                    result.gpu_bytes = result.weights_bytes + result.kv_bytes

    def _native_prediction(self, bundle, request, result):
        manifest = self.manager.runtime.current()
        executable = require_planner(manifest)
        bags = resolve_bags(startup=request.startup)
        selected = loading_startup_settings(bags)
        # Operational endpoints and aliases cannot affect allocation. They are
        # neither needed nor passed to the subprocess's real server parser.
        for key in ("host", "port", "alias"):
            selected.pop(key, None)
        identities = []
        for file in bundle.files:
            if not file.name.lower().endswith(".gguf"):
                continue
            stat = Path(file.path).stat()
            if stat.st_size != file.size_bytes:
                raise ValueError("Model files changed; verify them in Models before predicting memory.")
            identities.append((file.path, file.size_bytes, file.sha256, stat.st_mtime_ns))
        draft = selected.get("spec_draft_model")
        if draft:
            from workbench_backend.inference.hashes import cached_sha256_file
            path = Path(draft)
            if not path.is_file():
                raise ValueError("The selected draft model is unavailable; its allocation is unknown.")
            stat = path.stat()
            identities.append((str(path), stat.st_size, cached_sha256_file(path), stat.st_mtime_ns))
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
                arguments = [str(executable), "-m", bundle.primary_path, *startup_cli_args(selected)]
                projector = mmproj_companion(bundle)
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
        result.source = "native_prediction"
        result.estimated_at = prediction["estimated_at"]
        result.evaluated_startup = prediction["evaluated_startup"]
        result.devices = prediction["devices"]
        result.completeness = prediction["completeness"]
        for key in ("effective_context", "effective_context_per_slot", "effective_parallel", "kv_unified", "context_maximum"):
            setattr(result, key, prediction[key])
        result.plan_identity = loaded_model_identity(manifest, bundle, bags)
        result.weights_bytes = sum(row["weights_bytes"] for row in result.devices)
        result.kv_bytes = sum(row["kv_bytes"] for row in result.devices)
        result.runtime_overhead_bytes = sum(row["runtime_overhead_bytes"] for row in result.devices)
        projector_measured = prediction["components"]["projector"] != "unavailable"
        speculation_measured = prediction["components"]["speculation"] != "unavailable"
        result.projector_bytes = sum(row["projector_bytes"] for row in result.devices) if projector_measured else None
        result.speculation_bytes = sum(row["speculation_bytes"] for row in result.devices) if speculation_measured else None
        if not speculation_measured:
            result.weights_bytes = result.kv_bytes = result.runtime_overhead_bytes = None
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
        if (not isinstance(payload, dict) or payload.get("protocol") != PROTOCOL
                or payload.get("native_build") != 11045 or payload.get("native_commit") != COMMIT
                or payload.get("native_fingerprint") != manifest.memory_planner_native_fingerprint
                or payload.get("completeness") not in {"complete", "partial"}):
            raise ValueError("The native allocation result does not match the selected runtime.")
        rows = payload.get("devices")
        if not isinstance(rows, list) or not rows or not any(row.get("id") == "Host" for row in rows if isinstance(row, dict)):
            raise ValueError("The native allocation result contains no usable device breakdown.")
        components = payload.get("components")
        if (not isinstance(payload.get("evaluated_startup"), dict) or not isinstance(components, dict)
                or components.get("target") != "measured" or any(components.get(key) not in
                    {"measured", "not_selected", "unavailable"} for key in ("projector", "speculation"))):
            raise ValueError("The native component allocation status is invalid.")
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
