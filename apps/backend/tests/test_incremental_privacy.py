"""Capture fingerprints skip old scans without trusting mutable content."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
import unittest
from unittest.mock import patch

from workbench_backend.agents.schemas import AgentEvent, AgentRun, ModelRequestCapture
from workbench_backend.knowledge import diagnostics, redaction
from workbench_backend.knowledge.schemas import ContextCaptureSettings


NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
SECRET = "wb_synthetic_private_1234"
ASSIGNMENT = f"API_KEY={SECRET}"


def capture(**values) -> ModelRequestCapture:
    return ModelRequestCapture(at=NOW.isoformat(), messages=[{"content": ASSIGNMENT}], **values)


class IncrementalCapturePrivacyTests(unittest.TestCase):
    def setUp(self):
        self.settings = ContextCaptureSettings()

    def normalized(self, value=None, settings=None, now=NOW):
        return diagnostics.apply_capture_policy(value or capture(), settings or self.settings, now=now)

    def test_initial_scan_and_saved_fingerprint_reuse_preserve_redaction_provenance(self):
        original = capture(http_payload={"body": ASSIGNMENT})
        applied = self.normalized(original)
        self.assertIsNot(applied, original)
        self.assertIn(SECRET, original.messages[0]["content"])
        self.assertNotIn(SECRET, applied.model_dump_json())
        self.assertEqual(len(applied.privacy_fingerprint), 64)
        loaded = ModelRequestCapture.model_validate_json(applied.model_dump_json())
        with patch.object(diagnostics, "redact_structured", wraps=diagnostics.redact_structured) as scan:
            reused = self.normalized(loaded)
        scan.assert_not_called()
        self.assertIs(reused, loaded)
        self.assertTrue(reused.redacted)
        self.assertIn("api_key", reused.redacted_fields)

    def test_nested_body_edits_invalidate_every_sensitive_capture_field(self):
        for name, value in {
            "instructions": ASSIGNMENT,
            "messages": [{"content": {"nested": [ASSIGNMENT]}}],
            "generation_settings": {"nested": [ASSIGNMENT]},
            "retrieved_material": [ASSIGNMENT],
            "http_payload": {"nested": [ASSIGNMENT]},
            "http_payloads": [{"nested": [ASSIGNMENT]}],
            "failure": {"nested": [ASSIGNMENT]},
        }.items():
            with self.subTest(field=name):
                previous = self.normalized()
                setattr(previous, name, value)
                # The persisted fingerprint survives these in-place edits.
                if isinstance(value, list):
                    value.append(value[0])
                with patch.object(diagnostics, "redact_structured", wraps=diagnostics.redact_structured) as scan:
                    applied = self.normalized(previous)
                self.assertGreater(scan.call_count, 0)
                self.assertIsNot(applied, previous)
                self.assertNotIn(SECRET, applied.model_dump_json())

    def test_settings_changes_recheck_content_and_preserve_prior_redaction(self):
        previous = self.normalized()
        for settings in [ContextCaptureSettings(retention_seconds=60), ContextCaptureSettings(redaction_mode="retain")]:
            with self.subTest(settings=settings):
                with patch.object(diagnostics, "redact_structured", wraps=diagnostics.redact_structured) as scan:
                    applied = self.normalized(previous, settings)
                self.assertGreater(scan.call_count, 0)
                self.assertNotEqual(applied.privacy_fingerprint, previous.privacy_fingerprint)
                self.assertEqual(applied.redaction_mode, settings.redaction_mode)
                self.assertEqual(applied.retention_seconds, settings.retention_seconds)
                self.assertTrue(applied.redacted)
                self.assertIn("api_key", applied.redacted_fields)

    def test_expiry_is_checked_on_reuse_and_cannot_expose_late_injected_content(self):
        settings = ContextCaptureSettings(retention_seconds=20)
        previous = self.normalized(settings=settings)
        with patch.object(diagnostics, "redact_structured", wraps=diagnostics.redact_structured) as scan:
            self.assertIs(self.normalized(previous, settings, NOW + timedelta(seconds=19)), previous)
        scan.assert_not_called()
        expired = self.normalized(previous, settings, NOW + timedelta(seconds=20))
        self.assertTrue(expired.expired)
        self.assertFalse(expired.retained)
        self.assertEqual(expired.messages, [])
        self.assertTrue(expired.redacted)
        self.assertIn("api_key", expired.redacted_fields)
        expired.http_payload = {"injected": ASSIGNMENT}
        applied = self.normalized(expired, settings, NOW + timedelta(seconds=21))
        self.assertIsNone(applied.http_payload)
        self.assertNotIn(SECRET, applied.model_dump_json())
        self.assertIn(diagnostics.POLICY_EXPIRED_GAP, applied.capture_gaps)

    def test_discard_change_clears_bodies_and_detects_later_in_place_edits(self):
        previous = self.normalized(capture(available_tools=["echo"], memory_versions=["knv_fixture"]))
        settings = ContextCaptureSettings(redaction_mode="discard")
        discarded = self.normalized(previous, settings)
        self.assertTrue(discarded.discarded)
        self.assertEqual(discarded.messages, [])
        self.assertEqual(discarded.available_tools, ["echo"])
        self.assertEqual(discarded.memory_versions, ["knv_fixture"])
        self.assertTrue(discarded.redacted)
        self.assertIn("api_key", discarded.redacted_fields)
        self.assertIs(self.normalized(discarded, settings), discarded)
        discarded.messages.append({"content": ASSIGNMENT})
        self.assertEqual(self.normalized(discarded, settings).messages, [])

    def test_detector_and_policy_versions_invalidate_saved_fingerprint(self):
        previous = self.normalized()
        for module, name in [(redaction, "DETECTOR_VERSION"), (diagnostics, "POLICY_VERSION")]:
            with self.subTest(version=name), patch.object(module, name, getattr(module, name) + 1):
                with patch.object(diagnostics, "redact_structured", wraps=diagnostics.redact_structured) as scan:
                    applied = self.normalized(previous)
                self.assertGreater(scan.call_count, 0)
                self.assertNotEqual(applied.privacy_fingerprint, previous.privacy_fingerprint)
                self.assertTrue(applied.redacted)

    def test_changed_detector_patterns_recheck_previously_unknown_content(self):
        previous = self.normalized(ModelRequestCapture(at=NOW.isoformat(), instructions="NEW_SYNTHETIC_CREDENTIAL"))
        extra = ("new_fixture", re.compile("(NEW_)SYNTHETIC_CREDENTIAL"))
        with patch.object(redaction, "SECRET_PATTERNS", (*redaction.SECRET_PATTERNS, extra)):
            applied = self.normalized(previous)
        self.assertNotIn("NEW_SYNTHETIC_CREDENTIAL", applied.instructions)
        self.assertIn("new_fixture", applied.redacted_fields)

    def test_legacy_or_modified_fingerprint_never_skips_normalization(self):
        for fingerprint in [None, "0" * 64]:
            previous = self.normalized()
            previous.privacy_fingerprint = fingerprint
            with patch.object(diagnostics, "redact_structured", wraps=diagnostics.redact_structured) as scan:
                applied = self.normalized(previous)
            self.assertGreater(scan.call_count, 0)
            self.assertTrue(applied.redacted)
            self.assertIn("api_key", applied.redacted_fields)

    def test_creation_time_edit_invalidates_expiry_and_canonical_key_order_reuses(self):
        settings = ContextCaptureSettings(retention_seconds=60)
        previous = self.normalized(capture(http_payload={"b": "safe", "a": "safe"}), settings)
        previous.http_payload = {"a": "safe", "b": "safe"}
        self.assertIs(self.normalized(previous, settings), previous)
        previous.at = (NOW - timedelta(seconds=60)).isoformat()
        self.assertTrue(self.normalized(previous, settings).expired)

    def test_large_run_reuses_old_captures_and_never_deep_copies_execution_state(self):
        class CannotCopy:
            def __deepcopy__(self, _memo):
                raise AssertionError("diagnostic normalization copied execution state")

        retained = self.normalized(ModelRequestCapture(at=NOW.isoformat(), messages=[{"content": "safe " * 50000}]))
        run = AgentRun(id="privacy_fixture", deployment_id="fixture", task="task",
            enabled_tools=["echo"], presented_tools=["echo"],
            created_at=NOW.isoformat(), updated_at=NOW.isoformat(), model_requests=[retained] * 50,
            events=[AgentEvent(at=NOW.isoformat(), kind="fixture", detail={"owner": CannotCopy()})])
        self.assertGreater(sum(len(item.model_dump_json()) for item in run.model_requests), 10_000_000)
        with patch.object(diagnostics, "redact_structured", wraps=diagnostics.redact_structured) as scan:
            self.assertIs(diagnostics.apply_run_diagnostic_policy(run, self.settings, now=NOW), run)
        scan.assert_not_called()
        new = capture()
        run.model_requests.append(new)
        with patch.object(diagnostics, "redact_structured", wraps=diagnostics.redact_structured) as scan:
            changed = diagnostics.apply_run_diagnostic_policy(run, self.settings, now=NOW)
        self.assertGreater(scan.call_count, 0)
        self.assertLessEqual(scan.call_count, 7)
        self.assertIsNot(changed, run)
        self.assertIs(changed.events, run.events)
        self.assertTrue(all(item is retained for item in changed.model_requests[:-1]))
        self.assertIs(run.model_requests[-1], new)
        self.assertNotIn(SECRET, changed.model_requests[-1].model_dump_json())


if __name__ == "__main__":
    unittest.main()
