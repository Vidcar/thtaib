"""Accepted policy, persisted binding and transmitted allowance stay aligned."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from workbench_backend.agents.helpers import freeze_settings
from workbench_backend.agents.effective_setup import effective_setting_values
from workbench_backend.agents.setup_schemas import SetupConfiguration
from workbench_backend.errors import HarnessError
from workbench_backend.inference.adapter import _direct_kwargs, _extra_body, _model_profile, _reasoning_replay_scope
from workbench_backend.inference.response_budget import bind_output_budget, freeze_output_policy
from workbench_backend.inference.schemas import Deployment, RunProfile, ServerProperties, SettingsBags
from workbench_backend.inference.settings import resolve_bags


def deployment(capacity=8192):
    return Deployment(id="budget-child", display_name="Budget child", scope="managed", status="running", endpoint="http://127.0.0.1:9999/v1",
        loaded_model_identity="exact-loaded-model", created_at="now", updated_at="now",
        server_props=ServerProperties(fetched="now", source_url="test", n_ctx=capacity,
            chat_template_caps={"supports_preserve_reasoning": True}))


class ResponseBudgetTests(unittest.TestCase):
    def test_auto_wire_and_compaction_share_once_bound_allowance(self):
        dep = deployment()
        for thinking, divisor in (("on", 2), ("off", 4), ("auto", 2)):
            bag = bind_output_budget(dep, freeze_output_policy(resolve_bags(per_request={"reasoning": thinking}).per_request))
            expected = (8192 - int(8192 * .08)) // divisor
            self.assertEqual(_direct_kwargs(bag)["max_tokens"], expected)
            self.assertEqual(_model_profile(dep, bag)["max_input_tokens"], 8192 - int(8192 * .08) - expected)
            self.assertEqual(bag.output_budget_binding.total_tokens, expected)
            # Reopening a run cannot re-tune its allowance from later capacity.
            reopened = type(bag).model_validate(bag.model_dump(mode="json"))
            self.assertEqual(bind_output_budget(deployment(16384), reopened).output_budget_binding, bag.output_budget_binding)
            with self.assertRaises(HarnessError) as error:
                bind_output_budget(deployment(expected), reopened)
            self.assertEqual(error.exception.code, "response_budget_capacity_conflict")

    def test_explicit_and_publisher_caps_are_not_clamped_or_replaced(self):
        explicit = bind_output_budget(deployment(), resolve_bags(per_request={"max_tokens": 701, "reasoning": "on"}).per_request)
        publisher = bind_output_budget(deployment(), resolve_bags(per_request_defaults={"max_tokens": 901}).per_request)
        self.assertEqual(explicit.output_budget_policy.mode, "explicit")
        self.assertEqual(publisher.output_budget_policy.mode, "publisher")
        self.assertEqual(_direct_kwargs(explicit)["max_tokens"], 701)
        self.assertEqual(_direct_kwargs(publisher)["max_tokens"], 901)
        with self.assertRaises(HarnessError):
            bind_output_budget(deployment(512), explicit)

    def test_known_template_default_changes_policy_without_adding_a_request_override(self):
        omitted = resolve_bags().per_request
        accepted = freeze_output_policy(omitted, default_thinking=False)
        self.assertNotIn("reasoning", accepted.requested)
        self.assertNotIn("reasoning", accepted.applied)
        self.assertFalse(accepted.output_budget_policy.thinking)
        self.assertEqual(bind_output_budget(deployment(), accepted).applied["max_tokens"], 1884)
        explicit = freeze_output_policy(resolve_bags(per_request={"reasoning": "on"}).per_request,
            default_thinking=False)
        self.assertTrue(explicit.output_budget_policy.thinking)

    def test_chat_admission_freezes_selected_defaults_and_choices_not_child_defaults(self):
        profile = RunProfile(id="selected", display_name="Selected", created_at="now", updated_at="now",
            bags=resolve_bags(per_request={"temperature": .31}, per_request_defaults={"top_p": .82}))
        manager = SimpleNamespace(get_profile=lambda _: profile,
            get_deployment=lambda _: deployment().model_copy(update={"settings": resolve_bags(per_request={"max_tokens": 123, "top_p": .2})}))
        config = SetupConfiguration(profile_id="selected", deployment_id="budget-child", per_request_overrides={"reasoning": "off"})
        accepted = SettingsBags.model_validate(freeze_settings(manager, config))
        profile.bags.per_request.applied["top_p"] = .1
        self.assertEqual(accepted.per_request.applied["temperature"], .31)
        self.assertEqual(accepted.per_request.applied["top_p"], .82)
        self.assertFalse(accepted.per_request.output_budget_policy.thinking)
        self.assertNotIn("max_tokens", accepted.per_request.applied)
        self.assertEqual(bind_output_budget(deployment(), accepted.per_request).applied["max_tokens"], 1884)

    def test_request_history_policy_matches_wire_and_replay(self):
        dep = deployment()
        on = resolve_bags(per_request={"reasoning": "on", "reasoning_preserve": True}).per_request
        off = resolve_bags(per_request={"reasoning_preserve": False}).per_request
        self.assertEqual(_extra_body(on)["chat_template_kwargs"], {"enable_thinking": True, "preserve_reasoning": True})
        self.assertEqual(_reasoning_replay_scope(dep, on), "full_history")
        self.assertEqual(_reasoning_replay_scope(dep, off), "current_turn")

    def test_unknown_endpoint_capacity_does_not_invent_numeric_auto(self):
        bag = bind_output_budget(deployment(None), resolve_bags().per_request)
        self.assertIsNone(bag.output_budget_binding)
        self.assertNotIn("max_tokens", _direct_kwargs(bag))

    def test_cold_preview_labels_auto_and_preserves_publisher_allowance(self):
        profile = RunProfile(id="selected", display_name="Selected", created_at="now", updated_at="now",
            bags=resolve_bags())
        manager = SimpleNamespace(store=SimpleNamespace(get_profile=lambda _: profile, get_deployment=lambda _: None))
        config = SetupConfiguration(profile_id="selected")
        auto = effective_setting_values(manager, config, {})["per_request.max_tokens"]
        self.assertEqual(auto.source, "Workbench Auto")
        self.assertFalse(auto.known)
        self.assertIsNone(auto.value)
        profile.bags = resolve_bags(per_request_defaults={"max_tokens": 901})
        publisher = effective_setting_values(manager, config, {})["per_request.max_tokens"]
        self.assertEqual(publisher.source, "Publisher recommendation")
        self.assertEqual(publisher.value, 901)
        self.assertTrue(publisher.known)

    def test_saved_native_unlimited_and_numeric_strings_are_preserved(self):
        unlimited = bind_output_budget(deployment(), resolve_bags(per_request={"max_tokens": -1}).per_request)
        self.assertEqual(unlimited.output_budget_policy.mode, "explicit")
        self.assertEqual(_direct_kwargs(unlimited)["max_tokens"], -1)
        self.assertEqual(_model_profile(deployment(), unlimited)["max_input_tokens"], 8192 - int(8192 * .08))
        numeric = bind_output_budget(deployment(), resolve_bags(per_request={"max_tokens": "701"}).per_request)
        self.assertEqual(numeric.output_budget_policy.mode, "explicit")
        self.assertEqual(_direct_kwargs(numeric)["max_tokens"], 701)

    def test_runtime_binding_cannot_silently_move_to_another_exact_model(self):
        bag = bind_output_budget(deployment(), resolve_bags().per_request)
        changed = deployment().model_copy(update={"loaded_model_identity": "different-native-model"})
        with self.assertRaises(HarnessError) as error:
            bind_output_budget(changed, bag)
        self.assertEqual(error.exception.code, "response_budget_model_conflict")
        unknown_capacity = changed.model_copy(update={"server_props": None})
        with self.assertRaises(HarnessError) as error:
            bind_output_budget(unknown_capacity, bag)
        self.assertEqual(error.exception.code, "response_budget_model_conflict")


if __name__ == "__main__":
    unittest.main()
