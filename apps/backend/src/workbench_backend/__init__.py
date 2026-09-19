"""Local AI Workbench backend package."""

from __future__ import annotations

import os

# Tracing is optional and not the product home (OQ-012). Disable unless set.
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
os.environ.setdefault("LANGSMITH_TRACING", "false")

__all__ = ["__version__", "PRODUCT_NAME"]

__version__ = "0.1.0"
PRODUCT_NAME = "Local AI Workbench"
