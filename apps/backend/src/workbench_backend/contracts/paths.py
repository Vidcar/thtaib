"""Repository-relative generated-contract locations."""

from __future__ import annotations

from pathlib import Path

OPENAPI_RELATIVE = "apps/backend/contracts/openapi.json"
MANIFEST_RELATIVE = "apps/backend/contracts/generated-manifest.json"
JSONSCHEMA_DIR_RELATIVE = "apps/backend/contracts/jsonschema"
DESKTOP_TYPES_RELATIVE = "apps/desktop/src/generated/shared-contracts/openapi.d.ts"
HANDWRITTEN_GENERATED_DIR_FILES = frozenset({"README.md"})

JSONSCHEMA_MODELS = (
    "LocalSessionTrustContract",
    "RunLifecycleContract",
    "RunLifecycleStatus",
    "RunStreamContract",
    "RunStreamEnvelope",
    "RunStreamEventType",
    "SharedAgentEvent",
)


def repo_root_from(start: Path) -> Path:
    for parent in [start, *start.parents]:
        if (parent / "specs" / "catalog.json").is_file() and (
            parent / "apps" / "desktop" / "package.json"
        ).is_file():
            return parent
    raise RuntimeError("cannot locate the Local AI Workbench repository root")


def jsonschema_relative(model_name: str) -> str:
    return f"{JSONSCHEMA_DIR_RELATIVE}/{model_name}.schema.json"


def generated_relative_paths() -> tuple[str, ...]:
    schema_files = tuple(jsonschema_relative(name) for name in JSONSCHEMA_MODELS)
    return (OPENAPI_RELATIVE, MANIFEST_RELATIVE, *schema_files, DESKTOP_TYPES_RELATIVE)
