"""Performance, Memory and Challenges through existing execution owners."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from contextlib import ExitStack
from statistics import mean
from typing import Callable

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentBudgets, AgentStartRequest
from workbench_backend.agents.setup_schemas import AgentInputPolicy
from workbench_backend.contracts.lifecycle import is_run_lifecycle_live
from workbench_backend.errors import LabError
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.inference.configuration_options import SMALL_CONTEXT_VALUES
from workbench_backend.inference.configurations import loading_startup_settings
from workbench_backend.inference.schemas import ManagedDeploymentRequest
from workbench_backend.inference.service import ModelManager
from workbench_backend.lab.native import LabStopped, NativeLabClient, timing_sample
from workbench_backend.lab.needles import needle_task, score_needle
from workbench_backend.lab.workbench_schemas import (
    ChallengeWrite, LabChallenge, LabMeasurement, LabRun, LabRunRequest, LabSeries,
)
from workbench_backend.state.store import ApplicationStore
from workbench_backend.state.assistant_text import assistant_text

LIVE = {"queued", "running", "stopping"}
LOAD_CONTROLS = {"ctx_size", "n_gpu_layers", "fit", "flash_attn", "cache_type_k", "cache_type_v", "spec_type", "spec_draft_n_max"}


class LabWorkbenchService:
    def __init__(self, manager_provider: Callable[[], ModelManager], harness_provider: Callable[[], HarnessService],
                 store: ApplicationStore, *, client_factory=NativeLabClient):
        self._manager_provider = manager_provider
        self._harness_provider = harness_provider
        self.store = store
        self.client_factory = client_factory
        self._lock = threading.RLock()
        self._workers: dict[str, threading.Thread] = {}
        self._cancels: dict[str, threading.Event] = {}
        self._recovered = False

    @property
    def manager(self):
        return self._manager_provider()

    @property
    def harness(self):
        return self._harness_provider()

    def recover(self):
        with self._lock:
            if self._recovered:
                return
            self.manager.release_lab_deployments()
            for run in self.store.list_lab_runs():
                if run.status in LIVE:
                    run.status = "stopped"
                    run.current = None
                    run.error = "The application closed before this run finished. Completed measurements were kept."
                    run.updated_at = utc_now()
                    self.store.put_lab_run(run)
            self._recovered = True

    def list_runs(self):
        return self.store.list_lab_runs()

    def get_run(self, run_id: str):
        run = self.store.get_lab_run(run_id)
        if run is None:
            raise LabError("Unknown Lab result.", code="lab_run_missing", status_code=404)
        return run

    def list_challenges(self):
        return self.store.list_lab_challenges()

    def get_challenge(self, challenge_id: str):
        challenge = next((item for item in self.list_challenges() if item.id == challenge_id), None)
        if challenge is None:
            raise LabError("Unknown challenge.", code="lab_challenge_missing", status_code=404)
        return challenge

    def save_challenge(self, body: ChallengeWrite, challenge_id: str | None = None):
        self.list_challenges()  # Persist first-use seeding before adding a card.
        previous = self.get_challenge(challenge_id) if challenge_id else None
        now = utc_now()
        return self.store.put_lab_challenge(LabChallenge(**body.model_dump(), id=challenge_id or new_id("challenge"),
            created_at=previous.created_at if previous else now, updated_at=now))

    def delete_challenge(self, challenge_id: str):
        self.get_challenge(challenge_id)
        self.store.delete_lab_challenge(challenge_id)

    def start(self, request: LabRunRequest) -> LabRun:
        self.recover()
        with self._lock, self.manager.store.configuration_lock():
            if any(thread.is_alive() for thread in self._workers.values()):
                raise LabError("Stop the current Lab run before starting another.", code="lab_busy", status_code=409)
            now = utc_now()
            run = LabRun(id=new_id("lab"), kind=request.kind, created_at=now, updated_at=now,
                request=request.model_copy(deep=True), challenge_snapshot=self.get_challenge(request.challenge_id) if request.kind == "challenge" else None)
            seen = set()
            for selection in request.configurations:
                profile = self.manager.get_profile(selection.configuration_id)
                if not profile.bundle_id:
                    raise LabError("Choose an installed model configuration.", code="lab_model_required", status_code=422)
                options = self.manager.get_bundle_configuration_options(profile.bundle_id, configuration_id=profile.id)
                descriptors = {**options.startup_defaults, "ctx_size": options.context_size, "n_gpu_layers": options.gpu_layers}
                for key, value in selection.startup.items():
                    descriptor = descriptors.get(key)
                    if key not in LOAD_CONTROLS or descriptor is None or descriptor.supported is False:
                        raise LabError(f"{key} is not a supported Lab control for this model.", code="lab_control_invalid", status_code=422)
                    if value is not None and value not in [item.value for item in descriptor.options]:
                        if descriptor.domain in {"integer", "number"} and isinstance(value, (int, float)) and not isinstance(value, bool):
                            if ((descriptor.domain == "integer" and type(value) is not int)
                                or descriptor.minimum is not None and value < descriptor.minimum
                                or descriptor.maximum is not None and value > descriptor.maximum
                                or descriptor.step and value % descriptor.step != 0):
                                raise LabError(f"Choose a legal value for {descriptor.label}.", code="lab_control_invalid", status_code=422)
                        elif descriptor.options and value not in [item.value for item in descriptor.options]:
                            raise LabError(f"Choose a legal value for {descriptor.label}.", code="lab_control_invalid", status_code=422)
                concurrent_options = [item.value for item in descriptors["parallel"].options if type(item.value) is int and item.value > 0] if "parallel" in descriptors else []
                if selection.concurrent_requests not in (concurrent_options or [1, 2, 4, 8]):
                    raise LabError("Choose a supported concurrent request count.", code="lab_concurrency_invalid", status_code=422)
                merged = {**profile.bags.startup.requested, **selection.startup}
                maximum = options.context_size.maximum
                selected_context = merged.get("ctx_size")
                requested_context = maximum if selected_context in {None, "auto", 0} else selected_context
                if type(requested_context) is not int or requested_context <= 0:
                    raise LabError("Choose a known context size for this model.", code="lab_context_required", status_code=422)
                legal_lengths = set(SMALL_CONTEXT_VALUES) | {item.value for item in options.context_size.options if type(item.value) is int and item.value > 0}
                if maximum:
                    legal_lengths.add(maximum)
                if maximum:
                    legal_lengths = {value for value in legal_lengths if value <= maximum}
                if any(length not in legal_lengths or length > requested_context for length in request.prompt_lengths):
                    raise LabError("A prompt length exceeds this model's legal selected context.", code="lab_length_invalid", status_code=422)
                startup = dict(selection.startup)
                if request.mode == "concurrent":
                    startup["parallel"] = selection.concurrent_requests
                deployment = self.manager.create_managed(ManagedDeploymentRequest(bundle_id=profile.bundle_id,
                    profile_id=profile.id, startup=startup, auto_start=False))
                if profile.id in seen:
                    raise LabError("Select each saved configuration once; use concurrent requests for multiple streams.", code="lab_duplicate_configuration", status_code=422)
                seen.add(profile.id)
                bundle = self.manager.store.get_bundle(profile.bundle_id)
                run.series.append(LabSeries(id=new_id("series"), configuration_id=profile.id,
                    name=f"{bundle.display_name if bundle else profile.bundle_id} · {profile.display_name}",
                    deployment_id=deployment.id, startup=dict(deployment.applied_startup),
                    requested_context_size=requested_context, concurrent_requests=selection.concurrent_requests))
            if request.mode == "concurrent":
                groups = {}
                for series, selection in zip(run.series, request.configurations):
                    prepared = self.manager.get_deployment(series.deployment_id)
                    plan = loading_startup_settings(prepared.settings)
                    plan.pop("parallel", None)
                    key = (prepared.bundle_id, json.dumps(plan, sort_keys=True))
                    groups.setdefault(key, []).append((series, selection))
                for (bundle_id, _), members in groups.items():
                    if len(members) < 2:
                        continue
                    # Identical loading settings can share weights, but every
                    # requested stream needs a real native slot. Preserve one
                    # chart series per saved configuration and record the total
                    # native parallel setting on each shared series.
                    total = sum(series.concurrent_requests for series, _selection in members)
                    first, selected = members[0]
                    shared = self.manager.create_managed(ManagedDeploymentRequest(bundle_id=bundle_id,
                        profile_id=first.configuration_id, startup={**selected.startup, "parallel": total}, auto_start=False))
                    for series, _selection in members:
                        series.deployment_id = shared.id
                        series.startup = dict(shared.applied_startup)
            self.store.put_lab_run(run)
            cancel = threading.Event()
            worker = threading.Thread(target=self._execute, args=(run.id, cancel), name=f"lab-{run.id}", daemon=True)
            self._cancels[run.id], self._workers[run.id] = cancel, worker
            worker.start()
            return run

    def stop(self, run_id: str):
        with self._lock:
            run = self.get_run(run_id)
            if run.status in LIVE:
                self._cancels.get(run_id, threading.Event()).set()
                run.status = "stopping"
                run.updated_at = utc_now()
                self.store.put_lab_run(run)
                if run.agent_run_id:
                    self.harness.cancel(run.agent_run_id)
            return run

    def delete_run(self, run_id: str):
        with self._lock:
            run = self.get_run(run_id)
            if run.status in LIVE:
                raise LabError("Stop this run before deleting it.", code="lab_run_active", status_code=409)
            self.store.delete_lab_run(run_id)

    def leave(self, run_ids: list[str] | None = None):
        selected = set(run_ids) if run_ids is not None else None
        for run in self.list_runs():
            if selected is not None and run.id not in selected:
                continue
            if run.status in LIVE:
                self.stop(run.id)
            elif not (self._workers.get(run.id) and self._workers[run.id].is_alive()):
                # A previous cleanup failure remains owned and retryable.
                self.manager.release_lab_deployments(run.id)
        return {"stopping": any(worker.is_alive() for ident, worker in self._workers.items()
            if selected is None or ident in selected)}

    def close(self):
        self.leave()
        for worker in list(self._workers.values()):
            worker.join(timeout=30)
            if worker.is_alive():
                raise RuntimeError("Lab is still releasing its model; application storage cannot close yet.")

    def _update(self, run_id: str, **updates):
        with self._lock:
            run = self.get_run(run_id)
            for name, value in updates.items():
                setattr(run, name, value)
            run.updated_at = utc_now()
            return self.store.put_lab_run(run)

    def _append(self, run_id: str, result: LabMeasurement):
        with self._lock:
            run = self.get_run(run_id)
            run.measurements.append(result)
            run.updated_at = utc_now()
            self.store.put_lab_run(run)

    def _execute(self, run_id: str, cancel: threading.Event):
        terminal, error = "completed", None
        try:
            self._update(run_id, status="running", current={"message": "Loading model"})
            with ExitStack() as reservations:
                run = self.get_run(run_id)
                loaded_plans = {}
                for series, selection in zip(run.series, run.request.configurations):
                    if cancel.is_set():
                        raise LabStopped()
                    prepared_id = series.deployment_id
                    deployment = loaded_plans.get(prepared_id)
                    if deployment is None:
                        deployment = self.manager.prepare_lab_deployment(selection.configuration_id, selection.startup,
                            owner=run_id, concurrent=run.request.mode == "concurrent", deployment_id=prepared_id,
                            cancelled=cancel.is_set)
                        loaded_plans[prepared_id] = deployment
                    series.deployment_id = deployment.id
                    series.benchmark_owned = deployment.benchmark_owner == run_id
                    series.context_size = deployment.server_props.n_ctx if deployment.server_props else None
                    series.context_adjusted = series.context_size is not None and series.context_size != series.requested_context_size
                    reservations.enter_context(self.manager.reserve_deployment(deployment.id))
                    self._update(run_id, series=run.series)
                if cancel.is_set():
                    raise LabStopped()
                if run.kind == "challenge":
                    self._challenge(run_id, cancel)
                else:
                    asyncio.run(self._measure(run_id, cancel))
        except LabStopped:
            terminal = "stopped"
        except Exception as exc:
            terminal, error = ("stopped", None) if cancel.is_set() else ("failed", str(exc))
        finally:
            try:
                self.manager.release_lab_deployments(run_id)
            except Exception as exc:
                terminal, error = "failed", f"Could not release the benchmark's extra model: {exc}"
            if cancel.is_set() and terminal == "completed":
                terminal = "stopped"
            self._update(run_id, status=terminal, error=error, current=None)

    async def _measure(self, run_id: str, cancel: threading.Event):
        client = self.client_factory(cancel)
        run = self.get_run(run_id)
        if run.kind == "memory":
            series = run.series[0]
            deployment = self.manager.get_deployment(series.deployment_id)
            task = needle_task(run.request.memory_test)
            for depth in run.request.depths:
                if cancel.is_set():
                    raise LabStopped()
                self._update(run_id, current={"series_id": series.id, "depth": depth, "message": f"Testing depth {depth}%"})
                result = LabMeasurement(id=new_id("measurement"), series_id=series.id, depth=depth, expected=task.expected, created_at=utc_now())
                try:
                    prompt, facts = await client.memory_prompt(deployment, task, depth, series.context_size or series.requested_context_size)
                    payload = await client.completion(deployment, prompt, 512, exact=False)
                    result.answer = str(payload.get("content", ""))
                    result.found, result.missing = score_needle(result.answer, task.expected)
                    result.prompt_tokens = payload.get("tokens_evaluated")
                    result.samples = [facts]
                except LabStopped:
                    raise
                except Exception as exc:
                    result.error = str(exc)
                    self._append(run_id, result)
                    raise
                self._append(run_id, result)
            return
        for length in run.request.prompt_lengths:
            if cancel.is_set():
                raise LabStopped()
            self._update(run_id, current={"prompt_length": length, "message": f"Measuring {length:,} prompt tokens"})
            prepared = []
            for series in run.series:
                deployment = self.manager.get_deployment(series.deployment_id)
                prompt = await client.performance_prompt(deployment, length, run.request.generation_length)
                prepared.append((series, deployment, prompt))
            # Prepare every input before scheduling any stream. One native
            # request per chosen slot, all configurations launched together.
            async def measure_series(series, deployment, prompt):
                result = LabMeasurement(id=new_id("measurement"), series_id=series.id, requested_prompt_length=length, created_at=utc_now())
                try:
                    payloads = await asyncio.gather(*[client.completion(deployment, prompt, run.request.generation_length, exact=True)
                        for _ in range(series.concurrent_requests)])
                    result.samples = [timing_sample(payload, run.request.generation_length) for payload in payloads]
                    for name in ("prompt_tokens", "context_tokens", "generated_tokens"):
                        setattr(result, name, round(mean(sample[name] for sample in result.samples)))
                    result.prefill_tps = mean(sample["prefill_tps"] for sample in result.samples)
                    result.generation_tps = mean(sample["generation_tps"] for sample in result.samples)
                except LabStopped:
                    raise
                except Exception as exc:
                    result.error = str(exc)
                return result
            pending = [asyncio.create_task(measure_series(*item)) for item in prepared]
            errors = []
            try:
                for completed in asyncio.as_completed(pending):
                    result = await completed
                    self._append(run_id, result)
                    if result.error:
                        errors.append(result.error)
            finally:
                for item in pending:
                    if not item.done():
                        item.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
            if errors:
                raise LabError(errors[0], code="lab_measurement_failed", status_code=502)

    def _challenge(self, run_id: str, cancel: threading.Event):
        run = self.get_run(run_id)
        challenge, series = run.challenge_snapshot, run.series[0]
        started = self.harness.start(AgentStartRequest(
            deployment_id=series.deployment_id, task=challenge.task, source_surface="lab",
            presented_tools=["echo", "time_now"], connection_ids=[], helper_agent_ids=[],
            memory_version_refs=[], skill_version_refs=[], protected_instruction_version_refs=[], knowledge_version_refs=[],
            embedding_deployment_id=None, retrieval_project_paths=[],
            input_policy=AgentInputPolicy(tool_loading="always", pinned_tools=["echo", "time_now"], excluded_sources=["tool:read_file"]),
            system_prompt="Complete the task using only the supplied Echo and Clock tools. Give a concise final answer. No approval is needed for these two read-only tools.",
            budgets=AgentBudgets(max_steps=12, max_tool_calls=8),
        ))
        self._update(run_id, agent_run_id=started.id, current={"message": "Running challenge"})
        while True:
            current = self.harness.get_run(started.id)
            if cancel.is_set():
                self.harness.cancel(started.id)
            if not is_run_lifecycle_live(current.status):
                break
            cancel.wait(0.1) if not cancel.is_set() else time.sleep(0.05)
        if cancel.is_set():
            raise LabStopped()
        answer = assistant_text(current) or ""
        tools = list(dict.fromkeys(item.name for item in current.tool_outcomes.values()
            if item.name in {"echo", "time_now"} and item.outcome == "succeeded"))
        missing = [challenge.required_text] if challenge.required_text and challenge.required_text not in answer else []
        passed = not missing and (challenge.required_tool is None or challenge.required_tool in tools) and current.status.value == "completed"
        self._append(run_id, LabMeasurement(id=new_id("measurement"), series_id=series.id,
            created_at=utc_now(), answer=answer, expected=[challenge.required_text] if challenge.required_text else [],
            missing=missing, tool_calls=tools, passed=passed, error=current.error))
        if current.error:
            raise LabError(current.error, code="lab_challenge_failed", status_code=502)
