"""SSE publisher for application run events (API-006).

LangGraph ``stream_mode="updates"`` stays inside the harness. This module
publishes the recorded ``AgentEvent`` rows over FastAPI EventSourceResponse.
"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi.sse import ServerSentEvent

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentEvent, AgentRun, AgentRunStatus
from workbench_backend.chat.service import ChatService
from workbench_backend.contracts.events import (
    RunStreamEnvelope,
    RunStreamEventType,
    SharedAgentEvent,
)
from workbench_backend.contracts.lifecycle import is_run_lifecycle_live
from workbench_backend.errors import WorkbenchError

WAIT_TIMEOUT_SECONDS = 15.0


def resume_after_snapshot(event_count: int) -> int:
    """Return the ``wait_after`` cursor after a full snapshot was sent.

    ``event_count`` is ``len(snapshot.events)``. Those rows are already in the
    snapshot, so ``Last-Event-ID`` must not rewind the cursor. A stale id from
    a previous run on the same conversation can exceed this run's length; still
    resume at the snapshot, not that id.
    """

    return event_count


def iter_workbench_events(
    *,
    harness: HarnessService,
    chat: ChatService,
    run_id: str | None,
    conversation_id: str | None,
    last_event_id: int | None,
) -> Iterable[ServerSentEvent]:
    """Yield snapshot, then only rows newer than that snapshot.

    ``last_event_id`` is the ``Last-Event-ID`` header. It is accepted so a
    reconnecting client can send it; resume is ``len(snapshot.events)``, not a
    rewind to that id.
    """

    if (run_id is None) == (conversation_id is None):
        raise WorkbenchError(
            "Provide exactly one of run_id or conversation_id.",
            code="event_target_required",
            status_code=400,
        )
    _ = last_event_id
    if conversation_id is not None:
        yield from _iter_conversation(
            harness=harness,
            chat=chat,
            conversation_id=conversation_id,
        )
        return
    assert run_id is not None
    yield from _iter_run(
        harness=harness,
        run_id=run_id,
        conversation_id=None,
    )


def _iter_conversation(
    *,
    harness: HarnessService,
    chat: ChatService,
    conversation_id: str,
) -> Iterable[ServerSentEvent]:
    view = chat.get(conversation_id)
    current = view.current_run
    yield _sse(
        event="snapshot",
        envelope=_snapshot_envelope(
            snapshot=view.model_dump(mode="json"),
            run_id=current.id if current is not None else None,
            conversation_id=conversation_id,
            status=current.status if current is not None else None,
        ),
    )
    if current is None:
        yield _sse(
            event="stream_end",
            envelope=_end_envelope(run_id=None, conversation_id=conversation_id, status=None),
        )
        return
    yield from _follow_run(
        harness=harness,
        chat=chat,
        run_id=current.id,
        conversation_id=conversation_id,
        initial=current,
    )


def _iter_run(
    *,
    harness: HarnessService,
    run_id: str,
    conversation_id: str | None,
) -> Iterable[ServerSentEvent]:
    run = harness.get_run(run_id)
    yield _sse(
        event="snapshot",
        envelope=_snapshot_envelope(
            snapshot=run.model_dump(mode="json"),
            run_id=run.id,
            conversation_id=conversation_id,
            status=run.status,
        ),
    )
    yield from _follow_run(
        harness=harness,
        chat=None,
        run_id=run.id,
        conversation_id=conversation_id,
        initial=run,
    )


def _follow_run(
    *,
    harness: HarnessService,
    chat: ChatService | None,
    run_id: str,
    conversation_id: str | None,
    initial: AgentRun,
) -> Iterable[ServerSentEvent]:
    after = resume_after_snapshot(len(initial.events))
    if not is_run_lifecycle_live(initial.status):
        yield _sse(
            event="stream_end",
            envelope=_end_envelope(
                run_id=run_id,
                conversation_id=conversation_id,
                status=initial.status,
            ),
        )
        return
    while True:
        run, extra = harness.wait_after(run_id, after, timeout=WAIT_TIMEOUT_SECONDS)
        for offset, event in enumerate(extra):
            seq = after + offset + 1
            yield _sse(
                event="run_event",
                event_id=str(seq),
                envelope=_run_event_envelope(
                    event=event,
                    seq=seq,
                    run_id=run_id,
                    conversation_id=conversation_id,
                    status=run.status,
                ),
            )
        after += len(extra)
        if not is_run_lifecycle_live(run.status):
            yield _terminal_snapshot(
                harness=harness,
                chat=chat,
                run_id=run_id,
                conversation_id=conversation_id,
            )
            yield _sse(
                event="stream_end",
                envelope=_end_envelope(
                    run_id=run_id,
                    conversation_id=conversation_id,
                    status=run.status,
                ),
            )
            return
        if not extra:
            yield ServerSentEvent(comment="keepalive")


def _terminal_snapshot(
    *,
    harness: HarnessService,
    chat: ChatService | None,
    run_id: str,
    conversation_id: str | None,
) -> ServerSentEvent:
    if chat is not None and conversation_id is not None:
        view = chat.get(conversation_id)
        current = view.current_run
        return _sse(
            event="snapshot",
            envelope=_snapshot_envelope(
                snapshot=view.model_dump(mode="json"),
                run_id=current.id if current is not None else run_id,
                conversation_id=conversation_id,
                status=current.status if current is not None else None,
            ),
        )
    run = harness.get_run(run_id)
    return _sse(
        event="snapshot",
        envelope=_snapshot_envelope(
            snapshot=run.model_dump(mode="json"),
            run_id=run.id,
            conversation_id=conversation_id,
            status=run.status,
        ),
    )


def _sse(
    *,
    event: str,
    envelope: RunStreamEnvelope,
    event_id: str | None = None,
) -> ServerSentEvent:
    return ServerSentEvent(
        data=envelope.model_dump(mode="json"),
        event=event,
        id=event_id,
    )


def _snapshot_envelope(
    *,
    snapshot: dict[str, object],
    run_id: str | None,
    conversation_id: str | None,
    status: AgentRunStatus | None,
) -> RunStreamEnvelope:
    return RunStreamEnvelope(
        type=RunStreamEventType.snapshot,
        run_id=run_id,
        conversation_id=conversation_id,
        status=status,
        snapshot=snapshot,
    )


def _run_event_envelope(
    *,
    event: AgentEvent,
    seq: int,
    run_id: str,
    conversation_id: str | None,
    status: AgentRunStatus,
) -> RunStreamEnvelope:
    return RunStreamEnvelope(
        type=RunStreamEventType.run_event,
        seq=seq,
        run_id=run_id,
        conversation_id=conversation_id,
        status=status,
        event=SharedAgentEvent(at=event.at, kind=event.kind, detail=event.detail),
    )


def _end_envelope(
    *,
    run_id: str | None,
    conversation_id: str | None,
    status: AgentRunStatus | None,
) -> RunStreamEnvelope:
    return RunStreamEnvelope(
        type=RunStreamEventType.stream_end,
        run_id=run_id,
        conversation_id=conversation_id,
        status=status,
    )
