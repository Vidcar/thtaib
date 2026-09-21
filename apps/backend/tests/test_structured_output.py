from __future__ import annotations

import unittest
from typing import Any

from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain.agents.structured_output import (
    MultipleStructuredOutputsError,
    StructuredOutputValidationError,
)
from langchain_core.messages import AIMessage

from workbench_backend.agents.structured import (
    OutputSchemaRequest,
    StructuredOutputRepairMiddleware,
    StructuredOutputResult,
    response_format_for_run,
    update_structured_result_from_state,
)
from workbench_backend.errors import HarnessError
from workbench_backend.inference.capabilities import setup_fingerprint
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import (
    Deployment,
    DeploymentStatus,
    ManagementScope,
)


class StructuredOutputTests(unittest.TestCase):
    def test_schema_rejects_malformed_remote_ref_bad_version_and_name(self) -> None:
        with self.assertRaises(ValueError):
            OutputSchemaRequest(
                schema_version=0,
                name="Answer",
                schema={"type": "object"},
            )
        with self.assertRaises(ValueError):
            OutputSchemaRequest(
                schema_version=1,
                name="not-stable-name",
                schema={"type": "object"},
            )
        with self.assertRaises(HarnessError) as remote:
            OutputSchemaRequest(
                schema_version=1,
                name="Answer",
                schema={"type": "object", "$ref": "https://example.test/schema.json"},
            )
        self.assertEqual(remote.exception.code, "structured_schema_remote_ref")
        with self.assertRaises(HarnessError):
            OutputSchemaRequest(
                schema_version=1,
                name="Answer",
                schema={"type": "object", "properties": {"x": {"type": 7}}},
            )

    def test_jsonschema_validates_nested_enum_additional_properties_and_minimum(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "status": {"type": "string", "enum": ["ok", "blocked"]},
                "score": {"type": "integer", "minimum": 1},
                "nested": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"label": {"type": "string"}},
                    "required": ["label"],
                },
            },
            "required": ["status", "score", "nested"],
        }
        result = StructuredOutputResult(
            requested_schema_version=2,
            schema_name="Answer",
            requested_json_schema=schema,
            validation_status="missing",
        )

        valid = update_structured_result_from_state(
            result,
            {"structured_response": {"status": "ok", "score": 1, "nested": {"label": "done"}}},
        )
        assert valid is not None
        self.assertEqual(valid.validation_status, "valid")

        invalid = update_structured_result_from_state(
            result,
            {
                "structured_response": {
                    "status": "maybe",
                    "score": 0,
                    "nested": {"label": "done"},
                    "extra": True,
                }
            },
        )
        assert invalid is not None
        self.assertEqual(invalid.validation_status, "invalid")
        self.assertIsNotNone(invalid.error)

    def test_schema_valid_result_is_not_factual_correctness(self) -> None:
        schema = {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        }
        result = StructuredOutputResult(
            requested_schema_version=1,
            schema_name="Answer",
            requested_json_schema=schema,
            validation_status="missing",
        )

        updated = update_structured_result_from_state(
            result,
            {"structured_response": {"answer": "2 + 2 = 5"}},
        )

        assert updated is not None
        self.assertEqual(updated.validation_status, "valid")
        self.assertIn("not factual correctness", updated.note)

    def test_repair_middleware_retries_once_with_zero_tools_and_failure_messages(self) -> None:
        output = StructuredOutputResult(
            requested_schema_version=1,
            schema_name="Answer",
            requested_json_schema={"type": "object"},
            validation_status="missing",
        )
        events: list[tuple[str, dict[str, Any]]] = []
        middleware = StructuredOutputRepairMiddleware(output, on_event=lambda k, d: events.append((k, d)))
        request = _request()
        seen: list[ModelRequest] = []
        bad_message = AIMessage(
            content="",
            tool_calls=[
                {"name": "Answer", "args": {"value": 1}, "id": "call_1"},
                {"name": "Other", "args": {"value": 2}, "id": "call_2"},
            ],
        )

        def handler(item: ModelRequest) -> ModelResponse:
            seen.append(item)
            if len(seen) == 1:
                raise StructuredOutputValidationError(
                    "Answer",
                    ValueError("bad shape"),
                    bad_message,
                )
            return ModelResponse(result=[AIMessage(content="repaired")])

        response = middleware.wrap_model_call(request, handler)

        self.assertEqual(response.result[0].content, "repaired")
        self.assertEqual(output.repair_attempts, 1)
        self.assertEqual(seen[1].tools, [])
        self.assertIs(seen[1].response_format, request.response_format)
        self.assertEqual(seen[1].messages[-3], bad_message)
        self.assertEqual([message.tool_call_id for message in seen[1].messages[-2:]], ["call_1", "call_2"])
        self.assertEqual(events[0][0], "structured_output_repair_attempted")

    def test_repair_middleware_propagates_second_structured_error(self) -> None:
        output = StructuredOutputResult(
            requested_schema_version=1,
            schema_name="Answer",
            requested_json_schema={"type": "object"},
            validation_status="missing",
        )
        events: list[str] = []
        middleware = StructuredOutputRepairMiddleware(output, on_event=lambda k, _d: events.append(k))
        bad_message = AIMessage(
            content="",
            tool_calls=[{"name": "Answer", "args": {"value": 1}, "id": "call_1"}],
        )

        def handler(_item: ModelRequest) -> ModelResponse:
            raise MultipleStructuredOutputsError(["Answer", "Other"], bad_message)

        with self.assertRaises(MultipleStructuredOutputsError):
            middleware.wrap_model_call(_request(), handler)

        self.assertEqual(output.repair_attempts, 1)
        self.assertEqual(events, ["structured_output_repair_attempted", "structured_output_repair_failed"])

    def test_strategy_requires_strategy_specific_with_tools_evidence(self) -> None:
        deployment = _deployment()
        schema = OutputSchemaRequest(
            schema_version=1,
            name="Answer",
            schema={"type": "object"},
        )
        deployment.capability_evidence = [
            _evidence(deployment, "tools"),
            _evidence(deployment, "structured_tools"),
        ]

        with self.assertRaises(HarnessError) as missing_combined:
            response_format_for_run(
                output_schema=schema,
                deployment=deployment,
                per_request=None,
                tools_presented=True,
            )
        self.assertEqual(missing_combined.exception.code, "structured_tools_with_tools_unavailable")

        deployment.capability_evidence.append(_evidence(deployment, "structured_tools_with_tools"))
        response_format, result = response_format_for_run(
            output_schema=schema,
            deployment=deployment,
            per_request=None,
            tools_presented=True,
        )
        self.assertIsNotNone(response_format)
        assert result is not None
        self.assertEqual(result.strategy, "tool")

    def test_tools_off_is_explicit_not_same_as_no_tools_presented(self) -> None:
        deployment = _deployment()
        schema = OutputSchemaRequest(
            schema_version=1,
            name="Answer",
            schema={"type": "object"},
        )
        deployment.capability_evidence = [_evidence(deployment, "structured_tools")]

        response_format, result = response_format_for_run(
            output_schema=schema,
            deployment=deployment,
            per_request=None,
            tools_presented=False,
            tools_off=False,
        )

        self.assertIsNotNone(response_format)
        assert result is not None
        self.assertEqual(result.strategy, "tool")

    def test_schema_payload_uses_stable_request_name_over_inner_title(self) -> None:
        deployment = _deployment()
        schema = OutputSchemaRequest(
            schema_version=1,
            name="StableAnswer",
            schema={"title": "CallerCanNotRenameTool", "type": "object"},
        )
        deployment.capability_evidence = [_evidence(deployment, "structured_tools")]

        response_format, result = response_format_for_run(
            output_schema=schema,
            deployment=deployment,
            per_request=None,
            tools_presented=False,
        )

        self.assertIsNotNone(response_format)
        assert result is not None
        self.assertEqual(result.schema_name, "StableAnswer")
        self.assertEqual(response_format.schema_specs[0].name, "StableAnswer")


def _request() -> ModelRequest:
    return ModelRequest(
        model=None,  # type: ignore[arg-type]
        messages=[AIMessage(content="answer")],
        tools=[{"type": "function", "function": {"name": "effectful", "parameters": {}}}],
        response_format={"type": "json_schema"},
    )


def _deployment() -> Deployment:
    return Deployment(
        id="deploy_structured",
        display_name="structured",
        scope=ManagementScope.connected,
        status=DeploymentStatus.running,
        endpoint="http://127.0.0.1:9/v1",
        created_at=utc_now(),
        updated_at=utc_now(),
    )


def _evidence(deployment: Deployment, capability: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": f"probe_{capability}",
        "deployment_id": deployment.id,
        "capability": capability,
        "status": "passed",
        "fingerprint": setup_fingerprint(deployment),
        "setup": {},
        "tested_at": utc_now(),
        "inputs": {},
        "observations": {},
    }


if __name__ == "__main__":
    unittest.main()
