"""Counts and speed are request-local reported measurements, not chunk guesses."""

import unittest
from unittest.mock import patch

from workbench_backend.inference.telemetry import RequestTelemetry


def sample(*, ident="request-one", output=10, cached=80, processed=20, **extra):
    return {"id": ident, "timings": {"cache_n": cached, "prompt_n": processed,
            "predicted_n": output, "predicted_ms": 200, "predicted_per_second": 45.0}, **extra}


class RequestTelemetryTests(unittest.TestCase):
    def test_prefill_reports_full_prompt_then_generation_includes_cached_tokens(self):
        seen = []
        telemetry = RequestTelemetry(seen.append)
        self.assertTrue(seen.pop()["reset"])
        telemetry.receive(sample(output=0, processed=0, prompt_progress={"total": 100}))
        self.assertEqual(seen[-1]["input_tokens"], 100)
        self.assertEqual(seen[-1]["context_used_tokens"], 100)
        self.assertEqual(seen[-1]["phase"], "prompt_processing")
        self.assertIsNone(seen[-1]["tokens_per_second"])
        telemetry.receive(sample())
        self.assertEqual(seen[-1]["context_used_tokens"], 110)
        self.assertEqual(seen[-1]["tokens_per_second"], 45.0)
        self.assertNotEqual(seen[-1]["tokens_per_second"], 10 / .2)
        telemetry.finish()
        self.assertEqual(seen[-1]["phase"], "completed")
        self.assertEqual(seen[-1]["interval"], "last_model_call_generation")

    def test_throttled_updates_retain_latest_counts_on_cancellation_and_next_request_resets(self):
        seen = []
        with patch("workbench_backend.inference.telemetry.time.monotonic", return_value=1.0):
            telemetry = RequestTelemetry(seen.append)
            for count in range(2, 50):
                telemetry.receive(sample(output=count))
            self.assertEqual(len(seen), 2)
            telemetry.finish(interrupted=True)
        self.assertEqual(seen[-1]["output_tokens"], 49)
        self.assertEqual(seen[-1]["phase"], "interrupted")
        request_id = seen[-1]["request_id"]
        RequestTelemetry(seen.append)
        self.assertTrue(seen[-1]["reset"])
        self.assertNotEqual(seen[-1]["request_id"], request_id)

    def test_unrelated_or_decreasing_counts_cannot_replace_request_sample(self):
        seen = []
        telemetry = RequestTelemetry(seen.append)
        telemetry.receive(sample(output=20))
        telemetry.receive(sample(ident="another-request", output=999))
        telemetry.receive(sample(output=1))
        telemetry.finish()
        self.assertEqual(seen[-1]["output_tokens"], 20)

    def test_missing_invalid_and_partial_prompt_counts_are_not_invented(self):
        for timings in ({}, {"predicted_n": True}, {"predicted_n": -1}, {"predicted_n": 0, "prompt_n": 15, "cache_n": 3}):
            with self.subTest(timings=timings):
                seen = []
                telemetry = RequestTelemetry(seen.append)
                telemetry.receive({"id": "test", "timings": timings})
                telemetry.finish()
                self.assertTrue(seen[-1].get("reset") or seen[-1]["input_tokens"] is None)
        seen = []
        telemetry = RequestTelemetry(seen.append)
        value = sample()
        value["timings"]["predicted_per_second"] = float("inf")
        telemetry.receive(value)
        self.assertIsNone(seen[-1]["tokens_per_second"])
