"""Real Workbench composition with deterministic inference and transport faults."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from uuid import uuid4
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr
import psutil

from tests_ui import REPO_ROOT, configure_environment


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


# Recovered verbatim from the failed three-range trial's durable submission and
# saved seed. This separate fixture never substitutes the later one-read task.
INSTRUCTION_RETENTION_TASK = (
    "Remember this exact fact: COMPACTION-FACT-JUPITER-7391. First call write_file exactly once with file_path "
    "/compaction-effect.txt and content exactly one compaction history effect. Then call read_file three times "
    "with file_path /compaction-source.txt, limit 500, and offsets 0, then 500, then 1000. Call only one tool "
    "in each assistant response and wait for its result before the next call. Read only these three ranges. "
    "If a result is clipped, keep going to the next requested range. Do not reread a range, do not repeat the "
    "write, and do not read conversation_history files. After all three reads, reply briefly with COMPACTION-FACT-JUPITER-7391."
)
INSTRUCTION_RETENTION_TASK_SHA256 = "7300beba4d465b03749b5466dbff49e58f4e1926d3fecf7e10dd2ea2ca6cfc31"
INSTRUCTION_RETENTION_SOURCE_SHA256 = "ac3c21676569968ffbe4bd89a7b24cfcaca71be69bdac9fb59a05743c1a15c33"
COMPACTION_SCENARIOS = frozenset({"compaction_history", "instruction_retention"})


class FixtureModel(BaseChatModel):
    """Replace only model inference; native graph/tools/interrupts execute normally."""

    _fixture: Any = PrivateAttr()
    _run: Any = PrivateAttr()
    _script: list[AIMessage] = PrivateAttr()
    _index: int = PrivateAttr(default=0)
    _instruction_tools: list[Any] = PrivateAttr(default_factory=list)

    def __init__(self, fixture, run, script):
        super().__init__()
        self._fixture, self._run, self._script = fixture, run, script

    @property
    def _llm_type(self):
        return "deterministic-ui-fixture"

    def bind_tools(self, tools, **kwargs):
        if self._fixture.scenario == "instruction_retention":
            self._instruction_tools = list(tools)
        return self

    def project_context_payload(self, messages, **kwargs):
        from workbench_backend.inference.request_projection import project_context_payload
        payload = project_context_payload(messages, **kwargs)
        if self._fixture.scenario in COMPACTION_SCENARIOS:
            from workbench_backend.agents.context import estimate_payload
            # This is the same projection and estimated fallback the stock
            # token-counter closure already uses; it is never a native count.
            self._fixture.record_input_count(self._run, payload, estimate_payload(payload), basis="estimated")
        return payload

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if self._fixture.scenario == "instruction_retention":
            from workbench_backend.inference.request_projection import project_context_payload
            from workbench_backend.inference.telemetry import current_request_purpose
            purpose = current_request_purpose()
            payload = project_context_payload(messages, tools=self._instruction_tools if purpose == "work" else None)
            if purpose == "work" and self._fixture.negative_control == "instruction_missing_text" and self._fixture.instruction_after_compaction(self._run.id):
                # A deficient deterministic model-input boundary is a deliberate
                # gate control. It never changes graph state or actual inference.
                payload["messages"] = [message for message in payload["messages"]
                    if not self._fixture._task_occurrences(message.get("content"), self._run.task)]
            self._fixture.record_instruction_input(self._run, payload, boundary="deterministic_inference", native_messages=messages)
        if self._fixture.scenario in COMPACTION_SCENARIOS:
            from workbench_backend.agents.context import count_context_tokens
            from workbench_backend.inference.telemetry import current_request_purpose
            purpose = current_request_purpose()
            with self._fixture.lock:
                self._fixture.compaction_model_calls.append({"run_id": self._run.id,
                    "purpose": purpose, "input_tokens": count_context_tokens(messages),
                    "message_ids": [message.id for message in messages],
                    "input_sha256": hashlib.sha256(json.dumps([message.model_dump(mode="json")
                        for message in messages], sort_keys=True).encode()).hexdigest(),
                    "basis": "deterministic fixture; approximate count"})
                self._fixture.compaction_calls_path.write_text(
                    json.dumps(self._fixture.compaction_model_calls), encoding="utf-8")
            if purpose == "summary":
                if self._fixture.scenario == "instruction_retention":
                    # Deliberately lossy native summary: retain progress but
                    # change the requested limit and omit the no-repeat rule.
                    content = ("INTERNAL-INSTRUCTION-RETENTION-SUMMARY. Remember COMPACTION-FACT-JUPITER-7391. "
                        "The write completed. Read the remaining ranges at offsets 500 and 1000 with limit 50, "
                        "then reply with the fact.")
                    return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])
                data = self._fixture.seed_data["compaction"]
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content=
                    data["internal_summary_marker"] + ". Remember " + data["marker"]
                    + ". The requested file write has already completed; never repeat it. "
                    "Earlier clipped read results remain in the saved history. Continue the requested remaining reads."))])
        if self._fixture.hold_model and (self._fixture.scenario != "command" or self._index > 0):
            deadline = time.monotonic() + 45
            while not self._fixture.release.wait(.02):
                cancel = self._fixture.app.state.harness._cancels.get(self._run.id)
                if cancel is not None and cancel.is_set():
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError("UI fixture model hold was not released")
        message = self._script[min(self._index, len(self._script) - 1)]
        self._index += 1
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return await asyncio.to_thread(self._generate, messages, stop=stop, run_manager=run_manager, **kwargs)


class ApplicationFixture:
    def __init__(self, data_root: Path, *, inference: str = "deterministic"):
        if inference not in {"deterministic", "real"}:
            raise ValueError("Unknown isolated inference mode")
        self.inference = inference
        self.real_server = None
        self.real_identity = None
        self.root = configure_environment(data_root)
        # Deliberately import only after configuring the import-time app instance.
        from workbench_backend.app import app as initial_app, create_app
        from workbench_backend.inference.process import ProcessSupervisor

        self.app = initial_app if initial_app.state.manager.paths.root.resolve() == self.root else create_app(data_root=self.root)
        self.scenario = "baseline"
        self.hold_model = False
        self.release = threading.Event()
        self.release.set()
        self.load_release = threading.Event()
        self.load_release.set()
        self.fail_model_start = False
        self.fail_shutdown = False
        self.lose_next_ack = False
        self.disconnect_next_stream = False
        self.reject_next_submit = False
        self.fail_state_reads = 0
        self.submit_release = threading.Event()
        self.submit_release.set()
        self.submissions: list[dict[str, Any]] = []
        self.failed_lookup_paths: list[str] = []
        self.negative_control = None
        self.faults = {"lost_acknowledgements": 0, "stream_disconnects": 0, "draft_losses": 0, "state_lookup_failures": 0}
        self.model_run_ids: list[str] = []
        self.helper_models: dict[str, FixtureModel] = {}
        self.compaction_calls_path = self.root / "compaction-calls.json"
        self.compaction_model_calls: list[dict[str, Any]] = (json.loads(self.compaction_calls_path.read_text(encoding="utf-8"))
            if self.compaction_calls_path.exists() else [])
        self.compaction_counts_path = self.root / "compaction-input-counts.json"
        self.compaction_input_counts: list[dict[str, Any]] = (json.loads(self.compaction_counts_path.read_text(encoding="utf-8"))
            if self.compaction_counts_path.exists() else [])
        self.compaction_count_capture_errors: list[dict[str, Any]] = []
        self.instruction_inputs_path = self.root / "instruction-inputs.json"
        self.instruction_inputs: list[dict[str, Any]] = (json.loads(self.instruction_inputs_path.read_text(encoding="utf-8"))
            if self.instruction_inputs_path.exists() else [])
        self.instruction_input_capture_errors: list[dict[str, Any]] = []
        self.model_process_identities: list[Any] = []
        self.lock = threading.RLock()
        self.seed_path = self.root / "ui-seed.json"
        self.seed_data = json.loads(self.seed_path.read_text(encoding="utf-8")) if self.seed_path.exists() else {}
        self.compaction_native_path = self.root / "compaction-native.json"
        self.compaction_native = (json.loads(self.compaction_native_path.read_text(encoding="utf-8"))
            if self.compaction_native_path.exists() else {"tool_results": {}, "cutoffs": []})
        self._closed = False
        self.cleanup_errors: list[str] = []
        self.native_model_factory = self.app.state.harness._model_factory
        self.app.state.harness._model_factory = self.model_factory
        native_observer = self.app.state.harness._interaction_observer
        def observe_native(run, event, **kwargs):
            if self.scenario in COMPACTION_SCENARIOS and event and event.get("method") == "values":
                params = event.get("params", {})
                if not params.get("namespace"):
                    data = params.get("data", {})
                    with self.lock:
                        if self.scenario == "instruction_retention":
                            self.remember_instruction_input(run, data.get("messages", []), origin="native_values")
                        captured = self.compaction_native["tool_results"].setdefault(run.id, {})
                        for message in data.get("messages", []):
                            value = message.model_dump(mode="json") if hasattr(message, "model_dump") else message
                            if value.get("type") == "tool" and value.get("id") and value["id"] not in captured:
                                captured[value["id"]] = {key: value[key] for key in (
                                    "id", "type", "content", "name", "tool_call_id", "status") if key in value}
                        summary = data.get("_summarization_event")
                        if summary and type(summary.get("cutoff_index")) is int:
                            observed = {"run_id": run.id, "cutoff_index": summary["cutoff_index"]}
                            if self.scenario == "instruction_retention":
                                active_id = (self.compaction_native.get("inputs", {}).get(run.id) or {}).get("id")
                                active_index = next((index for index, message in enumerate(data.get("messages", []))
                                    if (message.get("id") if isinstance(message, dict) else message.id) == active_id), None)
                                observed.update(input_message_id=active_id, input_index=active_index,
                                    native_input_removed=active_index is not None and active_index < summary["cutoff_index"])
                            if observed not in self.compaction_native["cutoffs"]:
                                self.compaction_native["cutoffs"].append(observed)
                        self.compaction_native_path.write_text(json.dumps(self.compaction_native), encoding="utf-8")
            if native_observer is not None:
                return native_observer(run, event, **kwargs)
        self.app.state.harness._interaction_observer = observe_native
        fixture = self

        class BoundarySupervisor(ProcessSupervisor):
            def start(self, argv, **kwargs):
                if not fixture.load_release.wait(30):
                    raise TimeoutError("UI fixture model load hold was not released")
                if fixture.fail_model_start:
                    fixture.fail_model_start = False
                    raise OSError("Baseline model load failed")
                identity = super().start(argv, **kwargs)
                with fixture.lock:
                    fixture.model_process_identities.append(identity)
                return identity

        supervisor = BoundarySupervisor()
        self.model_supervisor = supervisor
        self.app.state.manager.deployments.processes = supervisor
        self.app.state.manager.deployments.router.processes = supervisor
        self._install_controls()

    def model_factory(self, run, sink):
        with self.lock:
            self.model_run_ids.append(run.id)
        if self.inference == "real":
            model = self.native_model_factory(run, sink)
            if self.scenario in COMPACTION_SCENARIOS:
                self.observe_existing_native_counts(model, run)
            if self.scenario == "instruction_retention":
                self.observe_final_native_input(model, run)
            return model
        if self.scenario == "instruction_retention" and run.task != "Saved baseline question":
            data = self.seed_data["instruction_retention"]
            if run.task == data["followup_task"]:
                script = [AIMessage(content=data["marker"])]
            else:
                script = [AIMessage(content="Creating the instruction retention marker", tool_calls=[{
                    "name": "write_file", "args": {"file_path": data["write_path"], "content": data["write_content"]},
                    "id": run.id + "-instruction-write"}])]
                script.extend(AIMessage(content=f"Reading original range {offset}", tool_calls=[{
                    "name": "read_file", "args": {"file_path": data["read_path"], "offset": offset,
                        "limit": 50 if offset == 1000 and self.negative_control == "instruction_changed_arguments" else 500},
                    "id": run.id + f"-instruction-read-{offset}"}]) for offset in (0, 500, 1000))
                if self.negative_control == "instruction_batched_calls":
                    reads = script[-2:]
                    script[-2:] = [AIMessage(content="Batching the final two reads deliberately",
                        tool_calls=[call for message in reads for call in message.tool_calls])]
                if self.negative_control == "instruction_repeated_action":
                    script.append(AIMessage(content="Repeating the write deliberately", tool_calls=[{
                        "name": "write_file", "args": {"file_path": data["write_path"], "content": data["write_content"]},
                        "id": run.id + "-instruction-repeat-write"}]))
                script.append(AIMessage(content="Instruction retention completed. " + data["marker"]))
            return FixtureModel(self, run, script)
        if self.scenario == "compaction_history" and run.task != "Saved baseline question":
            data = self.seed_data["compaction"]
            if run.task == data["followup_task"]:
                script = [AIMessage(content=data["marker"])]
            else:
                script = [AIMessage(content="Creating the compaction history marker", tool_calls=[{
                    "name": "write_file", "args": {"file_path": data["write_path"], "content": data["write_content"]},
                    "id": run.id + "-compaction-write"}])]
                script.extend(AIMessage(content=f"Reading original range {offset}", tool_calls=[{
                    "name": "read_file", "args": {"file_path": data["read_path"], "offset": offset, "limit": 500},
                    "id": run.id + f"-compaction-read-{offset}"}]) for offset in (0, 500, 1000))
                script.append(AIMessage(content="Compaction history completed. " + data["marker"]))
            return FixtureModel(self, run, script)
        if self.scenario == "parallel_helpers":
            if run.id in self.helper_models:
                return self.helper_models[run.id]
            if run.parent_run_id:
                helper = next(item for item in self.seed_data["parallel_helpers"] if item["id"] == run.agent_setup_id)
                script = [AIMessage(content=f"{helper['name']} requests its own write", tool_calls=[{
                    "name": "write_file", "args": {"file_path": helper["file_path"], "content": helper["content"]},
                    "id": "shared-helper-write"}]), AIMessage(content=f"{helper['name']} settled")]
            else:
                script = [AIMessage(content="Delegating two independent writes", tool_calls=[{
                    "name": "task", "args": {"subagent_type": item["id"], "description": item["task"]},
                    "id": f"delegate-{index}"} for index, item in enumerate(self.seed_data["parallel_helpers"])]),
                    AIMessage(content="Parallel helper decisions settled")]
            model = FixtureModel(self, run, script)
            self.helper_models[run.id] = model
            return model
        if run.task == "Saved baseline question":
            script = [AIMessage(content="Saved baseline answer")]
        elif self.scenario in {"approval", "retained"}:
            filename = "/approved.txt" if self.scenario == "approval" else "/baseline-output.txt"
            content = "Approved baseline output" if self.scenario == "approval" else "Retained baseline output"
            script = [AIMessage(content="", tool_calls=[{"name": "write_file", "args": {"file_path": filename, "content": content}, "id": "baseline-write"}]),
                      AIMessage(content="Baseline file operation completed")]
        elif self.scenario == "command":
            script = [AIMessage(content="", tool_calls=[{"name": "start_command", "args": {"command": [sys.executable, str(self.root / "project" / "owned-command.py")], "timeout_seconds": 40}, "id": "baseline-command"}]),
                      AIMessage(content="Baseline command completed")]
        elif self.scenario == "partial_effect":
            script = [AIMessage(content="", tool_calls=[{"name": "execute", "args": {"command": subprocess.list2cmdline([sys._base_executable, str(self.root / "project" / "partial-command.py")]), "timeout": 2}, "id": "baseline-partial-command"}]),
                      AIMessage(content="Must not continue after an uncertain effect")]
        else:
            script = [AIMessage(content="Baseline response completed")]
        return FixtureModel(self, run, script)

    def observe_existing_native_counts(self, model, run):
        """Observe existing counter calls without adding a call or changing it."""
        original = model.count_input_tokens
        def count(payload):
            # Deliberately outside the capture try: the original counter's
            # return and exception remain its own, including unavailable None.
            result = original(payload)
            self.record_input_count(run, payload, result, basis="native" if type(result) is int else "unavailable")
            return result
        object.__setattr__(model, "count_input_tokens", count)

    def record_input_count(self, run, payload, count, *, basis):
        try:
            from workbench_backend.inference.telemetry import current_request_purpose
            tools = payload.get("tools")
            with self.lock:
                self.compaction_input_counts.append({"ordinal": len(self.compaction_input_counts) + 1,
                    "run_id": run.id, "purpose": current_request_purpose(), "input_tokens": count, "basis": basis,
                    "payload_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True,
                        ensure_ascii=False, default=str).encode()).hexdigest(),
                    "tools_sha256": hashlib.sha256(json.dumps(tools, sort_keys=True,
                        ensure_ascii=False, default=str).encode()).hexdigest() if tools else None})
                self.compaction_counts_path.write_text(json.dumps(self.compaction_input_counts), encoding="utf-8")
            if self.scenario == "instruction_retention":
                self.record_instruction_input(run, payload, boundary="count", count=count, basis=basis)
        except Exception as exc:
            # An evidence write failure must not alter inference. The gate
            # rejects incomplete capture through this separate diagnostic.
            with self.lock:
                self.compaction_count_capture_errors.append({"run_id": run.id, "error_kind": type(exc).__name__})

    def observe_final_native_input(self, model, run):
        """Capture the existing final payload after its own guard; add no calls."""
        original = model._get_request_payload
        def payload(*args, **kwargs):
            result = original(*args, **kwargs)
            try:
                native = model._convert_input(args[0]).to_messages() if args else []
                self.record_instruction_input(run, result, boundary="final_request", native_messages=native)
            except Exception as exc:
                with self.lock:
                    self.instruction_input_capture_errors.append({"run_id": run.id, "error_kind": type(exc).__name__})
            return result
        object.__setattr__(model, "_get_request_payload", payload)

    def instruction_after_compaction(self, run_id):
        return any(item["run_id"] == run_id for item in self.compaction_native["cutoffs"])

    def remember_instruction_input(self, run, messages, *, origin):
        """Capture the original native author/ID before reduction; never match text."""
        existing = self.compaction_native.setdefault("inputs", {})
        if run.id in existing:
            return
        originals = []
        for message in messages:
            value = message.model_dump(mode="json") if hasattr(message, "model_dump") else message
            meta = value.get("additional_kwargs", {})
            if (value.get("type") == "human" and value.get("id")
                    and not meta.get("workbench_tool_context")
                    and meta.get("lc_source") not in {"summarization", "rubric_grader", "workbench_current_task_reference"}
                    and value.get("name") != "rubric_grader"):
                originals.append(value)
        original = (next((message for message in originals if message["id"] == run.input_message_id), None)
            if run.input_message_id else originals[-1] if originals else None)
        if original is not None:
            existing[run.id] = {"id": original["id"], "content": original["content"], "origin": origin}
            self.compaction_native_path.write_text(json.dumps(self.compaction_native), encoding="utf-8")

    @staticmethod
    def _task_occurrences(content, task):
        if isinstance(content, str):
            return content.count(task)
        if isinstance(content, list):
            return sum(ApplicationFixture._task_occurrences(block.get("text"), task)
                for block in content if isinstance(block, dict) and block.get("type") in {"text", "input_text"})
        return 0

    def record_instruction_input(self, run, payload, *, boundary, count=None, basis=None, native_messages=None):
        try:
            from workbench_backend.inference.telemetry import current_request_purpose
            copied = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
            messages = copied.get("messages", [])
            task_indices = [index for index, message in enumerate(messages)
                if self._task_occurrences(message.get("content"), run.task)]
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
            with self.lock:
                if native_messages:
                    self.remember_instruction_input(run, native_messages, origin=boundary)
                source_id = (self.compaction_native.get("inputs", {}).get(run.id) or {}).get("id") or run.input_message_id
                matching = [item for item in self.compaction_input_counts
                    if item["run_id"] == run.id and item["payload_sha256"] == digest]
                self.instruction_inputs.append({"ordinal": len(self.instruction_inputs) + 1,
                    "run_id": run.id, "input_message_id": source_id,
                    "purpose": current_request_purpose(), "boundary": boundary,
                    "after_compaction": self.instruction_after_compaction(run.id),
                    "native_input_removed": any(item["run_id"] == run.id and item.get("native_input_removed")
                        for item in self.compaction_native["cutoffs"]),
                    "payload_sha256": digest,
                    "tools_sha256": hashlib.sha256(json.dumps(payload["tools"], sort_keys=True,
                        ensure_ascii=False, default=str).encode()).hexdigest() if payload.get("tools") else None,
                    "messages": messages, "task_occurrences": sum(self._task_occurrences(message.get("content"), run.task) for message in messages),
                    "user_task_occurrences": sum(self._task_occurrences(message.get("content"), run.task) for message in messages if message.get("role") == "user"),
                    "task_message_indices": task_indices,
                    "task_reference_indices": [index for index, message in enumerate(native_messages or [])
                        if message.additional_kwargs.get("lc_source") == "workbench_current_task_reference"],
                    "native_message_ids": [message.id for message in native_messages or []],
                    "task_source_ids": [message.id for message in native_messages or []
                        if self._task_occurrences(message.content, run.task)],
                    "task_reference_ids": [message.id for message in native_messages or []
                        if message.additional_kwargs.get("lc_source") == "workbench_current_task_reference"],
                    "task_reference_input_ids": [message.additional_kwargs.get("workbench_current_task_input_id")
                        for message in native_messages or []
                        if message.additional_kwargs.get("lc_source") == "workbench_current_task_reference"],
                    "matching_count_ordinals": [item["ordinal"] for item in matching],
                    "count_ordinal": matching[-1]["ordinal"] if boundary == "count" and matching else None,
                    "input_tokens": count if boundary == "count" else matching[-1]["input_tokens"] if matching else None,
                    "basis": basis if boundary == "count" else matching[-1]["basis"] if matching else "unavailable"})
                self.instruction_inputs_path.write_text(json.dumps(self.instruction_inputs), encoding="utf-8")
        except Exception as exc:
            # Capture is passive. An incomplete evidence gate must reject it.
            with self.lock:
                self.instruction_input_capture_errors.append({"run_id": run.id, "error_kind": type(exc).__name__})

    def _install_controls(self):
        @self.app.post("/__test__/seed")
        def seed(body: dict[str, Any]):
            return self.seed(body.get("scenario", "baseline"))

        @self.app.post("/__test__/scenario")
        def scenario(body: dict[str, Any]):
            return self.configure(body)

        @self.app.post("/__test__/reset")
        def reset():
            self.configure({"scenario": "baseline", "release_model": True, "release_model_load": True})
            self.lose_next_ack = self.disconnect_next_stream = False
            self.negative_control = None
            self.failed_lookup_paths.clear()
            self.faults = {"lost_acknowledgements": 0, "stream_disconnects": 0, "draft_losses": 0, "state_lookup_failures": 0}
            return self.state()

        @self.app.get("/__test__/state")
        def state():
            return self.state()

        @self.app.post("/__test__/shutdown")
        def shutdown():
            self.close()
            # Match the native launcher: observers finish before ASGI lifespan
            # waits for their responses and closes their application store.
            self.app.state.shutdown_requested.set()
            server = getattr(self.app.state, "ui_fixture_server", None)
            if server is not None:
                server.should_exit = True
            if self.fail_shutdown:
                self.fail_shutdown = False
                raise HTTPException(500, "Baseline native shutdown failed")
            return {"stopping": True}

        @self.app.middleware("http")
        async def transport_fault(request, call_next):
            from workbench_backend.local_trust import tokens_match
            authenticated = tokens_match(request.headers.get("X-Workbench-Local-Token", ""), self.app.state.local_trust_token)
            path = request.url.path
            command = authenticated and request.method == "POST" and path.endswith("/commands")
            if command:
                body = await request.json()
                if body.get("method") == "run.start":
                    with self.lock:
                        self.submissions.append({"thread_id": path.split("/")[-2], "payload": body})
                    if self.reject_next_submit:
                        self.reject_next_submit = False
                        return JSONResponse({"type": "error", "id": body.get("id"), "error": "fixture_rejected", "message": "Baseline task rejected before acceptance"}, status_code=409)
                    if not await asyncio.to_thread(self.submit_release.wait, 30):
                        return JSONResponse({"error": "Admission hold exceeded its test deadline"}, status_code=503)
            state_read = (path.startswith("/v1/agent-interaction/") and path.endswith("/state")) or (path.startswith("/v1/chat/conversations/") and len(path.split("/")) == 5)
            if self.submissions:
                original_thread = self.submissions[-1]["thread_id"]
                state_read = path in {f"/v1/agent-interaction/threads/{original_thread}/state", f"/v1/chat/conversations/{self.seed_data.get('conversation_id')}"}
            if authenticated and request.method == "GET" and state_read and self.fail_state_reads:
                self.fail_state_reads -= 1
                self.faults["state_lookup_failures"] += 1
                self.failed_lookup_paths.append(path)
                return JSONResponse({"error": "Baseline state lookup temporarily unavailable"}, status_code=503)
            if self.negative_control == "lose_draft" and request.method == "GET" and self.seed_data and request.url.path == f"/v1/chat/conversations/{self.seed_data['conversation_id']}" and tokens_match(request.headers.get("X-Workbench-Local-Token", ""), self.app.state.local_trust_token):
                saved = self.app.state.chat.store.get(self.seed_data["conversation_id"])
                if saved and saved.draft and saved.draft.content:
                    from workbench_backend.chat.schemas import ChatDraftUpdateRequest
                    self.app.state.chat.update_draft(saved.id, ChatDraftUpdateRequest(content=""))
                    self.negative_control = None
                    self.faults["draft_losses"] += 1
            response = await call_next(request)
            path = request.url.path
            if command and body.get("method") == "run.start" and response.status_code < 300 and self.negative_control in {"duplicate_execution", "compaction_duplicate_execution"}:
                # Deliberately violate one-execution acceptance through the real
                # graph owner. This test-only control never changes production.
                from workbench_backend.agents.schemas import AgentStartRequest
                message = body["params"]["input"]["messages"][0]
                setup = {key: value for key, value in body["params"].get("metadata", {}).get("workbench", {}).items() if key in AgentStartRequest.model_fields}
                setup.update(task=message["content"], input_message_id=f"negative-{uuid4()}", thread_id=f"negative-{uuid4()}", source_surface="agent-run")
                self.negative_control = None
                self.app.state.harness.start(AgentStartRequest.model_validate(setup))
            if authenticated and request.method == "GET" and path.startswith("/v1/agent-interaction/threads/") and path.endswith("/state") and response.status_code < 300 and self.negative_control in {"compaction_overwritten_history", "compaction_visible_summary"}:
                # Corrupt only observation; the evidence oracle reads unchanged
                # actual durable records. No production hook knows this switch.
                payload = json.loads(b"".join([chunk async for chunk in response.body_iterator]))
                messages = payload["values"]["messages"]
                if self.negative_control == "compaction_overwritten_history":
                    from workbench_backend.state.checkpointer import conversation_state
                    binding = self.app.state.interaction.binding(path.split("/")[-2])
                    checkpoint = conversation_state(self.app.state.manager.paths.checkpoints_db,
                        binding["graph_thread_id"])
                    canonical = {message.id: message for message in checkpoint.get("messages", [])
                        if message.type == "tool" and message.id}
                    for message in messages:
                        reduced = canonical.get(message.get("id"))
                        if (message.get("type") == "tool" and reduced is not None
                                and len(str(reduced.content)) < len(str(message.get("content")))):
                            # Mirror the defect: native clipping replaces the
                            # same-ID visible tool result, without changing its
                            # identity, position or the durable display archive.
                            message["content"] = reduced.model_dump(mode="json")["content"]
                            break
                else:
                    messages.append({"id": "negative-visible-summary", "type": "ai",
                        "content": self.seed_data["compaction"]["internal_summary_marker"]})
                headers = {key: value for key, value in response.headers.items() if key.lower() != "content-length"}
                return JSONResponse(payload, headers=headers, background=response.background)
            if self.lose_next_ack and request.method == "POST" and response.status_code < 300 and (path.endswith("/commands") or path.endswith("/start") or path.endswith("/queue")):
                self.lose_next_ack = False
                self.faults["lost_acknowledgements"] += 1
                return JSONResponse({"error": "Baseline acknowledgement lost after acceptance"}, status_code=503)
            if path.endswith("/stream/events") and response.status_code < 300:
                async def disconnected():
                    try:
                        async for chunk in response.body_iterator:
                            yield chunk
                            # Arm faults after a page's observer is already open;
                            # terminate only observation after a real native frame.
                            if self.disconnect_next_stream:
                                self.disconnect_next_stream = False
                                self.faults["stream_disconnects"] += 1
                                break
                    finally:
                        await response.body_iterator.aclose()
                return StreamingResponse(
                    disconnected(),
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type="text/event-stream",
                    background=response.background,
                )
            return response

    def configure(self, body):
        scenario = body.get("scenario", self.scenario)
        if scenario not in {"baseline", "lost_ack", "approval", "command", "retained", "model", "partial_effect", "parallel_helpers", "compaction_history", "instruction_retention"}:
            raise HTTPException(400, "Unknown UI fixture scenario")
        self.scenario = scenario
        if scenario == "parallel_helpers" and self.seed_data:
            self.prepare_parallel_helpers()
        if scenario == "compaction_history" and self.seed_data:
            self.prepare_compaction_history()
        if scenario == "instruction_retention" and self.seed_data:
            self.prepare_instruction_retention()
        if "hold_model" in body:
            self.hold_model = bool(body["hold_model"])
            self.release.clear() if self.hold_model else self.release.set()
        if body.get("release_model"):
            self.hold_model = False
            self.release.set()
        if "hold_submit" in body:
            self.submit_release.clear() if body["hold_submit"] else self.submit_release.set()
        if body.get("release_submit"):
            self.submit_release.set()
        if "fail_state_reads" in body:
            self.fail_state_reads = max(0, int(body["fail_state_reads"]))
        if "hold_model_load" in body:
            self.load_release.clear() if body["hold_model_load"] else self.load_release.set()
        if body.get("release_model_load"):
            self.load_release.set()
        for field in ("lose_next_ack", "disconnect_next_stream", "fail_model_start", "fail_shutdown", "reject_next_submit"):
            if field in body:
                setattr(self, field, bool(body[field]))
        if "negative_control" in body:
            value = body["negative_control"]
            if value not in {None, "lose_draft", "duplicate_execution", "compaction_overwritten_history", "compaction_visible_summary", "compaction_duplicate_execution",
                    "instruction_missing_text", "instruction_changed_arguments", "instruction_repeated_action", "instruction_batched_calls"}:
                raise HTTPException(400, "Unknown negative control")
            if self.inference == "real" and value in {"instruction_missing_text", "instruction_changed_arguments", "instruction_repeated_action", "instruction_batched_calls"}:
                raise HTTPException(400, "Instruction controls require deterministic inference")
            self.negative_control = value
        if body.get("change_source"):
            (self.root / "project" / "baseline-output.txt").write_text("Changed source after retention", encoding="utf-8")
        return self.state()

    def prepare_compaction_history(self):
        """Only author isolated inputs; stock middleware owns all reduction."""
        if "compaction" not in self.seed_data:
            marker = "COMPACTION-FACT-JUPITER-7391"
            data = {"marker": marker, "internal_summary_marker": "INTERNAL-COMPACTION-SUMMARY",
                "read_path": "/compaction-source.txt", "write_path": "/compaction-effect.txt",
                "write_content": "one compaction history effect",
                "expected_read_count": 1 if self.inference == "real" else 3,
                "tool_start_marker": "ORIGINAL-COMPACTION-RANGE-0-START",
                "tool_end_marker": "ORIGINAL-COMPACTION-RANGE-0-END",
                "tools": ["read_file", "write_file"],
                "request_settings": {"temperature": 0.0, "seed": 7, "max_tokens": 512}}
            deployment = self.app.state.manager.get_deployment(self.seed_data["deployment_id"])
            if self.inference == "real" and deployment.server_props and deployment.server_props.chat_template_caps.get("supports_thinking"):
                data["request_settings"]["reasoning"] = "off"
            reads = (f"Then call read_file exactly once with file_path {data['read_path']}, offset 0, and limit 500. "
                if self.inference == "real" else
                f"Then call read_file three times with file_path {data['read_path']}, limit 500, and offsets 0, then 500, then 1000. ")
            read_guidance = ("Read only this one range. If the result is clipped, proceed to your final answer. "
                if self.inference == "real" else
                "Read only these three ranges. If a result is clipped, keep going to the next requested range. ")
            finish = "After this single read" if self.inference == "real" else "After all three reads"
            data["task"] = (f"Remember this exact fact: {marker}. First call write_file exactly once with file_path "
                f"{data['write_path']} and content exactly {data['write_content']}. " + reads +
                "Call only one tool in each assistant response and wait for its result before the next call. "
                + read_guidance +
                "Do not reread a range, do not repeat the write, and do not read conversation_history files. "
                f"{finish}, reply briefly with {marker}.")
            data["followup_task"] = "Reply with only the exact COMPACTION-FACT code I originally asked you to remember. Do not call any tools."
            # Complete modest lines create native context pressure. The archive
            # must preserve the emitted result including its final marker when
            # native overflow recovery replaces the checkpoint's same-ID tail.
            lines = [f"line {index:04d}: a b c d e f g h i j k l" for index in range(1500)]
            for offset in (0, 500, 1000):
                lines[offset] = f"ORIGINAL-COMPACTION-RANGE-{offset // 500}-START {marker}"
                lines[offset + 499] = f"ORIGINAL-COMPACTION-RANGE-{offset // 500}-END"
            source = "\n".join(lines) + "\n"
            (self.root / "project" / data["read_path"].lstrip("/")).write_text(source, encoding="utf-8")
            data["source_sha256"] = hashlib.sha256(source.encode()).hexdigest()
            self.seed_data["compaction"] = data
            self.seed_data.update(compaction_task=data["task"], compaction_followup_task=data["followup_task"],
                compaction_marker=marker, compaction_tool_output=data["tool_start_marker"])
            self.seed_path.write_text(json.dumps(self.seed_data), encoding="utf-8")
        from workbench_backend.agents.setup_schemas import AgentInputPolicy
        conversation = self.app.state.chat.store.get(self.seed_data["conversation_id"])
        data = self.seed_data["compaction"]
        selection = {"presented_tools": data["tools"], "approval_mode": "full_access",
            "input_policy": AgentInputPolicy(tool_loading="always"), "per_request_overrides": data["request_settings"]}
        self.app.state.chat.store.put(conversation.model_copy(update={**selection,
            "setup_overrides": conversation.setup_overrides.model_copy(update=selection)}))

    def prepare_instruction_retention(self):
        """Author the recovered original input; native compaction owns progress."""
        if "instruction_retention" not in self.seed_data:
            task_hash = hashlib.sha256(INSTRUCTION_RETENTION_TASK.encode()).hexdigest()
            if task_hash != INSTRUCTION_RETENTION_TASK_SHA256:
                raise ValueError("Recovered instruction task changed")
            marker = "COMPACTION-FACT-JUPITER-7391"
            data = {"marker": marker, "internal_summary_marker": "INTERNAL-INSTRUCTION-RETENTION-SUMMARY",
                "read_path": "/compaction-source.txt", "write_path": "/compaction-effect.txt",
                "write_content": "one compaction history effect", "expected_read_count": 3,
                "tool_start_marker": "ORIGINAL-COMPACTION-RANGE-0-START", "tool_end_marker": "ORIGINAL-COMPACTION-RANGE-0-END",
                "tools": ["read_file", "write_file"], "request_settings": {"temperature": 0.0, "seed": 7, "max_tokens": 512},
                "task": INSTRUCTION_RETENTION_TASK, "task_sha256": task_hash,
                "followup_task": "Reply with only the exact COMPACTION-FACT code I originally asked you to remember. Do not call any tools.",
                "recovered_trial": {"run_id": "agent_d519f7ec4b14", "task_sha256": task_hash,
                    "source_sha256": INSTRUCTION_RETENTION_SOURCE_SHA256,
                    "evidence": ".scratch/task03-compaction/broader-model-failure-recovery.json"}}
            lines = [f"line {index:04d}: a b c d e f g h i j k l" for index in range(1500)]
            for offset in (0, 500, 1000):
                lines[offset] = f"ORIGINAL-COMPACTION-RANGE-{offset // 500}-START {marker}"
                lines[offset + 499] = f"ORIGINAL-COMPACTION-RANGE-{offset // 500}-END"
            source = "\n".join(lines) + "\n"
            data["source_sha256"] = hashlib.sha256(source.encode()).hexdigest()
            if data["source_sha256"] != INSTRUCTION_RETENTION_SOURCE_SHA256:
                raise ValueError("Recovered instruction source changed")
            data["expected_calls"] = [{"name": "write_file", "args": {"file_path": data["write_path"], "content": data["write_content"]}},
                *[{"name": "read_file", "args": {"file_path": data["read_path"], "offset": offset, "limit": 500}} for offset in (0, 500, 1000)]]
            source_path = self.root / "project" / data["read_path"].lstrip("/")
            source_path.write_text(source, encoding="utf-8")
            data["source_file_sha256"] = hashlib.sha256(source_path.read_bytes()).hexdigest()
            self.seed_data["instruction_retention"] = data
            self.seed_data.update(instruction_retention_task=data["task"], instruction_retention_followup_task=data["followup_task"])
            self.seed_path.write_text(json.dumps(self.seed_data), encoding="utf-8")
        from workbench_backend.agents.setup_schemas import AgentInputPolicy
        conversation = self.app.state.chat.store.get(self.seed_data["conversation_id"])
        data = self.seed_data["instruction_retention"]
        selection = {"presented_tools": data["tools"], "approval_mode": "full_access",
            "input_policy": AgentInputPolicy(tool_loading="always"), "per_request_overrides": data["request_settings"]}
        self.app.state.chat.store.put(conversation.model_copy(update={**selection,
            "setup_overrides": conversation.setup_overrides.model_copy(update=selection)}))

    def prepare_parallel_helpers(self):
        """Author disposable selections; actual admission/graphs own every request."""
        from workbench_backend.agents.setup_schemas import AgentSetupCreateRequest

        if "parallel_helpers" not in self.seed_data:
            helpers = []
            request_settings = {"temperature": 0.0, "seed": 7, "max_tokens": 128}
            deployment = self.app.state.manager.get_deployment(self.seed_data["deployment_id"])
            if self.inference == "real" and deployment.server_props and deployment.server_props.chat_template_caps.get("supports_thinking"):
                request_settings["reasoning"] = "off"
            for name, stem in (("Alpha helper", "alpha"), ("Beta helper", "beta")):
                file_path, content = f"/helper-{stem}.txt", f"{stem} helper output"
                task = f"Call write_file exactly once with file_path {file_path} and content exactly {content}. If denied, do not retry. Return one short final answer."
                helper = self.app.state.setups.create_setup(AgentSetupCreateRequest(name=name,
                    role=task, configuration={"deployment_id": self.seed_data["deployment_id"],
                        "presented_tools": ["write_file"], "approval_mode": "ask",
                        "input_policy": {"tool_loading": "always"},
                        "per_request_overrides": request_settings}))
                helpers.append({"id": helper.id, "name": name, "file_path": file_path, "content": content, "task": task})
            self.seed_data["parallel_helpers"] = helpers
            self.seed_data["parallel_helper_task"] = (
                "Call task twice in one assistant response, using exactly these two separate argument objects: "
                + json.dumps([{"subagent_type": item["id"], "description": item["task"]} for item in helpers])
                + " Each helper's description contains only its own task. Do not call write_file yourself. After the helpers settle, reply briefly and do not delegate again.")
            self.seed_data["parallel_request_settings"] = {**request_settings, "max_tokens": 512}
            conversation = self.app.state.chat.store.get(self.seed_data["conversation_id"])
            from workbench_backend.agents.setup_schemas import AgentInputPolicy
            selection = {"helper_agent_ids": [item["id"] for item in helpers], "approval_mode": "ask",
                "presented_tools": ["write_file"], "input_policy": AgentInputPolicy(tool_loading="always"),
                "per_request_overrides": self.seed_data["parallel_request_settings"]}
            self.app.state.chat.store.put(conversation.model_copy(update={**selection,
                "setup_overrides": conversation.setup_overrides.model_copy(update=selection)}))
            self.seed_path.write_text(json.dumps(self.seed_data), encoding="utf-8")

    def seed_real(self, project, project_path):
        from tests_integration.assets import resolve_assets
        from tests_integration.test_real_model_smoke import RealLlamaServer
        from workbench_backend.chat.schemas import ChatConversationCreateRequest
        from workbench_backend.inference.schemas import ConnectedDeploymentRequest
        from workbench_backend.inference.hashes import sha256_file
        assets = resolve_assets()
        self.real_server = RealLlamaServer(assets, self.root / "real-llama-server.log")
        try:
            self.real_server.wait_ready()
        except Exception:
            self.real_server.close()
            raise
        identity = psutil.Process(self.real_server.process.pid)
        version = subprocess.run([str(assets.llama_server), "--version"], capture_output=True, text=True, timeout=15)
        if version.returncode:
            raise RuntimeError("The existing native runtime did not report its version")
        self.real_identity = {"pid": self.real_server.process.pid, "create_time": identity.create_time(),
            "runtime_sha256": sha256_file(assets.llama_server),
            "model_sha256": sha256_file(assets.model), "version": (version.stdout + version.stderr).strip(),
            "runtime_name": assets.llama_server.name, "model_name": assets.model.name,
            "inference": "actual local llama.cpp; no scripted model", "startup": {"ctx_size": 8192, "parallel": 1}}
        manager = self.app.state.manager
        deployment = manager.attach_connected(ConnectedDeploymentRequest(endpoint=self.real_server.endpoint, display_name="Existing real local model", startup={"ctx_size": 8192}))
        # Connected servers have no installed bundle. Use their public setup
        # ownership with authored request overrides, not an orphan model profile.
        conversation = self.app.state.chat.create(ChatConversationCreateRequest(title="Real model conversation", project_id=project.id, deployment_id=deployment.id, per_request_overrides={"temperature": 0.0, "seed": 7, "max_tokens": 128}, approval_mode="full_access", presented_tools=["write_file"], input_policy={"tool_loading": "always"}))
        self.seed_data = {"project_id": project.id, "conversation_id": conversation.id, "deployment_id": deployment.id, "profile_id": None,
            "fixture_root": str(self.root), "project_path": str(project_path), "seed_run_ids": [], "retained_asset_ids": [], "real_model_identity": self.real_identity}
        self.seed_path.write_text(json.dumps(self.seed_data), encoding="utf-8")
        if self.scenario == "compaction_history":
            self.prepare_compaction_history()
        if self.scenario == "instruction_retention":
            self.prepare_instruction_retention()
        return {**self.seed_data, "scenario": self.scenario}

    def seed(self, scenario="baseline"):
        from workbench_backend.agents.setup_schemas import ProjectCreateRequest
        from workbench_backend.chat.schemas import ChatConversationCreateRequest, ChatStartRequest
        from workbench_backend.inference.schemas import LocalImportRequest, ManagedDeploymentRequest, PinRuntimeRequest, ProfileWriteRequest
        from gguf import GGUFWriter
        import numpy as np

        self.configure({"scenario": scenario, "release_model": True, "release_model_load": True})
        if self.seed_data:
            deployment = self.app.state.manager.get_deployment(self.seed_data["deployment_id"])
            if deployment.status.value == "stopped":
                self.app.state.manager.start_deployment(deployment.id)
            if scenario == "retained" and not self.seed_data["retained_asset_ids"]:
                self._retain_seed_output()
            return {**self.seed_data, "scenario": self.scenario}
        project_path = self.root / "project"
        project_path.mkdir(exist_ok=True)
        (project_path / "owned-command.py").write_text("import time\nprint('Baseline owned command running', flush=True)\ntime.sleep(40)\n", encoding="utf-8")
        (project_path / "partial-command.py").write_text("import threading\nfrom pathlib import Path\nwith Path('partial-marker.txt').open('a') as marker: marker.write('once\\n')\nthreading.Event().wait(120)\n", encoding="utf-8")
        project = self.app.state.setups.create_project(ProjectCreateRequest(name="Baseline project", path=str(project_path)))
        if self.inference == "real":
            return self.seed_real(project, project_path)
        gguf = self.root / "baseline-model.gguf"
        writer = GGUFWriter(str(gguf), "llama")
        writer.add_name("Baseline model")
        writer.add_quantization_version(2)
        writer.add_file_type(0)
        writer.add_context_length(4096)
        writer.add_block_count(1)
        writer.add_tensor("token_embd.weight", np.zeros((2, 2), dtype=np.float32))
        writer.write_header_to_file(); writer.write_kv_data_to_file(); writer.write_tensors_to_file(); writer.close()
        manager = self.app.state.manager
        job = manager.import_local(LocalImportRequest(source_path=str(gguf)))
        deadline = time.monotonic() + 15
        while job.status.value in {"pending", "running", "stopping"}:
            if time.monotonic() >= deadline:
                raise TimeoutError("Baseline model metadata import did not finish")
            time.sleep(.02)
            job = manager.get_job(job.id)
        if not job.bundle_id:
            raise RuntimeError(f"Baseline model metadata import failed: {job}")
        bundle = manager.rename_bundle(job.bundle_id, "Baseline model")
        runtime = self.root / "inference-boundary"
        runtime.mkdir(exist_ok=True)
        executable = runtime / "fake-llama-server"
        executable.write_text(f"#!{sys.executable}\nimport runpy\nrunpy.run_path({str(REPO_ROOT / 'apps/backend/tests/fake_llama_server.py')!r}, run_name='__main__')\n", encoding="utf-8")
        executable.chmod(0o755)
        (runtime / "cudart64_134.dll").write_bytes(b"deterministic-test-boundary")
        manager.pin_runtime(PinRuntimeRequest(local_executable=str(executable)))
        profile = manager.create_profile(ProfileWriteRequest(display_name="Baseline setup", bundle_id=bundle.id, startup={"port": free_port(), "ctx_size": 4096}, per_request={}, agent={}))
        manager.set_default_configuration(bundle.id, profile.id)
        deployment = manager.create_managed(ManagedDeploymentRequest(bundle_id=bundle.id, profile_id=profile.id))
        if deployment.status.value != "running":
            raise RuntimeError(f"Baseline deterministic inference boundary did not start: {deployment.error}")
        conversation = self.app.state.chat.create(ChatConversationCreateRequest(title="Baseline conversation", project_id=project.id, deployment_id=deployment.id, profile_id=profile.id, approval_mode="ask", presented_tools=["write_file", "execute", "start_command", "command_status", "stop_command"], input_policy={"tool_loading": "always"}))
        other = self.app.state.chat.create(ChatConversationCreateRequest(title="Other baseline conversation", project_id=project.id, deployment_id=deployment.id, profile_id=profile.id, approval_mode="ask"))
        self.app.state.chat.start(conversation.id, ChatStartRequest(task="Saved baseline question"))
        self.wait_terminal(conversation.id)
        self.seed_data = {"project_id": project.id, "conversation_id": conversation.id, "other_conversation_id": other.id, "deployment_id": deployment.id, "profile_id": profile.id, "bundle_id": bundle.id, "fixture_root": str(self.root), "project_path": str(project_path), "owned_effect_path": str(project_path / "approved.txt"), "retained_asset_ids": [], "seed_run_ids": [run.id for run in self.app.state.app_store.list_runs()]}
        if scenario == "retained":
            self._retain_seed_output()
        if scenario == "compaction_history":
            self.prepare_compaction_history()
        if scenario == "instruction_retention":
            self.prepare_instruction_retention()
        self.seed_path.write_text(json.dumps(self.seed_data), encoding="utf-8")
        return {**self.seed_data, "scenario": self.scenario}

    def _retain_seed_output(self):
        from workbench_backend.assets.schemas import RetainedAssetListFilters
        from workbench_backend.chat.schemas import ChatStartRequest

        conversation_id = self.seed_data["conversation_id"]
        self.app.state.chat.start(conversation_id, ChatStartRequest(task="Create the retained baseline output", approval_mode="full_access"))
        run = self.wait_terminal(conversation_id)
        deadline = time.monotonic() + 5
        while True:
            collected = [asset for asset in self.app.state.assets.list_assets(
                RetainedAssetListFilters(session_id=conversation_id))
                if asset.source_run_id == run.id and asset.source_tool_call_id == "baseline-write"]
            if collected:
                if len(collected) != 1:
                    raise RuntimeError("Native terminal reconciliation retained more than one baseline output")
                asset, = collected
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("Native terminal reconciliation did not retain the baseline output")
            time.sleep(.02)
        conversation = self.app.state.chat.store.get(conversation_id)
        self.app.state.chat.store.put(conversation.model_copy(update={"approval_mode": "ask"}))
        self.seed_data["retained_asset_ids"] = [asset.id]
        self.seed_data["retained_source_path"] = str(self.root / "project" / "baseline-output.txt")
        self.seed_data["seed_run_ids"].append(run.id)
        self.seed_path.write_text(json.dumps(self.seed_data), encoding="utf-8")

    def wait_terminal(self, conversation_id, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            conversation = self.app.state.chat.get(conversation_id)
            run = conversation.current_run
            if run and run.status.value in {"completed", "failed", "cancelled"}:
                if run.status.value != "completed":
                    raise RuntimeError(f"Baseline seed run failed: {run.error}")
                return run
            time.sleep(.02)
        raise TimeoutError("Baseline history seed did not finish")

    def compaction_evidence(self, tested_runs, *, key="compaction"):
        """Read native checkpoints and display records; never execute a graph."""
        if key not in self.seed_data:
            return {"rows": []}
        from workbench_backend.agents.harness_backend import build_run_backend
        from workbench_backend.state.checkpointer import conversation_state
        fields = ("id", "type", "content", "name", "tool_calls", "tool_call_id", "status")
        def public_message(message):
            value = message.model_dump(mode="json") if hasattr(message, "model_dump") else message
            return {key: value[key] for key in fields if key in value and value[key] is not None}
        rows = []
        threads = dict.fromkeys(run.thread_id or run.id for run in tested_runs if not run.parent_run_id)
        for graph_id in threads:
            related = [run for run in tested_runs if (run.thread_id or run.id) == graph_id]
            run = related[-1]
            interaction_id = self.app.state.app_store.interaction_id_for_graph(graph_id)
            if interaction_id is None:
                continue
            display = self.app.state.interaction.state(interaction_id)
            current_id = (display["values"].get("workbench", {}).get("run") or {}).get("id")
            run = next((item for item in related if item.id == current_id), run)
            checkpoint = conversation_state(self.app.state.manager.paths.checkpoints_db, graph_id)
            canonical = [public_message(message) for message in checkpoint.get("messages", [])]
            archive = [public_message(message) for message in display["values"].get("messages", [])]
            compacted = [{"run_id": item.id, **event.model_dump(mode="json")}
                for item in related for event in item.events if event.kind == "context_compacted"]
            summary = checkpoint.get("_summarization_event") or {}
            paths = list(dict.fromkeys(event["detail"].get("history_preserved_at")
                for event in compacted if event["detail"].get("history_preserved_at")))
            offloads = []
            backend = build_run_backend(run, self.app.state.manager.paths, prepare_storage=False)
            for path in paths:
                result = backend.download_files([path])[0]
                raw = result.content or b""
                offloads.append({"path": path, "readable": result.error is None,
                    "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                    "has_marker": self.seed_data[key]["marker"].encode() in raw,
                    "has_read_results": b"ORIGINAL-COMPACTION-RANGE-" in raw})
            related_ids = {item.id for item in related}
            model_calls = ([{**sample.model_dump(mode="json"), "run_id": item.id}
                for item in related for sample in item.generation_history] if self.inference == "real" else
                [dict(call) for call in self.compaction_model_calls if call["run_id"] in related_ids])
            outcomes = [outcome.model_dump(mode="json") for item in related for outcome in item.tool_outcomes.values()]
            writes = [call for item in related for call in item.tool_invocations if call["name"] == "write_file"]
            reads = [call for item in related for call in item.tool_invocations if call["name"] == "read_file"]
            effect = self.root / "project" / self.seed_data[key]["write_path"].lstrip("/")
            data = self.seed_data[key]
            with self.lock:
                original_tool_results = [dict(message) for item in related
                    for message in self.compaction_native["tool_results"].get(item.id, {}).values()]
                observed_cutoffs = [dict(item) for item in self.compaction_native["cutoffs"] if item["run_id"] in related_ids]
                input_counts = [dict(item) for item in self.compaction_input_counts if item["run_id"] in related_ids]
                capture_errors = [dict(item) for item in self.compaction_count_capture_errors if item["run_id"] in related_ids]
            rows.append({"thread_id": interaction_id, "graph_thread_id": graph_id, "source_surface": run.source_surface,
                "run_id": run.id, "run_ids": [item.id for item in related], "status": run.status.value,
                "archive": archive, "canonical": canonical, "interaction_cursor": display["interaction_cursor"],
                "native_summary_count": sum(call["purpose"] == "summary" for call in model_calls),
                "cutoff_index": summary.get("cutoff_index", 0), "observed_cutoffs": observed_cutoffs,
                "summary_marker": data["internal_summary_marker"], "compacted_events": compacted,
                "model_calls": model_calls, "write_count": len(writes), "read_count": len(reads),
                "native_input_counts": input_counts, "native_input_capture_errors": capture_errors,
                "tool_outcomes": outcomes, "original_tool_results": original_tool_results,
                "write_content": effect.read_text(encoding="utf-8") if effect.exists() else None,
                "offload_readable": bool(offloads) and all(item["readable"] for item in offloads), "offloads": offloads,
                "context_observation": run.context_observation.model_dump(mode="json") if run.context_observation else None,
                "housekeeping_context": {key: value.model_dump(mode="json") for key, value in run.housekeeping_context.items()},
                "archive_sha256": hashlib.sha256(json.dumps(archive, sort_keys=True).encode()).hexdigest(),
                "canonical_sha256": hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()})
            if key == "instruction_retention":
                with self.lock:
                    inputs = [dict(item) for item in self.instruction_inputs if item["run_id"] in related_ids]
                    errors = [dict(item) for item in self.instruction_input_capture_errors if item["run_id"] in related_ids]
                native_input = self.compaction_native.get("inputs", {}).get(run.id) or {}
                rows[-1].update(accepted_task=run.task, accepted_task_sha256=hashlib.sha256(run.task.encode()).hexdigest(),
                    accepted_input_id=native_input.get("id") or run.input_message_id, original_native_input=dict(native_input),
                    calls=[{"id": call.get("id"), "name": call["name"], "args": call.get("args", {})}
                        for item in related for call in item.tool_invocations],
                    work_inputs=[item for item in inputs if item["purpose"] == "work" and item["boundary"] != "count"],
                    counted_inputs=[item for item in inputs if item["boundary"] == "count"],
                    input_capture_errors=errors)
        return {"rows": rows}

    def state(self):
        runs = self.app.state.app_store.list_runs()
        seed_ids = set(self.seed_data.get("seed_run_ids", []))
        tested_runs = [run for run in runs if run.id not in seed_ids and not run.parent_run_id]
        helper_runs = [run for run in runs if run.parent_run_id in {item.id for item in tested_runs}]
        pending_interrupts = []
        for run in tested_runs:
            interaction_id = self.app.state.app_store.interaction_id_for_graph(run.thread_id or run.id)
            if interaction_id:
                projected = self.app.state.interaction.state(interaction_id)["values"].get("__interrupt__", [])
                pending_interrupts.extend({"run_id": run.id, **item["value"]} for item in projected)
            else:
                # Direct Agent admission has no UI binding until Attention opens
                # it. Once bound, only the product's actual projection is used.
                pending = self.app.state.harness.saved_pending_interrupts(run)
                pending_interrupts.extend({"run_id": run.id, **item.model_dump(mode="json")} for item in pending)
        helper_evidence = {"helper_runs": [run.model_dump(mode="json", include={"id", "parent_run_id", "agent_setup_id", "task", "status", "tool_invocations", "tool_outcomes", "pending_interrupt", "events"}) for run in helper_runs],
            "pending_interrupts": pending_interrupts,
            "helper_files": {item["file_path"]: (self.root / "project" / item["file_path"].lstrip("/")).read_text(encoding="utf-8") if (self.root / "project" / item["file_path"].lstrip("/")).exists() else None for item in self.seed_data.get("parallel_helpers", [])}}
        commands = []
        with self.app.state.managed_commands._lock:
            for command in self.app.state.managed_commands._commands.values():
                commands.append({"command_id": command.id, "run_id": command.run.id, "pid": command.process.pid, "alive": command.process.poll() is None, "state": command.state, "exit_code": command.exit_code})
        deployments = self.app.state.manager.list_deployments()
        effects = self.app.state.effects.list_effects()
        return {**helper_evidence, "compaction": self.compaction_evidence(tested_runs),
            "instruction_retention": self.compaction_evidence(tested_runs, key="instruction_retention"),
            "pid": os.getpid(), "data_root": str(self.root), "seed": self.seed_data, "scenario": self.scenario, "submissions": list(self.submissions), "failed_lookup_paths": list(self.failed_lookup_paths), "real_model_identity": self.real_identity, "model_factory_run_ids": list(self.model_run_ids), "model_processes": self.model_process_evidence(), "cleanup_errors": list(self.cleanup_errors), "run_ids": [run.id for run in tested_runs], "input_ids": [run.input_message_id for run in tested_runs], "run_count": len(tested_runs), "runs": [{"id": run.id, "status": run.status.value, "input_message_id": run.input_message_id, "tool_invocations": run.tool_invocations, "stop_reason": run.stop_reason} for run in tested_runs], "commands": commands, "effects": [effect.model_dump(mode="json") for effect in effects], "deployments": [{"id": deployment.id, "status": deployment.status.value, "pid": deployment.pid, "process_alive": bool(deployment.pid and psutil.pid_exists(deployment.pid)), "error": deployment.error} for deployment in deployments], "faults": dict(self.faults), "approved_file_exists": (self.root / "project" / "approved.txt").exists()}

    def model_process_evidence(self):
        from workbench_backend.inference.process import classify_identity

        with self.lock:
            identities = list(self.model_process_identities)
        evidence = []
        for identity in identities:
            verdict = "unproven" if identity.create_time <= 0 or not identity.executable else classify_identity(
                identity, inspector=self.model_supervisor.inspector)
            evidence.append({"pid": identity.pid, "create_time": identity.create_time,
                             "alive": None if verdict == "unproven" else verdict == "match",
                             "identity_verdict": verdict})
        return evidence

    def close(self):
        if self._closed:
            return
        self.release.set()
        self.load_release.set()
        self.submit_release.set()
        errors: list[Exception] = []

        def attempt(label, operation):
            try:
                return operation()
            except Exception as exc:
                problem = RuntimeError(f"{label}: {exc}")
                problem.__cause__ = exc
                errors.append(problem)
                return None

        attempt("Agent workers", self.app.state.harness.close)
        attempt("Owned commands", self.app.state.managed_commands.shutdown)
        if self.real_server is not None:
            attempt("Owned real local model", self.real_server.close)
        deployments = attempt("Model inventory", self.app.state.manager.list_deployments) or []
        for deployment in deployments:
            if deployment.scope.value == "managed" and deployment.pid:
                attempt(f"Owned model {deployment.id}",
                        lambda target=deployment: self.app.state.manager.stop_deployment(target.id))
        self.cleanup_errors = [str(error) for error in errors]
        if errors:
            raise ExceptionGroup("UI fixture cleanup attempted every owned phase", errors)
        self._closed = True
