"""One output allowance policy for admission, transport and context accounting.

Authored policy is frozen before queueing. Its numeric allowance binds once to
the first verified per-request capacity; no model call silently retunes it.
"""
from __future__ import annotations

import hashlib
import json

from workbench_backend.errors import HarnessError
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import Deployment, ResponseBudgetBinding, ResponseBudgetPolicy, SettingsBag
from workbench_backend.inference.settings import normalize_on_off_auto, normalize_int

TOKEN_MARGIN_RATIO = 0.08


def freeze_output_policy(bag: SettingsBag, *, publisher_source: str | None = None,
        default_thinking: bool | None = None) -> SettingsBag:
    """Capture intent without using a resident child's capacity or defaults."""
    frozen = bag.model_copy(deep=True)
    thinking = normalize_on_off_auto(frozen.applied.get("reasoning", "auto"), allow_auto=True)
    enabled = True if thinking == "on" else False if thinking == "off" else default_thinking
    effort = frozen.applied.get("reasoning_effort")
    if thinking == "auto" and effort not in (None, "default", "auto"):
        enabled = effort not in ("none", "off")
    cap = frozen.applied.get("max_tokens")
    explicit = normalize_int(frozen.requested.get("max_tokens"), allow_negative=True)
    if (type(cap) is int and cap > 0) or explicit == -1:
        mode = "explicit" if type(explicit) is int and (explicit > 0 or explicit == -1) else "publisher"
        frozen.output_budget_policy = ResponseBudgetPolicy(mode=mode, total_tokens=cap,
            thinking=enabled, source="From setup" if mode == "explicit" else publisher_source or "Publisher recommendation")
    else:
        frozen.output_budget_policy = ResponseBudgetPolicy(thinking=enabled)
    frozen.output_budget_binding = None
    return frozen


def verified_capacity(deployment: Deployment) -> int | None:
    value = deployment.server_props.n_ctx if deployment.server_props else None
    return value if type(value) is int and value > 0 else None


def _loaded_identity(deployment: Deployment) -> str:
    if deployment.loaded_model_identity:
        return deployment.loaded_model_identity
    # Connected endpoints and historical records still have a bounded identity.
    facts = {"id": deployment.id, "endpoint": deployment.endpoint,
        "bundle": deployment.bundle_id, "startup": deployment.applied_startup,
        "model": deployment.server_props.model_path if deployment.server_props else None}
    return hashlib.sha256(json.dumps(facts, sort_keys=True, default=str).encode()).hexdigest()


def bind_output_budget(deployment: Deployment, bag: SettingsBag) -> SettingsBag:
    """Resolve once; retain a persisted binding through retries and resumes."""
    bound = bag.model_copy(deep=True)
    if bound.output_budget_policy is None:
        bound = freeze_output_policy(bound)
    policy = bound.output_budget_policy
    assert policy is not None
    if policy.version != 1:
        raise HarnessError("This accepted response policy is not supported by the current application. Deliberately retry with new choices.",
            code="response_budget_policy_unsupported", status_code=409)
    capacity = verified_capacity(deployment)
    if bound.output_budget_binding is not None:
        validate_output_binding(deployment, bound)
        bound.applied["max_tokens"] = bound.output_budget_binding.total_tokens
        return bound
    if capacity is None:
        # A connected endpoint with no capacity facts cannot receive an invented
        # automatic cap. Explicit/publisher caps remain as authored.
        return bound
    margin = int(capacity * TOKEN_MARGIN_RATIO)
    usable = capacity - margin
    total = policy.total_tokens if policy.mode != "workbench_auto" else max(1, usable // (4 if policy.thinking is False else 2))
    if total is None or (total != -1 and (total <= 0 or total >= usable)):
        raise HarnessError("The saved response allowance leaves no conversation space at this loaded capacity. Increase conversation capacity or change the response allowance in Models.",
            code="response_budget_capacity_conflict", status_code=409)
    bound.output_budget_binding = ResponseBudgetBinding(total_tokens=total, capacity_tokens=capacity,
        margin_tokens=margin, source=policy.source, model_identity=_loaded_identity(deployment), bound_at=utc_now())
    bound.applied["max_tokens"] = total
    return bound


def validate_output_binding(deployment: Deployment, bag: SettingsBag) -> None:
    binding = bag.output_budget_binding
    capacity = verified_capacity(deployment)
    if binding is None:
        return
    if binding.model_identity != _loaded_identity(deployment):
        raise HarnessError("This accepted task is bound to a different exact loaded model. Restore its model plan or deliberately retry with new choices.",
            code="response_budget_model_conflict", status_code=409)
    if capacity is None:
        return
    if binding.total_tokens >= capacity - int(capacity * TOKEN_MARGIN_RATIO):
        raise HarnessError("This accepted task's response allowance no longer fits the loaded conversation capacity. Restore its capacity or deliberately retry with new choices.",
            code="response_budget_capacity_conflict", status_code=409)


def output_reservation(bag: SettingsBag | None) -> int:
    if bag is None:
        return 0
    if bag.output_budget_binding is not None:
        return max(0, bag.output_budget_binding.total_tokens)
    value = bag.applied.get("max_tokens")
    return value if type(value) is int and value > 0 else 0
