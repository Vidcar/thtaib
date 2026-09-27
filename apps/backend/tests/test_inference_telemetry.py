"""Counts and speed are request-local reported measurements, not chunk guesses."""

import unittest
import threading
from unittest.mock import patch

from workbench_backend.inference.telemetry import COMPLETED_REQUEST_LIMIT, LatestGenerationPublisher, RequestTelemetry, request_purpose


def sample(*, ident="request-one", output=10, cached=80, processed=20, **extra):
    return {"id": ident, "timings": {"cache_n": cached, "prompt_n": processed,
            "predicted_n": output, "predicted_ms": 200, "predicted_per_second": 45.0}, **extra}


class RequestTelemetryTests(unittest.TestCase):
    def test_prefill_is_server_reported_and_first_output_is_local_stream_delay(self):
        seen = []
        with patch("workbench_backend.inference.telemetry.time.monotonic", return_value=10.0):
            telemetry = RequestTelemetry(seen.append)
            telemetry.receive(sample(output=0, choices=[{"delta": {"role": "assistant", "content": ""}}]))
        with patch("workbench_backend.inference.telemetry.time.monotonic", return_value=14.5):
            value = sample(choices=[{"delta": {"reasoning_content": "Check"}}])
            value["timings"]["prompt_ms"] = 4200.0
            telemetry.receive(value)
        with patch("workbench_backend.inference.telemetry.time.monotonic", return_value=18.0):
            telemetry.receive({**value, "choices": [{"delta": {"content": "Answer"}}]})
            telemetry.finish()
        self.assertEqual(seen[-1]["prefill_seconds"], 4.2)
        self.assertEqual(seen[-1]["time_to_first_token_seconds"], 4.5)
        self.assertEqual(seen[-1]["elapsed_seconds"], .2, "decode duration remains separate")
        self.assertTrue(seen[-1]["request_started_at"])

    def test_nonstream_and_empty_deltas_cannot_invent_first_output_delay(self):
        for choices in ([{"message": {"content": "completed answer"}}], [{"delta": {"role": "assistant"}}], []):
            seen = []
            telemetry = RequestTelemetry(seen.append)
            telemetry.receive(sample(choices=choices))
            telemetry.finish()
            self.assertIsNone(seen[-1]["time_to_first_token_seconds"])

    def test_function_argument_delta_is_substantive_output(self):
        seen = []
        with patch("workbench_backend.inference.telemetry.time.monotonic", return_value=1.0):
            telemetry = RequestTelemetry(seen.append)
        with patch("workbench_backend.inference.telemetry.time.monotonic", return_value=2.0):
            telemetry.receive(sample(choices=[{"delta": {"tool_calls": [{"function": {"arguments": "{"}}]}}]))
            telemetry.finish(interrupted=True)
        self.assertEqual(seen[-1]["time_to_first_token_seconds"], 1)

    def test_delta_without_timing_retains_first_output_time_for_later_measurement(self):
        seen = []
        with patch("workbench_backend.inference.telemetry.time.monotonic", return_value=1.0):
            telemetry = RequestTelemetry(seen.append)
        with patch("workbench_backend.inference.telemetry.time.monotonic", return_value=3.0):
            telemetry.receive({"id": "request-one", "choices": [{"delta": {"content": "First"}}]})
        with patch("workbench_backend.inference.telemetry.time.monotonic", return_value=5.0):
            telemetry.receive(sample())
            telemetry.finish()
        self.assertEqual(seen[-1]["time_to_first_token_seconds"], 2)

    def test_missing_invalid_prompt_timings_are_unavailable(self):
        for duration in (None, -1, True, float("nan"), float("inf"), "450"):
            with self.subTest(duration=duration):
                seen = []
                telemetry = RequestTelemetry(seen.append)
                value = sample()
                value["timings"]["prompt_ms"] = duration
                telemetry.receive(value)
                telemetry.finish()
                self.assertIsNone(seen[-1]["prefill_seconds"])

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


class LatestGenerationPublisherTests(unittest.TestCase):
    def test_terminal_history_survives_reset_and_slow_display_publication(self):
        entered, release = threading.Event(), threading.Event()

        def callback(value):
            entered.set()
            if not release.wait(5):
                raise TimeoutError("measurement publisher was not released")

        publisher = LatestGenerationPublisher(callback)
        try:
            work = RequestTelemetry(publisher.publish)
            self.assertTrue(entered.wait(2))
            work.receive(sample())
            work.finish()
            with request_purpose("summary"):
                summary = RequestTelemetry(publisher.publish)
                summary.receive(sample(ident="summary"))
                summary.finish(interrupted=True)
            RequestTelemetry(publisher.publish)
            history = publisher.completed_samples()
            self.assertEqual([item["purpose"] for item in history], ["work", "summary"])
            self.assertEqual([item["phase"] for item in history], ["completed", "interrupted"])
            self.assertTrue(publisher.latest_sample("work")["reset"])
            history[0]["output_tokens"] = 999
            self.assertEqual(publisher.completed_samples()[0]["output_tokens"], 10)
        finally:
            release.set()
            publisher.close()

    def test_history_is_bounded_and_updates_same_request_without_duplicates(self):
        publisher = LatestGenerationPublisher(lambda _: None)
        try:
            for index in range(COMPLETED_REQUEST_LIMIT + 3):
                ident = str(index)
                publisher.publish({"request_id": ident, "reset": True})
                publisher.publish({"request_id": ident, "phase": "completed", "output_tokens": index})
            publisher.publish({"request_id": ident, "phase": "completed", "output_tokens": 999})
            history = publisher.completed_samples()
            self.assertEqual(len(history), COMPLETED_REQUEST_LIMIT)
            self.assertEqual(history[0]["request_id"], "3")
            self.assertEqual(history[-1]["output_tokens"], 999)
            publisher.publish({"request_id": "new", "reset": True})
            publisher.publish({"request_id": ident, "phase": "interrupted", "output_tokens": 999})
            self.assertEqual(publisher.completed_samples()[-1]["phase"], "interrupted")
            self.assertEqual(publisher.latest_sample()["request_id"], "new")
        finally:
            publisher.close()

    def test_blocked_publication_keeps_only_newest_request_reset_and_sample(self):
        entered, release = threading.Event(), threading.Event()
        seen = []

        def callback(sample):
            seen.append(sample)
            if sample["request_id"] == "old":
                entered.set()
                if not release.wait(5):
                    raise TimeoutError("measurement publisher was not released")

        publisher = LatestGenerationPublisher(callback)
        try:
            publisher.publish({"request_id": "old", "reset": True})
            self.assertTrue(entered.wait(2))
            publisher.publish({"request_id": "old", "output_tokens": 1})
            publisher.publish({"request_id": "old", "output_tokens": 2})
            publisher.publish({"request_id": "new", "reset": True})
            publisher.publish({"request_id": "new", "output_tokens": 3})
            publisher.publish({"request_id": "new", "output_tokens": 4, "phase": "completed"})
            self.assertEqual(publisher.latest_sample()["output_tokens"], 4)
            release.set()
            self.assertTrue(publisher.wait_idle(2))
            self.assertEqual(seen, [
                {"request_id": "old", "reset": True},
                {"request_id": "new", "reset": True},
                {"request_id": "new", "output_tokens": 4, "phase": "completed"},
            ])
        finally:
            release.set()
            publisher.close()
