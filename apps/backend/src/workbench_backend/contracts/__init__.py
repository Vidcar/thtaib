"""Canonical shared contracts for desktop↔backend types (CTT-001)."""

from workbench_backend.contracts.auth import (
    WORKBENCH_LOCAL_BIND,
    WORKBENCH_LOCAL_TOKEN_HEADER,
    WORKBENCH_LOCAL_TOKEN_SCHEME,
    LocalSessionTrustContract,
)
from workbench_backend.contracts.lifecycle import (
    LIVE_RUN_LIFECYCLE_STATUSES,
    TERMINAL_RUN_LIFECYCLE_STATUSES,
    RunLifecycleContract,
    RunLifecycleStatus,
    is_run_lifecycle_live,
)
from workbench_backend.contracts.schema_app import create_shared_contract_app

__all__ = [
    "LIVE_RUN_LIFECYCLE_STATUSES",
    "TERMINAL_RUN_LIFECYCLE_STATUSES",
    "WORKBENCH_LOCAL_BIND",
    "WORKBENCH_LOCAL_TOKEN_HEADER",
    "WORKBENCH_LOCAL_TOKEN_SCHEME",
    "LocalSessionTrustContract",
    "RunLifecycleContract",
    "RunLifecycleStatus",
    "create_shared_contract_app",
    "is_run_lifecycle_live",
]
