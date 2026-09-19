"""STATE-004 unknown-effect safety.

Snapshots do not undo external actions. Reconnect/resume/restart must not
silently repeat an operation whose outcome is unknown. This is not an
exactly-once claim and does not close OQ-004.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, Field

from workbench_backend.agents.schemas import AgentRun
from workbench_backend.contracts.lifecycle import RunLifecycleStatus, is_run_lifecycle_live
from workbench_backend.errors import StateError
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.state.schemas import (
    ExternalEffect,
    ExternalEffectOutcome,
    RecoverAction,
)
from workbench_backend.state.store import ApplicationStore

NO_REPLAY_NOTE = (
    "Outcome is unknown. The operation will not be silently repeated. "
    "Snapshots do not roll back external effects."
)

CANCEL_REQUESTED_RECOVERY_NOTE = (
    NO_REPLAY_NOTE
    + " Linked run is cancel_requested, which is still live; "
    "that is not a confirmed stop and not permission to replay."
)

LIVE_RUN_RECOVERY_NOTE = (
    NO_REPLAY_NOTE
    + " Linked run is still live; recovery reports uncertainty and does not replay."
)


class DispatchEffectRequest(BaseModel):
    operation: str
    run_id: str | None = None
    adapter_id: str = "application-ledger"
    payload: dict[str, Any] = Field(default_factory=dict)


class AcknowledgeEffectRequest(BaseModel):
    evidence: dict[str, Any] | None = None


class ReconcileEffectRequest(BaseModel):
    evidence: dict[str, Any]


class RecoverEffectRequest(BaseModel):
    action: RecoverAction = RecoverAction.reconnect
    evidence: dict[str, Any] | None = None


class RecoveryReport(BaseModel):
    effect: ExternalEffect
    action: RecoverAction
    replayed: Literal[False] = False
    uncertainty: bool
    reconciled: bool
    rollback_promise: Literal["none"] = "none"
    environment_restore: Literal["not_supported"] = "not_supported"
    note: str = NO_REPLAY_NOTE


class RollbackRefusal(BaseModel):
    code: Literal["external_effect_rollback_unsupported"] = "external_effect_rollback_unsupported"
    rollback_promise: Literal["none"] = "none"
    environment_restore: Literal["not_supported"] = "not_supported"
    note: str = (
        "Snapshots and recovery do not undo external actions unless an adapter "
        "explicitly supports that restore. This adapter does not."
    )


class EffectService:
    """Application-owned external-effect ledger. No silent replay. No rollback promise."""

    def __init__(
        self,
        store: ApplicationStore,
        *,
        run_lookup: Callable[[str], AgentRun | None] | None = None,
    ) -> None:
        self.store = store
        self._run_lookup = run_lookup

    def _linked_run(self, run_id: str) -> AgentRun | None:
        if self._run_lookup is not None:
            found = self._run_lookup(run_id)
            if found is not None:
                return found
        return self.store.get_run(run_id)

    def _recovery_note_for_linked_run(self, run: AgentRun) -> str:
        status = RunLifecycleStatus(run.status)
        if status == RunLifecycleStatus.cancel_requested:
            return CANCEL_REQUESTED_RECOVERY_NOTE
        if is_run_lifecycle_live(status):
            return LIVE_RUN_RECOVERY_NOTE
        return NO_REPLAY_NOTE

    def list_effects(self, *, run_id: str | None = None, unresolved_only: bool = False) -> list[ExternalEffect]:
        return self.store.list_effects(run_id=run_id, unresolved_only=unresolved_only)

    def get_effect(self, effect_id: str) -> ExternalEffect:
        effect = self.store.get_effect(effect_id)
        if effect is None:
            raise StateError("Unknown external effect", code="effect_missing", status_code=404)
        return effect

    def dispatch(self, request: DispatchEffectRequest) -> ExternalEffect:
        now = utc_now()
        effect = ExternalEffect(
            id=new_id("effect"),
            run_id=request.run_id,
            adapter_id=request.adapter_id,
            operation=request.operation,
            payload=dict(request.payload),
            outcome=ExternalEffectOutcome.dispatched,
            unresolved=True,
            dispatched_at=now,
        )
        return self.store.put_effect(effect)

    def acknowledge(self, effect_id: str, request: AcknowledgeEffectRequest | None = None) -> ExternalEffect:
        effect = self.get_effect(effect_id)
        request = request or AcknowledgeEffectRequest()
        if effect.outcome is ExternalEffectOutcome.acknowledged:
            return effect
        updated = effect.model_copy(
            update={
                "outcome": ExternalEffectOutcome.acknowledged,
                "unresolved": False,
                "acknowledged_at": utc_now(),
                "evidence": request.evidence,
                "note": "Local acknowledgement recorded. Outcome is known.",
            }
        )
        return self.store.put_effect(updated)

    def recover(self, effect_id: str, request: RecoverEffectRequest | None = None) -> RecoveryReport:
        effect = self.get_effect(effect_id)
        request = request or RecoverEffectRequest()
        if request.evidence:
            effect = self.reconcile(effect_id, ReconcileEffectRequest(evidence=request.evidence))
            return RecoveryReport(
                effect=effect,
                action=request.action,
                uncertainty=False,
                reconciled=True,
                note="Reconciled with authoritative evidence. The operation was not replayed.",
            )
        if effect.outcome is ExternalEffectOutcome.acknowledged:
            return RecoveryReport(
                effect=effect,
                action=request.action,
                uncertainty=False,
                reconciled=False,
                note="Outcome already acknowledged. The operation was not replayed.",
            )
        if effect.outcome is ExternalEffectOutcome.reconciled:
            return RecoveryReport(
                effect=effect,
                action=request.action,
                uncertainty=False,
                reconciled=True,
                note="Outcome already reconciled. The operation was not replayed.",
            )
        note = NO_REPLAY_NOTE
        if effect.run_id:
            run = self._linked_run(effect.run_id)
            if run is not None:
                note = self._recovery_note_for_linked_run(run)
        updated = effect.model_copy(
            update={
                "outcome": ExternalEffectOutcome.unknown,
                "unresolved": True,
                "recovered_at": utc_now(),
                "last_recovery_action": request.action,
                "note": note,
            }
        )
        stored = self.store.put_effect(updated)
        return RecoveryReport(
            effect=stored,
            action=request.action,
            uncertainty=True,
            reconciled=False,
            note=note,
        )

    def reconcile(self, effect_id: str, request: ReconcileEffectRequest) -> ExternalEffect:
        effect = self.get_effect(effect_id)
        if not request.evidence:
            raise StateError(
                "Reconciliation requires authoritative evidence.",
                code="effect_evidence_required",
                status_code=400,
            )
        updated = effect.model_copy(
            update={
                "outcome": ExternalEffectOutcome.reconciled,
                "unresolved": False,
                "reconciled_at": utc_now(),
                "evidence": request.evidence,
                "note": "Reconciled with authoritative evidence. The operation was not replayed.",
            }
        )
        return self.store.put_effect(updated)

    def refuse_rollback(self, effect_id: str | None = None) -> RollbackRefusal:
        if effect_id is not None:
            self.get_effect(effect_id)
        return RollbackRefusal()

    def unresolved_ids_for_run(self, run_id: str | None) -> list[str]:
        if not run_id:
            return []
        return [item.id for item in self.list_effects(run_id=run_id, unresolved_only=True)]
