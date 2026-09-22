"""Computed runtime controls for a bundle.

These descriptors are UI-facing data derived from GGUF metadata, Workbench
startup defaults and optional observed llama-server properties. They do not
rewrite profiles or infer capabilities.
"""

from __future__ import annotations

from typing import Any

import psutil

from workbench_backend.inference.schemas import (
    BundleConfigurationOptions,
    Deployment,
    GgufRuntimeMetadata,
    RuntimeControlDescriptor,
    RuntimeControlOption,
)
from workbench_backend.inference.settings import DEFAULT_GPU_PROFILE, STARTUP_ENUMS

SMALL_CONTEXT_VALUES = (1024, 2048, 4096, 8192, 16384)
MIN_LARGE_CONTEXT_OPTION = 32 * 1024
CONTEXT_FRACTIONS = (1 / 8, 3 / 16, 1 / 4, 3 / 8, 1 / 2, 5 / 8, 3 / 4, 1)


def bundle_configuration_options(
    bundle_id: str,
    metadata: GgufRuntimeMetadata,
    *,
    deployment: Deployment | None = None,
    recommended_threads: int | None = None,
) -> BundleConfigurationOptions:
    """Build controls from read-only bundle metadata and optional live props."""

    observed_context = (
        deployment.server_props.n_ctx
        if deployment is not None and deployment.server_props is not None
        else None
    )
    return BundleConfigurationOptions(
        bundle_id=bundle_id,
        deployment_id=deployment.id if deployment is not None else None,
        context_size=_context_descriptor(metadata.context_length, observed_context),
        gpu_layers=_gpu_layers_descriptor(metadata.block_count),
        startup_defaults=_startup_defaults(recommended_threads=recommended_threads),
        per_request_defaults=_per_request_defaults(),
        metadata={
            "architecture": metadata.architecture,
            "name": metadata.name,
            "context_length": metadata.context_length,
            "block_count": metadata.block_count,
        },
    )


def _per_request_defaults() -> dict[str, RuntimeControlDescriptor]:
    return {
        "reasoning_effort": RuntimeControlDescriptor(
            key="reasoning_effort",
            label="Thinking effort",
            description=(
                "Per-request reasoning effort values accepted by the pinned "
                "llama.cpp OpenAI-compatible request schema."
            ),
            source="pinned_runtime_schema",
            applied="default",
            options=[
                RuntimeControlOption(
                    value=value,
                    label="Model default" if value == "default" else _title_effort(value),
                    description=(
                        "Leave reasoning effort to the model or profile default."
                        if value == "default"
                        else f"Send reasoning_effort={value} with this Chat request."
                    ),
                )
                for value in _ordered_reasoning_efforts()
            ],
        )
    }


def _ordered_reasoning_efforts() -> list[str]:
    preferred = ["default", "minimal", "low", "medium", "high", "xhigh", "max"]
    supported = STARTUP_ENUMS["reasoning_effort"]
    ordered = [value for value in preferred if value in supported]
    ordered.extend(sorted(supported - set(ordered)))
    return ordered


def _title_effort(value: str) -> str:
    return value.replace("_", " ").title()


def _context_descriptor(maximum: int | None, observed: int | None) -> RuntimeControlDescriptor:
    options = [
        RuntimeControlOption(
            value=None,
            label="Automatic fit",
            description="Let llama.cpp choose the largest context that fits this start.",
        )
    ]
    options.extend(
        RuntimeControlOption(
            value=value,
            label=_format_tokens(value),
            description=f"Start llama-server with --ctx-size {value}.",
        )
        for value in _context_values(maximum)
    )
    return RuntimeControlDescriptor(
        key="ctx_size",
        flag="--ctx-size",
        label="Context size",
        description=(
            "Maximum tokens available to a conversation. Automatic fit leaves "
            "--ctx-size unset; the observed value is recorded from /props once a "
            "server is healthy."
        ),
        source="gguf_metadata" if maximum is not None else "runtime_observation",
        applied=None,
        observed=observed,
        maximum=maximum,
        options=options,
    )


def _gpu_layers_descriptor(block_count: int | None) -> RuntimeControlDescriptor:
    maximum = block_count + 1 if block_count is not None and block_count >= 0 else None
    if maximum is None:
        layer_values = [-1, 0]
    else:
        layer_values = [-1, *range(0, maximum + 1)]
    return RuntimeControlDescriptor(
        key="n_gpu_layers",
        flag="--n-gpu-layers",
        label="GPU layers",
        description=(
            "How many transformer layers llama.cpp should place on the GPU. -1 asks "
            "the runtime to offload all layers it can."
        ),
        source="gguf_metadata" if maximum is not None else "workbench_default",
        applied=DEFAULT_GPU_PROFILE["n_gpu_layers"],
        maximum=maximum,
        options=[
            RuntimeControlOption(
                value=value,
                label="All available GPU layers" if value == -1 else str(value),
                description=(
                    "Start llama-server with --n-gpu-layers -1."
                    if value == -1
                    else f"Start llama-server with --n-gpu-layers {value}."
                ),
            )
            for value in layer_values
        ],
    )


def _startup_defaults(*, recommended_threads: int | None) -> dict[str, RuntimeControlDescriptor]:
    threads = _threads_descriptor(recommended_threads)
    return {
        "n_gpu_layers": RuntimeControlDescriptor(
            key="n_gpu_layers",
            flag="--n-gpu-layers",
            label="GPU layers",
            description="Workbench starts managed GPU deployments with full available offload by default.",
            source="workbench_default",
            applied=DEFAULT_GPU_PROFILE["n_gpu_layers"],
        ),
        "flash_attn": RuntimeControlDescriptor(
            key="flash_attn",
            flag="--flash-attn",
            label="Flash attention",
            description="Workbench enables flash attention for managed GPU deployments by default.",
            source="workbench_default",
            applied=DEFAULT_GPU_PROFILE["flash_attn"],
            options=[
                RuntimeControlOption(value="on", label="On"),
                RuntimeControlOption(value="off", label="Off"),
                RuntimeControlOption(value="auto", label="Automatic"),
            ],
        ),
        "ctx_size": RuntimeControlDescriptor(
            key="ctx_size",
            flag="--ctx-size",
            label="Context size",
            description="Workbench leaves this unset by default so llama.cpp can fit the model.",
            source="automatic_fit",
            applied=None,
        ),
        "threads": threads,
        "cache_type_k": RuntimeControlDescriptor(
            key="cache_type_k",
            flag="--cache-type-k",
            label="K cache",
            description="Pinned llama.cpp starts with f16 K cache unless this is overridden.",
            source="pinned_runtime_default",
            applied="f16",
        ),
        "cache_type_v": RuntimeControlDescriptor(
            key="cache_type_v",
            flag="--cache-type-v",
            label="V cache",
            description="Pinned llama.cpp starts with f16 V cache unless this is overridden.",
            source="pinned_runtime_default",
            applied="f16",
        ),
        "fit": RuntimeControlDescriptor(
            key="fit",
            flag="--fit",
            label="Fit model to memory",
            description="Pinned llama.cpp fits the model to available memory unless this is overridden.",
            source="pinned_runtime_default",
            applied="on",
        ),
    }


def recommended_cpu_threads() -> int:
    physical = psutil.cpu_count(logical=False)
    logical = psutil.cpu_count(logical=True)
    return max(1, int(physical or logical or 1))


def _threads_descriptor(recommended_threads: int | None) -> RuntimeControlDescriptor:
    recommended = recommended_threads if recommended_threads is not None else recommended_cpu_threads()
    values = sorted({1, 2, 4, 8, 12, 16, recommended})
    values = [value for value in values if value <= max(recommended, 16)]
    return RuntimeControlDescriptor(
        key="threads",
        flag="--threads",
        label="CPU threads",
        description=(
            "llama.cpp defaults to -1 for automatic thread selection. Workbench recommends "
            "the detected CPU count when the user chooses an explicit value."
        ),
        source="backend_recommendation",
        applied=None,
        recommended=recommended,
        observed=None,
        maximum=recommended,
        options=[
            RuntimeControlOption(
                value=None,
                label="Automatic",
                description="Leave --threads unset so llama.cpp uses its -1 automatic default.",
            ),
            *[
                RuntimeControlOption(
                    value=value,
                    label=f"{value} threads" if value != 1 else "1 thread",
                    description=f"Start llama-server with --threads {value}.",
                )
                for value in values
            ],
        ],
    )


def _context_values(maximum: int | None) -> list[int]:
    if maximum is None or maximum < 1024:
        return []
    small = [value for value in SMALL_CONTEXT_VALUES if value <= maximum]
    if maximum < MIN_LARGE_CONTEXT_OPTION:
        return sorted({*small, maximum})
    values = {
        _round_to_1024(maximum * fraction)
        for fraction in CONTEXT_FRACTIONS
        if _round_to_1024(maximum * fraction) >= 1024
    }
    values.add(maximum)
    return sorted(value for value in values if value <= maximum)


def _round_to_1024(value: float) -> int:
    return int(round(value / 1024)) * 1024


def _format_tokens(value: int) -> str:
    if value % 1024 == 0:
        return f"{value // 1024}k"
    return f"{value:,}"
