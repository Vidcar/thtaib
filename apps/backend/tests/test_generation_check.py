"""Readiness or a successful HTTP status alone is not text generation."""
import unittest
from unittest.mock import patch
import httpx
from workbench_backend.inference.process import HttpProbe


class GenerationCheckTests(unittest.TestCase):
    def test_success_status_without_generated_text_is_not_success(self):
        for payload in ({}, {"choices": []}, {"choices": [{"message": {"content": ""}}]}):
            with self.subTest(payload=payload), patch("workbench_backend.inference.process.httpx.post", return_value=httpx.Response(200, json=payload)):
                self.assertFalse(HttpProbe().smoke("http://127.0.0.1:8080/v1")[0])

    def test_valid_returned_text_is_distinct_generation_evidence(self):
        with patch("workbench_backend.inference.process.httpx.post", return_value=httpx.Response(200, json={"choices": [{"message": {"content": "pong"}}]})):
            ok, detail = HttpProbe().smoke("http://127.0.0.1:8080/v1")
        self.assertTrue(ok)
        self.assertIn("text", detail)

    def test_html_success_response_is_not_generation(self):
        with patch("workbench_backend.inference.process.httpx.post", return_value=httpx.Response(200, text="<html>server ready</html>")):
            self.assertFalse(HttpProbe().smoke("http://127.0.0.1:8080/v1")[0])
