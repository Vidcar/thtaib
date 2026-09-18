"""Minimal FastAPI application for the Local AI Workbench scaffold.

Provisional localhost HTTP is for smoke only. It does not select a trust
model and does not close OQ-002.
"""

from fastapi import FastAPI

from workbench_backend import __version__

PRODUCT_NAME = "Local AI Workbench"

app = FastAPI(
    title=PRODUCT_NAME,
    version=__version__,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "product": PRODUCT_NAME,
        "surface": "scaffold",
    }
