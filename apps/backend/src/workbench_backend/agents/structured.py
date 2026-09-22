"""Structured-output policy for the embedded Deep Agents harness."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Literal

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.structured_output import ProviderStrategy, ToolStrategy
from langchain.agents.structured_output import (
    MultipleStructuredOutputsError,
    StructuredOutputValidationError,
)
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import BaseModel, ConfigDict, Field, field_validator

from workbench_backend.errors import HarnessError
from workbench_backend.inference.capabilities import capability_support
from workbench_backend.inference.schemas import Deployment, SettingsBag

StructuredStrategyName = Literal["provider", "tool"]
StructuredRepairEvent = Callable[[str, dict[str, Any]], None]
SCHEMA_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,119}$")


class OutputSchemaRequest(BaseModel):
    """Caller-supplied JSON schema for one run.

    The schema is passed to Deep Agents' existing ``response_format`` seam.
    It is not parsed out of assistant prose.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    schema_version: int = Field(default=1, ge=1)
    name: str = Field(min_length=1, max_length=120, pattern=SCHEMA_NAME_PATTERN.pattern)
    json_schema: dict[str, Any] = Field(default_factory=dict, alias="schema")
    description: str | None = None
    strategy: Literal["auto", "native", "tool"] = "auto"

    @field_validator("json_schema")
    @classmethod
    def validate_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_schema_document(value)
        return value


class StructuredOutputResult(BaseModel):
    schema_version: int = 1
    requested_schema_version: int
    schema_name: str
    requested_json_schema: dict[str, Any] = Field(default_factory=dict)
    strategy: StructuredStrategyName | None = None
    validation_status: Literal["not_requested", "valid", "missing", "invalid"] = "not_requested"
    result: Any = None
    error: str | None = None
    repair_attempts: int = 0
    note: str = (
        "Structured output is the agent structured_response, not JSON-looking answer text. "
        "Schema validity is not factual correctness."
    )


def response_format_for_run(
    *,
    output_schema: OutputSchemaRequest | None,
    deployment: Deployment,
    per_request: SettingsBag | None,
    tools_presented: bool,
    tools_off: bool = False,
) -> tuple[Any | None, StructuredOutputResult | None]:
    if output_schema is None:
        return None, None
    _validate_json_schema(output_schema)
    strategy = _select_strategy(
        output_schema=output_schema,
        deployment=deployment,
        per_request=per_request,
        tools_presented=tools_presented,
        tools_off=tools_off,
    )
    schema_payload = _schema_payload(output_schema)
    result = StructuredOutputResult(
        schema_name=output_schema.name,
        requested_schema_version=output_schema.schema_version,
        requested_json_schema=output_schema.json_schema,
        strategy=strategy,
        validation_status="missing",
    )
    if strategy == "provider":
        return ProviderStrategy(schema_payload, strict=True), result
    return (
        ToolStrategy(
            schema_payload,
            handle_errors=False,
        ),
        result,
    )


def update_structured_result_from_state(
    current: StructuredOutputResult | None,
    state_values: dict[str, Any] | None,
) -> StructuredOutputResult | None:
    if current is None:
        return None
    updated = current.model_copy(deep=True)
    values = state_values or {}
    if "structured_response" not in values:
        updated.validation_status = "missing"
        updated.error = updated.error or "Agent completed without a structured_response."
        return updated
    response = values.get("structured_response")
    updated.result = _jsonable(response)
    validation_error = _validate_value(updated.result, current_schema=updated.requested_json_schema)
    if validation_error:
        updated.validation_status = "invalid"
        updated.error = validation_error
        return updated
    updated.validation_status = "valid"
    updated.error = None
    return updated


def mark_structured_failure(
    current: StructuredOutputResult | None,
    error: str,
) -> StructuredOutputResult | None:
    if current is None:
        return None
    updated = current.model_copy(deep=True)
    updated.validation_status = "invalid"
    updated.error = error
    return updated


def _select_strategy(
    *,
    output_schema: OutputSchemaRequest,
    deployment: Deployment,
    per_request: SettingsBag | None,
    tools_presented: bool,
    tools_off: bool = False,
) -> StructuredStrategyName:
    if output_schema.strategy in {"auto", "native"}:
        if capability_support(deployment, "structured_native", per_request) == "passed":
            if tools_presented and capability_support(deployment, "structured_with_tools", per_request) != "passed" and output_schema.strategy == "native":
                raise HarnessError(
                    "This setup has not passed combined structured-output plus tool-call evidence.",
                    code="structured_with_tools_unavailable",
                    status_code=409,
                    details={
                        "support": capability_support(
                            deployment,
                            "structured_with_tools",
                            per_request,
                        )
                    },
                )
            if not tools_presented or capability_support(deployment, "structured_with_tools", per_request) == "passed":
                return "provider"
        if output_schema.strategy == "native":
            raise HarnessError(
                "This setup has not passed a native structured-output probe.",
                code="structured_native_unavailable",
                status_code=409,
                details={"support": capability_support(deployment, "structured_native", per_request)},
            )
    if tools_off:
        raise HarnessError(
            "Structured output with tools off requires passed native structured-output evidence.",
            code="structured_tools_off_unavailable",
            status_code=409,
            details={"support": capability_support(deployment, "structured_native", per_request)},
        )
    tool_support = capability_support(deployment, "structured_tools", per_request)
    if tool_support != "passed":
        raise HarnessError(
            "This setup has not passed a tool-based structured-output probe.",
            code="structured_tools_unavailable",
            status_code=409,
            details={"support": tool_support},
        )
    if tools_presented and capability_support(deployment, "structured_tools_with_tools", per_request) != "passed":
        raise HarnessError(
            "This setup has not passed combined tool-based structured-output plus executable-tool evidence.",
            code="structured_tools_with_tools_unavailable",
            status_code=409,
            details={
                "support": capability_support(
                    deployment,
                    "structured_tools_with_tools",
                    per_request,
                )
            },
        )
    if tools_presented and capability_support(deployment, "tools", per_request) != "passed":
        raise HarnessError(
            "This setup has not passed a tool-call probe required for tool-based structured output.",
            code="structured_tool_calls_unavailable",
            status_code=409,
            details={"support": capability_support(deployment, "tools", per_request)},
        )
    return "tool"


def _validate_json_schema(output_schema: OutputSchemaRequest) -> None:
    _validate_schema_document(output_schema.json_schema)


def _schema_payload(output_schema: OutputSchemaRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {
        **output_schema.json_schema,
        "title": output_schema.name,
    }
    if output_schema.description:
        payload.setdefault("description", output_schema.description)
    return payload


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _validate_value(value: Any, *, current_schema: Any) -> str | None:
    if not isinstance(current_schema, dict):
        return None
    try:
        validator = Draft202012Validator(current_schema)
        validator.validate(value)
    except ValidationError as exc:
        return exc.message
    return None


class StructuredOutputRepairMiddleware(AgentMiddleware):
    """Retry one structured-formatting model call without granting tool authority.

    The retry is the same model call path with ``tools=[]`` and the same
    response_format. It does not rerun the whole agent and cannot dispatch
    executable tools.
    """

    def __init__(
        self,
        result: StructuredOutputResult,
        *,
        on_event: StructuredRepairEvent | None = None,
    ) -> None:
        super().__init__()
        self.result = result
        self.on_event = on_event

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        try:
            return handler(request)
        except (StructuredOutputValidationError, MultipleStructuredOutputsError) as exc:
            return self._repair_once(request, handler, exc)

    def _repair_once(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
        exc: StructuredOutputValidationError | MultipleStructuredOutputsError,
    ) -> ModelResponse:
        retry = self._repair_request(request, exc)
        try:
            return self._validate_repair_response(handler(retry))
        except (StructuredOutputValidationError, MultipleStructuredOutputsError) as retry_exc:
            self._repair_failed(retry_exc)
            raise

    async def awrap_model_call(self, request: ModelRequest, handler: Any) -> ModelResponse:
        try:
            return await handler(request)
        except (StructuredOutputValidationError, MultipleStructuredOutputsError) as exc:
            retry = self._repair_request(request, exc)
            try:
                return self._validate_repair_response(await handler(retry))
            except (StructuredOutputValidationError, MultipleStructuredOutputsError) as retry_exc:
                self._repair_failed(retry_exc)
                raise

    def _repair_request(self, request: ModelRequest, exc: Any) -> ModelRequest:
        if self.result.repair_attempts >= 1:
            self._record_event(
                "structured_output_repair_failed",
                {"error": str(exc), "attempts": self.result.repair_attempts},
            )
            raise exc
        self.result.repair_attempts += 1
        self._record_event(
            "structured_output_repair_attempted",
            {
                "attempt": self.result.repair_attempts,
                "error": str(exc),
                "tools_presented_on_retry": [],
            },
        )
        return request.override(
            messages=[
                *request.messages,
                exc.ai_message,
                *_repair_tool_messages(exc.ai_message),
            ],
            tools=[],
            response_format=request.response_format,
        )

    def _validate_repair_response(self, response: ModelResponse) -> ModelResponse:
        for message in response.result:
            for call in getattr(message, "tool_calls", []):
                if call.get("name") != self.result.schema_name:
                    raise HarnessError("Formatting recovery cannot execute task tools or repeat effects.", code="structured_repair_tool_forbidden", status_code=409)
        return response

    def _repair_failed(self, exc: Any) -> None:
        self._record_event("structured_output_repair_failed",
            {"error": str(exc), "attempts": self.result.repair_attempts})

    def _record_event(self, kind: str, detail: dict[str, Any]) -> None:
        if self.on_event is not None:
            self.on_event(kind, detail)


def _repair_tool_messages(ai_message: AIMessage) -> list[ToolMessage]:
    calls = _message_tool_calls(ai_message)
    messages: list[ToolMessage] = []
    for index, call in enumerate(calls):
        name = str(call.get("name") or "structured_output")
        call_id = str(call.get("id") or f"structured_repair_{index}")
        messages.append(
            ToolMessage(
                content=(
                    "Structured output failed validation. Retry formatting only; "
                    "do not call external tools or repeat side effects."
                ),
                name=name,
                tool_call_id=call_id,
                status="error",
            )
        )
    return messages


def _message_tool_calls(ai_message: AIMessage) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for item in getattr(ai_message, "tool_calls", None) or []:
        if isinstance(item, dict):
            calls.append(item)
    for item in getattr(ai_message, "invalid_tool_calls", None) or []:
        if isinstance(item, dict):
            calls.append(item)
    return calls


def _validate_schema_document(schema: dict[str, Any]) -> None:
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise HarnessError(
            "Structured output schema must be a JSON object schema.",
            code="structured_schema_invalid",
            status_code=400,
        )
    remote_ref = _remote_ref(schema)
    if remote_ref is not None:
        raise HarnessError(
            "Structured output schemas cannot use remote references.",
            code="structured_schema_remote_ref",
            status_code=400,
            details={"ref": remote_ref},
        )
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise HarnessError(
            "Structured output schema is not a valid JSON Schema.",
            code="structured_schema_invalid",
            status_code=400,
            details={"error": exc.message},
        ) from exc


def _remote_ref(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("$ref", "$dynamicRef", "$recursiveRef"):
            ref = value.get(key)
            if isinstance(ref, str) and not ref.startswith("#"):
                return ref
        schema_id = value.get("$id")
        if isinstance(schema_id, str) and ("://" in schema_id or schema_id.startswith("urn:")):
            return schema_id
        for item in value.values():
            found = _remote_ref(item)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _remote_ref(item)
            if found is not None:
                return found
    return None
