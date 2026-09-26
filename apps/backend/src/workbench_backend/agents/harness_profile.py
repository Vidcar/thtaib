"""Ordinary Chat exclusions for the embedded Deep Agents harness.

Deep Agents adds ``task`` and recursive ``delete`` unless a harness profile
says otherwise. Extra ``tools=`` are additive, and a parent-only catalogue
filter is not inherited by a compiled child. Registration follows the
provider the model actually reports, so the same switch applies to the
parent and to a child compiled with that model.
"""

from __future__ import annotations

from collections.abc import Mapping
import sys

from deepagents import GeneralPurposeSubagentProfile, HarnessProfile, register_harness_profile
from langchain_core.language_models.chat_models import BaseChatModel

# Upstream recursive filesystem deletion is outside the selected Chat tools.
RECURSIVE_DELETE_TOOL = "delete"

_registered_providers: set[str] = set()


def ordinary_chat_profile() -> HarnessProfile:
    """Profile that ordinary Chat passes through ``create_deep_agent``."""

    return HarnessProfile(
        excluded_tools=frozenset({RECURSIVE_DELETE_TOOL}),
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
        tool_description_overrides={
            "ls": "List the project directory at path. File paths are relative to the bound project; / is its root, not the host drive. Reserved framework routes use their supplied virtual paths.",
            "read_file": "Read a project-relative file, or an explicitly supplied framework/capture path. Text is paginated using zero-based offset and line limit. Images require the selected model's verified image-reading support. Use returned virtual paths, not host-drive paths.",
            "write_file": "Create or replace a UTF-8 file at a project-relative path. Missing parent directories are created. Existing content is replaced in full; use edit_file for a targeted change. Distinct files can be written together; never mutate the same file twice in one response.",
            "edit_file": "Replace an exact old_string in a project-relative text file with new_string. Read the relevant file first. Set replace_all only when every matching occurrence should change. Never mutate the same file twice in one response.",
            "glob": "Find project files using a glob pattern, optionally below a project-relative path. This is filename matching, not content search. Use * for a basename pattern and **/ for recursive path patterns. Results may be bounded; read any truncation notice.",
            "grep": "Search project text for a literal string, optionally within a project-relative path and filename glob. Pattern is literal text, not a regular expression: punctuation such as | is searched literally. Results include paths and line numbers and may be bounded.",
            "execute": (
                "Run a Windows Command Prompt (cmd.exe) command in the bound project folder on this host. This is not Bash or a sandbox. Use Windows syntax; to use PowerShell invoke powershell -NoProfile -Command explicitly. "
                if sys.platform == "win32" else
                "Run a host shell command in the bound project folder. Host execution is not sandboxed. "
            ) + "The application enforces the selected approval policy. On Windows, the command's process tree stops when the call ends, times out or is cancelled. When start_preview is selected, use it for an owned long-running web preview instead of leaving a background server behind.",
        },
    )


def model_provider(model: BaseChatModel) -> str | None:
    """Provider key Deep Agents uses to look up a harness profile."""

    try:
        params = model._get_ls_params()
    except (AttributeError, TypeError, NotImplementedError):
        return None
    if not isinstance(params, Mapping):
        return None
    provider = params.get("ls_provider")
    if isinstance(provider, str) and provider:
        return provider
    return None


def ensure_ordinary_chat_profile(model: BaseChatModel) -> str | None:
    """Register the ordinary-Chat profile for this model's provider.

    Registration merges. Calling this again for the same provider does not
    stack a second profile or re-enable the general-purpose subagent.
    """

    provider = model_provider(model)
    if provider is None or provider in _registered_providers:
        return provider
    register_harness_profile(provider, ordinary_chat_profile())
    _registered_providers.add(provider)
    return provider
