"""Scaffold checks for the Local AI Workbench backend."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from workbench_backend.app import PRODUCT_NAME, app


class HealthEndpointTests(unittest.TestCase):
    def test_health_returns_scaffold_identity(self) -> None:
        client = TestClient(app)
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["product"], PRODUCT_NAME)
        self.assertEqual(body["surface"], "scaffold")

    def test_openapi_is_not_published(self) -> None:
        client = TestClient(app)
        self.assertEqual(client.get("/openapi.json").status_code, 404)
        self.assertEqual(client.get("/docs").status_code, 404)


if __name__ == "__main__":
    unittest.main()
