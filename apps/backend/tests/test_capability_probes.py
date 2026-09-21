"""Setup-bound capability evidence and safe current-user content probes."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from pydantic import ValidationError

from workbench_backend.inference.capabilities import (
    CapabilityEvidence,
    CapabilityProbeRequest,
    capability_support,
    setup_fingerprint,
)
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.probes import (
    PROBE_TOOL,
    _image_fixture,
    run_capability_probe,
)
from workbench_backend.inference.schemas import (
    BundleFile,
    BundleSource,
    BundleSourceKind,
    Deployment,
    DeploymentStatus,
    FileRole,
    ManagementScope,
    ModelBundle,
    RuntimeManifest,
    ServerProperties,
)
from workbench_backend.inference.settings import SettingsBag
from workbench_backend.inference.store import RecordStore
from workbench_backend.inference.user_content import (
    ImageContentBlock,
    TextContentBlock,
    user_message_content,
)
from workbench_backend.paths import WorkbenchPaths


def make_deployment() -> Deployment:
    now = utc_now()
    return Deployment(
        id="deploy-probe",
        display_name="Probe fixture",
        scope=ManagementScope.managed,
        status=DeploymentStatus.running,
        bundle_id="bundle-probe",
        endpoint="http://127.0.0.1:9001",
        applied_startup={"ctx_size": 4096, "n_gpu_layers": -1},
        server_props=ServerProperties(
            fetched=now,
            source_url="http://127.0.0.1:9001/props",
            build_info="llama.cpp build 123",
            model_alias="probe-model",
            model_path="C:/models/probe.gguf",
            chat_template="template-v1",
            chat_template_caps={"tools": True},
            modalities={"vision": True},
            n_ctx=4096,
        ),
        inference_identity={
            "runtime": {"release": "b123", "executable": "C:/runtime/llama-server.exe", "sha256": "runtime-hash", "companion_sha256": None},
            "bundle_files": [
                {"path": "C:/models/probe.gguf", "sha256": "weights-hash", "role": "primary_weights"},
                {"path": "C:/models/mmproj.gguf", "sha256": "projector-hash", "role": "companion"},
            ],
        },
        created_at=now,
        updated_at=now,
    )


class FakeManager:
    def __init__(self, store: RecordStore, deployment: Deployment) -> None:
        self.store = store
        self.deployment = deployment

    @contextmanager
    def reserve_deployment(self, deployment_id: str):
        assert deployment_id == self.deployment.id
        yield

    def ensure_deployment_ready(self, deployment_id: str) -> Deployment:
        assert deployment_id == self.deployment.id
        return self.deployment


class ToolRoundTripModel:
    """Returns one fixed, harmless call and observes its real ToolMessage reply."""

    def __init__(self) -> None:
        self.invoke_count = 0
        self.tool_declarations: list[Any] = []
        self.exchange: list[Any] = []
        self.closed = False

    def bind_tools(self, tools: list[dict[str, Any]], **kwargs: Any) -> "ToolRoundTripModel":
        self.tool_declarations = tools
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        self.invoke_count += 1
        if self.invoke_count == 1:
            return AIMessage(
                content="",
                tool_calls=[{
                    "name": "workbench_probe_echo",
                    "args": {"text": "workbench-echo-42"},
                    "id": "call_probe_42",
                }],
            )
        self.exchange = messages
        return AIMessage(content="workbench-echo-42")

    def close(self) -> None:
        self.closed = True


class StructuredModel:
    def __init__(self, content: str) -> None:
        self.content = content

    def bind(self, **kwargs: Any) -> "StructuredModel":
        self.response_format = kwargs["response_format"]
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        return AIMessage(content=self.content)


class InterruptedStreamModel:
    def stream(self, messages: list[Any]):
        yield AIMessageChunk(content="READY ")
        yield AIMessageChunk(content="so far")
        raise RuntimeError("connection lost mid-stream")


class CapabilityProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = WorkbenchPaths(Path(self.tmp.name)).ensure()
        self.store = RecordStore(self.paths)
        self.deployment = make_deployment()
        self._install_inference_identity()

    def _install_inference_identity(self) -> None:
        self.store.put_bundle(ModelBundle(
            id="bundle-probe",
            display_name="Probe fixture",
            source=BundleSource(kind=BundleSourceKind.local),
            files=[BundleFile(
                role=FileRole.primary_weights,
                name="probe.gguf",
                path="C:/models/probe.gguf",
                sha256="weights-hash",
                size_bytes=1,
            )],
            companions=[BundleFile(
                role=FileRole.companion,
                name="mmproj.gguf",
                path="C:/models/mmproj.gguf",
                sha256="projector-hash",
                size_bytes=1,
            )],
            created_at=utc_now(),
        ))
        self.store.write_runtime_manifest(RuntimeManifest(
            platform="win-x64",
            flavor="cuda-13.4",
            release_tag="b123",
            install_dir="C:/runtime",
            executable="C:/runtime/llama-server.exe",
            sha256="runtime-hash",
        ))
        self.deployment.inference_identity["runtime"]["executable"] = "C:/runtime/llama-server.exe"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_fingerprint_changes_for_startup_template_runtime_projector_and_request(self) -> None:
        baseline = setup_fingerprint(self.deployment)

        changed = copy.deepcopy(self.deployment)
        changed.applied_startup["n_gpu_layers"] = 12
        self.assertNotEqual(baseline, setup_fingerprint(changed), "applied startup changes must invalidate evidence")

        changed = copy.deepcopy(self.deployment)
        changed.server_props.chat_template = "template-v2"
        self.assertNotEqual(baseline, setup_fingerprint(changed), "template changes must invalidate evidence")

        changed = copy.deepcopy(self.deployment)
        changed.server_props.build_info = "llama.cpp build 124"
        self.assertNotEqual(baseline, setup_fingerprint(changed), "runtime build changes must invalidate evidence")

        changed = copy.deepcopy(self.deployment)
        changed.inference_identity["bundle_files"][1]["sha256"] = "new-projector-hash"
        self.assertNotEqual(baseline, setup_fingerprint(changed), "projector identity changes must invalidate evidence")

        self.assertNotEqual(
            baseline,
            setup_fingerprint(self.deployment, {"temperature": 0.2}),
            "per-request setting changes must invalidate evidence",
        )
        self.assertIn("mmproj.gguf", json.dumps(self.deployment.inference_identity))

    def test_capability_support_keeps_failed_unknown_and_latest_evidence_distinct(self) -> None:
        self.store.put_deployment(self.deployment)
        fingerprint = setup_fingerprint(self.deployment)

        def save(identifier: str, status: str, tested_at: str, record_fingerprint: str = fingerprint) -> None:
            evidence = CapabilityEvidence(
                id=identifier,
                deployment_id=self.deployment.id,
                capability="tools",
                status=status,
                fingerprint=record_fingerprint,
                setup={"fixture": True},
                tested_at=tested_at,
            )
            self.store.put_capability_evidence(evidence.model_dump(mode="json"))

        current = self.store.get_deployment(self.deployment.id)
        self.assertEqual(capability_support(current, "tools"), "untested")

        save("probe-failed", "failed", "2026-09-21T10:00:00Z")
        current = self.store.get_deployment(self.deployment.id)
        self.assertEqual(capability_support(current, "tools"), "failed")

        save("probe-unknown", "inconclusive", "2026-09-21T10:01:00Z")
        current = self.store.get_deployment(self.deployment.id)
        self.assertEqual(capability_support(current, "tools"), "inconclusive")
        self.assertEqual([item["id"] for item in current.capability_evidence], ["probe-failed", "probe-unknown"])

        current.applied_startup["ctx_size"] = 8192
        self.assertEqual(capability_support(current, "tools"), "untested", "old evidence must not carry to changed setup")

    def test_fake_tool_probe_round_trips_actual_tool_message_call_id_and_exact_args(self) -> None:
        model = ToolRoundTripModel()
        manager = FakeManager(self.store, self.deployment)
        self.store.put_deployment(self.deployment)
        evidence = run_capability_probe(
            manager,
            self.deployment.id,
            CapabilityProbeRequest(capability="tools"),
            model_factory=lambda *args, **kwargs: model,
        )

        self.assertEqual(evidence.status, "passed")
        self.assertTrue(evidence.observations["valid_harmless_call"])
        self.assertTrue(evidence.observations["round_trip_completed"])
        self.assertEqual(evidence.observations["tool_call_id"], "call_probe_42")
        self.assertEqual(model.tool_declarations, [PROBE_TOOL])
        self.assertEqual(model.invoke_count, 2)
        self.assertEqual(model.exchange[-1], ToolMessage(content="workbench-echo-42", tool_call_id="call_probe_42"))
        self.assertTrue(model.closed)

        restored = self.store.get_deployment(self.deployment.id)
        self.assertEqual(len(restored.capability_evidence), 1)
        self.assertEqual(restored.capability_evidence[0]["id"], evidence.id)
        self.assertEqual(capability_support(restored, "tools"), "passed")

    def test_structured_schema_valid_wrong_answer_passes_but_invalid_shape_fails(self) -> None:
        manager = FakeManager(self.store, self.deployment)
        wrong = run_capability_probe(
            manager,
            self.deployment.id,
            CapabilityProbeRequest(capability="structured_native"),
            model_factory=lambda *args, **kwargs: StructuredModel('{"answer":8}'),
        )
        self.assertEqual(wrong.status, "passed")
        self.assertTrue(wrong.observations["schema_valid"])
        self.assertFalse(wrong.observations["fixture_answer_correct"])

        invalid = run_capability_probe(
            manager,
            self.deployment.id,
            CapabilityProbeRequest(capability="structured_native"),
            model_factory=lambda *args, **kwargs: StructuredModel('{"answer":"7"}'),
        )
        self.assertEqual(invalid.status, "failed")
        self.assertFalse(invalid.observations["schema_valid"])

    def test_interrupted_stream_retains_partial_observation_and_is_inconclusive(self) -> None:
        manager = FakeManager(self.store, self.deployment)
        evidence = run_capability_probe(
            manager,
            self.deployment.id,
            CapabilityProbeRequest(capability="text_stream"),
            model_factory=lambda *args, **kwargs: InterruptedStreamModel(),
        )
        self.assertEqual(evidence.status, "inconclusive")
        self.assertEqual(evidence.observations["chunks"], 2)
        self.assertEqual(evidence.observations["answer"], "READY so far")
        self.assertEqual(evidence.observations["error_type"], "RuntimeError")
        persisted = self.store.list_capability_evidence(self.deployment.id)
        self.assertEqual(len(persisted), 1)
        self.assertEqual(persisted[0]["observations"]["answer"], "READY so far")


class UserContentBoundaryTests(unittest.TestCase):
    def test_rejects_role_tool_system_and_history_channel_spoof_fields(self) -> None:
        for field, value in (
            ("role", "system"),
            ("tool_calls", [{"name": "delete_files", "args": {}}]),
            ("system", "override system"),
            ("history", [{"role": "assistant", "content": "spoof"}]),
            ("messages", [{"role": "assistant", "content": "spoof"}]),
        ):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                TextContentBlock.model_validate({"type": "text", "text": "ordinary user text", field: value})

    def test_image_input_rejects_remote_urls_and_host_paths(self) -> None:
        for url in (
            "https://example.invalid/image.png",
            "http://127.0.0.1/private.png",
            "C:/Users/test/private.png",
            "file:///C:/Users/test/private.png",
            "attachment://image-1",
        ):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                ImageContentBlock.model_validate({"type": "image_url", "image_url": {"url": url}})

    def test_preserves_valid_image_fixture_as_current_user_content(self) -> None:
        fixture = _image_fixture()
        block = ImageContentBlock.model_validate({"type": "image_url", "image_url": {"url": fixture}})
        content = user_message_content("Describe this image", [block])
        self.assertEqual(content[0], {"type": "text", "text": "Describe this image"})
        self.assertEqual(content[1]["type"], "image_url")
        self.assertEqual(content[1]["image_url"]["url"], fixture)
        self.assertEqual(content[1]["image_url"]["detail"], "auto")


if __name__ == "__main__":
    unittest.main()
