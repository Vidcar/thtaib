"""AGT-006: keep completion evidence distinct from model judgement."""

from __future__ import annotations

from workbench_backend.agents.schemas import (
    AgentRun,
    CompletionReport,
    ExecutableCheck,
    ExpectedArtifact,
    ModelJudgement,
)


def build_completion(run: AgentRun) -> CompletionReport:
    invoked = {str(item.get("name")) for item in run.tool_invocations}
    checks: list[ExecutableCheck] = []
    for name in run.criteria.checks:
        if name == "enabled_tool_invoked":
            expected = set(run.presented_tools) or set(run.enabled_tools)
            hit = sorted(invoked & expected)
            checks.append(
                ExecutableCheck(
                    name=name,
                    passed=bool(hit),
                    detail=f"invoked={sorted(invoked)} expected_any={sorted(expected)}",
                )
            )
            continue
        if name.startswith("tool:"):
            tool = name.split(":", 1)[1]
            checks.append(
                ExecutableCheck(
                    name=name,
                    passed=tool in invoked,
                    detail=f"tool={tool} invoked={tool in invoked}",
                )
            )
            continue
        checks.append(
            ExecutableCheck(
                name=name,
                passed=False,
                detail="unknown executable check",
            )
        )

    artifacts: list[ExpectedArtifact] = []
    reply = _last_assistant_text(run)
    for name in run.criteria.expected_artifacts:
        if name == "assistant_reply":
            artifacts.append(
                ExpectedArtifact(
                    name=name,
                    present=bool(reply),
                    detail="final assistant text present" if reply else "no assistant text",
                )
            )
            continue
        artifacts.append(ExpectedArtifact(name=name, present=False, detail="artifact not produced"))

    return CompletionReport(
        evidence={
            "executable_checks": [item.model_dump() for item in checks],
            "expected_artifacts": [item.model_dump() for item in artifacts],
        },
        judgement=ModelJudgement(
            model_review=reply,
            note="Model judgement, not an executable check. Rubric middleware is not required.",
        ),
    )


def _last_assistant_text(run: AgentRun) -> str | None:
    for event in reversed(run.events):
        if event.kind != "assistant_message":
            continue
        content = event.detail.get("content")
        if isinstance(content, str) and content.strip():
            return content
    return None
