"""Durable, local Lab records. Separate from case replay and Chat."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LabConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    configuration_id: str
    startup: dict[str, Any] = Field(default_factory=dict)
    concurrent_requests: int = Field(default=1, ge=1, le=64)


class LabLeaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_ids: list[str] = Field(default_factory=list, max_length=1000)


class LabRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["performance", "memory", "challenge"]
    mode: Literal["single", "concurrent"] = "single"
    configurations: list[LabConfiguration] = Field(min_length=1, max_length=16)
    prompt_lengths: list[int] = Field(default_factory=list, max_length=32)
    generation_length: Literal[256, 512, 1024] = 512
    memory_test: Literal["uuid", "multi_key", "multi_value"] = "uuid"
    depths: list[Literal[0, 25, 50, 75, 100]] = Field(default_factory=lambda: [0, 25, 50, 75, 100])
    challenge_id: str | None = None

    @model_validator(mode="after")
    def validate_shape(self):
        if (self.mode == "single" or self.kind != "performance") and (
            len(self.configurations) != 1 or self.configurations[0].concurrent_requests != 1
        ):
            raise ValueError("Choose one configuration and one request for this test.")
        if self.kind == "performance" and not self.prompt_lengths:
            raise ValueError("Choose at least one prompt length.")
        if any(type(value) is not int or value <= 0 for value in self.prompt_lengths):
            raise ValueError("Prompt lengths must be positive whole numbers.")
        if self.kind == "memory" and not self.depths:
            raise ValueError("Choose at least one depth.")
        if self.kind == "challenge" and not self.challenge_id:
            raise ValueError("Choose a challenge.")
        self.prompt_lengths = sorted(set(self.prompt_lengths))
        self.depths = sorted(set(self.depths))
        return self


class ChallengeWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    task: str = Field(min_length=1, max_length=16000)
    required_text: str = Field(default="", max_length=4000)
    required_tool: Literal["echo", "time_now"] | None = None

    @model_validator(mode="after")
    def meaningful(self):
        self.name = self.name.strip()
        self.task = self.task.strip()
        self.required_text = self.required_text.strip()
        if not self.name or not self.task or not (self.required_text or self.required_tool):
            raise ValueError("A challenge needs a name, task, and required text or tool.")
        return self


class LabChallenge(ChallengeWrite):
    id: str
    created_at: str
    updated_at: str


class LabSeries(BaseModel):
    id: str
    configuration_id: str
    name: str
    deployment_id: str
    startup: dict[str, Any] = Field(default_factory=dict)
    context_size: int | None = None
    requested_context_size: int | None = None
    context_adjusted: bool = False
    concurrent_requests: int = 1
    benchmark_owned: bool = False


class LabMeasurement(BaseModel):
    id: str
    series_id: str
    requested_prompt_length: int | None = None
    prompt_tokens: int | None = None
    context_tokens: int | None = None
    generated_tokens: int | None = None
    prefill_tps: float | None = None
    generation_tps: float | None = None
    depth: int | None = None
    found: bool | None = None
    answer: str | None = None
    expected: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    tool_calls: list[str] = Field(default_factory=list)
    passed: bool | None = None
    error: str | None = None
    samples: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str


class LabRun(BaseModel):
    id: str
    kind: Literal["performance", "memory", "challenge"]
    status: Literal["queued", "running", "stopping", "completed", "stopped", "failed"] = "queued"
    created_at: str
    updated_at: str
    request: LabRunRequest
    series: list[LabSeries] = Field(default_factory=list)
    measurements: list[LabMeasurement] = Field(default_factory=list)
    current: dict[str, Any] | None = None
    error: str | None = None
    challenge_snapshot: LabChallenge | None = None
    agent_run_id: str | None = None
