"""Domain errors. These are not a second execution owner."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class WorkbenchError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        status_code: int = 400,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class ManagerError(WorkbenchError):
    """Model-manager domain error."""


class HarnessError(WorkbenchError):
    """Embedded Deep Agents harness domain error."""


class LabError(WorkbenchError):
    """Lab case/snapshot/evaluation domain error. Not a second agent loop."""


class KnowledgeError(WorkbenchError):
    """Durable knowledge store error. Not a retrieval/RAG product."""


class ChatError(WorkbenchError):
    """Chat surface error. Chat is not a second agent loop."""


def workbench_error_handler(_request: Request, exc: WorkbenchError) -> JSONResponse:
    content: dict[str, object] = {"error": exc.message, "code": exc.code}
    content.update(exc.details)
    return JSONResponse(
        status_code=exc.status_code,
        content=content,
    )


def manager_error_handler(request: Request, exc: ManagerError) -> JSONResponse:
    return workbench_error_handler(request, exc)
