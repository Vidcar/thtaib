"""Readiness or a successful HTTP status alone is not text generation."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import httpx
from workbench_backend.errors import HarnessError
from workbench_backend.inference.deployments import DeploymentService
from workbench_backend.inference.lifecycle import LifecycleCoordinator
from workbench_backend.inference.process import HttpProbe
from workbench_backend.inference.schemas import Deployment, ServerProperties


class GenerationCheckTests(unittest.TestCase):
    def test_success_status_without_generated_text_is_not_success(self):
        for payload in ({}, {"choices": []}, {"choices": [{"message": {"content": ""}}]}):
            with self.subTest(payload=payload), patch("workbench_backend.inference.process.httpx.post", return_value=httpx.Response(200, json=payload)):
                self.assertFalse(HttpProbe().smoke("http://127.0.0.1:8080/v1", model="selected-model")[0])

    def test_valid_returned_text_is_distinct_generation_evidence(self):
        with patch("workbench_backend.inference.process.httpx.post", return_value=httpx.Response(200, json={"choices": [{"message": {"content": "pong"}}]})):
            ok, detail = HttpProbe().smoke("http://127.0.0.1:8080/v1", model="selected-model")
        self.assertTrue(ok)
        self.assertIn("text", detail)

    def test_html_success_response_is_not_generation(self):
        with patch("workbench_backend.inference.process.httpx.post", return_value=httpx.Response(200, text="<html>server ready</html>")):
            self.assertFalse(HttpProbe().smoke("http://127.0.0.1:8080/v1", model="selected-model")[0])

    def test_router_request_uses_exact_model_without_autoload(self):
        def routed_response(url, *, json, timeout):
            # Native routing rejects an invented name and can warm an unloaded
            # child unless the diagnostic explicitly disables autoload.
            if json["model"] != "deploy-selected" or httpx.URL(url).params.get("autoload") != "false":
                return httpx.Response(400, json={"error": "wrong model or autoload policy"})
            return httpx.Response(200, json={"choices": [{"message": {"content": "pong"}}]})

        with patch("workbench_backend.inference.process.httpx.post", side_effect=routed_response) as post:
            ok, _ = HttpProbe().smoke("http://127.0.0.1:8080/v1", model="deploy-selected", autoload=False)
        self.assertTrue(ok)
        self.assertEqual(post.call_args.kwargs["json"]["model"], "deploy-selected")


class DeploymentGenerationIdentityTests(unittest.TestCase):
    def service(self, *, preset=None, alias=None):
        deployment = Deployment(id="selected-deployment", display_name="Selected", scope="managed" if preset else "connected",
            status="running", endpoint="http://identity-fixture/v1", router_preset_id=preset,
            server_props=ServerProperties(fetched="now", source_url="fixture", model_alias=alias) if alias else None,
            created_at="now", updated_at="now")
        service = object.__new__(DeploymentService)
        service.store = SimpleNamespace(get_deployment=lambda _: deployment)
        service.lifecycle = LifecycleCoordinator()
        service.probe = HttpProbe()
        return service

    def test_selected_router_preset_takes_precedence_over_child_alias(self):
        service = self.service(preset="selected-preset", alias="child-alias")
        with patch("workbench_backend.inference.process.httpx.post", return_value=httpx.Response(200,
            json={"choices": [{"message": {"content": "pong"}}]})) as post:
            result = service.smoke("selected-deployment")
        self.assertTrue(result.ok)
        self.assertEqual(post.call_args.kwargs["json"]["model"], "selected-preset")
        self.assertEqual(httpx.URL(post.call_args.args[0]).params.get("autoload"), "false")

    def test_connected_generation_uses_observed_alias(self):
        service = self.service(alias="connected-model")
        with patch("workbench_backend.inference.process.httpx.post", return_value=httpx.Response(200,
            json={"choices": [{"message": {"content": "pong"}}]})) as post:
            self.assertTrue(service.smoke("selected-deployment").ok)
        self.assertEqual(post.call_args.kwargs["json"]["model"], "connected-model")

    def test_unobserved_connection_requires_one_unambiguous_model(self):
        for identities in ([], ["only-model"], ["first-model", "second-model"]):
            with self.subTest(identities=identities):
                service = self.service()
                paths = []
                def listing(request):
                    paths.append(request.url.path)
                    return httpx.Response(200, json={"data": [{"id": name} for name in identities]})
                client = httpx.Client(transport=httpx.MockTransport(listing))
                with patch("workbench_backend.inference.deployments.httpx.Client", return_value=client), \
                    patch("workbench_backend.inference.process.httpx.post", return_value=httpx.Response(200,
                        json={"choices": [{"message": {"content": "pong"}}]})) as post:
                    if len(identities) == 1:
                        self.assertTrue(service.smoke("selected-deployment").ok)
                        self.assertEqual(post.call_args.kwargs["json"]["model"], "only-model")
                    else:
                        with self.assertRaises(HarnessError) as raised:
                            service.smoke("selected-deployment")
                        self.assertIn(raised.exception.code, {"model_identity_unavailable", "ambiguous_model_identity"})
                        post.assert_not_called()
                self.assertEqual(paths, ["/v1/models"])
                self.assertTrue(client.is_closed)
