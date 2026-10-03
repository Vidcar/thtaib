"""Application preferences, exact approvals and explicit project mutation grants."""
from __future__ import annotations

from pathlib import Path
from typing import Literal
from fnmatch import translate
import os
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from workbench_backend.inference.ids import new_id, utc_now


class PresentationPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    theme: Literal["system", "light", "dark"] = "system"
    detailed_streams: bool = False
    attention_notifications: bool = True
    success_notifications: bool = False


class PermissionGrant(BaseModel):
    id: str
    scope: Literal["session", "always"]
    thread_id: str | None = None
    project_path: str | None = None
    action: str
    arguments: dict
    created_at: str
    source_run_id: str
    # Old rows keep exact-action semantics. Only a deliberate UI/API action
    # creates the distinct project-files kind.
    kind: Literal["exact_action", "project_files"] = "exact_action"
    project_id: str | None = None
    operations: list[Literal["write_file", "edit_file"]] = Field(default_factory=list)
    excluded_paths: list[str] = Field(default_factory=list)
    # Resolved This-computer folder. Empty values never match. Old rows stay null.
    starting_folder: str | None = None


PROJECT_FILE_EXCLUSIONS = (".git", ".git/**", "**/.git", "**/.git/**")
DEFAULT_SECRET_EXCLUSIONS = (".env", ".env.*", "**/.env", "**/.env.*")
_EXCLUDED_EDIT_TOOLS = frozenset({"write_file", "edit_file", "apply_edits"})
HOST_COMMAND_ACTIONS = frozenset({"execute", "start_command", "execute_skill_script", "start_preview"})


def is_host_command_action(name: str, arguments: dict) -> bool:
    """Custom preview argv uses the host; a confined static HTML entry does not."""
    return name in HOST_COMMAND_ACTIONS and (
        name != "start_preview" or isinstance(arguments, dict) and arguments.get("command") is not None
    )


class ProjectFileGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(min_length=1)
    operations: list[Literal["write_file", "edit_file"]] = Field(default_factory=lambda: ["write_file", "edit_file"], min_length=1)
    excluded_paths: list[str] = Field(default_factory=lambda: list(DEFAULT_SECRET_EXCLUSIONS), max_length=128)

    @field_validator("operations")
    @classmethod
    def unique_operations(cls, values):
        return list(dict.fromkeys(values))

    @field_validator("excluded_paths")
    @classmethod
    def relative_exclusions(cls, values):
        result = []
        for value in values:
            value = value.strip().replace("\\", "/")
            if (not value or len(value) > 512 or any(ord(char) < 32 for char in value)
                    or value.startswith(("/", "~")) or ":" in value
                    or any(part in {".", "..", ""} for part in value.rstrip("/").split("/"))):
                raise ValueError("Exclusions must be project-relative paths or glob patterns without traversal.")
            if value.endswith("/"):
                value += "**"
            if value not in result:
                result.append(value)
        return result


class MatchedPermissionGrant(PermissionGrant):
    """The particular grant used for a tool call, retained even after revocation."""

    display_name: str


def matched_permission_snapshot(grant: PermissionGrant, run) -> MatchedPermissionGrant:
    def compact(value: str) -> str:
        value = " ".join(value.split())
        return value if len(value) <= 96 else value[:93] + "…"

    args = grant.arguments
    path = args.get("file_path")
    if grant.kind == "project_files":
        label = "Project file changes"
    elif grant.action == "execute":
        command = args.get("command")
        label = "Run " + compact(command) if isinstance(command, str) and command else "Run command"
    elif grant.action in {"write_file", "edit_file"}:
        verb = {"write_file": "Write", "edit_file": "Edit"}[grant.action]
        label = f"{verb} {compact(path)}" if isinstance(path, str) and path else f"{verb} file"
    else:
        label = grant.action
        for connection in run.connection_snapshots:
            selected = next((tool for tool in connection.tools if tool.name == grant.action), None)
            if selected is not None:
                label = f"{connection.name} · {selected.remote_name}"
                break
    scope = "Always allow" if grant.scope == "always" else "This session"
    return MatchedPermissionGrant(**grant.model_dump(mode="json"), display_name=f"{label} · {scope}")


def tool_authorization_metadata(run, tool_call_id: str) -> dict:
    """Project recorded authority; never guess a grant for source-only history."""
    if run.tool_authorizations.get(tool_call_id) != "saved_permission":
        return {}
    metadata = {"authorization_source": "saved_permission"}
    grant = run.tool_authorization_grants.get(tool_call_id)
    if grant is not None:
        metadata["authorization_grant"] = grant.model_dump(mode="json")
    return metadata


class PreferenceStore:
    def __init__(self, store):
        self.store = store

    def preferences(self) -> PresentationPreferences:
        with self.store._lock:
            row = self.store._conn.execute("SELECT payload FROM presentation_preferences WHERE id=1").fetchone()
        return PresentationPreferences.model_validate_json(row[0]) if row else PresentationPreferences()

    def save_preferences(self, value: PresentationPreferences) -> PresentationPreferences:
        with self.store._lock, self.store._conn:
            self.store._conn.execute("INSERT OR REPLACE INTO presentation_preferences VALUES(1, ?)", (value.model_dump_json(),))
        return value

    def update_preferences(self, patch: PresentationPreferences) -> PresentationPreferences:
        with self.store._lock, self.store._conn:
            value = self.preferences().model_copy(update=patch.model_dump(exclude_unset=True))
            self.store._conn.execute("INSERT OR REPLACE INTO presentation_preferences VALUES(1, ?)", (value.model_dump_json(),))
        return value

    def grants(self) -> list[PermissionGrant]:
        with self.store._lock:
            rows = self.store._conn.execute("SELECT payload FROM permission_grants ORDER BY id").fetchall()
        return [PermissionGrant.model_validate_json(row[0]) for row in rows]

    def revoke(self, grant_id: str) -> None:
        with self.store._lock, self.store._conn:
            self.store._conn.execute("DELETE FROM permission_grants WHERE id=?", (grant_id,))

    def notification_claim(self, identity: str) -> bool:
        with self.store._lock, self.store._conn:
            cursor = self.store._conn.execute("INSERT OR IGNORE INTO attention_receipts VALUES (?, ?)", (identity, utc_now()))
            return cursor.rowcount == 1

    def notification_sent(self, identity: str) -> bool:
        with self.store._lock:
            return self.store._conn.execute("SELECT 1 FROM attention_receipts WHERE identity=?", (identity,)).fetchone() is not None

    def dismiss_attention(self, identity: str) -> None:
        self._dismiss_keys([f"id:{identity}"])

    def dismiss_runs(self, run_ids: list[str]) -> None:
        self._dismiss_keys([f"run:{run_id}" for run_id in run_ids if run_id])

    def attention_hidden(self, identity: str, run_id: str) -> bool:
        with self.store._lock:
            row = self.store._conn.execute(
                "SELECT 1 FROM attention_dismissals WHERE key IN (?, ?) LIMIT 1",
                (f"id:{identity}", f"run:{run_id}"),
            ).fetchone()
        return row is not None

    def _dismiss_keys(self, keys: list[str]) -> None:
        if not keys:
            return
        now = utc_now()
        with self.store._lock, self.store._conn:
            self.store._conn.executemany(
                "INSERT OR REPLACE INTO attention_dismissals VALUES (?, ?)",
                [(key, now) for key in keys],
            )

    def confirm_host_shell(self, thread_id: str) -> None:
        """Remember that this chat approved This computer. Reject does not call this."""
        if not thread_id:
            raise ValueError("This computer confirmation requires a chat.")
        with self.store._lock, self.store._conn:
            self.store._conn.execute(
                "INSERT OR REPLACE INTO host_shell_confirmations VALUES (?, ?)",
                (thread_id, utc_now()),
            )

    def host_shell_confirmed(self, thread_id: str | None) -> bool:
        if not thread_id:
            return False
        with self.store._lock:
            row = self.store._conn.execute(
                "SELECT 1 FROM host_shell_confirmations WHERE thread_id=?",
                (thread_id,),
            ).fetchone()
        return row is not None

    def allow(self, run, action, scope: Literal["session", "always"]) -> PermissionGrant:
        arguments = dict(action.args)
        starting_folder = None
        if is_host_command_action(action.name, action.args):
            # The card shows the resolved folder. Do not keep a model-supplied path.
            arguments.pop("starting_folder", None)
            starting_folder = resolved_starting_folder(run)
        grant = PermissionGrant(id=new_id("grant"), scope=scope,
            thread_id=run.thread_id if scope == "session" else None,
            project_path=_project(run.project_path), action=action.name,
            arguments=arguments, created_at=utc_now(), source_run_id=run.id,
            starting_folder=starting_folder)
        if scope == "session" and not grant.thread_id:
            raise ValueError("A session grant requires a saved thread.")
        with self.store._lock, self.store._conn:
            self.store._conn.execute("INSERT INTO permission_grants VALUES(?, ?)", (grant.id, grant.model_dump_json()))
        return grant

    def matches(self, run, name: str, arguments: dict) -> bool:
        return self.matching_grant(run, name, arguments) is not None

    def excluded_file_edit(self, run, name: str, arguments: dict) -> bool:
        """One edit of a path the standing project grant already excludes."""
        if name not in _EXCLUDED_EDIT_TOOLS or not isinstance(arguments, dict):
            return False
        key = arguments.get("file_path")
        if not isinstance(key, str) or not key.strip():
            return False
        standing = self._standing_project_grants(run)
        if not standing:
            return False
        patterns = list(PROJECT_FILE_EXCLUSIONS)
        for grant in standing:
            patterns.extend(grant.excluded_paths)
        return _path_is_excluded(getattr(run, "project_path", None), key, patterns)

    def matching_grant(self, run, name: str, arguments: dict) -> PermissionGrant | None:
        # Exact arguments deliberately avoid shell-prefix or inferred path grants.
        if name not in run.presented_tools or name not in run.enabled_tools:
            return None
        if self.excluded_file_edit(run, name, arguments):
            return None
        if is_host_command_action(name, arguments):
            return next((grant for grant in self.grants() if self._host_command_grant_matches(grant, run, name, arguments)), None)
        grants = self.grants()
        exact = next((grant for grant in grants if grant.kind == "exact_action" and grant.action == name and grant.arguments == arguments
            and grant.project_path == _project(run.project_path)
            and (grant.scope == "always" or grant.thread_id == run.thread_id)), None)
        if exact is not None:
            return exact
        return next((grant for grant in grants if self._project_file_match(grant, run, name, arguments)), None)

    def _host_command_grant_matches(self, grant, run, name, arguments) -> bool:
        if grant.kind != "exact_action" or grant.action != name or not isinstance(arguments, dict):
            return False
        thread_id = chat_confirmation_thread(run)
        if thread_id is not None and not self.host_shell_confirmed(thread_id):
            return False
        if grant.scope != "always" and grant.thread_id != getattr(run, "thread_id", None):
            return False
        if name == "execute":
            command = arguments.get("command")
            if not isinstance(command, str) or command != grant.arguments.get("command"):
                return False
        else:
            supplied = dict(arguments)
            supplied.pop("starting_folder", None)
            if supplied != grant.arguments:
                return False
        try:
            folder = resolved_starting_folder(run)
        except ValueError:
            return False
        return _same_folder(grant.starting_folder, folder)

    def _standing_project_grants(self, run) -> list[PermissionGrant]:
        project_path = getattr(run, "project_path", None)
        if not project_path:
            return []
        from workbench_backend.agents.harness_backend import canonical_root
        try:
            root = canonical_root(project_path)
        except (OSError, RuntimeError, ValueError):
            return []
        found = []
        for grant in self.grants():
            if grant.kind != "project_files" or not grant.project_path:
                continue
            try:
                if canonical_root(grant.project_path) == root:
                    found.append(grant)
            except (OSError, RuntimeError, ValueError):
                continue
        return found

    def allow_project_files(self, project, request: ProjectFileGrantRequest) -> PermissionGrant:
        """Save an explicit human-granted mutation scope, never shell authority."""
        grant = PermissionGrant(id=new_id("grant"), kind="project_files", scope="always",
            project_id=project.id, project_path=_project(project.path), action="project_files",
            arguments={}, created_at=utc_now(), source_run_id="settings",
            operations=request.operations,
            excluded_paths=list(dict.fromkeys([*PROJECT_FILE_EXCLUSIONS, *request.excluded_paths])))
        with self.store._lock, self.store._conn:
            existing = next((value for value in self.grants() if value.kind == "project_files"
                and value.project_id == grant.project_id and value.project_path == grant.project_path
                and set(value.operations) == set(grant.operations) and set(value.excluded_paths) == set(grant.excluded_paths)), None)
            if existing is not None:
                return existing
            self.store._conn.execute("INSERT INTO permission_grants VALUES(?, ?)", (grant.id, grant.model_dump_json()))
        return grant

    def _project_file_match(self, grant, run, name, arguments) -> bool:
        if (grant.kind != "project_files" or name not in grant.operations
                or name not in {"write_file", "edit_file"} or not run.project_path
                or not grant.project_path or not isinstance(arguments.get("file_path"), str)):
            return False
        # Resolve the concrete target again, including junction/symlink parents.
        # Routed knowledge/results can never acquire project write authority.
        from workbench_backend.agents.harness_backend import canonical_root, is_reserved_framework_path, resolve_project_tool_path
        key = arguments["file_path"]
        if is_reserved_framework_path(key):
            return False
        try:
            if canonical_root(grant.project_path) != canonical_root(run.project_path):
                return False
            project = self.store.get_project(grant.project_id) if grant.project_id else None
            if project is None or not project.active or canonical_root(project.path) != canonical_root(grant.project_path):
                return False
            target = resolve_project_tool_path(grant.project_path, key)
            relative = target.relative_to(Path(grant.project_path).resolve()).as_posix()
            supplied = key.lstrip("/").replace("\\", "/")
        except (ValueError, OSError, RuntimeError):
            return False
        if os.name == "nt":
            relative = relative.casefold()
            supplied = supplied.casefold()
        exclusions = [*PROJECT_FILE_EXCLUSIONS, *grant.excluded_paths]
        return not any(_excluded(path, pattern.casefold() if os.name == "nt" else pattern)
            for path in (relative, supplied) for pattern in exclusions)

    def matching_grant_by_id(self, run, name: str, arguments: dict, grant_id: str) -> PermissionGrant | None:
        if name not in run.presented_tools or name not in run.enabled_tools:
            return None
        grant = next((value for value in self.grants() if value.id == grant_id), None)
        if grant is None:
            return None
        if self.excluded_file_edit(run, name, arguments):
            return None
        if is_host_command_action(name, arguments):
            return grant if self._host_command_grant_matches(grant, run, name, arguments) else None
        if grant.kind == "project_files":
            return grant if self._project_file_match(grant, run, name, arguments) else None
        return grant if (grant.action == name and grant.arguments == arguments
            and grant.project_path == _project(run.project_path)
            and (grant.scope == "always" or grant.thread_id == run.thread_id)) else None


def chat_confirmation_thread(run) -> str | None:
    """Chat threads confirm This computer. A direct run's checkpoint id does not."""
    if getattr(run, "source_surface", None) != "chat":
        return None
    thread_id = getattr(run, "thread_id", None)
    return thread_id if isinstance(thread_id, str) and thread_id.strip() else None


def resolved_starting_folder(run) -> str:
    """Project folder, or the resolved user profile when the run has no project."""
    raw = getattr(run, "project_path", None) or str(Path.home())
    folder = str(Path(raw).expanduser().resolve())
    if not folder or folder in {".", ""}:
        raise ValueError("The starting folder must be a resolved path.")
    return folder


def _project(value: str | None) -> str | None:
    return str(Path(value).resolve()) if value else None


def _same_folder(left: str | None, right: str | None) -> bool:
    if not isinstance(left, str) or not isinstance(right, str) or not left.strip() or not right.strip():
        return False
    try:
        first = str(Path(left).expanduser().resolve())
        second = str(Path(right).expanduser().resolve())
    except (OSError, RuntimeError, ValueError):
        return False
    return first.casefold() == second.casefold() if os.name == "nt" else first == second


def _path_is_excluded(project_path: str | None, key: str, patterns: list[str]) -> bool:
    candidates = [key.lstrip("/").replace("\\", "/")]
    if project_path:
        from workbench_backend.agents.harness_backend import resolve_project_tool_path
        try:
            target = resolve_project_tool_path(project_path, key)
            candidates.append(target.relative_to(Path(project_path).resolve()).as_posix())
        except (OSError, RuntimeError, ValueError):
            pass
    if os.name == "nt":
        candidates = [item.casefold() for item in candidates]
        patterns = [item.casefold() for item in patterns]
    return any(_excluded(path, pattern) for path in candidates for pattern in patterns)


def _excluded(relative: str, pattern: str) -> bool:
    # Glob **/ includes zero subdirectories. Plain directory exclusions also
    # cover descendants. Control characters are rejected before persistence.
    expression = translate(pattern.replace("**/", "\x00")).replace("\x00", "(?:.*/)?")
    return re.fullmatch(expression, relative) is not None or relative.startswith(pattern.rstrip("/") + "/")
