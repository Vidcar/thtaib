"""Exact accepted generation values and native full-capacity profiles."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from deepagents.middleware.summarization import create_summarization_middleware
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import HumanMessage

from tests.scripted_model import ScriptedChatModel
from workbench_backend.agents.helpers import freeze_settings, require_accepted_model_identity
from workbench_backend.agents.effective_setup import effective_setting_values
from workbench_backend.agents.setup_schemas import SetupConfiguration
from workbench_backend.errors import HarnessError
from workbench_backend.inference.adapter import _direct_kwargs, _extra_body, _model_profile, _reasoning_replay_scope
from workbench_backend.inference.schemas import Deployment, RunProfile, ServerProperties, SettingsBags
from workbench_backend.inference.settings import resolve_bags


def deployment(capacity=32768):
    return Deployment(id="native-child", display_name="Native child", scope="managed", status="running",
        endpoint="http://127.0.0.1:9999/v1", loaded_model_identity="exact-loaded-model", created_at="now", updated_at="now",
        server_props=ServerProperties(fetched="now", source_url="test", n_ctx=capacity,
            chat_template_caps={"supports_preserve_reasoning": True}))


class NativeOutputDefaultsTests(unittest.TestCase):
    def test_default_is_unlimited_and_thinking_never_changes_capacity_or_compaction(self):
        for capacity in (8192, 32768, 98304, 131072):
            for thinking in ("on", "off", "auto"):
                with self.subTest(capacity=capacity, thinking=thinking):
                    bag = resolve_bags(per_request={"reasoning": thinking}).per_request
                    self.assertEqual(_direct_kwargs(bag)["max_tokens"], -1)
                    self.assertEqual(_model_profile(deployment(capacity), bag)["max_input_tokens"], capacity)
                    model = ScriptedChatModel([], profile={"max_input_tokens": capacity})
                    native = create_summarization_middleware(model, backend=lambda _: None)
                    request = ModelRequest(model=model, messages=[HumanMessage(content="hello")],
                        tools=[], model_settings={"max_tokens": -1})
                    threshold = int(capacity * .85)
                    self.assertFalse(native._should_summarize(request.messages, threshold - 1))
                    self.assertTrue(native._should_summarize(request.messages, threshold))
                    self.assertEqual(native._lc_helper.keep, ("fraction", .10))
                    self.assertEqual(native._input_budget(request), int(capacity * .95))
                    self.assertEqual(int(capacity * .85), 27852 if capacity == 32768 else int(capacity * .85))

    def test_explicit_finite_output_is_exact_and_sdk_reserves_it_once(self):
        for value in (701, "701", -1):
            bag = resolve_bags(per_request={"max_tokens": value}).per_request
            self.assertEqual(_direct_kwargs(bag)["max_tokens"], int(value))
            profile = _model_profile(deployment(), bag)
            self.assertEqual(profile["max_input_tokens"], 32768)
            model = ScriptedChatModel([], profile=profile)
            native = create_summarization_middleware(model, backend=lambda _: None)
            request = ModelRequest(model=model, messages=[HumanMessage(content="hello")], tools=[],
                model_settings={"max_tokens": int(value), "max_completion_tokens": int(value)})
            self.assertEqual(native._input_budget(request), int(32768 * .95) - max(0, int(value)))

    def test_chat_admission_freezes_selected_values_not_later_saved_or_child_defaults(self):
        profile = RunProfile(id="selected", display_name="Selected", created_at="now", updated_at="now",
            bags=resolve_bags(startup_defaults={"ctx_size": 32768}, per_request={"temperature": .31},
                per_request_defaults={"top_p": .82}))
        manager = SimpleNamespace(get_profile=lambda _: profile,
            get_deployment=lambda _: deployment().model_copy(update={"settings": resolve_bags(per_request={"max_tokens": 123, "top_p": .2})}))
        config = SetupConfiguration(profile_id="selected", deployment_id="native-child",
            startup_overrides={"n_gpu_layers": 12}, per_request_overrides={"reasoning": "off"})
        accepted = SettingsBags.model_validate(freeze_settings(manager, config))
        profile.bags.per_request.applied["top_p"] = .1
        self.assertEqual(accepted.per_request.applied["temperature"], .31)
        self.assertEqual(accepted.per_request.applied["top_p"], .82)
        self.assertEqual(accepted.per_request.applied["max_tokens"], -1)
        self.assertEqual(accepted.startup.applied["ctx_size"], 32768)
        self.assertEqual(accepted.startup.applied["n_gpu_layers"], 12)
        self.assertNotIn("output_budget_policy", accepted.per_request.model_dump())
        self.assertNotIn("output_budget_binding", accepted.per_request.model_dump())

    def test_request_history_policy_matches_wire_and_replay(self):
        dep = deployment()
        on = resolve_bags(per_request={"reasoning": "on", "reasoning_preserve": True}).per_request
        off = resolve_bags(per_request={"reasoning_preserve": False}).per_request
        self.assertEqual(_extra_body(on)["chat_template_kwargs"], {"enable_thinking": True, "preserve_reasoning": True})
        self.assertEqual(_reasoning_replay_scope(dep, on), "full_history")
        self.assertEqual(_reasoning_replay_scope(dep, off), "current_turn")

    def test_unknown_capacity_uses_sdk_fallback_without_invented_cloud_limit(self):
        bag = resolve_bags().per_request
        profile = _model_profile(deployment(None), bag)
        self.assertNotIn("max_input_tokens", profile)
        model = ScriptedChatModel([], profile=profile)
        native = create_summarization_middleware(model, backend=lambda _: None)
        self.assertFalse(native._should_summarize([HumanMessage(content="hello")], 169999))
        self.assertTrue(native._should_summarize([HumanMessage(content="hello")], 170000))
        self.assertEqual(native._lc_helper.keep, ("messages", 6))
        self.assertEqual(_direct_kwargs(bag)["max_tokens"], -1)

    def test_cold_preview_shows_actual_native_unlimited(self):
        profile = RunProfile(id="selected", display_name="Selected", created_at="now", updated_at="now", bags=resolve_bags())
        manager = SimpleNamespace(store=SimpleNamespace(get_profile=lambda _: profile, get_deployment=lambda _: None))
        actual = effective_setting_values(manager, SetupConfiguration(profile_id="selected"), {})["per_request.max_tokens"]
        self.assertEqual(actual.value, -1)
        self.assertTrue(actual.known)

    def test_exact_model_identity_still_rejects_a_changed_model(self):
        bags = resolve_bags()
        bags.accepted_loading_identity = "exact-loaded-model"
        require_accepted_model_identity(deployment(), bags)
        with self.assertRaises(HarnessError) as caught:
            require_accepted_model_identity(deployment().model_copy(update={"loaded_model_identity": "different-model"}), bags)
        self.assertEqual(caught.exception.code, "accepted_model_identity_changed")


if __name__ == "__main__":
    unittest.main()
