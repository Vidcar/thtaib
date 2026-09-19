"""Requested versus applied settings bags (MOD-003).

Known keys may be passed through. Unknown keys are unsupported. Values the
workbench accepts but has not UAT-verified remain unverified. This does not
close OQ-007.

Valued startup enums (Issue #21): ``flash_attn`` serializes as
``--flash-attn on|off|auto`` and ``load_mode`` as ``--load-mode MODE``.
Every current STARTUP_KEY takes a value; there are no bare flags. Never
emit a bare ``--flash-attn``.

The pinned llama.cpp b11045 rejects ``--mlock`` and ``--no-mmap``
(``error: invalid argument``); upstream replaced both with ``--load-mode``.
The retired ``mlock`` / ``no_mmap`` keys are therefore reported as
unsupported with a migration note instead of being emitted or silently
dropped.
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
    "load_mode": "--load-mode",
    "alias": "--alias",
}

STARTUP_ENUMS: dict[str, frozenset[str]] = {
    "flash_attn": frozenset({"on", "off", "auto"}),
    "load_mode": frozenset({"auto", "none", "mmap", "mlock", "mmap+mlock", "dio"}),
}

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
        "stop",
        "seed",
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


def normalize_load_mode(value: Any) -> str | None:
    """Map a requested load_mode value to a b11045 ``--load-mode`` mode, or None if invalid."""
    if isinstance(value, str):
        candidate = value.strip().lower()
        if candidate in STARTUP_ENUMS["load_mode"]:
            return candidate
    return None


def normalize_startup_enum(key: str, value: Any) -> str | None:
    if key == "flash_attn":
        return normalize_flash_attn(value)
    if key == "load_mode":
        return normalize_load_mode(value)
    return None


def normalize_startup_requested(requested: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Normalise valued startup enums. Invalid enums become unsupported."""
    cleaned = dict(requested)
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
    return cleaned, invalid


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
    startup_bag = startup_bag.model_copy(
        update={
            "requested": dict(startup or {}),
            "unsupported": sorted(set(startup_bag.unsupported) | set(invalid_enums)),
            "retired": retired_startup_notes(startup or {}),
        }
    )
    return SettingsBags(
        startup=startup_bag,
        per_request=resolve_bag(per_request or {}, PER_REQUEST_KEYS),
        agent=resolve_bag(agent or {}, AGENT_KEYS),
    )


def startup_cli_args(applied: dict[str, Any]) -> list[str]:
    """Serialize applied startup keys to llama-server argv.

    Valued enums always include the value; an invalid enum value is skipped
    rather than emitted. Retired keys are never in ``STARTUP_KEYS`` so they
    never reach argv. ``flash_attn`` never becomes a bare ``--flash-attn``.
    """
    args: list[str] = []
    for key, flag in STARTUP_KEYS.items():
        if key not in applied:
            continue
        value = applied[key]
        if key in STARTUP_ENUMS:
            normalized = normalize_startup_enum(key, value)
            if normalized is None:
                continue
            args.extend([flag, normalized])
            continue
        args.extend([flag, str(value)])
    return args
