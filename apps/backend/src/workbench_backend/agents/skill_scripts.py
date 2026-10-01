"""Explicit execution of an immutable selected skill resource on the owned shell."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import shlex
import sys
import uuid
from typing import Annotated

from langchain_core.tools import StructuredTool, ToolException
from pydantic import BaseModel, Field

from workbench_backend.agents.harness_backend import harness_scratch_root
from workbench_backend.knowledge.packages import safe_resource_path

MAX_SCRIPT_PACKAGE_BYTES = 10_000_000


class SkillScriptInput(BaseModel):
    entry_id: str = Field(min_length=1, description="Already selected frozen skill entry ID.")
    version_id: str = Field(min_length=1, description="Exact accepted immutable version; current saved edits do not replace it.")
    resource_path: str = Field(min_length=1, max_length=512, description="Python resource under scripts/ in that selected skill package; virtual /skills paths are not host paths.")
    resource_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$", description="Optional expected resource hash; retained manifest hash is always enforced.")
    arguments: list[Annotated[str, Field(max_length=4096, pattern=r"^[^\x00]*$")]] = Field(default_factory=list, max_length=40, description="Literal script arguments; no shell interpolation.")
    timeout_seconds: int = Field(default=120, ge=1, le=1800, description="Per-operation timeout in seconds, separate from optional whole-task budgets.")


def _command(script: Path, arguments: list[str]) -> str:
    values = [sys.executable, "-I", str(script), *arguments]
    if sys.platform != "win32":
        return shlex.join(values)
    # Encode the whole fixed invocation, not individual untrusted shell words.
    # PowerShell single-quoted literals escape only single quotes; argument
    # text can contain cmd metacharacters without becoming cmd source.
    quoted = ["'" + item.replace("'", "''") + "'" for item in values]
    source = "& " + " ".join(quoted) + "; exit $LASTEXITCODE"
    encoded = base64.b64encode(source.encode("utf-16-le")).decode("ascii")
    return "powershell -NoProfile -NonInteractive -EncodedCommand " + encoded


def skill_script_tool(service, run, backend, plan):
    def execute(entry_id, version_id, resource_path, resource_sha256=None, arguments=None, timeout_seconds=120):
        if (not run.project_path or run.work_mode == "plan" or not {"execute", "execute_skill_script"}.issubset(run.presented_tools)
                or not {"execute", "execute_skill_script"}.issubset(run.enabled_tools)):
            raise ToolException("Skill scripts require separately selected host-command access and the script operation in a bound Work-mode project.")
        reference = next((item for item in plan.references if item.entry_id == entry_id and item.version_id == version_id and item.kind == "skill" and item.mode != "off"), None)
        if reference is None or version_id not in run.skill_version_refs:
            raise ToolException("Only the already accepted selected skill version can execute; start a new input to change it.")
        try:
            relative = safe_resource_path(resource_path)
        except Exception:
            raise ToolException("Choose a safe resource path inside the selected skill package.") from None
        if not relative.startswith("scripts/") or not relative.endswith(".py"):
            raise ToolException("This script bridge supports selected scripts/*.py resources only.")
        arguments = arguments or []
        if any(len(item) > 4096 or "\x00" in item for item in arguments):
            raise ToolException("A script argument is invalid or exceeds 4096 characters.")
        provider = service._knowledge_provider() if service._knowledge_provider else None
        if provider is None:
            raise ToolException("The retained skill resource owner is unavailable.")
        version = provider.get_version(version_id)
        if version.entry_id != entry_id or version.kind != "skill":
            raise ToolException("The selected skill version identity changed.")
        resource = next((item for item in version.resources if item.path == relative), None)
        if resource is None:
            raise ToolException("The script is not declared in that frozen skill version.")
        if resource_sha256 is not None and resource_sha256 != resource.sha256:
            raise ToolException("The requested script hash differs from the frozen resource manifest.")
        source_root = reference.path.rsplit("/", 1)[0]
        frozen = dict(plan.uploads)
        uploads, size = [], 0
        for item in version.resources:
            resource_name = safe_resource_path(item.path)
            data = frozen.get(source_root + "/" + resource_name)
            if data is None or len(data) != item.size_bytes or hashlib.sha256(data).hexdigest() != item.sha256:
                raise ToolException("A frozen selected skill resource is missing or changed; no script was materialized.")
            size += len(data)
            if size > MAX_SCRIPT_PACKAGE_BYTES:
                raise ToolException("The selected execution package exceeds its explicit byte limit.")
            uploads.append((resource_name, data))
        # Every resource is validated before creating the owned execution area.
        owner = run.id if run.parent_run_id else run.thread_id or run.id
        execution_root = harness_scratch_root(service.manager.paths, owner) / "skill_execution"
        execution_root.mkdir(parents=True, exist_ok=True)
        if execution_root.is_symlink() or execution_root.is_junction():
            raise ToolException("The owned script execution directory was replaced by a link.")
        directory = execution_root / uuid.uuid4().hex
        directory.mkdir()
        for resource_name, data in uploads:
            destination = directory / resource_name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        script = directory / relative
        if hashlib.sha256(script.read_bytes()).hexdigest() != resource.sha256:
            raise ToolException("The materialized script changed before execution.")
        result = backend.execute(_command(script, arguments), timeout=timeout_seconds)
        identity = {"entry_id": entry_id, "version_id": version_id, "resource_path": relative, "resource_sha256": resource.sha256,
            "exit_code": result.exit_code, "truncated": result.truncated, "output": result.output,
            "execution_scope": "owned selected-resource directory; real host authority, not a sandbox"}
        return json.dumps(identity, ensure_ascii=False), {"exit_code": result.exit_code, "resource_identity": {key: identity[key] for key in ("entry_id", "version_id", "resource_path", "resource_sha256")}}
    return StructuredTool.from_function(name="execute_skill_script", func=execute, args_schema=SkillScriptInput,
        response_format="content_and_artifact", handle_tool_error=True,
        description="Run a Python scripts/ resource from an already selected frozen skill version after manifest/hash validation and owned materialization. Requires separately selected execute authority and this operation's approval. Arguments are literal; output includes true exit status and retained evidence. This is real host execution.")
