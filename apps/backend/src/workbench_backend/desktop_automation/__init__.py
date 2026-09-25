"""Optional, conversation-scoped Windows UI automation."""

from workbench_backend.desktop_automation.runtime import WinAppCliRuntime
from workbench_backend.desktop_automation.service import (
    DESKTOP_TOOL_NAMES,
    DesktopAccessScope,
    DesktopAutomationError,
    DesktopAutomationService,
    DesktopCapture,
    DesktopWindow,
    WindowIdentity,
)

__all__ = [
    "DESKTOP_TOOL_NAMES",
    "DesktopAccessScope",
    "DesktopAutomationError",
    "DesktopAutomationService",
    "DesktopCapture",
    "DesktopWindow",
    "WinAppCliRuntime",
    "WindowIdentity",
]
