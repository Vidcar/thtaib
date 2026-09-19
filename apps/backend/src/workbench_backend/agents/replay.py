"""Recorded-tool fixture identity and isolated reconstruction (LAB-003 / #67).

Recorded mode replays claimed tools from fixtures. It is not a live integration
and is not proof of current live behaviour.

Invocation identity is the tool name plus canonical arguments. Fixtures are
consumed in capture order among matches. Two same-tool calls with different
arguments cannot silently consume each other's results.

Matched ``write_file`` / ``edit_file`` fixtures may reconstruct recorded bytes
only under the replay workspace (the run ``project_path`` / restored Lab
workspace). That write is fixture application, not a Deep Agents
``FilesystemBackend`` invocation, and never targets the parent workspace.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from workbench_backend.errors import ReplayError

PATH_ARG_KEYS = frozenset({"file_path", "path"})
RECONSTRUCTED_TOOLS = frozenset({"write_file", "edit_file"})

RECONSTRUCTION_NOTE = (
    "Fixture-driven reconstruction is isolated to the replay workspace. "
    "It is not a live FilesystemBackend invocation and is not proof of a "
    "current live integration."
)

REPLAY_FAILURE_CODES = frozenset(
    {
        "recorded_fixture_missing",
        "recorded_fixture_exhausted",
        "recorded_fixture_arg_mismatch",
        "recorded_replay_unsupported",
    }
)


def canonical_args(args: Any) -> Any:
    """JSON-stable argument identity. ``None`` values are omitted."""

    if args is None:
        return {}
    if isinstance(args, dict):
        normalised: dict[str, Any] = {}
        for key in sorted(str(item) for item in args):
            value = args.get(key)
            if value is None:
                continue
            if key in PATH_ARG_KEYS and isinstance(value, str):
                normalised[key] = _canonical_path(value)
            else:
                normalised[key] = canonical_args(value)
        return normalised
    if isinstance(args, list):
        return [canonical_args(item) for item in args]
    return args


def invocation_identity(name: str, args: Any) -> tuple[str, Any]:
    return str(name), canonical_args(args)


def isolated_replay_path(workspace: Path, virtual_path: str) -> Path:
    """Resolve a virtual tool path inside the replay workspace only."""

    relative = _canonical_path(virtual_path)
    if not relative or relative in {".", ".."} or relative.startswith("../"):
        raise ReplayError(
            "recorded-tool reconstruction path is empty or escapes the replay workspace.",
            code="recorded_replay_unsupported",
            status_code=409,
        )
    root = workspace.expanduser().resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise ReplayError(
            "recorded-tool reconstruction refused a path outside the replay workspace.",
            code="recorded_replay_unsupported",
            status_code=409,
            details={"path": virtual_path},
        )
    return target


def apply_recorded_reconstruction(
    name: str,
    args: dict[str, Any],
    replay_workspace: str | Path | None,
) -> list[dict[str, str]]:
    """Apply matched write/edit fixture args inside the replay workspace only."""

    if name not in RECONSTRUCTED_TOOLS or not replay_workspace:
        return []
    raw_path = args.get("file_path") or args.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return []
    target = isolated_replay_path(Path(replay_workspace), raw_path)
    if name == "write_file":
        content = args.get("content")
        if not isinstance(content, str):
            return []
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return [{"tool": name, "path": str(target), "note": RECONSTRUCTION_NOTE}]
    if name == "edit_file":
        old = args.get("old_string")
        new = args.get("new_string")
        if not isinstance(old, str) or not isinstance(new, str) or not target.is_file():
            return []
        text = target.read_text(encoding="utf-8")
        replace_all = bool(args.get("replace_all"))
        if replace_all:
            updated = text.replace(old, new)
        elif text.count(old) != 1:
            return []
        else:
            updated = text.replace(old, new, 1)
        target.write_text(updated, encoding="utf-8")
        return [{"tool": name, "path": str(target), "note": RECONSTRUCTION_NOTE}]
    return []


class FixtureBank:
    """Consume fixtures by invocation identity (name + canonical args)."""

    def __init__(self, fixtures: list[dict[str, Any]]) -> None:
        self._remaining = [dict(item) for item in fixtures]
        self._supplied_names = {str(item.get("name")) for item in fixtures}

    def take(self, name: str, args: Any = None) -> str:
        wanted = invocation_identity(name, args)
        same_name_indexes = [
            index
            for index, item in enumerate(self._remaining)
            if str(item.get("name")) == name
        ]
        if not same_name_indexes:
            if name in self._supplied_names:
                raise ReplayError(
                    f"recorded-tool fixtures for {name} are exhausted. "
                    "This is not a live tool call and is not live-equivalent success.",
                    code="recorded_fixture_exhausted",
                    status_code=409,
                    details={"name": name, "args": canonical_args(args)},
                )
            raise ReplayError(
                f"recorded-tool has no fixture for {name}. "
                "This is not a live tool call and is not live-equivalent success.",
                code="recorded_fixture_missing",
                status_code=409,
                details={"name": name, "args": canonical_args(args)},
            )
        for index in same_name_indexes:
            item = self._remaining[index]
            if invocation_identity(str(item.get("name")), item.get("args") or {}) == wanted:
                consumed = self._remaining.pop(index)
                result = consumed.get("result")
                return result if isinstance(result, str) else str(result)
        raise ReplayError(
            f"recorded-tool fixture arguments for {name} do not match this invocation. "
            "Same-tool fixtures with different arguments are not interchangeable. "
            "This is not a live tool call and is not live-equivalent success.",
            code="recorded_fixture_arg_mismatch",
            status_code=409,
            details={"name": name, "args": canonical_args(args)},
        )


def is_replay_failure(error: str | None, code: str | None = None) -> bool:
    if code in REPLAY_FAILURE_CODES:
        return True
    if not error:
        return False
    lowered = error.lower()
    return "recorded-tool" in lowered and any(
        token in lowered
        for token in ("exhausted", "no fixture", "do not match", "not a live tool")
    )


def _canonical_path(value: str) -> str:
    return value.replace("\\", "/").lstrip("/")
