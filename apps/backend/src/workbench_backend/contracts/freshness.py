"""Compare generated shared-contract artifacts with the committed tree."""

from __future__ import annotations

from pathlib import Path

from workbench_backend.contracts.paths import (
    HANDWRITTEN_GENERATED_DIR_FILES,
    generated_relative_paths,
)

GENERATED_TREE_ROOTS = (
    "apps/backend/contracts",
    "apps/desktop/src/generated/shared-contracts",
)


def normalize_newlines(payload: bytes) -> bytes:
    return payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def list_generated_tree_files(root: Path) -> set[str]:
    found: set[str] = set()
    for relative_dir in GENERATED_TREE_ROOTS:
        directory = root / relative_dir
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path.name in HANDWRITTEN_GENERATED_DIR_FILES:
                continue
            found.add(path.relative_to(root).as_posix())
    return found


def compare_generated_trees(expected_root: Path, committed_root: Path) -> list[str]:
    """Return human-readable drift errors covering changed, removed, and new files."""
    expected_files = list_generated_tree_files(expected_root)
    committed_files = list_generated_tree_files(committed_root)
    declared = set(generated_relative_paths())
    errors: list[str] = []

    missing_from_generation = declared - expected_files
    if missing_from_generation:
        errors.append(
            "generator did not produce declared outputs: "
            + ", ".join(sorted(missing_from_generation))
        )

    newly_generated = expected_files - committed_files
    if newly_generated:
        errors.append(
            "newly generated files are not committed: " + ", ".join(sorted(newly_generated))
        )

    removed = committed_files - expected_files
    if removed:
        errors.append(
            "committed generated files are no longer produced: " + ", ".join(sorted(removed))
        )

    for relative in sorted(expected_files & committed_files):
        expected_bytes = normalize_newlines((expected_root / relative).read_bytes())
        committed_bytes = normalize_newlines((committed_root / relative).read_bytes())
        if expected_bytes != committed_bytes:
            errors.append(f"generated output drifted: {relative}")
    return errors
