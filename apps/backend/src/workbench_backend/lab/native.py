"""Lab requests to the existing loaded llama-server, with cancellable I/O."""

from __future__ import annotations

import asyncio
import math
import threading
from typing import Any

import httpx

from workbench_backend.errors import LabError
from workbench_backend.inference.schemas import Deployment
from workbench_backend.lab.needles import NeedleTask, needle_text


class LabStopped(Exception):
    pass


class NativeLabClient:
    def __init__(self, cancel: threading.Event):
        self.cancel = cancel

    async def post(self, deployment: Deployment, route: str, body: dict[str, Any]) -> dict[str, Any]:
        if self.cancel.is_set():
            raise LabStopped()
        if not deployment.endpoint:
            raise LabError("The loaded model has no endpoint.", code="lab_endpoint_missing", status_code=409)
        base = deployment.endpoint.removesuffix("/v1").rstrip("/")
        payload = {**body, "model": deployment.router_preset_id or deployment.id}
        async with httpx.AsyncClient(timeout=httpx.Timeout(3600, connect=10), trust_env=False) as client:
            pending = asyncio.create_task(client.post(base + route, json=payload, params={"autoload": "false"}))
            try:
                while not pending.done():
                    if self.cancel.is_set():
                        pending.cancel()
                        raise LabStopped()
                    await asyncio.wait({pending}, timeout=0.05)
                response = await pending
                response.raise_for_status()
                result = response.json()
                if not isinstance(result, dict):
                    raise ValueError("Expected an object from llama-server.")
                return result
            except httpx.HTTPStatusError as exc:
                try:
                    detail = exc.response.json().get("error", {})
                    message = detail.get("message") if isinstance(detail, dict) else str(detail)
                except ValueError:
                    message = None
                raise LabError(message or f"The model returned HTTP {exc.response.status_code}.", code="lab_native_failed", status_code=502) from exc
            finally:
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)

    async def tokenize(self, deployment: Deployment, text: str, *, special: bool = False) -> list[int]:
        result = await self.post(deployment, "/tokenize", {"content": text, "add_special": special, "parse_special": True})
        tokens = result.get("tokens")
        if not isinstance(tokens, list) or not all(type(token) is int for token in tokens):
            raise LabError("The model did not return valid token IDs.", code="lab_tokenizer_invalid", status_code=502)
        return tokens

    async def performance_prompt(self, deployment: Deployment, length: int, generation: int) -> list[int]:
        capacity = deployment.server_props.n_ctx if deployment.server_props else None
        # Preserve the requested switch in the result, but leave native context
        # room for exact generation, including models without context shifting.
        actual = min(length, capacity - generation - 8) if capacity else length
        if actual < 1:
            raise LabError("Loaded context is too small for this generation length.", code="lab_context_small", status_code=422)
        text = "The river passes the garden and the path follows the water. "
        unit = await self.tokenize(deployment, text)
        if not unit:
            raise LabError("The model returned no prompt tokens.", code="lab_tokenizer_empty", status_code=502)
        return (unit * (actual // len(unit) + 1))[:actual]

    async def completion(self, deployment: Deployment, prompt: list[int], generation: int, *, exact: bool) -> dict[str, Any]:
        return await self.post(deployment, "/completion", {
            "prompt": prompt, "n_predict": generation, "ignore_eos": exact,
            "cache_prompt": False, "temperature": 0, "stream": False,
            "stop": [], "seed": 42,
        })

    async def memory_prompt(self, deployment: Deployment, task: NeedleTask, depth: int,
                            context_size: int, generation: int = 512) -> tuple[list[int], dict[str, Any]]:
        target = context_size - generation - 32
        if target < 128:
            raise LabError("Memory needs room for the question and a short answer.", code="lab_context_small", status_code=422)

        async def rendered(size: int) -> list[int]:
            text = needle_text(task, size, depth)
            formatted = await self.post(deployment, "/apply-template", {
                "messages": [{"role": "user", "content": text}],
                "add_generation_prompt": True, "chat_template_kwargs": {"enable_thinking": False},
            })
            prompt = formatted.get("prompt")
            if not isinstance(prompt, str):
                raise LabError("The model did not render its chat template.", code="lab_template_missing", status_code=502)
            return await self.tokenize(deployment, prompt)

        low, high = 0, context_size * 12
        best = await rendered(0)
        if len(best) > target:
            raise LabError("The needle and question exceed this context size.", code="lab_context_small", status_code=422)
        # Native token counts include the real chat template, question, and all
        # four values. The tail is never discarded to make a sample fit.
        while high - low > 32:
            middle = (high + low) // 2
            candidate = await rendered(middle)
            if len(candidate) <= target:
                low, best = middle, candidate
            else:
                high = middle
        return best, {"input_tokens": len(best), "reserved_answer_tokens": generation,
                      "reserved_margin_tokens": 32, "filler_characters": low,
                      "needle_before_question": True}


def timing_sample(payload: dict[str, Any], expected_generation: int) -> dict[str, Any]:
    """Names and meanings verified against llama.cpp b11045 server-task.cpp.

    tokens_cached is the final slot prompt size (server-context.cpp), not the
    configured capacity or just the reused prefix. prompt_n is processed input.
    """
    timings = payload.get("timings") or {}
    sample = {
        "prompt_tokens": payload.get("tokens_evaluated"),
        "context_tokens": payload.get("tokens_cached"),
        "generated_tokens": timings.get("predicted_n"),
        "prefill_tps": timings.get("prompt_per_second"),
        "generation_tps": timings.get("predicted_per_second"),
        "processed_prompt_tokens": timings.get("prompt_n"),
        "timings": timings,
    }
    for key in ("prompt_tokens", "context_tokens", "generated_tokens"):
        if type(sample[key]) is not int or sample[key] <= 0:
            raise LabError(f"llama-server did not report {key.replace('_', ' ')}.", code="lab_timings_missing", status_code=502)
    for key in ("prefill_tps", "generation_tps"):
        value = sample[key]
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
            raise LabError(f"llama-server did not report {key.replace('_', ' ')}.", code="lab_timings_missing", status_code=502)
    if sample["generated_tokens"] != expected_generation:
        raise LabError(f"The model generated {sample['generated_tokens']} of {expected_generation} requested tokens; this is not a complete speed sample.", code="lab_generation_short", status_code=502)
    return sample
