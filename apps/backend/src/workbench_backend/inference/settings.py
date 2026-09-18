"""Requested versus applied settings bags (MOD-003).

Known keys may be passed through. Unknown keys are unsupported. Values the
workbench accepts but has not UAT-verified remain unverified. This does not
close OQ-007.
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

DEFAULT_STARTUP: dict[str, Any] = {
    "host": "127.0.0.1",
    "port": 8080,
}


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
    return SettingsBags(
        startup=resolve_bag(
            startup or {},
            STARTUP_KEYS,
            defaults=DEFAULT_STARTUP,
            overrides=startup_overrides,
        ),
        per_request=resolve_bag(per_request or {}, PER_REQUEST_KEYS),
        agent=resolve_bag(agent or {}, AGENT_KEYS),
    )


def startup_cli_args(applied: dict[str, Any]) -> list[str]:
    args: list[str] = []
    for key, flag in STARTUP_KEYS.items():
        if key not in applied:
            continue
        value = applied[key]
        if isinstance(value, bool):
            if value:
                args.append(flag)
            continue
        args.extend([flag, str(value)])
    return args
