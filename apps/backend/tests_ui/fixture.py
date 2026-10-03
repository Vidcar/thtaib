"""Real Workbench composition with deterministic inference and transport faults."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
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


class FixtureModel(BaseChatModel):
    """Replace only model inference; native graph/tools/interrupts execute normally."""

    _fixture: Any = PrivateAttr()
    _run: Any = PrivateAttr()
    _script: list[AIMessage] = PrivateAttr()
    _index: int = PrivateAttr(default=0)

    def __init__(self, fixture, run, script):
        super().__init__()
        self._fixture, self._run, self._script = fixture, run, script

    @property
    def _llm_type(self):
        return "deterministic-ui-fixture"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
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
    def __init__(self, data_root: Path):
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
        self.negative_control = None
        self.faults = {"lost_acknowledgements": 0, "stream_disconnects": 0, "draft_losses": 0}
        self.model_run_ids: list[str] = []
        self.model_process_identities: list[Any] = []
        self.lock = threading.RLock()
        self.seed_path = self.root / "ui-seed.json"
        self.seed_data = json.loads(self.seed_path.read_text(encoding="utf-8")) if self.seed_path.exists() else {}
        self._closed = False
        self.cleanup_errors: list[str] = []
        self.app.state.harness._model_factory = self.model_factory
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
        else:
            script = [AIMessage(content="Baseline response completed")]
        return FixtureModel(self, run, script)

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
            self.faults = {"lost_acknowledgements": 0, "stream_disconnects": 0, "draft_losses": 0}
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
            if self.negative_control == "lose_draft" and request.method == "GET" and self.seed_data and request.url.path == f"/v1/chat/conversations/{self.seed_data['conversation_id']}" and tokens_match(request.headers.get("X-Workbench-Local-Token", ""), self.app.state.local_trust_token):
                saved = self.app.state.chat.store.get(self.seed_data["conversation_id"])
                if saved and saved.draft and saved.draft.content:
                    from workbench_backend.chat.schemas import ChatDraftUpdateRequest
                    self.app.state.chat.update_draft(saved.id, ChatDraftUpdateRequest(content=""))
                    self.negative_control = None
                    self.faults["draft_losses"] += 1
            response = await call_next(request)
            path = request.url.path
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
        if scenario not in {"baseline", "lost_ack", "approval", "command", "retained", "model"}:
            raise HTTPException(400, "Unknown UI fixture scenario")
        self.scenario = scenario
        if "hold_model" in body:
            self.hold_model = bool(body["hold_model"])
            self.release.clear() if self.hold_model else self.release.set()
        if body.get("release_model"):
            self.hold_model = False
            self.release.set()
        if "hold_model_load" in body:
            self.load_release.clear() if body["hold_model_load"] else self.load_release.set()
        if body.get("release_model_load"):
            self.load_release.set()
        for field in ("lose_next_ack", "disconnect_next_stream", "fail_model_start", "fail_shutdown"):
            if field in body:
                setattr(self, field, bool(body[field]))
        if "negative_control" in body:
            value = body["negative_control"]
            if value not in {None, "lose_draft"}:
                raise HTTPException(400, "Unknown negative control")
            self.negative_control = value
        if body.get("change_source"):
            (self.root / "project" / "baseline-output.txt").write_text("Changed source after retention", encoding="utf-8")
        return self.state()

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
        project = self.app.state.setups.create_project(ProjectCreateRequest(name="Baseline project", path=str(project_path)))
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
        conversation = self.app.state.chat.create(ChatConversationCreateRequest(title="Baseline conversation", project_id=project.id, deployment_id=deployment.id, profile_id=profile.id, approval_mode="ask", presented_tools=["write_file", "start_command", "command_status", "stop_command"], input_policy={"tool_loading": "always"}))
        self.app.state.chat.start(conversation.id, ChatStartRequest(task="Saved baseline question"))
        self.wait_terminal(conversation.id)
        self.seed_data = {"project_id": project.id, "conversation_id": conversation.id, "deployment_id": deployment.id, "profile_id": profile.id, "bundle_id": bundle.id, "fixture_root": str(self.root), "project_path": str(project_path), "owned_effect_path": str(project_path / "approved.txt"), "retained_asset_ids": [], "seed_run_ids": [run.id for run in self.app.state.app_store.list_runs()]}
        if scenario == "retained":
            self._retain_seed_output()
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

    def state(self):
        runs = self.app.state.app_store.list_runs()
        seed_ids = set(self.seed_data.get("seed_run_ids", []))
        tested_runs = [run for run in runs if run.id not in seed_ids]
        commands = []
        with self.app.state.managed_commands._lock:
            for command in self.app.state.managed_commands._commands.values():
                commands.append({"command_id": command.id, "run_id": command.run.id, "pid": command.process.pid, "alive": command.process.poll() is None, "state": command.state, "exit_code": command.exit_code})
        deployments = self.app.state.manager.list_deployments()
        effects = self.app.state.effects.list_effects()
        return {"pid": os.getpid(), "data_root": str(self.root), "seed": self.seed_data, "scenario": self.scenario, "model_factory_run_ids": list(self.model_run_ids), "model_processes": self.model_process_evidence(), "cleanup_errors": list(self.cleanup_errors), "run_ids": [run.id for run in tested_runs], "input_ids": [run.input_message_id for run in tested_runs], "run_count": len(tested_runs), "runs": [{"id": run.id, "status": run.status.value, "input_message_id": run.input_message_id, "tool_invocations": run.tool_invocations, "stop_reason": run.stop_reason} for run in tested_runs], "commands": commands, "effects": [effect.model_dump(mode="json") for effect in effects], "deployments": [{"id": deployment.id, "status": deployment.status.value, "pid": deployment.pid, "process_alive": bool(deployment.pid and psutil.pid_exists(deployment.pid)), "error": deployment.error} for deployment in deployments], "faults": dict(self.faults), "approved_file_exists": (self.root / "project" / "approved.txt").exists()}

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
        deployments = attempt("Model inventory", self.app.state.manager.list_deployments) or []
        for deployment in deployments:
            if deployment.scope.value == "managed" and deployment.pid:
                attempt(f"Owned model {deployment.id}",
                        lambda target=deployment: self.app.state.manager.stop_deployment(target.id))
        self.cleanup_errors = [str(error) for error in errors]
        if errors:
            raise ExceptionGroup("UI fixture cleanup attempted every owned phase", errors)
        self._closed = True
