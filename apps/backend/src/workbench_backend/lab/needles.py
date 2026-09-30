"""Locally generated exact-answer memory tasks; no model judge."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True)
class NeedleTask:
    expected: list[str]
    needle: str
    question: str
    filler: str


def needle_task(kind: str) -> NeedleTask:
    values = [str(uuid4()) for _ in range(4 if kind == "multi_value" else 1)]
    name = "Juniper"
    if kind == "multi_key":
        filler = "\n".join(f"Record {index}: code {uuid4()}." for index in range(128)) + "\n"
        needle = f"The requested record {name} has code {values[0]}.\n"
        question = f"What is the exact code for record {name}? Reply with that code only."
    elif kind == "multi_value":
        filler = "The river passes the garden. Leaves turn toward the daylight. The path continues beside the water.\n" * 32
        needle = f"The four values assigned to {name} are: " + ", ".join(values) + ".\n"
        question = f"List all four exact values assigned to {name}. Reply with the four codes only."
    else:
        filler = "The river passes the garden. Leaves turn toward the daylight. The path continues beside the water.\n" * 32
        needle = f"The secret code is {values[0]}.\n"
        question = "What is the exact secret code? Reply with the code only."
    return NeedleTask(values, needle, question, filler)


def needle_text(task: NeedleTask, filler_characters: int, depth: int) -> str:
    filler = (task.filler * (filler_characters // len(task.filler) + 1))[:filler_characters]
    position = round(len(filler) * depth / 100)
    return ("Read the following records carefully. Recover only the requested code values.\n\n"
            + filler[:position] + "\n" + task.needle + filler[position:]
            + "\n\nQuestion: " + task.question)


def score_needle(answer: str, expected: list[str]) -> tuple[bool, list[str]]:
    missing = [value for value in expected if value not in answer]
    return not missing, missing
