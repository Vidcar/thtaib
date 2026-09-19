"""Domain errors. These are not a second execution owner."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class WorkbenchError(Exception):
    def __init__(self, message: str, *, code: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class ManagerError(WorkbenchError):
    """Model-manager domain error."""


class HarnessError(WorkbenchError):
    """Embedded Deep Agents harness domain error."""


def workbench_error_handler(_request: Request, exc: WorkbenchError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message, "code": exc.code},
    )


def manager_error_handler(request: Request, exc: ManagerError) -> JSONResponse:
    return workbench_error_handler(request, exc)
