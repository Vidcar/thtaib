"""Per-turn tool disclosure around the existing native graph and tool node.

The accepted ``presented_tools`` list remains the authorization envelope. This
module only chooses which of those schemas a model step receives.
"""
from __future__ import annotations

import copy
import base64
import hashlib
import json
import binascii
import asyncio
import re
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from deepagents.middleware.filesystem import FilesystemMiddleware
from langchain.agents.middleware import AgentMiddleware, AgentState, ModelRequest, TodoListMiddleware
from langchain.agents.middleware.types import PrivateStateAttr
from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, Field
from workbench_backend.agents.tool_catalogue import TOOL_PRESENTATIONS, CHECKLIST_DESCRIPTION, model_description_overrides, presentation
from workbench_backend.agents.tool_schema import model_tool_schema
from langgraph.types import Command, Overwrite
from typing_extensions import NotRequired

from workbench_backend.agents.execution_policy import plan_tool_names
from workbench_backend.agents.tools import tool_name
from workbench_backend.errors import HarnessError

FIND_TOOLS = "find_tools"
DISCLOSED_TOOLS = "disclosed_tools"
DISCOVERY_LIMIT = 5
COMPACT_DESCRIPTIONS = model_description_overrides()


class FindTools(BaseModel):
    # Native ToolNode supplies ToolRuntime alongside this public input model.
    # BaseTool preserves injected keys after validating the model fields.
    model_config = ConfigDict(extra="ignore")
    query: str = Field(min_length=1, max_length=1000, description="Task wording, alias, or exact tool/connection operation name.")
    group: str | None = Field(default=None, max_length=120, description="Optional project, shell, browser, windows, preview, knowledge, planning, input, diagnostics, connections, or selected connection name/id.")
    cursor: str | None = Field(default=None, max_length=2048, description="Returned next_cursor with the same query/group. Omit to prefer undisclosed matches.")



def has_input_policy(run: Any) -> bool:
    return getattr(run, "input_policy", None) is not None


def deferred_tools(run: Any) -> bool:
    policy = getattr(run, "input_policy", None)
    return bool(policy is not None and policy.tool_loading == "when_needed")


def authorized_tool_names(run: Any) -> set[str]:
    if not run.presented_tools:
        return set()
    allowed = set(run.presented_tools)
    if run.framework_read_paths:
        allowed.add("read_file")
    policy = getattr(run, "input_policy", None)
    if policy is not None:
        allowed.difference_update(source.removeprefix("tool:") for source in policy.excluded_sources if source.startswith("tool:"))
    if run.work_mode == "plan":
        allowed.intersection_update(plan_tool_names(run.connection_snapshots))
    return allowed


def bootstrap_tool_names(run: Any) -> set[str]:
    allowed = authorized_tool_names(run)
    policy = getattr(run, "input_policy", None)
    if policy is None or policy.tool_loading == "always":
        return allowed
    return allowed.intersection({FIND_TOOLS, "ask_user", "read_file", "read_reference", *policy.pinned_tools})


def always_skill_dependencies(run: Any, plan: Any) -> tuple[set[str], set[str]]:
    """Validate pre-included skills against the final accepted capability envelope."""
    from workbench_backend.agents.input_sources import skill_selection_error
    tools, connections = set(), set()
    if not has_input_policy(run):
        return tools, connections
    allowed = set(authorized_tool_names(run))
    # The automatic framework reader shares the read_file name. It is not the
    # project reader a skill can require.
    presented = set(getattr(run, "presented_tools", ()) or ())
    if getattr(run, "framework_read_paths", None) and "read_file" not in presented:
        allowed.discard("read_file")
    selected_connections = {item.id: item for item in run.connection_snapshots}
    for reference in plan.references:
        if reference.kind != "skill" or reference.mode != "always":
            continue
        error = skill_selection_error(reference, tool_names=allowed,
            connection_ids=selected_connections, project_bound=bool(run.project_path))
        if error is not None:
            raise error
        for connection_id in reference.required_connections:
            snapshot = selected_connections[connection_id]
            if not allowed.intersection(tool.name for tool in snapshot.tools):
                if not snapshot.tools:
                    raise HarnessError("Test this selected connection, then start a new message to accept its tool manifest.",
                        code="connection_manifest_required", status_code=409)
                raise HarnessError(f"Enable a tool from required connection {connection_id} before including this skill.",
                    code="skill_selection_required", status_code=409)
        tools.update(reference.required_tools)
        connections.update(reference.required_connections)
    return tools, connections


def discovery_context(run: Any) -> str:
    if not deferred_tools(run) or FIND_TOOLS not in authorized_tool_names(run):
        return ""
    connections = ", ".join(item.name for item in run.connection_snapshots)
    text = "Find selected tools with find_tools(query, group?, cursor?). Each batch loads at most five matches. Follow next_cursor with the same query/group; repeating without cursor prefers undisclosed matches. Pinned tools are already available; discovery grants no access."
    if connections:
        text += " Selected connections: " + connections + "."
    return text


def _discovery_score(query: str, name: str, description: str) -> int:
    """Prefer task families and name terms before weak prose matches."""
    terms = set(re.findall(r"[\w]+", query.casefold())) - {"tool", "tools", "use", "the", "a", "to"}
    name_terms = set(name.casefold().split("_"))
    score = 8 * len(terms.intersection(name_terms))
    score += sum(1 for term in terms if term in description.casefold())
    from workbench_backend.agents.tools import FILESYSTEM_TOOL_NAMES, SHELL_TOOL_NAMES
    browser_intent = bool(terms.intersection({"browser", "chrome", "webpage", "dom"}) or any(term.startswith("browser_") for term in terms))
    windows_intent = bool(terms.intersection({"desktop", "windows", "window", "winapp"}) or any(term.startswith("desktop_") for term in terms))
    file_intent = bool(terms.intersection({"file", "files", "folder", "folders", "directory", "filesystem", "project"}))
    if file_intent and not browser_intent and not windows_intent:
        if name in FILESYSTEM_TOOL_NAMES:
            score += 40
        elif name.startswith(("browser_", "desktop_")):
            score = 0
    if browser_intent and name.startswith("browser_"):
        score += 40
    if windows_intent and name.startswith("desktop_"):
        score += 40
    if terms.intersection({"shell", "command", "powershell", "terminal", "execute"}) and name in SHELL_TOOL_NAMES:
        score += 40
    if name.casefold() in terms or query.strip().casefold() == name.replace("_", " ").casefold():
        score += 1000
    return score


def projectless_virtual_read_paths(run: Any) -> list[str]:
    """Virtual routes a projectless ``ls`` / ``read_file`` may open.

    These are selected knowledge or capture routes, not a project folder.
    The list matches the projectless allow checks in the tool middleware.
    """

    from workbench_backend.agents.memory_skills import knowledge_routes_selected

    paths: list[str] = []
    if knowledge_routes_selected(getattr(run, "memory_version_refs", None), getattr(run, "skill_version_refs", None)):
        paths.extend(["/memories/", "/skills/", "/large_tool_results/", "/conversation_history/", "/retrieved/"])
    if getattr(run, "capture_routes_enabled", False):
        paths.append("/captures/")
    return paths


def _projectless_reader_limit(virtual_read_paths: list[str] | None) -> str:
    routes = [path for path in (virtual_read_paths or []) if path]
    limit = "This run has no project folder. Project files are not authorized. / is not a project root."
    if routes:
        return "Only these virtual routes are permitted: " + ", ".join(routes) + ". " + limit
    return "No project or knowledge route is authorized. " + limit


def compact_tool(
    tool: Any,
    *,
    framework_read_paths: list[str] | None = None,
    project_bound: bool = True,
    virtual_read_paths: list[str] | None = None,
) -> Any:
    """Project schema documentation only; native executor validation is untouched."""
    if not isinstance(tool, BaseTool):
        return tool
    schema = tool.tool_call_schema
    schema = copy.deepcopy(schema if isinstance(schema, dict) else schema.model_json_schema())
    # Schema annotations and literal data are retained. Removing every title
    # key also removes a legitimate argument named title and corrupts defaults.
    properties = schema.get("properties", {})
    framework_reader = tool.name == "read_file" and bool(framework_read_paths)
    projectless_reader = not project_bound and tool.name in {"ls", "read_file"} and not framework_reader
    if tool.name in {"ls", "read_file", "write_file", "edit_file", "glob", "grep"} and not projectless_reader:
        for name in ("path", "file_path"):
            if name in properties:
                properties[name]["description"] = "Project-relative path, or an explicitly supplied framework virtual path. / is the project root."
    if tool.name == "execute" and "command" in properties:
        properties["command"]["description"] = "Host shell command in the bound project; cmd.exe syntax on Windows."
    description = COMPACT_DESCRIPTIONS.get(tool.name, tool.description)
    if framework_reader:
        paths = ", ".join(framework_read_paths or [])
        description = "Read framework-saved results or history with zero-based line pagination. Only these paths are permitted: " + paths + ". Project and knowledge files are not authorized by this reader."
        if "file_path" in properties:
            properties["file_path"]["description"] = "A supplied framework virtual path under: " + paths + "."
    elif projectless_reader:
        limit = _projectless_reader_limit(virtual_read_paths)
        if tool.name == "ls":
            description = "List immediate entries in an authorized virtual directory. " + limit
        else:
            description = "Read an authorized virtual file with zero-based line pagination. " + limit
        for name in ("path", "file_path"):
            if name in properties:
                properties[name]["description"] = limit
    return tool.model_copy(update={"description": description, "args_schema": schema})


def input_tool_schemas(names: list[str], *, extra_tools: Any = ()) -> dict[str, dict[str, Any]]:
    """Cold built-in schema inspection; never builds a graph or invokes a tool."""
    from deepagents.middleware.filesystem import LsSchema, ReadFileSchema, WriteFileSchema, EditFileSchema, DeleteSchema, GlobSchema, GrepSchema, ExecuteSchema
    from langchain.agents.middleware.todo import WriteTodosInput
    from deepagents.middleware.subagents import TaskToolSchema
    from workbench_backend.assets.tools import AttachmentRead
    from workbench_backend.agents.retrieval import DocumentSearch
    from workbench_backend.agents.memory_skills import ReferenceRead
    from workbench_backend.agents.tool_results import ResultReadInput
    from workbench_backend.agents.file_operations import ApplyEditsInput
    from workbench_backend.agents.skill_scripts import SkillScriptInput
    from workbench_backend.connections.resources import ResourceListInput, ResourceReadInput
    from workbench_backend.agents.managed_commands import ManagedCommandService, COMMAND_TOOL_NAMES
    from types import SimpleNamespace
    from workbench_backend.agents.tools import ENABLED_TOOLS, memory_proposal_tool
    schema_types = {"ls": LsSchema, "read_file": ReadFileSchema, "write_file": WriteFileSchema,
        "edit_file": EditFileSchema, "delete": DeleteSchema, "apply_edits": ApplyEditsInput,
        "glob": GlobSchema, "grep": GrepSchema, "execute": ExecuteSchema, "execute_skill_script": SkillScriptInput,
        "write_todos": WriteTodosInput, "read_attachment": AttachmentRead, "search_knowledge": DocumentSearch,
        "task": TaskToolSchema, "read_reference": ReferenceRead, "read_tool_result": ResultReadInput,
        "list_connection_resources": ResourceListInput, "read_connection_resource": ResourceReadInput}
    definitions = dict(ENABLED_TOOLS)
    # The owning service constructs its typed tool definitions without starting
    # a process. Inspection shares exactly the executor's argument schemas.
    if set(names).intersection(COMMAND_TOOL_NAMES):
        cold_run = SimpleNamespace(project_path="schema-only", work_mode="work", tool_mode=None, presented_tools=list(COMMAND_TOOL_NAMES))
        definitions.update({tool.name: tool for tool in ManagedCommandService(None).tools_for_run(cold_run)})
    for name, schema in schema_types.items():
        definitions[name] = StructuredTool(name=name, description=COMPACT_DESCRIPTIONS.get(name,
            "Delegate a self-contained task to a selected helper. The helper shares this input's access bounds."), args_schema=schema)
    definitions["propose_memory"] = memory_proposal_tool("", None)
    definitions[FIND_TOOLS] = StructuredTool(name=FIND_TOOLS,
        description="Find selected tools for a task or tool name. Matching tools become available with their schemas. Discovery grants no access.",
        args_schema=FindTools)
    for item in extra_tools:
        if isinstance(item, BaseTool):
            definitions[item.name] = item
        elif hasattr(item, "input_schema"):
            definitions[item.name] = StructuredTool(name=item.name, description=item.description, args_schema=item.input_schema)
    return {name: model_tool_schema(compact_tool(definitions[name])) for name in names if name in definitions}


def _merge_disclosed(left: list[str], right: list[str]) -> list[str]:
    return list(dict.fromkeys([*left, *right]))


class ToolDisclosureState(AgentState):
    disclosed_tools: NotRequired[Annotated[list[str], PrivateStateAttr, _merge_disclosed]]


class ToolDisclosureMiddleware(AgentMiddleware):
    state_schema = ToolDisclosureState

    def __init__(self, run: Any, *, loader: Any = None, on_setup: Callable[..., Awaitable[bool]] | None = None,
                 ensure_approval: Callable[[str], None] | None = None):
        self.run = run
        self.loader = loader
        self.on_setup = on_setup
        self.ensure_approval = ensure_approval
        self.reference_requirements: dict[str, Any] = {}
        self._definitions: dict[str, BaseTool] = {}
        self._metadata = {name: row.description + " " + " ".join(row.aliases) for name, row in TOOL_PRESENTATIONS.items()}
        self._groups = {name: row.group for name, row in TOOL_PRESENTATIONS.items()}
        self._remote_names = {}
        for connection in run.connection_snapshots:
            for item in connection.tools:
                self._metadata[item.name] = f"{connection.name}: {item.remote_name}. {item.description}"
                self._groups[item.name] = connection.id
                self._remote_names[item.name] = item.remote_name
        self.tools = [StructuredTool.from_function(name=FIND_TOOLS,
            description="Find selected tools for a task or tool name. Matching tools become available with their schemas. Discovery grants no access.",
            coroutine=self._find_tools, args_schema=FindTools)] if FIND_TOOLS in authorized_tool_names(run) else []

    def before_agent(self, state, runtime, config):
        # A fresh turn runs this hook; an interrupt resume restarts its saved
        # node and retains the activation state without re-running this hook.
        return {DISCLOSED_TOOLS: Overwrite([])}

    async def abefore_agent(self, state, runtime, config):
        return self.before_agent(state, runtime, config)

    def visible_names(self, state: dict[str, Any]) -> set[str]:
        allowed = authorized_tool_names(self.run)
        return bootstrap_tool_names(self.run) | allowed.intersection(state.get(DISCLOSED_TOOLS) or [])

    def prepare_request(self, request: ModelRequest) -> ModelRequest:
        for item in request.tools:
            if isinstance(item, BaseTool) and item.name in authorized_tool_names(self.run):
                self._definitions[item.name] = item
        if self.loader is not None:
            self._definitions.update(self.loader.definitions)
        visible = self.visible_names(request.state)
        definitions = {tool_name(item): item for item in request.tools}
        definitions.update(self._definitions)
        project_bound = bool(getattr(self.run, "project_path", None))
        framework_read_paths = self.run.framework_read_paths if "read_file" not in self.run.presented_tools else None
        virtual_read_paths = None if project_bound or framework_read_paths else projectless_virtual_read_paths(self.run)
        return request.override(tools=[compact_tool(
            item, framework_read_paths=framework_read_paths, project_bound=project_bound, virtual_read_paths=virtual_read_paths)
            for name, item in definitions.items() if name in visible])

    def wrap_model_call(self, request, handler):
        return handler(self.prepare_request(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self.prepare_request(request))

    async def _find_tools(self, query: str, runtime: ToolRuntime, group: str | None = None, cursor: str | None = None) -> Command:
        """Activate bounded name/description matches inside the accepted envelope."""
        if self.on_setup is not None and not await self.on_setup(FIND_TOOLS, None, runtime):
            return Command(update={"messages": [ToolMessage(content="Setup was skipped; no additional tools were disclosed.",
                name=FIND_TOOLS, tool_call_id=runtime.tool_call_id)]})
        allowed = authorized_tool_names(self.run) - {FIND_TOOLS}
        terms = set(re.findall(r"[\w]+", query.casefold())) - {"tool", "tools", "use", "the", "a", "to"}
        for connection in self.run.connection_snapshots:
            # An absent manifest cannot be obtained as a side effect of a weak
            # prose match. The selected feature itself must be requested.
            explicit_connection = (connection.id.casefold() in terms or query.strip().casefold() == connection.name.casefold())
            if connection.tools or not explicit_connection:
                continue
            error = HarnessError("Test this selected connection in Settings, then start a new message to accept its tool manifest.",
                code="connection_manifest_required", status_code=409)
            if self.on_setup is not None:
                await self.on_setup("connection:" + connection.id, error, runtime)
            return Command(update={"messages": [ToolMessage(content=str(error),
                name=FIND_TOOLS, tool_call_id=runtime.tool_call_id)]})
        group_key = group.strip().casefold() if group else None
        connection_groups = {item.id for item in self.run.connection_snapshots
            if group_key in {item.id.casefold(), item.name.casefold()}}
        scores = []
        for name in allowed:
            family = self._groups.get(name, presentation(name).group if presentation(name) else "other")
            if group_key and not (family == group_key or family in connection_groups
                or group_key == "connections" and name in self._remote_names):
                continue
            description = self._metadata.get(name, getattr(self._definitions.get(name), "description", ""))
            score = _discovery_score(query, name, description)
            if remote_name := self._remote_names.get(name):
                score = max(score, _discovery_score(query, remote_name, description))
            if score:
                priority = {"read_file": 0, "edit_file": 1, "write_file": 2, "glob": 3, "grep": 4, "ls": 5}.get(name, 10)
                scores.append((-score, priority, name, description))
        activated = list(runtime.state.get(DISCLOSED_TOOLS) or [])
        scores.sort()
        # The cursor binds ordering and accepted capabilities, including frozen
        # connection versions/manifests. Disclosure state may grow between pages.
        identity = hashlib.sha256(json.dumps({"query": query, "group": group_key,
            "allowed": sorted(allowed), "mode": self.run.work_mode,
            "connections": [item.model_dump(mode="json") for item in self.run.connection_snapshots],
            "matches": [row[:3] for row in scores]}, sort_keys=True).encode()).hexdigest()
        offset = 0
        ordered = [row[2] for row in scores]
        if cursor:
            try:
                page = json.loads(base64.urlsafe_b64decode(cursor))
                if page["identity"] != identity or type(page["offset"]) is not int or not 0 <= page["offset"] <= len(scores):
                    raise ValueError()
                offset = page["offset"]
            except (ValueError, KeyError, TypeError, binascii.Error, UnicodeDecodeError):
                return Command(update={"messages": [ToolMessage(content="This discovery cursor no longer matches the query, group or selected capabilities. Search again without cursor.",
                    name=FIND_TOOLS, tool_call_id=runtime.tool_call_id, status="error")]})
        exact = query.strip().casefold()
        loaded = set(activated) | bootstrap_tool_names(self.run)
        # A page cursor follows stable ranking. A fresh broad search skips loaded
        # names, while an exact lookup always remains reachable.
        indices = [index for index, name in enumerate(ordered) if index >= offset and
            (cursor or name not in loaded or exact in {name.casefold(), name.replace("_", " ").casefold(), self._remote_names.get(name, "").casefold()})][:DISCOVERY_LIMIT]
        lookup = {row[2]: row for row in scores}
        matches = [lookup[ordered[index]] for index in indices]
        next_offset = indices[-1] + 1 if indices else len(ordered)
        has_more = next_offset < len(ordered)
        next_cursor = base64.urlsafe_b64encode(json.dumps({"identity": identity, "offset": next_offset}).encode()).decode() if has_more else None
        lines = []
        results = []
        for _, _, name, description in matches:
            known = name in self._definitions or name in getattr(self.loader, "definitions", {})
            if not known:
                explicit = name.casefold() in terms or query.strip().casefold() == name.replace("_", " ").casefold()
                explicit_feature = (name.startswith("browser_") and terms.intersection({"browser", "chrome"})
                    or name.startswith("desktop_") and terms.intersection({"desktop", "windows", "window", "winapp"}))
                if not explicit and not explicit_feature:
                    lines.append(f"{name}: selected; schema unavailable until setup. Request this tool by name when needed.")
                    continue
                if not await self._local_ready(name, runtime):
                    lines.append(f"{name}: setup was skipped; unavailable.")
                    continue
                if self.loader is not None and self.loader.owns(name):
                    if not await self._load(name, runtime):
                        lines.append(f"{name}: setup was skipped; unavailable.")
                        continue
                if name not in self._definitions:
                    lines.append(f"{name}: unavailable for this run.")
                    continue
            if self.ensure_approval is not None:
                self.ensure_approval(name)
            if name not in activated:
                activated.append(name)
            if name == "read_file" and "read_file" not in self.run.presented_tools and self.run.framework_read_paths:
                description = "Only these paths are permitted: " + ", ".join(self.run.framework_read_paths) + "."
            elif name in {"ls", "read_file"} and not getattr(self.run, "project_path", None):
                description = _projectless_reader_limit(projectless_virtual_read_paths(self.run))
            else:
                description = COMPACT_DESCRIPTIONS.get(name, description)
            lines.append(f"{name}: {description}")
            row = presentation(name)
            results.append({"name": name, "label": row.label if row else self._remote_names.get(name, name),
                "group": self._groups.get(name, row.group if row else "other"),
                "already_disclosed": name in set(runtime.state.get(DISCLOSED_TOOLS) or []) | bootstrap_tool_names(self.run),
                "description": description})
        if not matches:
            lines = ["No selected tools match. Try a specific task, tool name or group. Discovery cannot enable unselected tools."]
        return Command(update={DISCLOSED_TOOLS: activated, "messages": [ToolMessage(
            content=json.dumps({"query": query, "group": group, "results": results, "notice": "\n".join(lines),
                "has_more": has_more, "next_cursor": next_cursor}, ensure_ascii=False), name=FIND_TOOLS, tool_call_id=runtime.tool_call_id)]})

    async def _load(self, name: str, runtime: ToolRuntime) -> bool:
        while True:
            try:
                tool = await self.loader.load(name)
                break
            except HarnessError as exc:
                if self.on_setup is None:
                    raise
                if not await self.on_setup(name, exc, runtime):
                    return False
        self._definitions[name] = tool
        if self.ensure_approval is not None:
            self.ensure_approval(name)
        return True

    async def _local_ready(self, name: str, runtime: ToolRuntime) -> bool:
        from workbench_backend.agents.tools import FILESYSTEM_TOOL_NAMES, PROJECT_FREE_HOST_COMMANDS, SHELL_TOOL_NAMES
        project_tools = {*FILESYSTEM_TOOL_NAMES, *SHELL_TOOL_NAMES, "start_preview", "stop_preview", "preview_status"} - PROJECT_FREE_HOST_COMMANDS
        if self.run.project_path or name not in project_tools:
            return True
        if name in {"ls", "read_file"} and (self.run.framework_read_paths or self.run.memory_version_refs or self.run.skill_version_refs or self.run.capture_routes_enabled):
            return True
        error = HarnessError("Choose a project folder before using this selected tool. The current input has no authorized project.",
            code="filesystem_requires_project", status_code=409)
        if self.on_setup is None:
            raise error
        return await self.on_setup(name, error, runtime)

    async def awrap_tool_call(self, request, handler):
        name = request.tool_call["name"]
        if name not in authorized_tool_names(self.run):
            return ToolMessage(content="This tool was not selected for this input. The action was not executed.",
                name=name, tool_call_id=request.tool_call["id"], status="error")
        if name != FIND_TOOLS and self.on_setup is not None and not await self.on_setup(name, None, request.runtime):
            return ToolMessage(content="Setup was skipped; this action was not executed.", name=name,
                tool_call_id=request.tool_call["id"], status="error")
        if not await self._local_ready(name, request.runtime):
            return ToolMessage(content="Project setup was skipped; this action was not executed.", name=name,
                tool_call_id=request.tool_call["id"], status="error")
        if name == "read_file":
            path = str(request.tool_call.get("args", {}).get("file_path", "")).replace("\\", "/")
            path = path if path.startswith("/") else "/" + path
            reference = self.reference_requirements.get(path)
            if reference is not None:
                blocked = await self.require_reference_ready(reference, request.runtime)
                if blocked:
                    return ToolMessage(content=blocked, name=name,
                        tool_call_id=request.tool_call["id"], status="error")
        if self.loader is not None and self.loader.owns(name):
            if not await self._load(name, request.runtime):
                return ToolMessage(content="Setup was skipped; this action was not executed.",
                    name=name, tool_call_id=request.tool_call["id"], status="error")
            request = request.override(tool=self._definitions[name])
        return await handler(request)

    async def require_reference_ready(self, reference: Any, runtime: ToolRuntime) -> str | None:
        """Requirements restrict selected skills; they cannot select new tools."""
        from workbench_backend.agents.input_sources import skill_selection_error
        allowed = authorized_tool_names(self.run)
        connections = {item.id: item for item in self.run.connection_snapshots}
        error = skill_selection_error(reference, tool_names=allowed, connection_ids=connections,
            project_bound=bool(self.run.project_path))
        if error is not None:
            if self.on_setup is None:
                return str(error)
            if not await self.on_setup("skill:" + reference.entry_id, error, runtime):
                return "Skill setup was skipped; this skill was not used."
            return str(error)
        for name in reference.required_tools:
            if not await self._local_ready(name, runtime):
                return "Skill setup was skipped; this skill was not used."
            if self.loader is not None and self.loader.owns(name) and not await self._require_feature_ready(name, runtime):
                return "Skill setup was skipped; this skill was not used."
        for connection_id in reference.required_connections:
            snapshot = connections[connection_id]
            name = next((tool.name for tool in snapshot.tools if tool.name in allowed), None)
            if name is None:
                error = HarnessError("Test this selected connection, then start a new message to accept its tool manifest.",
                    code="connection_manifest_required", status_code=409)
                if self.on_setup is not None and not await self.on_setup("connection:" + connection_id, error, runtime):
                    return "Skill setup was skipped; this skill was not used."
                return str(error)
            if self.loader is not None and not await self._require_feature_ready(name, runtime):
                return "Skill setup was skipped; this skill was not used."
        return None

    async def _require_feature_ready(self, name: str, runtime: ToolRuntime) -> bool:
        while True:
            try:
                await self.loader.require_ready(name)
                return True
            except HarnessError as exc:
                if self.on_setup is None:
                    raise
                if not await self.on_setup(name, exc, runtime):
                    return False


class LeanFilesystemMiddleware(FilesystemMiddleware):
    """Keep native file mechanisms, filtering schemas before native guidance."""
    @property
    def name(self):
        return "FilesystemMiddleware"

    def __init__(self, *, disclosure: ToolDisclosureMiddleware | None = None,
                 request_preparer: Callable[[ModelRequest], ModelRequest] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.disclosure = disclosure
        self.request_preparer = request_preparer

    def prepare_request(self, request: ModelRequest) -> ModelRequest:
        if self.disclosure is not None:
            request = self.disclosure.prepare_request(request)
        return self.request_preparer(request) if self.request_preparer is not None else request

    def wrap_model_call(self, request, handler):
        return super().wrap_model_call(self.prepare_request(request), handler)

    async def awrap_model_call(self, request, handler):
        prepared = await asyncio.to_thread(self.prepare_request, request)
        return await super().awrap_model_call(prepared, handler)


class LeanTodoListMiddleware(TodoListMiddleware):
    def __init__(self):
        super().__init__(system_prompt="", tool_description=CHECKLIST_DESCRIPTION)

    def wrap_model_call(self, request, handler):
        return handler(request)

    async def awrap_model_call(self, request, handler):
        return await handler(request)


class DeferredToolCollection(list):
    """Run-owned service adapters; native ToolNode remains the only executor."""

    def __init__(self, run: Any, stack: Any, *, connections: Any, browser: Any = None, desktop: Any = None,
                 publish: Callable[[], None] | None = None):
        super().__init__()
        self.run, self.stack = run, stack
        self.connections, self.browser, self.desktop = connections, browser, desktop
        self.publish = publish or (lambda: None)
        self.definitions: dict[str, BaseTool] = {}
        self._loaded: dict[str, BaseTool] = {}
        self._groups: dict[str, str] = {}
        self._lock = asyncio.Lock()
        from workbench_backend.browser.service import BROWSER_TOOL_NAMES
        from workbench_backend.desktop_automation.service import DESKTOP_TOOL_NAMES
        self._groups.update({name: "browser" for name in BROWSER_TOOL_NAMES})
        self._groups.update({name: "windows" for name in DESKTOP_TOOL_NAMES})
        if browser is not None and hasattr(browser, "schema_tools_for_run"):
            try:
                self.definitions.update({tool.name: tool for tool in browser.schema_tools_for_run(run)
                    if tool.name in authorized_tool_names(run)})
            except HarnessError:
                pass  # Selected discovery supplies the actionable setup card.
        if desktop is not None:
            self.definitions.update({tool.name: tool for tool in desktop.tools_for_run(run, schema_only=True)
                if tool.name in authorized_tool_names(run)})
        for connection in run.connection_snapshots:
            for item in connection.tools:
                self._groups[item.name] = connection.id
                if item.name in authorized_tool_names(run):
                    self.definitions[item.name] = StructuredTool(name=item.name,
                        description=f"{connection.name}: {item.description}", args_schema=copy.deepcopy(item.input_schema))

    def owns(self, name: str) -> bool:
        return name in self._groups

    async def load(self, name: str) -> BaseTool:
        if name not in authorized_tool_names(self.run):
            raise HarnessError("This tool was not selected for this input.", code="tool_denied", status_code=409)
        async with self._lock:
            group = self._groups.get(name)
            await self._check_ready(name)
            if name in self._loaded:
                return self._loaded[name]
            if group == "browser":
                if self.browser is None:
                    raise HarnessError("Install the optional Browser worker in Settings.", code="browser_worker_missing", status_code=409)
                tools = await self.stack.enter_async_context(self.browser.open_tools(self.run))
            elif group == "windows":
                if self.desktop is None:
                    raise HarnessError("Windows control is unavailable. Configure it in Settings.", code="desktop_unavailable", status_code=409)
                tools = self.desktop.tools_for_run(self.run)
            else:
                snapshot = next((item for item in self.run.connection_snapshots if item.id == group), None)
                if snapshot is None:
                    raise HarnessError("The selected connection is no longer available.", code="connection_missing", status_code=409)
                scoped = self.run.model_copy(update={"connection_snapshots": [snapshot]})
                tools = await self.stack.enter_async_context(self.connections.open_tools(scoped))
            self._loaded.update({item.name: item for item in tools if item.name in authorized_tool_names(self.run)})
            self.definitions.update(self._loaded)
            if name not in self._loaded:
                code = "desktop_grant_required" if group == "windows" else "tool_unavailable"
                raise HarnessError("Repair the selected feature's setup before using this tool.", code=code, status_code=409)
            return self._loaded[name]

    async def require_ready(self, name: str) -> None:
        async with self._lock:
            await self._check_ready(name)

    async def _check_ready(self, name: str) -> None:
        if name not in authorized_tool_names(self.run):
            raise HarnessError("This tool was not selected for this input.", code="tool_denied", status_code=409)
        group = self._groups.get(name)
        if group == "windows":
            await self._ready_windows()
        elif group == "browser":
            if self.browser is None:
                raise HarnessError("Install the optional Browser worker in Settings.", code="browser_worker_missing", status_code=409)
            if hasattr(self.browser, "runtime"):
                await asyncio.to_thread(self.browser.runtime.require_installed)
        else:
            snapshot = next((item for item in self.run.connection_snapshots if item.id == group), None)
            if snapshot is None:
                raise HarnessError("The selected connection is no longer available.", code="connection_missing", status_code=409)
            await asyncio.to_thread(self.connections.validate_snapshot, snapshot)

    async def _ready_windows(self) -> None:
        from workbench_backend.desktop_automation.service import DesktopAutomationError
        from workbench_backend.desktop_automation.runtime import WinAppRuntimeError
        if self.run.desktop_access == "off":
            raise HarnessError("Select Windows access, then start a new message to accept that scope.",
                code="desktop_selection_required", status_code=409)
        if self.desktop is None:
            raise HarnessError("Configure the optional Windows worker in Settings.", code="desktop_unavailable", status_code=409)
        try:
            await asyncio.to_thread(self.desktop.runtime.command_path)
            scope, identity = await asyncio.to_thread(self.desktop.snapshot_grant, self.run.thread_id, self.run.desktop_access)
        except DesktopAutomationError as exc:
            raise HarnessError(str(exc), code=exc.code, status_code=409) from exc
        except WinAppRuntimeError as exc:
            raise HarnessError(str(exc), code="desktop_runtime_unavailable", status_code=409) from exc
        actual = ({"hwnd": identity.hwnd, "process_id": identity.process_id,
            "process_created_at": identity.process_created_at} if identity is not None else None)
        frozen = self.run.desktop_window
        if frozen is not None and actual != frozen:
            raise HarnessError("The selected target changed. Start a new message with the updated Windows target.",
                code="desktop_window_changed", status_code=409)
        if self.run.desktop_access == "selected" and actual is None:
            raise HarnessError("Choose a specific window for this selected scope.", code="desktop_window_required", status_code=409)
        if frozen is None and actual is not None:
            # A missing target within an already-selected scope can be repaired
            # once. All subsequent calls retain this exact process identity.
            from workbench_backend.agents.schemas import AgentEvent
            from workbench_backend.inference.ids import utc_now
            self.run.desktop_window = actual
            self.run.desktop_access = scope.value if hasattr(scope, "value") else scope
            self.run.events.append(AgentEvent(at=utc_now(), kind="desktop_target_bound", detail={"window": actual}))
            self.publish()


class CapabilitySetupBoundary:
    """Remember native pause order while checks re-run, without business effects."""

    def __init__(self, run: Any, publish: Callable[[], None]):
        self.run, self.publish = run, publish

    async def __call__(self, name: str, error: HarnessError | None, runtime: ToolRuntime) -> bool:
        from langgraph.types import interrupt
        from workbench_backend.agents.schemas import AgentEvent
        from workbench_backend.inference.ids import utc_now
        call_id = runtime.tool_call_id
        # Each replay uses a fresh middleware invocation but the same Python
        # instance. LangGraph's resume values are read again in stable order.
        if error is None:
            for event in self.run.events:
                if event.kind == "capability_setup_requested" and event.detail.get("call_id") == call_id:
                    response = interrupt(event.detail["interrupt"])
                    if not _setup_continue(response):
                        return False
                    if event.detail["interrupt"]["action_requests"][0]["setup"].get("requires_new_input"):
                        raise HarnessError("This repair changes the accepted selection. Start a new message with the updated setup.",
                            code="setup_new_input_required", status_code=409)
            return True
        setup = _setup_request(self.run, name, error)
        payload = {"kind": "capability_setup", "action_requests": [{"name": FIND_TOOLS,
            "args": {"tool": name}, "description": setup.message, "setup": setup.model_dump(mode="json")}],
            "review_configs": [{"action_name": FIND_TOOLS, "allowed_decisions": ["respond", "reject"]}]}
        self.run.events.append(AgentEvent(at=utc_now(), kind="capability_setup_requested",
            detail={"call_id": call_id, "interrupt": payload}))
        self.publish()
        response = interrupt(payload)
        if not _setup_continue(response):
            return False
        if setup.requires_new_input:
            raise HarnessError("This repair changes the accepted selection. Start a new message with the updated setup.",
                code="setup_new_input_required", status_code=409)
        return True


def _setup_continue(response: Any) -> bool:
    decisions = response.get("decisions", []) if isinstance(response, dict) else []
    return bool(decisions and decisions[0].get("type") == "respond" and decisions[0].get("message") == "continue")


def _setup_request(run: Any, name: str, error: HarnessError):
    from workbench_backend.agents.schemas import CapabilitySetupRequest
    from workbench_backend.browser.service import BROWSER_TOOL_NAMES
    from workbench_backend.desktop_automation.service import DESKTOP_TOOL_NAMES
    connection = next((item for item in run.connection_snapshots if item.id == name.removeprefix("connection:") or any(tool.name == name for tool in item.tools)), None)
    skill_id = name.removeprefix("skill:") if name.startswith("skill:") else None
    capability = "skill" if skill_id else "connection" if connection else "browser" if name in BROWSER_TOOL_NAMES else "windows" if name in DESKTOP_TOOL_NAMES else "tool"
    project_required = error.code in {"filesystem_requires_project", "shell_requires_project"}
    target = "project" if project_required else "knowledge" if skill_id else "settings" if connection else "windows" if capability == "windows" else "browser" if capability == "browser" else "agent"
    requires_new_input = project_required or error.code in {"connection_changed", "connection_schema_changed", "connection_manifest_required", "connection_disabled", "credential_missing", "skill_selection_required", "desktop_selection_required", "desktop_window_changed", "browser_thread_required"}
    return CapabilitySetupRequest(capability=capability, id=skill_id or (connection.id if connection else name),
        tool_names=[name], code=error.code, message=str(error),
        action="Update the selection, then start a new message." if requires_new_input else "Repair the selected feature, then continue.",
        target=target, target_id=skill_id or (connection.id if connection else None),
        requires_new_input=requires_new_input)
