"""Requested versus applied settings bags (MOD-003).

Known keys may be passed through. Unknown keys are unsupported. Values the
workbench accepts but has not UAT-verified remain unverified. This does not
close OQ-007.

Valued startup enums (Issue #21): ``flash_attn`` serializes as
``--flash-attn on|off|auto`` and ``load_mode`` as ``--load-mode MODE``.
Startup keys are valued except ``embedding: on``, which serialises the
llama-server bare flag ``--embedding`` (required for a dedicated embedder).
Never emit a bare ``--flash-attn``.

The pinned llama.cpp b11045 rejects ``--mlock`` and ``--no-mmap``
(``error: invalid argument``); upstream replaced both with ``--load-mode``.
The retired ``mlock`` / ``no_mmap`` keys are therefore reported as
unsupported with a migration note instead of being emitted or silently
dropped.
"""

from __future__ import annotations

import json
import math
from typing import Any

from workbench_backend.inference.schemas import SettingNote, SettingsBag, SettingsBags

STARTUP_KEYS: dict[str, str] = {
    "host": "--host",
    "port": "--port",
    "ctx_size": "--ctx-size",
    "n_gpu_layers": "--n-gpu-layers",
    "threads": "--threads",
    "threads_batch": "--threads-batch",
    "parallel": "--parallel",
    "kv_unified": "--kv-unified",
    "op_offload": "--op-offload",
    "mmproj_use_gpu": "--mmproj-offload",
    "batch_size": "--batch-size",
    "ubatch_size": "--ubatch-size",
    "flash_attn": "--flash-attn",
    "fit": "--fit",
    "cache_type_k": "--cache-type-k",
    "cache_type_v": "--cache-type-v",
    "kv_offload": "--kv-offload",
    "load_mode": "--load-mode",
    "alias": "--alias",
    "embedding": "--embedding",
    "pooling": "--pooling",
    "chat_template": "--chat-template",
    "chat_template_file": "--chat-template-file",
    "chat_template_kwargs": "--chat-template-kwargs",
    "reasoning": "--reasoning",
    "reasoning_format": "--reasoning-format",
    "reasoning_effort": "--reasoning-effort",
    "reasoning_budget": "--reasoning-budget",
    "reasoning_budget_message": "--reasoning-budget-message",
    "reasoning_preserve": "--reasoning-preserve",
    "spec_type": "--spec-type",
    "spec_draft_model": "--spec-draft-model",
    "spec_draft_n_max": "--spec-draft-n-max",
    "spec_draft_n_min": "--spec-draft-n-min",
    "spec_draft_p_split": "--spec-draft-p-split",
    "spec_draft_p_min": "--spec-draft-p-min",
    "spec_draft_threads": "--spec-draft-threads",
    "spec_draft_threads_batch": "--spec-draft-threads-batch",
    "spec_draft_ngl": "--spec-draft-ngl",
    "spec_draft_cache_type_k": "--spec-draft-type-k",
    "spec_draft_cache_type_v": "--spec-draft-type-v",
}

STARTUP_ENUMS: dict[str, frozenset[str]] = {
    "flash_attn": frozenset({"on", "off", "auto"}),
    "fit": frozenset({"on", "off"}),
    "cache_type_k": frozenset({"f32", "f16", "bf16", "q8_0", "q4_0", "q4_1", "iq4_nl", "q5_0", "q5_1"}),
    "cache_type_v": frozenset({"f32", "f16", "bf16", "q8_0", "q4_0", "q4_1", "iq4_nl", "q5_0", "q5_1"}),
    "load_mode": frozenset({"auto", "none", "mmap", "mlock", "mmap+mlock", "dio"}),
    "embedding": frozenset({"on", "off"}),
    # This integration uses /v1/embeddings. Other llama.cpp pooling modes
    # need their own token-embedding/reranking path before being exposed here.
    "pooling": frozenset({"mean", "cls", "last"}),
    "reasoning": frozenset({"on", "off", "auto"}),
    "reasoning_format": frozenset({"auto", "none", "deepseek", "deepseek-legacy"}),
    "spec_draft_cache_type_k": frozenset({"f32", "f16", "bf16", "q8_0", "q4_0", "q4_1", "iq4_nl", "q5_0", "q5_1"}),
    "spec_draft_cache_type_v": frozenset({"f32", "f16", "bf16", "q8_0", "q4_0", "q4_1", "iq4_nl", "q5_0", "q5_1"}),
}

STARTUP_BOOL_FLAGS: dict[str, tuple[str, str]] = {
    "kv_offload": ("--kv-offload", "--no-kv-offload"),
    "kv_unified": ("--kv-unified", "--no-kv-unified"),
    "op_offload": ("--op-offload", "--no-op-offload"),
    "mmproj_use_gpu": ("--mmproj-offload", "--no-mmproj-offload"),
    "reasoning_preserve": ("--reasoning-preserve", "--no-reasoning-preserve"),
}

STARTUP_INTS: frozenset[str] = frozenset(
    {
        "port",
        "ctx_size",
        "threads",
        "threads_batch",
        "parallel",
        "batch_size",
        "ubatch_size",
        "reasoning_budget",
        "spec_draft_n_max",
        "spec_draft_n_min",
        "spec_draft_threads",
        "spec_draft_threads_batch",
    }
)

STARTUP_FLOATS: frozenset[str] = frozenset({"spec_draft_p_split", "spec_draft_p_min"})

STARTUP_GPU_LAYERS: frozenset[str] = frozenset({"n_gpu_layers", "spec_draft_ngl"})

SPEC_TYPES: frozenset[str] = frozenset(
    {
        "none",
        "draft-simple",
        "draft-eagle3",
        "draft-mtp",
        "draft-dflash",
        "draft-dspark",
        "ngram-simple",
        "ngram-map-k",
        "ngram-map-k4v",
        "ngram-mod",
        "ngram-cache",
    }
)

STARTUP_STRINGS: frozenset[str] = frozenset(
    {
        "host",
        "alias",
        "chat_template",
        "chat_template_file",
        "reasoning_budget_message",
        "reasoning_effort",
        "spec_draft_model",
    }
)

# Keys the workbench used to map to llama-server flags that b11045 no longer accepts.
# The value is the note shown to the user; the key is never emitted on argv.
RETIRED_STARTUP_KEYS: dict[str, str] = {
    "mlock": (
        "llama.cpp b11045 rejects --mlock; use load_mode: 'mmap+mlock' "
        "(or 'mlock' to also disable mmap). Not applied."
    ),
    "no_mmap": (
        "llama.cpp b11045 rejects --no-mmap; use load_mode: 'none' "
        "(or 'mlock' to also lock memory). Not applied."
    ),
}

PER_REQUEST_KEYS: frozenset[str] = frozenset(
    {
        "temperature",
        "top_p",
        "top_k",
        "min_p",
        "typical_p",
        "repeat_penalty",
        "presence_penalty",
        "frequency_penalty",
        "max_tokens",
        "logit_bias",
        "stop",
        "seed",
        "reasoning",
        "reasoning_format",
        "reasoning_effort",
        "reasoning_budget_tokens",
        "reasoning_budget_message",
        "reasoning_preserve",
    }
)

AGENT_KEYS: frozenset[str] = frozenset(
    {
        "system_prompt",
    }
)

UNSUPPORTED_AGENT_REASONS: dict[str, str] = {
    "tools_enabled": (
        "Not implemented as a profile setting. Tools are selected by the run "
        "request and access policy; this requested value is preserved but not applied."
    ),
    "max_iterations": (
        "Not implemented. This requested value is preserved but not applied. "
        "The separate explicit max_steps budget controls LangGraph steps, not iterations."
    ),
}

DEFAULT_GPU_PROFILE: dict[str, Any] = {
    "n_gpu_layers": "auto",
    "fit": "on",
    "flash_attn": "auto",
    "parallel": 4,
    "kv_unified": True,
}

DEFAULT_STARTUP: dict[str, Any] = {
    "host": "127.0.0.1",
    "port": 8080,
    **DEFAULT_GPU_PROFILE,
}

# Shared validation and presentation facts. Suggested spans are comfortable UI
# ranges, not invented runtime limits. Native/model-specific constraints are
# added by configuration_options using the exact selected model/template.
CONTROL_FACTS: dict[str, dict[str, Any]] = {
    "ctx_size": {"domain": "integer", "unit": "tokens", "control": "tokens", "section": "memory", "minimum": 0, "step": 1},
    "n_gpu_layers": {"domain": "integer", "unit": "layers", "control": "choice", "section": "memory", "minimum": 0, "step": 1, "dependencies": ["fit"]},
    "threads": {"domain": "integer", "unit": "threads", "control": "number", "minimum": -1, "step": 1},
    "threads_batch": {"domain": "integer", "unit": "threads", "control": "number", "minimum": -1, "step": 1},
    "parallel": {"domain": "integer", "unit": "requests", "control": "number", "minimum": 1, "step": 1, "suggested_maximum": 8, "dependencies": ["kv_unified"]},
    "batch_size": {"domain": "integer", "unit": "tokens", "control": "number", "minimum": 1, "step": 1, "suggested_maximum": 8192, "dependencies": ["ubatch_size"]},
    "ubatch_size": {"domain": "integer", "unit": "tokens", "control": "number", "minimum": 1, "step": 1, "suggested_maximum": 2048, "dependencies": ["batch_size"]},
    "flash_attn": {"domain": "string", "dependencies": ["cache_type_v"]},
    "fit": {"domain": "string", "dependencies": ["n_gpu_layers"]},
    "cache_type_k": {"domain": "string", "dependencies": ["cache_type_v"]},
    "cache_type_v": {"domain": "string", "dependencies": ["flash_attn", "cache_type_k"]},
    "kv_offload": {"domain": "boolean", "control": "switch"},
    "kv_unified": {"domain": "boolean", "control": "switch", "dependencies": ["parallel"]},
    "op_offload": {"domain": "boolean", "control": "switch", "dependencies": ["n_gpu_layers"]},
    "mmproj_use_gpu": {"domain": "boolean", "control": "switch", "dependencies": ["n_gpu_layers"]},
    "embedding": {"domain": "string", "dependencies": ["pooling", "batch_size", "ubatch_size"]},
    "pooling": {"domain": "string", "dependencies": ["embedding"]},
    "chat_template_kwargs": {"domain": "object", "control": "json"},
    "temperature": {"domain": "number", "control": "number", "minimum": 0, "step": 0.05, "suggested_maximum": 2},
    "top_p": {"domain": "number", "control": "number", "minimum": 0, "maximum": 1, "step": 0.01},
    "min_p": {"domain": "number", "control": "number", "minimum": 0, "maximum": 1, "step": 0.01},
    "typical_p": {"domain": "number", "control": "number", "minimum": 0, "maximum": 1, "step": 0.01},
    "top_k": {"domain": "integer", "control": "number", "minimum": 0, "step": 1, "suggested_maximum": 100},
    "repeat_penalty": {"domain": "number", "control": "number", "minimum": 0, "step": 0.05, "suggested_maximum": 2},
    "presence_penalty": {"domain": "number", "control": "number", "step": 0.1, "suggested_minimum": -2, "suggested_maximum": 2},
    "frequency_penalty": {"domain": "number", "control": "number", "step": 0.1, "suggested_minimum": -2, "suggested_maximum": 2},
    "max_tokens": {"domain": "integer", "unit": "tokens", "control": "tokens", "section": "response", "minimum": -1, "step": 1},
    "seed": {"domain": "integer", "control": "number", "minimum": -1, "step": 1},
    "reasoning": {"domain": "string", "section": "response"},
    "reasoning_effort": {"domain": "string", "section": "response"},
    "reasoning_format": {"domain": "string"},
    "reasoning_budget_tokens": {"domain": "integer", "unit": "tokens", "control": "tokens", "minimum": -1, "step": 1, "dependencies": ["max_tokens", "reasoning"]},
    "reasoning_budget_message": {"domain": "string", "control": "text", "dependencies": ["reasoning_budget_tokens"]},
    "reasoning_preserve": {"domain": "boolean", "control": "choice", "dependencies": ["reasoning"]},
    "spec_draft_n_max": {"domain": "integer", "unit": "tokens", "control": "number", "minimum": 0, "step": 1, "suggested_maximum": 16, "dependencies": ["spec_type", "spec_draft_n_min"]},
    "spec_draft_n_min": {"domain": "integer", "unit": "tokens", "control": "number", "minimum": 0, "step": 1, "suggested_maximum": 16, "dependencies": ["spec_type", "spec_draft_n_max"]},
    "spec_draft_p_split": {"domain": "number", "control": "number", "minimum": 0, "maximum": 1, "step": 0.01, "dependencies": ["spec_type"]},
    "spec_draft_p_min": {"domain": "number", "control": "number", "minimum": 0, "maximum": 1, "step": 0.01, "dependencies": ["spec_type"]},
    "spec_draft_threads": {"domain": "integer", "unit": "threads", "control": "number", "minimum": -1, "step": 1, "dependencies": ["spec_type"]},
    "spec_draft_threads_batch": {"domain": "integer", "unit": "threads", "control": "number", "minimum": -1, "step": 1, "dependencies": ["spec_type"]},
    "spec_draft_ngl": {"domain": "integer", "unit": "layers", "control": "choice", "minimum": 0, "step": 1, "dependencies": ["spec_type", "fit"]},
    "logit_bias": {"domain": "json", "control": "json"},
    "stop": {"domain": "string", "control": "text"},
}

REQUEST_STARTUP_ALIASES = {
    "reasoning": "reasoning", "reasoning_effort": "reasoning_effort",
    "reasoning_format": "reasoning_format", "reasoning_preserve": "reasoning_preserve",
    "reasoning_budget": "reasoning_budget_tokens", "reasoning_budget_message": "reasoning_budget_message",
}
REQUEST_TEMPLATE_ALIASES = {
    "enable_thinking": "reasoning", "reasoning_effort": "reasoning_effort",
    "preserve_reasoning": "reasoning_preserve", "preserve_thinking": "reasoning_preserve",
}


def control_facts(key: str, *, per_request: bool = False) -> dict[str, Any]:
    facts = {"domain": "string", "control": "choice", "section": "advanced",
             "apply_timing": "next_request" if per_request else "reload",
             "reset_value": None}
    facts.update(CONTROL_FACTS.get(key, {}))
    return facts


def split_response_startup(startup: dict[str, Any], per_request: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Move only native request-capable defaults out of the loading plan."""
    loading, response = dict(startup), {}
    kwargs = loading.get("chat_template_kwargs")
    if isinstance(kwargs, str):
        try:
            kwargs = json.loads(kwargs)
        except ValueError:
            kwargs = None
    if isinstance(kwargs, dict):
        kwargs = dict(kwargs)
        for source, target in REQUEST_TEMPLATE_ALIASES.items():
            if source in kwargs:
                if source in {"enable_thinking", "preserve_reasoning", "preserve_thinking"} and not isinstance(kwargs[source], bool):
                    continue  # The startup validator rejects native wrong types.
                if source == "reasoning_effort" and normalize_string(kwargs[source]) is None:
                    continue
                value = kwargs.pop(source)
                response[target] = ("on" if value else "off") if source == "enable_thinking" and isinstance(value, bool) else value
        if kwargs:
            loading["chat_template_kwargs"] = json.dumps(kwargs, sort_keys=True, separators=(",", ":"))
        else:
            loading.pop("chat_template_kwargs", None)
    for source, target in REQUEST_STARTUP_ALIASES.items():
        if source in loading:
            value = loading.pop(source)
            if source == "reasoning" and normalize_on_off_auto(value, allow_auto=True) == "auto" and target in response:
                continue  # Native Auto retains an explicit template kwarg.
            response[target] = value
    response.update(per_request)
    return loading, response

_EMBEDDING_ALIASES: dict[Any, str] = {
    True: "on",
    False: "off",
    1: "on",
    0: "off",
    "1": "on",
    "0": "off",
    "true": "on",
    "false": "off",
    "on": "on",
    "off": "off",
}

_FLASH_ATTN_ALIASES: dict[Any, str] = {
    True: "on",
    False: "off",
    1: "on",
    0: "off",
    "1": "on",
    "0": "off",
    "true": "on",
    "false": "off",
    "on": "on",
    "off": "off",
    "auto": "auto",
}

_ON_OFF_AUTO_ALIASES: dict[Any, str] = {
    True: "on",
    False: "off",
    1: "on",
    0: "off",
    "1": "on",
    "0": "off",
    "true": "on",
    "false": "off",
    "on": "on",
    "off": "off",
    "auto": "auto",
}


def default_gpu_startup() -> dict[str, Any]:
    """Return a copy of the default managed GPU startup profile."""
    return dict(DEFAULT_GPU_PROFILE)


def normalize_flash_attn(value: Any) -> str | None:
    """Map a requested flash_attn value to on|off|auto, or None if invalid."""
    if isinstance(value, bool):
        return _FLASH_ATTN_ALIASES[value]
    if isinstance(value, int):
        return _FLASH_ATTN_ALIASES.get(value)
    if isinstance(value, str):
        return _FLASH_ATTN_ALIASES.get(value.strip().lower())
    return None


def normalize_load_mode(value: Any) -> str | None:
    """Map a requested load_mode value to a b11045 ``--load-mode`` mode, or None if invalid."""
    if isinstance(value, str):
        candidate = value.strip().lower()
        if candidate in STARTUP_ENUMS["load_mode"]:
            return candidate
    return None


def normalize_embedding(value: Any) -> str | None:
    """Map a requested embedding value to on|off, or None if invalid."""
    if isinstance(value, bool):
        return _EMBEDDING_ALIASES[value]
    if isinstance(value, int):
        return _EMBEDDING_ALIASES.get(value)
    if isinstance(value, str):
        return _EMBEDDING_ALIASES.get(value.strip().lower())
    return None


def normalize_pooling(value: Any) -> str | None:
    """Map pooling to llama-server modes that work with ``/v1/embeddings``."""
    if isinstance(value, str):
        candidate = value.strip().lower()
        if candidate in STARTUP_ENUMS["pooling"]:
            return candidate
    return None


def normalize_startup_enum(key: str, value: Any) -> str | None:
    if key == "flash_attn":
        return normalize_flash_attn(value)
    if key in {"fit", "reasoning"}:
        return normalize_on_off_auto(value, allow_auto=key == "reasoning")
    if key == "load_mode":
        return normalize_load_mode(value)
    if key == "embedding":
        return normalize_embedding(value)
    if key == "pooling":
        return normalize_pooling(value)
    if key in STARTUP_ENUMS and isinstance(value, str):
        candidate = value.strip().lower()
        if candidate in STARTUP_ENUMS[key]:
            return candidate
    return None


def normalize_startup_requested(requested: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Normalise startup values. Invalid values become unsupported."""
    cleaned = {key: value for key, value in requested.items() if value is not None}
    invalid: list[str] = []
    for key in STARTUP_ENUMS:
        if key not in cleaned:
            continue
        normalized = normalize_startup_enum(key, cleaned[key])
        if normalized is None:
            invalid.append(key)
            del cleaned[key]
        else:
            cleaned[key] = normalized
    for key in STARTUP_BOOL_FLAGS:
        if key not in cleaned:
            continue
        normalized = normalize_bool(cleaned[key])
        if normalized is None:
            invalid.append(key)
            del cleaned[key]
        else:
            cleaned[key] = normalized
    for key in STARTUP_INTS:
        if key not in cleaned:
            continue
        normalized = normalize_int(cleaned[key], allow_negative=key in {"reasoning_budget", "threads", "threads_batch", "parallel", "spec_draft_threads", "spec_draft_threads_batch"})
        if key == "port" and normalized is not None and not 1 <= normalized <= 65535:
            normalized = None
        if key in {"threads", "threads_batch", "parallel", "spec_draft_threads", "spec_draft_threads_batch", "reasoning_budget"} and normalized is not None and normalized < -1:
            normalized = None
        if key in {"parallel", "batch_size", "ubatch_size"} and normalized == 0:
            normalized = None
        if normalized is None:
            invalid.append(key)
            del cleaned[key]
        else:
            cleaned[key] = normalized
    for key in STARTUP_GPU_LAYERS:
        if key not in cleaned:
            continue
        normalized = normalize_gpu_layers(cleaned[key])
        if normalized is None:
            invalid.append(key)
            del cleaned[key]
        else:
            cleaned[key] = normalized
    for key in STARTUP_FLOATS:
        if key not in cleaned:
            continue
        normalized = normalize_probability(cleaned[key])
        if normalized is None:
            invalid.append(key)
            del cleaned[key]
        else:
            cleaned[key] = normalized
    if "chat_template_kwargs" in cleaned:
        normalized = normalize_json_object_string(cleaned["chat_template_kwargs"])
        if normalized is not None:
            kwargs = json.loads(normalized)
            if any(key in kwargs and not isinstance(kwargs[key], bool) for key in ("enable_thinking", "preserve_reasoning", "preserve_thinking")):
                normalized = None
            if "reasoning_effort" in kwargs and normalize_string(kwargs["reasoning_effort"]) is None:
                normalized = None
        if normalized is None:
            invalid.append("chat_template_kwargs")
            del cleaned["chat_template_kwargs"]
        else:
            cleaned["chat_template_kwargs"] = normalized
    if "spec_type" in cleaned:
        normalized = normalize_spec_type(cleaned["spec_type"])
        if normalized is None:
            invalid.append("spec_type")
            del cleaned["spec_type"]
        else:
            cleaned["spec_type"] = normalized
    for key in STARTUP_STRINGS:
        if key not in cleaned:
            continue
        normalized = normalize_string(cleaned[key])
        if normalized is None:
            invalid.append(key)
            del cleaned[key]
        else:
            cleaned[key] = normalized
    if cleaned.get("n_gpu_layers", DEFAULT_GPU_PROFILE["n_gpu_layers"]) in {"auto", -1} and cleaned.get("fit") == "off":
        invalid.append("fit")
        cleaned.pop("fit", None)
    if cleaned.get("flash_attn") == "off" and str(cleaned.get("cache_type_v", "f16")).startswith(("q", "iq")):
        invalid.append("cache_type_v")
        cleaned.pop("cache_type_v", None)
    if (type(cleaned.get("batch_size")) is int and type(cleaned.get("ubatch_size")) is int
            and cleaned["ubatch_size"] > cleaned["batch_size"]):
        invalid.append("ubatch_size")
        cleaned.pop("ubatch_size", None)
    if (type(cleaned.get("spec_draft_n_min")) is int and type(cleaned.get("spec_draft_n_max")) is int
            and cleaned["spec_draft_n_min"] > cleaned["spec_draft_n_max"]):
        invalid.append("spec_draft_n_min")
        cleaned.pop("spec_draft_n_min", None)
    if cleaned.get("n_gpu_layers") == 0:
        for key, value in (("kv_offload", False), ("op_offload", False), ("mmproj_use_gpu", False), ("spec_draft_ngl", 0)):
            cleaned.setdefault(key, value)
    return cleaned, invalid


def normalize_on_off_auto(value: Any, *, allow_auto: bool) -> str | None:
    if isinstance(value, bool):
        return _ON_OFF_AUTO_ALIASES[value]
    if isinstance(value, int):
        return _ON_OFF_AUTO_ALIASES.get(value)
    if isinstance(value, str):
        candidate = _ON_OFF_AUTO_ALIASES.get(value.strip().lower())
        if candidate == "auto" and not allow_auto:
            return None
        return candidate
    return None


def normalize_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        candidate = value.strip().lower()
        if candidate in {"1", "true", "on", "yes"}:
            return True
        if candidate in {"0", "false", "off", "no"}:
            return False
    return None


def normalize_int(value: Any, *, allow_negative: bool = False) -> int | str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        if (value < 0 and not allow_negative) or not -(2**31) <= value <= 2**31 - 1:
            return None
        return value
    if isinstance(value, str):
        candidate = value.strip()
        try:
            parsed = int(candidate)
        except ValueError:
            return None
        if (parsed < 0 and not allow_negative) or not -(2**31) <= parsed <= 2**31 - 1:
            return None
        return parsed
    return None


def normalize_gpu_layers(value: Any) -> int | str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        if not -1 <= value <= 2**31 - 1:
            return None
        return value
    if isinstance(value, str):
        candidate = value.strip().lower()
        if candidate in {"auto", "all"}:
            return candidate
        try:
            parsed = int(candidate)
        except ValueError:
            return None
        if not -1 <= parsed <= 2**31 - 1:
            return None
        return parsed
    return None


def normalize_seed(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = int(value.strip())
        except ValueError:
            return None
    return value if isinstance(value, int) and -1 <= value <= 2**32 - 1 else None


def normalize_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        try:
            parsed = float(value)
        except OverflowError:
            return None
        return parsed if math.isfinite(parsed) else None
    if isinstance(value, str):
        try:
            parsed = float(value.strip())
            return parsed if math.isfinite(parsed) else None
        except ValueError:
            return None
    return None


def normalize_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def normalize_json_object_string(value: Any) -> str | None:
    text = normalize_string(value)
    if text is None:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return text


def normalize_probability(value: Any) -> float | None:
    parsed = normalize_float(value)
    if parsed is None or parsed < 0.0 or parsed > 1.0:
        return None
    return parsed


def normalize_per_request_requested(requested: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Validate request values once for save, preview and every dispatch path."""
    cleaned = {key: value for key, value in requested.items() if value is not None}
    invalid: list[str] = []
    for key, value in list(cleaned.items()):
        if key not in PER_REQUEST_KEYS:
            continue
        facts = CONTROL_FACTS.get(key, {})
        domain = facts.get("domain")
        normalized = value
        if key == "seed":
            normalized = normalize_seed(value)
        elif domain == "integer":
            normalized = normalize_int(value, allow_negative=facts.get("minimum", 0) < 0)
        elif domain == "number":
            normalized = normalize_float(value)
        elif key == "reasoning":
            normalized = normalize_on_off_auto(value, allow_auto=True)
        elif key == "reasoning_preserve":
            normalized = normalize_bool(value)
        elif key == "reasoning_format":
            normalized = normalize_startup_enum(key, value)
        elif key == "reasoning_effort":
            normalized = normalize_string(value)
        elif key == "reasoning_budget_message":
            normalized = value if isinstance(value, str) else None
        elif key == "stop":
            normalized = value if isinstance(value, str) or (isinstance(value, list) and all(isinstance(item, str) for item in value)) else None
        elif key == "logit_bias":
            def bias(raw):
                return False if raw is False else normalize_float(raw)
            if isinstance(value, dict):
                normalized = {str(token): weight for token, raw in value.items() if (weight := bias(raw)) is not None}
                if len(normalized) != len(value):
                    normalized = None
            elif isinstance(value, list):
                normalized = []
                for pair in value:
                    if (not isinstance(pair, list) or len(pair) != 2 or isinstance(pair[0], bool)
                            or not isinstance(pair[0], int | str) or isinstance(pair[0], int) and pair[0] < 0
                            or (weight := bias(pair[1])) is None):
                        normalized = None
                        break
                    normalized.append([pair[0], weight])
            else:
                normalized = None
        if isinstance(normalized, int | float) and not isinstance(normalized, bool):
            if (facts.get("minimum") is not None and normalized < facts["minimum"]
                    or facts.get("maximum") is not None and normalized > facts["maximum"]
                    or key == "max_tokens" and normalized == 0):
                normalized = None
        if normalized is None:
            invalid.append(key)
            cleaned.pop(key, None)
        else:
            cleaned[key] = normalized
    return cleaned, invalid


def normalize_spec_type(value: Any) -> str | None:
    text = normalize_string(value)
    if text is None:
        return None
    parts = [part.strip().lower() for part in text.split(",")]
    if not parts or any(part not in SPEC_TYPES for part in parts):
        return None
    return ",".join(parts)


def retired_startup_notes(requested: dict[str, Any]) -> list[SettingNote]:
    """Explain each retired key the caller still requested. Never applied."""
    return [
        SettingNote(key=key, requested=requested[key], applied=None, reason=reason)
        for key, reason in RETIRED_STARTUP_KEYS.items()
        if key in requested
    ]


def resolve_bag(
    requested: dict[str, Any],
    known: frozenset[str] | dict[str, str],
    *,
    defaults: dict[str, Any] | None = None,
    overrides: dict[str, Any] | None = None,
    unsupported_reasons: dict[str, str] | None = None,
) -> SettingsBag:
    known_keys = set(known)
    raw_requested = dict(requested)
    invalid: list[str] = []
    if known_keys == set(PER_REQUEST_KEYS):
        requested, invalid = normalize_per_request_requested(requested)
        defaults, _ = normalize_per_request_requested(defaults or {})
    defaults = defaults or {}
    overrides = overrides or {}
    unsupported = sorted({key for key in requested if key not in known_keys} | set(invalid))
    reasons = unsupported_reasons or {}
    unsupported_notes = [
        SettingNote(
            key=key,
            requested=raw_requested.get(key),
            applied=None,
            reason=reasons.get(key, "Invalid value for this control's supported domain." if key in invalid else "Unsupported setting is preserved as requested but not applied."),
        )
        for key in unsupported
    ]
    applied: dict[str, Any] = dict(defaults)
    for key, value in requested.items():
        if key in known_keys:
            applied[key] = value
    overridden: list[SettingNote] = []
    for key, value in overrides.items():
        if key in applied and applied[key] != value:
            overridden.append(
                SettingNote(
                    key=key,
                    requested=applied.get(key),
                    applied=value,
                    reason="runtime selected a different applied value",
                )
            )
        applied[key] = value
    unverified = sorted(key for key in applied if key in known_keys)
    return SettingsBag(
        requested=raw_requested,
        applied=applied,
        unsupported=unsupported,
        unsupported_notes=unsupported_notes,
        overridden=overridden,
        unverified=unverified,
    )


def resolve_bags(
    *,
    startup: dict[str, Any] | None = None,
    per_request: dict[str, Any] | None = None,
    agent: dict[str, Any] | None = None,
    startup_overrides: dict[str, Any] | None = None,
    per_request_defaults: dict[str, Any] | None = None,
) -> SettingsBags:
    loading, response = split_response_startup(startup or {}, per_request or {})
    startup_requested, invalid_enums = normalize_startup_requested(loading)
    startup_bag = resolve_bag(
        startup_requested,
        STARTUP_KEYS,
        defaults=DEFAULT_STARTUP,
        overrides=startup_overrides,
    )
    startup_bag = startup_bag.model_copy(
        update={
            "requested": dict(startup or {}),
            "unsupported": sorted(set(startup_bag.unsupported) | set(invalid_enums)),
            "unsupported_notes": [*startup_bag.unsupported_notes, *[
                SettingNote(key=key, requested=loading.get(key), applied=None,
                            reason="Invalid value or dependency for this control. Correct it before loading.")
                for key in invalid_enums
            ]],
            "retired": retired_startup_notes(startup or {}),
        }
    )
    return SettingsBags(
        startup=startup_bag,
        per_request=resolve_bag(response, PER_REQUEST_KEYS, defaults=per_request_defaults),
        agent=resolve_bag(
            agent or {},
            AGENT_KEYS,
            unsupported_reasons=UNSUPPORTED_AGENT_REASONS,
        ),
    )


def resolve_declared_startup(requested: dict[str, Any] | None = None) -> SettingsBag:
    """Resolve startup keys without applying managed-process defaults.

    Connected endpoints do not start llama-server; recorded ``embedding`` /
    ``pooling`` values are a declaration, not applied argv.
    """
    raw = dict(requested or {})
    cleaned, invalid = normalize_startup_requested(raw)
    bag = resolve_bag(cleaned, STARTUP_KEYS)
    return bag.model_copy(
        update={
            "requested": raw,
            "unsupported": sorted(set(bag.unsupported) | set(invalid)),
            "retired": retired_startup_notes(raw),
        }
    )


def startup_cli_args(applied: dict[str, Any]) -> list[str]:
    """Serialize applied startup keys to llama-server argv.

    Valued enums always include the value; an invalid enum value is skipped
    rather than emitted. Retired keys are never in ``STARTUP_KEYS`` so they
    never reach argv. ``flash_attn`` never becomes a bare ``--flash-attn``.
    ``embedding: on`` emits the llama-server bare flag ``--embedding``;
    ``embedding: off`` omits it.
    """
    args: list[str] = []
    for key, flag in STARTUP_KEYS.items():
        if key not in applied:
            continue
        value = applied[key]
        if key == "embedding":
            if normalize_startup_enum(key, value) == "on":
                args.append(flag)
            continue
        if key in STARTUP_BOOL_FLAGS:
            on_flag, off_flag = STARTUP_BOOL_FLAGS[key]
            normalized = normalize_bool(value)
            if normalized is None:
                continue
            args.append(on_flag if normalized else off_flag)
            continue
        if key in STARTUP_ENUMS:
            normalized = normalize_startup_enum(key, value)
            if normalized is None:
                continue
            args.extend([flag, normalized])
            continue
        args.extend([flag, str(value)])
    return args
