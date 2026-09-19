"""Requested versus applied settings bags (MOD-003).

Known keys may be passed through. Unknown keys are unsupported. Values the
workbench accepts but has not UAT-verified remain unverified. This does not
close OQ-007.

Valued startup enums (Issue #21): ``flash_attn`` is the only current
STARTUP_KEYS enum and must serialize as ``--flash-attn on|off|auto``.
Boolean flags (``mlock``, ``no_mmap``) stay bare flags. Numeric/string
keys always take a value. Never emit a bare ``--flash-attn``.
"""

from __future__ import annotations

from typing import Any

from workbench_backend.inference.schemas import SettingNote, SettingsBag, SettingsBags

STARTUP_KEYS: dict[str, str] = {
    "host": "--host",
    "port": "--port",
    "ctx_size": "--ctx-size",
    "n_gpu_layers": "--n-gpu-layers",
    "threads": "--threads",
    "parallel": "--parallel",
    "batch_size": "--batch-size",
    "ubatch_size": "--ubatch-size",
    "flash_attn": "--flash-attn",
    "mlock": "--mlock",
    "no_mmap": "--no-mmap",
    "alias": "--alias",
}

# Issue #21 audit of STARTUP_KEYS value kinds. Only flash_attn is a valued enum.
STARTUP_FLAG_KEYS: frozenset[str] = frozenset({"mlock", "no_mmap"})
STARTUP_ENUMS: dict[str, frozenset[str]] = {
    "flash_attn": frozenset({"on", "off", "auto"}),
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
        "stop",
        "seed",
        "stream",
    }
)

AGENT_KEYS: frozenset[str] = frozenset(
    {
        "system_prompt",
        "tools_enabled",
        "max_iterations",
    }
)

DEFAULT_GPU_PROFILE: dict[str, Any] = {
    "ctx_size": 65536,
    "n_gpu_layers": -1,
    "flash_attn": "on",
}

DEFAULT_STARTUP: dict[str, Any] = {
    "host": "127.0.0.1",
    "port": 8080,
    **DEFAULT_GPU_PROFILE,
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


def default_gpu_startup() -> dict[str, Any]:
    """Return a copy of the default GPU + large-ctx startup profile."""
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


def normalize_startup_requested(requested: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Normalise valued startup enums. Invalid enums become unsupported."""
    cleaned = dict(requested)
    invalid: list[str] = []
    if "flash_attn" in cleaned:
        normalized = normalize_flash_attn(cleaned["flash_attn"])
        if normalized is None:
            invalid.append("flash_attn")
            del cleaned["flash_attn"]
        else:
            cleaned["flash_attn"] = normalized
    return cleaned, invalid


def resolve_bag(
    requested: dict[str, Any],
    known: frozenset[str] | dict[str, str],
    *,
    defaults: dict[str, Any] | None = None,
    overrides: dict[str, Any] | None = None,
) -> SettingsBag:
    known_keys = set(known)
    defaults = defaults or {}
    overrides = overrides or {}
    unsupported = sorted(key for key in requested if key not in known_keys)
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
        requested=dict(requested),
        applied=applied,
        unsupported=unsupported,
        overridden=overridden,
        unverified=unverified,
    )


def resolve_bags(
    *,
    startup: dict[str, Any] | None = None,
    per_request: dict[str, Any] | None = None,
    agent: dict[str, Any] | None = None,
    startup_overrides: dict[str, Any] | None = None,
) -> SettingsBags:
    startup_requested, invalid_enums = normalize_startup_requested(startup or {})
    startup_bag = resolve_bag(
        startup_requested,
        STARTUP_KEYS,
        defaults=DEFAULT_STARTUP,
        overrides=startup_overrides,
    )
    if invalid_enums:
        startup_bag = startup_bag.model_copy(
            update={
                "requested": dict(startup or {}),
                "unsupported": sorted(set(startup_bag.unsupported) | set(invalid_enums)),
            }
        )
    else:
        startup_bag = startup_bag.model_copy(update={"requested": dict(startup or {})})
    return SettingsBags(
        startup=startup_bag,
        per_request=resolve_bag(per_request or {}, PER_REQUEST_KEYS),
        agent=resolve_bag(agent or {}, AGENT_KEYS),
    )


def startup_cli_args(applied: dict[str, Any]) -> list[str]:
    """Serialize applied startup keys to llama-server argv.

    Valued enums always include the value. Boolean flags stay bare. ``flash_attn``
    never becomes a bare ``--flash-attn``.
    """
    args: list[str] = []
    for key, flag in STARTUP_KEYS.items():
        if key not in applied:
            continue
        value = applied[key]
        if key in STARTUP_ENUMS:
            allowed = STARTUP_ENUMS[key]
            if key == "flash_attn":
                normalized = normalize_flash_attn(value)
            elif isinstance(value, str) and value.strip().lower() in allowed:
                normalized = value.strip().lower()
            else:
                normalized = None
            if normalized is None:
                continue
            args.extend([flag, normalized])
            continue
        if key in STARTUP_FLAG_KEYS:
            if value:
                args.append(flag)
            continue
        if isinstance(value, bool):
            if value:
                args.append(flag)
            continue
        args.extend([flag, str(value)])
    return args
