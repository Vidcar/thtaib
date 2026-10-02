"""Persisted setup proof and the backend's independent automatic check owner."""

from __future__ import annotations

import copy
import tempfile
import threading
import time
import unittest
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage, AIMessageChunk

from tests.test_capability_probes import make_deployment
from workbench_backend.errors import ManagerError
from workbench_backend.inference.capabilities import (
    CapabilityEvidence, CapabilityProbeRequest, applicable_capabilities, capability_support,
    proof_fingerprint, setup_fingerprint, setup_identity,
)
from workbench_backend.inference.capability_checks import CapabilityCheckCoordinator
from workbench_backend.inference.capability_context import configuration_probe_context
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.inference.probes import run_capability_probe
from workbench_backend.inference.schemas import BundleFile, BundleSource, BundleSourceKind, FileRole, HealthReport, ModelBundle, RunProfile, RuntimeManifest
from workbench_backend.inference.settings import resolve_bags
from workbench_backend.inference.store import RecordStore
from workbench_backend.inference import hashes
from workbench_backend.paths import WorkbenchPaths


class CheckManager:
    def __init__(self, store):
        self.store = store
        self.reservations = []

    def get_deployment(self, identifier):
        return self.store.get_deployment(identifier)

    def get_profile(self, identifier):
        profile = self.store.get_profile(identifier)
        if profile is None:
            raise ManagerError("Unknown setup", code="profile_missing", status_code=404)
        return profile

    def get_bundle(self, identifier):
        return self.store.get_bundle(identifier)

    def ensure_deployment_ready(self, identifier):
        return self.get_deployment(identifier)

    @contextmanager
    def reserve_deployment(self, identifier, *, profile_id=None):
        self.reservations.append((identifier, profile_id))
        yield


class ReadyStream:
    def stream(self, messages):
        yield AIMessageChunk(content="READY")


class CapabilityCheckTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = RecordStore(WorkbenchPaths(Path(self.temporary.name)).ensure())
        self.manager = CheckManager(self.store)
        self.deployment = make_deployment()
        self.deployment.health = HealthReport(healthy=True, endpoint=self.deployment.endpoint, checked=utc_now())
        self.deployment.settings = resolve_bags(startup=self.deployment.applied_startup,
                                               per_request={"temperature": 0.2, "reasoning_preserve": True})
        self.deployment.server_props.chat_template_caps["supports_preserve_reasoning"] = True
        self.deployment.profile_id = "configuration-one"
        now = utc_now()
        self.store.put_bundle(ModelBundle(id=self.deployment.bundle_id, display_name="Original model",
            source=BundleSource(kind=BundleSourceKind.local), created_at=now,
            files=[BundleFile(role=FileRole.primary_weights, name="weights.gguf", path="C:/models/weights.gguf",
                              sha256="weights-hash", size_bytes=1)],
            companions=[BundleFile(role=FileRole.companion, name="mmproj.gguf", path="C:/models/mmproj.gguf",
                                   sha256="projector-hash", size_bytes=1)]))
        self.store.write_runtime_manifest(RuntimeManifest(platform="win-x64", flavor="cuda-13.4",
            release_tag="b123", install_dir="C:/runtime", executable="C:/runtime/llama-server.exe", sha256="runtime-hash"))
        self.store.put_profile(RunProfile(id="configuration-one", display_name="One", bundle_id=self.deployment.bundle_id,
            bags=self.deployment.settings, revision=1, created_at=now, updated_at=now))
        self.store.put_deployment(self.deployment)
        self.coordinator = CapabilityCheckCoordinator(self.manager)

    def tearDown(self):
        self.coordinator.close()
        self.temporary.cleanup()

    def record(self, deployment, capability="text_stream", *, per_request=None, status="passed"):
        evidence = CapabilityEvidence(id=new_id("probe"), deployment_id=deployment.id, capability=capability,
            status=status, fingerprint=setup_fingerprint(deployment, per_request),
            setup=setup_identity(deployment, per_request), tested_at=utc_now())
        self.store.put_capability_evidence(evidence.model_dump(mode="json"))
        return evidence

    def wait_for(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate():
            if time.monotonic() > deadline:
                self.fail("Capability worker did not reach its bounded condition")
            time.sleep(0.005)

    def test_replacement_and_unloaded_setup_keep_proof_after_original_record_deleted(self):
        original = self.manager.get_deployment(self.deployment.id)
        self.record(original)
        self.store.delete_deployment(original.id)
        # Reading the saved setup can reconstruct the observed native scope
        # from proof, even when the original deployment record was cleared.
        unloaded = configuration_probe_context(self.manager, "configuration-one", 1)
        self.assertEqual(capability_support(unloaded, "text_stream"), "passed")
        replacement = copy.deepcopy(self.deployment)
        replacement.id = "replacement"
        replacement.display_name = "Renamed setup"
        replacement.endpoint = "http://127.0.0.1:9999"
        replacement.server_props.model_alias = "new-router-alias"
        replacement.server_props.model_path = "D:/different/location.gguf"
        replacement.applied_startup.update(ctx_size=8192, n_gpu_layers=6, threads=3, load_mode="mmap")
        replacement.server_props.n_ctx = 8192
        self.store.put_deployment(replacement)
        restored = RecordStore(self.store.paths).get_deployment(replacement.id)
        self.assertEqual(capability_support(restored, "text_stream"), "passed")
        self.assertEqual(len(self.store.list_capability_evidence()), 1)

    def test_latest_scope_retest_replaces_older_exact_deployment_proof(self):
        original = self.manager.get_deployment(self.deployment.id)
        self.record(original, status="failed")
        replacement = original.model_copy(update={"id": "replacement", "endpoint": "http://127.0.0.1:9999"}, deep=True)
        self.store.put_deployment(replacement)
        self.record(self.manager.get_deployment(replacement.id), status="passed")
        self.assertEqual(capability_support(self.manager.get_deployment(original.id), "text_stream"), "passed")
        self.assertEqual(capability_support(self.manager.get_deployment(replacement.id), "text_stream"), "passed")
        self.record(self.manager.get_deployment(original.id), status="failed")
        self.assertEqual(capability_support(self.manager.get_deployment(replacement.id), "text_stream"), "failed")

    def test_behavior_runtime_weights_projector_and_template_changes_invalidate(self):
        original = self.manager.get_deployment(self.deployment.id)
        self.record(original)
        for mutation in (
            lambda d: d.inference_identity["runtime"].update(sha256="new-runtime"),
            lambda d: d.inference_identity["bundle_files"][0].update(sha256="new-weights"),
            lambda d: d.inference_identity["bundle_files"][1].update(sha256="new-projector"),
            lambda d: setattr(d.server_props, "chat_template", "different-template"),
        ):
            changed = copy.deepcopy(self.manager.get_deployment(original.id))
            mutation(changed)
            self.assertEqual(capability_support(changed, "text_stream"), "untested")

    def test_sampling_keeps_every_check_and_saved_thinking_drops_only_thinking(self):
        original = self.manager.get_deployment(self.deployment.id)
        names = (
            "text_stream", "tools", "structured_native", "structured_tools",
            "structured_with_tools", "structured_tools_with_tools", "reasoning",
            "reasoning_replay", "image", "tool_image",
        )
        for name in names:
            self.record(original, name)
        current = self.manager.get_deployment(original.id)
        sampling = copy.deepcopy(current)
        sampling.settings.per_request.applied.update(
            temperature=0.8, top_k=10, top_p=0.9, min_p=0.05, repeat_penalty=1.1,
            presence_penalty=0.1, frequency_penalty=0.1, max_tokens=256,
        )
        for name in names:
            self.assertEqual(capability_support(sampling, name), "passed", name)
        thinking = copy.deepcopy(current)
        thinking.settings.per_request.applied.update(reasoning="on", reasoning_effort="low")
        for name in names:
            expected = "untested" if name in {"reasoning", "reasoning_replay"} else "passed"
            self.assertEqual(capability_support(thinking, name), expected, name)
        history = copy.deepcopy(current)
        history.settings.per_request.applied.update(reasoning_preserve=False)
        for name in names:
            self.assertEqual(capability_support(history, name), "passed", name)

    def test_only_missing_reruns_thinking_after_a_saved_thinking_change(self):
        original = self.manager.get_deployment(self.deployment.id)
        reasoning = self.record(original, "reasoning")
        replay = self.record(original, "reasoning_replay")
        stream = self.record(original, "text_stream")
        current = self.manager.get_deployment(original.id)
        current.settings.per_request.applied.update(reasoning="on", reasoning_effort="low")
        self.store.put_deployment(current)
        calls = []

        class Answer:
            def invoke(self, _messages):
                calls.append("invoke")
                return AIMessage(content="391", additional_kwargs={"reasoning_content": "worked"})

            def stream(self, _messages):
                calls.append("stream")
                yield AIMessageChunk(content="READY")

        kept = run_capability_probe(self.manager, current.id, CapabilityProbeRequest(capability="text_stream"),
            model_factory=lambda *_args, **_kwargs: Answer(), only_missing=True)
        self.assertEqual(kept.id, stream.id)
        self.assertEqual(calls, [])
        rerun = run_capability_probe(self.manager, current.id, CapabilityProbeRequest(capability="reasoning"),
            model_factory=lambda *_args, **_kwargs: Answer(), only_missing=True)
        self.assertNotEqual(rerun.id, reasoning.id)
        self.assertEqual(calls, ["invoke"])
        replayed = run_capability_probe(self.manager, current.id, CapabilityProbeRequest(capability="reasoning_replay"),
            model_factory=lambda *_args, **_kwargs: Answer(), only_missing=True)
        self.assertNotEqual(replayed.id, replay.id)
        self.assertGreater(len(calls), 1)

    def test_external_template_bytes_invalidate_without_rehashing_weights(self):
        template = Path(self.temporary.name) / "template.jinja"
        template.write_text("template-one", encoding="utf-8")
        deployment = self.manager.get_deployment(self.deployment.id)
        deployment.applied_startup["chat_template_file"] = str(template)
        self.record(deployment)
        deployment.capability_evidence = self.store.list_capability_evidence()
        self.assertEqual(capability_support(deployment, "text_stream"), "passed")
        template.write_text("template-two", encoding="utf-8")
        self.assertEqual(capability_support(deployment, "text_stream"), "untested")

    def test_probe_does_not_label_new_disk_template_as_a_check_of_old_running_process(self):
        template = Path(self.temporary.name) / "template.jinja"
        template.write_text("new-disk-template", encoding="utf-8")
        deployment = self.manager.get_deployment(self.deployment.id)
        deployment.applied_startup["chat_template_file"] = str(template)
        self.store.put_deployment(deployment)
        with self.assertRaises(ManagerError) as failure:
            run_capability_probe(self.manager, deployment.id, CapabilityProbeRequest(capability="text_stream"),
                model_factory=lambda *_a, **_k: self.fail("changed template reached inference"))
        self.assertEqual(failure.exception.code, "probe_template_changed")
        self.assertEqual(self.store.list_capability_evidence(), [])

    def test_draft_model_verified_hash_survives_restart_but_changed_bytes_invalidate_without_full_read(self):
        draft = Path(self.temporary.name) / "draft.gguf"
        draft.write_bytes(b"old-draft" * 32000)
        hashes.cached_sha256_file(draft)  # the native load's existing verification
        deployment = self.manager.get_deployment(self.deployment.id)
        deployment.applied_startup["spec_draft_model"] = str(draft)
        deployment.settings = resolve_bags(startup=deployment.applied_startup,
                                         per_request=deployment.settings.per_request.requested)
        self.store.put_deployment(deployment)
        profile = self.manager.get_profile("configuration-one")
        self.store.put_profile(profile.model_copy(update={"bags": deployment.settings}))
        recorded = self.record(self.manager.get_deployment(deployment.id))
        self.assertTrue(recorded.setup["external_draft_model"]["sha256"])
        with patch.object(hashes, "_HASH_CACHE", OrderedDict()), patch.object(hashes, "sha256_file", side_effect=AssertionError("ordinary read hashed weights")):
            restored = self.manager.get_deployment(deployment.id)
            self.assertEqual(capability_support(restored, "text_stream"), "passed")
            unloaded = configuration_probe_context(self.manager, "configuration-one", 1)
            self.assertEqual(capability_support(unloaded, "text_stream"), "passed")
            draft.write_bytes(b"new-draft" * 32000)
            changed = self.manager.get_deployment(deployment.id)
            self.assertEqual(capability_support(changed, "text_stream"), "untested")

    def test_legacy_evidence_is_not_promoted_to_cross_deployment_proof(self):
        deployment = self.manager.get_deployment(self.deployment.id)
        legacy = self.record(deployment)
        legacy.setup["probe_version"] = 2
        legacy.id = "legacy-probe"
        self.store.put_capability_evidence(legacy.model_dump(mode="json"))
        self.store.delete_deployment(deployment.id)
        replacement = deployment.model_copy(update={"id": "replacement"})
        self.store.put_deployment(replacement)
        evidence = self.manager.get_deployment(replacement.id).capability_evidence
        self.assertEqual([item["id"] for item in evidence], [item["id"] for item in evidence if item["id"] != legacy.id])

    def test_selected_saved_response_and_revision_are_resolved_on_backend(self):
        profile = self.manager.get_profile("configuration-one").model_copy(deep=True)
        profile.id = "configuration-two"
        profile.bags = resolve_bags(startup=self.deployment.applied_startup,
                                  per_request={"temperature": 0.8, "reasoning_preserve": False})
        self.store.put_profile(profile)
        seen = []
        record = run_capability_probe(self.manager, self.deployment.id,
            CapabilityProbeRequest(capability="text_stream", configuration_id=profile.id, expected_configuration_revision=1),
            model_factory=lambda deployment, **kwargs: (seen.append(kwargs["per_request"].applied.copy()) or ReadyStream()))
        self.assertEqual(record.status, "passed")
        self.assertEqual(seen[0]["temperature"], 0.8)
        self.assertFalse(record.setup["request"]["reasoning_preserve"])
        self.assertIn((self.deployment.id, profile.id), self.manager.reservations)
        with self.assertRaises(ManagerError) as failure:
            run_capability_probe(self.manager, self.deployment.id,
                CapabilityProbeRequest(capability="text_stream", configuration_id=profile.id, expected_configuration_revision=2),
                model_factory=lambda *_a, **_k: self.fail("stale setup reached inference"))
        self.assertEqual(failure.exception.code, "configuration_revision_conflict")

    def test_manual_retest_runs_again_but_only_missing_keeps_failed_and_inconclusive_results(self):
        deployment = self.manager.get_deployment(self.deployment.id)
        previous = self.record(deployment, status="failed")
        skipped = run_capability_probe(self.manager, deployment.id, CapabilityProbeRequest(capability="text_stream"),
            only_missing=True, model_factory=lambda *_a, **_k: self.fail("automatic check repeated a recorded failure"))
        self.assertEqual(skipped.id, previous.id)
        rerun = run_capability_probe(self.manager, deployment.id, CapabilityProbeRequest(capability="text_stream"),
            model_factory=lambda *_a, **_k: ReadyStream())
        self.assertEqual(rerun.status, "passed")
        self.assertNotEqual(rerun.id, previous.id)
        self.assertEqual(len(self.store.list_capability_evidence()), 2)

    def test_concurrent_lazy_and_automatic_checks_share_one_request(self):
        entered, release = threading.Event(), threading.Event()
        calls, records, errors = [], [], []
        class Blocking(ReadyStream):
            def stream(inner, messages):
                calls.append("stream")
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("fixture timed out")
                yield from super().stream(messages)
        def run():
            try:
                records.append(run_capability_probe(self.manager, self.deployment.id,
                    CapabilityProbeRequest(capability="text_stream"), only_missing=True,
                    model_factory=lambda *_a, **_k: Blocking()))
            except Exception as exc:
                errors.append(exc)
        threads = [threading.Thread(target=run), threading.Thread(target=run)]
        try:
            threads[0].start()
            self.assertTrue(entered.wait(5))
            threads[1].start()
            release.set()
        finally:
            release.set()
            for thread in threads:
                if thread.ident:
                    thread.join(5)
        self.assertFalse(errors)
        self.assertEqual(calls, ["stream"])
        self.assertEqual([record.id for record in records], [records[0].id, records[0].id])

    def test_auto_checks_all_applicable_missing_kinds_once_and_cancel_leaves_rest_retryable(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        def probe(manager, identifier, request, **kwargs):
            calls.append(request.capability)
            if len(calls) == 1:
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("fixture timed out")
            deployment = manager.get_deployment(identifier)
            bag = manager.get_profile(request.configuration_id).bags.per_request
            if capability_support(deployment, request.capability, bag) == "untested":
                return self.record(deployment, request.capability, per_request=bag)
        with patch("workbench_backend.inference.probes.run_capability_probe", probe):
            self.coordinator.start(self.deployment.id, "configuration-one")
            self.assertTrue(entered.wait(5))
            scope = proof_fingerprint(self.manager.get_deployment(self.deployment.id))
            self.assertTrue(self.coordinator.state(scope)[0])
            self.coordinator.start(self.deployment.id, "configuration-one")
            self.coordinator.cancel(self.deployment.id)
            release.set()
            self.wait_for(lambda: not self.coordinator.state(scope)[0])
            self.assertEqual(calls, ["text_stream"])
            calls.clear()
            self.coordinator.start(self.deployment.id, "configuration-one")
            self.wait_for(lambda: not self.coordinator.state(scope)[0])
            # The coordinator delegates every applicable kind to the shared
            # only-missing gate, rather than duplicating its persistence rules.
            expected = applicable_capabilities(self.manager.get_deployment(self.deployment.id))
            self.assertEqual(calls, expected)
            calls.clear()
            self.coordinator.start(self.deployment.id, "configuration-one")
            self.assertEqual(calls, [])

    def test_auto_checks_wait_for_positive_health_and_stop_all_is_reusable(self):
        deployment = self.manager.get_deployment(self.deployment.id)
        self.store.put_deployment(deployment.model_copy(update={"health": None}))
        self.coordinator.start(deployment.id, "configuration-one")
        self.assertEqual(self.coordinator._workers, {})
        self.store.put_deployment(deployment)
        entered, release = threading.Event(), threading.Event()
        closed = []
        class Blocking(ReadyStream):
            def stream(inner, messages):
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("fixture timed out")
                yield from super().stream(messages)
            def close(inner):
                closed.append(True)
        original_probe = run_capability_probe
        def probe(manager, identifier, request, **kwargs):
            return original_probe(manager, identifier, request, model_factory=lambda *_a, **_k: Blocking(), **kwargs)
        with patch("workbench_backend.inference.capability_checks.applicable_capabilities", return_value=["text_stream"]), patch("workbench_backend.inference.probes.run_capability_probe", probe):
            self.coordinator.start(deployment.id, "configuration-one")
            self.assertTrue(entered.wait(5))
            errors = []
            def stop():
                try:
                    self.coordinator.stop_all()
                except Exception as exc:
                    errors.append(exc)
            stopper = threading.Thread(target=stop)
            stopper.start()
            self.wait_for(lambda: all(work.stop.is_set() for work in self.coordinator._workers.values()))
            release.set()
            stopper.join(5)
            self.assertFalse(stopper.is_alive())
            self.assertFalse(errors)
            self.assertEqual(closed, [True])
            self.assertEqual(self.store.list_capability_evidence(), [], "cancellation is not a capability failure")
            self.coordinator.start(deployment.id, "configuration-one")
            scope = proof_fingerprint(self.manager.get_deployment(deployment.id))
            self.wait_for(lambda: not self.coordinator.state(scope)[0])
            self.assertEqual(len(self.store.list_capability_evidence()), 1)

    def test_effort_none_excludes_both_thinking_checks(self):
        selected = {"reasoning": "on", "reasoning_effort": "none", "reasoning_preserve": True}
        names = applicable_capabilities(self.manager.get_deployment(self.deployment.id), selected)
        self.assertNotIn("reasoning", names)
        self.assertNotIn("reasoning_replay", names)

    def test_cancelled_transport_failure_remains_missing_and_can_retry(self):
        stopped = threading.Event()
        class Interrupted:
            def stream(inner, messages):
                stopped.set()
                raise OSError("native request interrupted")
        with self.assertRaises(ManagerError) as failure:
            run_capability_probe(self.manager, self.deployment.id, CapabilityProbeRequest(capability="text_stream"),
                model_factory=lambda *_a, **_k: Interrupted(), cancelled=stopped.is_set)
        self.assertEqual(failure.exception.code, "capability_checks_cancelled")
        self.assertEqual(self.store.list_capability_evidence(), [])
        stopped.clear()
        result = run_capability_probe(self.manager, self.deployment.id, CapabilityProbeRequest(capability="text_stream"),
            model_factory=lambda *_a, **_k: ReadyStream(), only_missing=True, cancelled=stopped.is_set)
        self.assertEqual(result.status, "passed")


if __name__ == "__main__":
    unittest.main()
