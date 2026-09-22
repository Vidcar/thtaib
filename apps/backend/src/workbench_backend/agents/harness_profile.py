"""Ordinary Chat exclusions for the embedded Deep Agents harness.

Deep Agents adds ``task`` and recursive ``delete`` unless a harness profile
says otherwise. Extra ``tools=`` are additive, and a parent-only catalogue
filter is not inherited by a compiled child. Registration follows the
provider the model actually reports, so the same switch applies to the
parent and to a child compiled with that model.
"""

from __future__ import annotations

from collections.abc import Mapping

from deepagents import GeneralPurposeSubagentProfile, HarnessProfile, register_harness_profile
from langchain_core.language_models.chat_models import BaseChatModel

# Upstream filesystem tool. ``delete_file`` is the one-file replacement.
RECURSIVE_DELETE_TOOL = "delete"

_registered_providers: set[str] = set()


def ordinary_chat_profile() -> HarnessProfile:
    """Profile that ordinary Chat passes through ``create_deep_agent``."""

    return HarnessProfile(
        excluded_tools=frozenset({RECURSIVE_DELETE_TOOL}),
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
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
