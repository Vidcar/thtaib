"""Application-owned run linkage. Checkpoint ids are references only."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RelatedFile(BaseModel):
    """A file the application associates with a run. Not a checkpointer row."""

    path: str
    kind: Literal["project_root", "written_file", "artifact"]


class RunLinkage(BaseModel):
    """Follow a persisted run to checkpoint ids and related files (STATE-001)."""

    run_id: str
    thread_id: str | None = None
    checkpoint_ids: list[str] = Field(default_factory=list)
    related_files: list[RelatedFile] = Field(default_factory=list)
    note: str = (
        "Application records link run → checkpoint id(s) → files. "
        "LangGraph owns checkpoint bytes. This is not an exactly-once claim."
    )
