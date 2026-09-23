"""The installed rubric loop owns review/revision; Workbench owns policy and evidence."""
from __future__ import annotations

from deepagents import RubricMiddleware
from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware
from workbench_backend.agents.tools import tool_name


class ReviewCaptureMiddleware(WorkbenchHarnessMiddleware):
    def __init__(self, *args, capture_owner, publish, **kwargs):
        super().__init__(*args, **kwargs)
        self.capture_owner = capture_owner
        self.publish = publish

    def _capture(self, *args, **kwargs):
        super()._capture(*args, **kwargs)
        captured = self.run.model_requests[-1].model_copy(update={"purpose": "review"})
        self.publish(lambda: self.capture_owner.model_requests.append(captured))

    def _presented(self, tools):
        # The one SDK structured-result tool cannot execute application effects.
        return [item for item in tools or [] if tool_name(item) == "GraderResponse"]


def review_middleware(run, model, http_sink, execution_control, settings_provider, publish):
    def observed(evaluation):
        run.review_observation.enabled = True
        run.review_observation.status = evaluation["result"]
        identity = (evaluation["grading_run_id"], evaluation["iteration"])
        run.review_observation.evaluations = [item for item in run.review_observation.evaluations
            if (item.get("grading_run_id"), item.get("iteration")) != identity] + [dict(evaluation)]
        publish()

    # Persist each review request onto its owner explicitly. Diagnostic-policy
    # sanitization replaces request lists, so sharing a list would lose captures.
    grader_run = run.model_copy(update={"work_mode": "plan", "presented_tools": [], "helper_snapshots": [], "model_requests": []})
    return RubricMiddleware(model=model, tools=[],
        grader_middleware=[ReviewCaptureMiddleware(grader_run, http_sink,
            settings_provider=settings_provider, execution_control=execution_control,
            capture_owner=run, publish=publish)],
        max_iterations=run.review.max_revisions + 1, on_evaluation=observed)
