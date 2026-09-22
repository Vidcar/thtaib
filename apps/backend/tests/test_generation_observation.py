"""Generation measurements require reported usage, never stream chunk counts."""

from types import SimpleNamespace
import unittest

from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware


class GenerationObservationTests(unittest.TestCase):
    def observe(self, usage, *, unverified=False):
        startup = SimpleNamespace(applied={"ctx_size": 8192}, unverified=["ctx_size"] if unverified else [])
        run = SimpleNamespace(effective_setup=SimpleNamespace(bags=SimpleNamespace(startup=startup)),
                              context_observation=SimpleNamespace(capacity_tokens=None if unverified else 8192))
        middleware = WorkbenchHarnessMiddleware(run)
        response = SimpleNamespace(result=[SimpleNamespace(usage_metadata=usage)])
        middleware._observe_generation(response, 2.0)
        return run.generation_observation

    def test_reported_usage_is_attributed_to_completed_model_call(self):
        observed = self.observe({"input_tokens": 120, "output_tokens": 30})
        self.assertEqual(observed.input_tokens, 120)
        self.assertEqual(observed.output_tokens, 30)
        self.assertEqual(observed.tokens_per_second, 15)
        self.assertEqual(observed.elapsed_seconds, 2)
        self.assertEqual(observed.context_limit, 8192)
        self.assertEqual(observed.context_used_tokens, 150)

    def test_missing_or_invalid_usage_remains_unavailable(self):
        for usage in (None, {}, {"input_tokens": True, "output_tokens": False},
                      {"input_tokens": -1, "output_tokens": -1}):
            with self.subTest(usage=usage):
                observed = self.observe(usage)
                self.assertIsNone(observed.input_tokens)
                self.assertIsNone(observed.output_tokens)
                self.assertIsNone(observed.tokens_per_second)

    def test_unverified_context_limit_is_not_presented_as_actual(self):
        observed = self.observe({"input_tokens": 120, "output_tokens": 0}, unverified=True)
        self.assertIsNone(observed.context_limit)
        self.assertEqual(observed.output_tokens, 0)
        self.assertEqual(observed.tokens_per_second, 0)
