"""Select CI tiers once. Unknown revisions/events run all checks, never skip them."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

TIERS = ("backend", "desktop", "contracts", "model")


def select(paths: list[str]) -> dict[str, bool]:
    result = dict.fromkeys(TIERS, False)
    for path in paths:
        if path.startswith(".github/"):
            return dict.fromkeys(TIERS, True)
        if path == "scripts/generate_shared_contracts.py":
            result["contracts"] = True
        if path.startswith("scripts/") and path not in ("scripts/check_specs.py", "scripts/generate_shared_contracts.py"):
            result["backend"] = result["desktop"] = True
        if path.startswith("apps/backend/"):
            result["backend"] = True
            # Schema imports cross module boundaries; keep this conservative.
            result["contracts"] = True
        if path.startswith("apps/desktop/"):
            result["desktop"] = True
        if path.startswith(("apps/backend/src/", "apps/backend/tests_integration/")) or path in (
            "apps/backend/pyproject.toml", "apps/backend/uv.lock", "apps/backend/tests/support.py",
            "apps/backend/tests/__init__.py",
        ):
            result["model"] = True
        if path.startswith("apps/desktop/src/generated/") or path in (
            "apps/desktop/package.json", "apps/desktop/pnpm-lock.yaml",
        ):
            result["contracts"] = True
    return result


def changed_paths(event_name: str, event: dict, sha: str) -> list[str] | None:
    if event_name == "pull_request":
        base = event.get("pull_request", {}).get("base", {}).get("sha")
        tip = event.get("pull_request", {}).get("head", {}).get("sha")
    elif event_name == "push":
        base, tip = event.get("before"), sha
    else:
        return None
    if not base or not tip or set(base) == {"0"}:
        return None
    try:
        return subprocess.check_output(
            ["git", "diff", "--name-only", "-z", base, tip], text=True,
        ).rstrip("\0").split("\0")
    except (OSError, subprocess.CalledProcessError):
        return None


def main() -> None:
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    paths = changed_paths(os.environ["GITHUB_EVENT_NAME"], event, os.environ["GITHUB_SHA"])
    selected = dict.fromkeys(TIERS, True) if paths is None else select(paths)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        for tier, enabled in selected.items():
            print(f"{tier}={str(enabled).lower()}", file=output)
    print(json.dumps(selected))


if __name__ == "__main__":
    main()
