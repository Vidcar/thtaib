"""Small, explicit adapter probes; no execution authority or general agent loop."""

from __future__ import annotations

import base64
import json
import re
import struct
import zlib
from typing import Any

from langchain_core.messages import HumanMessage, ToolMessage
from openai import BadRequestError

from workbench_backend.errors import HarnessError
from workbench_backend.inference.adapter import chat_model_for_deployment
from workbench_backend.inference.capabilities import CapabilityEvidence, CapabilityProbeRequest, setup_fingerprint, setup_identity
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.inference.settings import PER_REQUEST_KEYS, resolve_bag

PROBE_SCHEMA = {
    "title": "probe_answer",
    "type": "object", "properties": {"answer": {"type": "integer"}},
    "required": ["answer"], "additionalProperties": False,
}
PROBE_TOOL = {
    "type": "function", "function": {
        "name": "workbench_probe_echo", "description": "Return the given text and a generated receipt. Harmless capability test.",
        "strict": True,
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"], "additionalProperties": False},
    },
}


def _image_fixture(colour: str = "red") -> str:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 32, 32, 8, 2, 0, 0, 0))
    pixel = {"red": b"\xff\x00\x00", "blue": b"\x00\x00\xff"}[colour]
    data += chunk(b"IDAT", zlib.compress((b"\x00" + pixel * 32) * 32)) + chunk(b"IEND", b"")
    return "data:image/png;base64," + base64.b64encode(data).decode()


def run_capability_probe(manager: Any, deployment_id: str, request: CapabilityProbeRequest, *, model_factory=chat_model_for_deployment) -> CapabilityEvidence:
    # Protect owned lifecycle for the entire probe, including both halves of a tool exchange.
    with manager.reserve_deployment(deployment_id):
        deployment = manager.ensure_deployment_ready(deployment_id)
        bag = deployment.settings.per_request if request.per_request is None else resolve_bag(request.per_request, PER_REQUEST_KEYS)
        record = CapabilityEvidence(
            id=new_id("probe"), deployment_id=deployment.id, capability=request.capability,
            status="inconclusive", fingerprint=setup_fingerprint(deployment, bag),
            setup=setup_identity(deployment, bag), tested_at=utc_now(),
        )
        model = None
        wire: list[dict[str, Any]] = []
        try:
            model = model_factory(deployment, per_request=bag, timeout=60.0, capture_sink=wire)
            _exercise(model, request.capability, record)
        except Exception as exc:
            # A rejected request is a failure for this exact setup. Network,
            # authentication and runtime outages remain inconclusive.
            rejected = isinstance(exc, BadRequestError)
            record.status = "failed" if rejected else "inconclusive"
            record.observations["error_type"] = type(exc).__name__
            record.observations["error"] = (str(exc)[:1500] if isinstance(exc, (HarnessError, BadRequestError)) else
                "The probe did not complete. Check endpoint health and retry this setup.")
            if rejected:
                record.observations["status_code"] = exc.status_code
                record.note = "This setup rejected the probe request. Its failure does not establish universal model incompatibility."
        finally:
            if model is not None and callable(getattr(model, "close", None)):
                try:
                    model.close()
                except Exception as exc:
                    # Cleanup failure must not erase the completed probe or its
                    # original failure. It remains an actionable, rerunnable result.
                    record.observations["observed_status"] = record.status
                    record.observations["cleanup_error_type"] = type(exc).__name__
                    record.status = "inconclusive"
                    record.note = "The request finished, but its client could not be closed cleanly. Retry this check."
        record.observations["wire_requests"] = [{
            "model": entry.get("body", {}).get("model"),
            "settings": {key: entry.get("body", {}).get(key) for key in (*bag.applied, "chat_template_kwargs") if key in entry.get("body", {})},
            "status_code": entry.get("response_status_code"),
            "reasoning_replayed": any("reasoning_content_preview" in message for message in entry.get("body", {}).get("messages", [])),
        } for entry in wire[:4]]
        if request.capability == "reasoning_replay" and record.status == "passed" and not any(item["reasoning_replayed"] for item in record.observations["wire_requests"]):
            record.status = "inconclusive"
            record.observations["supported_reasoning_representation_sent"] = False
        manager.store.put_capability_evidence(record.model_dump(mode="json"))
        return record


def _exercise(model: Any, capability: str, record: CapabilityEvidence) -> None:
    if capability == "text_stream":
        prompt = "Reply with the single word READY."
        record.inputs = {"prompt": prompt}
        text, count, usage = "", 0, None
        for chunk in model.stream([HumanMessage(content=prompt)]):
            count += 1
            text = (text + str(chunk.content or ""))[:2048]
            usage = chunk.usage_metadata or usage
            record.observations = {"chunks": count, "answer": text, "chunks_are_not_tokens": True, "usage": usage}
        record.status = "passed" if text.strip() else "failed"
        return
    if capability in {"reasoning", "reasoning_replay"}:
        prompt = "Compute 17 times 23. Think carefully, then give the number."
        record.inputs = {"prompt": prompt}
        result = model.invoke([HumanMessage(content=prompt)])
        reasoning = result.additional_kwargs.get("reasoning_content") or result.additional_kwargs.get("reasoning")
        record.observations = {"answer": str(result.content)[:2048], "separate_reasoning_returned": bool(reasoning), "reasoning_characters": len(str(reasoning)) if reasoning else 0}
        record.status = "passed" if reasoning else "inconclusive"
        if capability == "reasoning_replay":
            if not reasoning or not getattr(model, "_reasoning_replay_supported", False):
                record.status = "inconclusive"
                record.note = "Replay needs returned reasoning and the selected template's preserve-reasoning setting."
            else:
                replayed = model.invoke([HumanMessage(content=prompt), result, HumanMessage(content="Repeat only the final number from the previous answer.")])
                record.observations.update({"replay_answer": str(replayed.content)[:2048], "supported_reasoning_representation_sent": True})
                record.status = "passed" if "391" in str(replayed.content) else "failed"
        return
    if capability == "image":
        prompt = "What is the dominant colour of this image? Reply with one colour."
        colours = ("red", "blue")
        record.inputs = {"prompt": prompt, "fixtures": [f"generated-solid-{colour}-png-32x32-v2" for colour in colours]}
        samples: list[dict[str, Any]] = []
        record.observations = {"samples": samples}
        for colour in colours:
            result = model.invoke([HumanMessage(content=[{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": _image_fixture(colour)}}])])
            answer = str(result.content)
            correct = re.fullmatch(rf"\s*{colour}[.!]?\s*", answer, flags=re.IGNORECASE) is not None
            samples.append({"expected_colour": colour, "answer": answer[:2048], "correct": correct})
        record.observations["fixture_answer_correct"] = all(sample["correct"] for sample in samples)
        record.status = "passed" if record.observations["fixture_answer_correct"] else "failed"
        return
    if capability == "tool_image":
        prompt = (
            "Call workbench_probe_echo with text exactly 'image-check'. "
            "Then identify the dominant colour of the image returned by that tool. "
            "Reply with one colour."
        )
        colours = ("red", "blue")
        record.inputs = {"prompt": prompt, "tool": PROBE_TOOL,
            "fixtures": [f"generated-solid-{colour}-png-32x32-v2" for colour in colours]}
        samples: list[dict[str, Any]] = []
        record.observations = {"samples": samples}
        bound = model.bind_tools([PROBE_TOOL], tool_choice="any")
        for colour in colours:
            initial = HumanMessage(content=prompt)
            call = bound.invoke([initial])
            calls = call.tool_calls
            valid_call = (len(calls) == 1 and calls[0]["name"] == "workbench_probe_echo"
                and calls[0].get("id") and calls[0]["args"] == {"text": "image-check"}
                and not call.invalid_tool_calls)
            if not valid_call:
                samples.append({"expected_colour": colour, "valid_harmless_call": False,
                    "returned_call_names": [item.get("name") for item in calls[:8]]})
                record.status = "failed"
                return
            image_data = _image_fixture(colour).partition(",")[2]
            image_result = ToolMessage(
                content_blocks=[{"type": "image", "base64": image_data, "mime_type": "image/png"}],
                name="workbench_probe_echo",
                tool_call_id=calls[0]["id"],
            )
            # The first call is forced to exercise a real tool exchange. The
            # answer call must be free to answer rather than be forced to call
            # another tool by the probe's `tool_choice="any"` setting.
            result = model.invoke([initial, call, image_result])
            answer = str(result.content)
            correct = re.fullmatch(rf"\s*{colour}[.!]?\s*", answer, flags=re.IGNORECASE) is not None
            samples.append({"expected_colour": colour, "answer": answer[:2048],
                "valid_harmless_call": True, "tool_call_id": calls[0]["id"], "correct": correct})
        record.observations["fixture_answer_correct"] = all(sample["correct"] for sample in samples)
        record.status = "passed" if record.observations["fixture_answer_correct"] else "failed"
        return
    native = {"type": "json_schema", "json_schema": {"name": "probe_answer", "strict": True, "schema": PROBE_SCHEMA}}
    if capability == "structured_native":
        record.inputs = {"prompt": "Return answer equal to 7.", "schema": PROBE_SCHEMA}
        result = model.bind(response_format=native).invoke([HumanMessage(content=record.inputs["prompt"])])
        _record_structured(result.content, record)
        return
    if capability == "structured_tools":
        tool = {"type": "function", "function": {"name": "probe_answer", "description": "Format the answer.", "parameters": PROBE_SCHEMA}}
        record.inputs = {"prompt": "Call probe_answer with answer equal to 7.", "schema": PROBE_SCHEMA}
        result = model.bind_tools([tool], tool_choice="any").invoke([HumanMessage(content=record.inputs["prompt"])])
        calls = result.tool_calls
        valid = len(calls) == 1 and calls[0]["name"] == "probe_answer" and bool(calls[0].get("id")) and not result.invalid_tool_calls
        _record_structured(calls[0]["args"] if valid else None, record)
        return
    if capability == "structured_tools_with_tools":
        formatter = {"type": "function", "function": {"name": "probe_answer", "description": "Format the final answer.", "parameters": PROBE_SCHEMA, "strict": True}}
        prompt = "First echo 'workbench-echo-42' using workbench_probe_echo. Then use probe_answer to return answer equal to 7."
        record.inputs = {"prompt": prompt, "tool": PROBE_TOOL, "schema": PROBE_SCHEMA}
        messages = [HumanMessage(content=prompt)]
        result = model.bind_tools([PROBE_TOOL, formatter], tool_choice="any").invoke(messages)
        calls = result.tool_calls
        valid = len(calls) == 1 and calls[0]["name"] == "workbench_probe_echo" and calls[0].get("id") and calls[0]["args"] == {"text": "workbench-echo-42"} and not result.invalid_tool_calls
        if not valid:
            record.status, record.observations = "failed", {"valid_harmless_call": False,
                "returned_call_names": [c.get("name") for c in calls[:8]], "invalid_calls": len(result.invalid_tool_calls),
                "answer": str(result.content)[:512]}
            return
        final = model.bind_tools([PROBE_TOOL, formatter], tool_choice="any").invoke(messages + [result, ToolMessage(content="workbench-echo-42", tool_call_id=calls[0]["id"])])
        formats = final.tool_calls
        correct_call = len(formats) == 1 and formats[0]["name"] == "probe_answer" and bool(formats[0].get("id")) and not final.invalid_tool_calls
        _record_structured(formats[0]["args"] if correct_call else None, record)
        record.observations.update({"valid_harmless_call": True, "tool_call_id": calls[0]["id"], "round_trip_completed": bool(correct_call)})
        return
    prompt = "Call workbench_probe_echo with text exactly 'workbench-echo-42'. After the tool result, reply with answer equal to 7." if capability == "structured_with_tools" else "Call workbench_probe_echo with text exactly 'workbench-echo-42'. After its result, reply with only the receipt from the tool result."
    record.inputs = {"prompt": prompt, "tool": PROBE_TOOL}
    bound = model.bind_tools([PROBE_TOOL], **({"response_format": native} if capability == "structured_with_tools" else {}))
    messages = [HumanMessage(content=prompt)]
    call = bound.invoke(messages)
    calls = call.tool_calls
    valid = len(calls) == 1 and calls[0]["name"] == "workbench_probe_echo" and calls[0].get("id") and calls[0]["args"] == {"text": "workbench-echo-42"} and not call.invalid_tool_calls
    if not valid:
        record.status = "failed"
        record.observations = {"valid_harmless_call": False}
        return
    # Only this exact pure fixture runs. No model-provided name is dispatched as code.
    receipt = new_id("receipt")
    tool_result = json.dumps({"text": calls[0]["args"]["text"], "receipt": receipt})
    result = bound.invoke(messages + [call, ToolMessage(content=tool_result, tool_call_id=calls[0]["id"])])
    if capability == "structured_with_tools":
        _record_structured(result.content, record)
    else:
        record.observations = {"answer": str(result.content)[:2048]}
        correct = str(result.content).strip().strip('"') == receipt
        record.status = "passed" if correct and not result.tool_calls else "failed"
        record.observations["tool_result_consumed"] = correct
    record.observations.update({"valid_harmless_call": True, "tool_call_id": calls[0]["id"], "tool_result": tool_result, "round_trip_completed": not bool(result.tool_calls)})


def _record_structured(content: Any, record: CapabilityEvidence) -> None:
    try:
        value = json.loads(content) if isinstance(content, str) else content
    except (ValueError, TypeError):
        value = None
    valid = isinstance(value, dict) and set(value) == {"answer"} and type(value["answer"]) is int
    record.observations = {"schema_valid": valid, "fixture_answer_correct": valid and value["answer"] == 7, "result": value if valid else None}
    record.status = "passed" if valid else "failed"
