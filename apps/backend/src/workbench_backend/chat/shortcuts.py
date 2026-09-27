"""Inert, versioned prompts in the existing Chat capability catalogue."""
from workbench_backend.errors import ChatError

SHORTCUTS = (
    {"id": "summarize", "version": "1", "name": "Summarize", "description": "Summarize the selected context.",
     "prompt": "Summarize the user's selected context, preserving its main facts and uncertainty. Use only the current authorized tools."},
    {"id": "explain", "version": "1", "name": "Explain", "description": "Explain the selected context.",
     "prompt": "Explain the user's selected context clearly, using concrete examples where helpful. Use only the current authorized tools."},
    {"id": "review", "version": "1", "name": "Review", "description": "Review the selected context and suggest improvements.",
     "prompt": "Review the user's selected context for issues and suggest improvements. This request does not authorize changes or additional access."},
)

def resolve_shortcuts(ids: list[str]) -> list[dict[str, str]]:
    catalogue = {item["id"]: item for item in SHORTCUTS}
    unknown = sorted(set(ids) - catalogue.keys())
    if unknown:
        raise ChatError("A selected task shortcut is unavailable.", code="shortcut_missing", status_code=409, details={"ids": unknown})
    return [dict(catalogue[ident]) for ident in dict.fromkeys(ids)]
