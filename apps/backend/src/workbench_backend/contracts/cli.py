"""Generate and freshness-check shared OpenAPI → TypeScript artifacts."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from workbench_backend.contracts.export import (
    sha256_bytes,
    write_manifest,
    write_python_artifacts,
)
from workbench_backend.contracts.freshness import compare_generated_trees
from workbench_backend.contracts.paths import (
    DESKTOP_TYPES_RELATIVE,
    OPENAPI_RELATIVE,
    repo_root_from,
)

OPENAPI_TYPESCRIPT_BIN = "openapi-typescript"
OPENAPI_TYPESCRIPT_CLI = Path("node_modules") / "openapi-typescript" / "bin" / "cli.js"


def resolve_executable(name: str) -> str | None:
    """Resolve a PATH executable, including Windows .cmd/.exe shims."""
    found = shutil.which(name)
    if found:
        return found
    if os.name == "nt":
        for suffix in (".cmd", ".exe", ".bat"):
            found = shutil.which(f"{name}{suffix}")
            if found:
                return found
    return None


def desktop_openapi_typescript_pin(repo_root: Path) -> str:
    package = json.loads((repo_root / "apps/desktop/package.json").read_text(encoding="utf-8"))
    version = package.get("devDependencies", {}).get("openapi-typescript")
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError("apps/desktop/package.json must pin openapi-typescript")
    return version


def openapi_typescript_command(output_root: Path, *, pnpm_dir: Path) -> list[str]:
    """Build the OpenAPI→TS argv.

    Windows ``CreateProcess`` (used by ``subprocess`` without a shell) does not
    resolve ``pnpm`` / ``pnpm.cmd``. Invoke the pinned package through ``node``
    and its ``bin/cli.js`` so both OSes use the same installed 7.13.0 bits.
    """
    output = output_root / DESKTOP_TYPES_RELATIVE
    cli_js = pnpm_dir / OPENAPI_TYPESCRIPT_CLI
    node = resolve_executable("node")
    args = [
        str(output_root / OPENAPI_RELATIVE),
        "-o",
        str(output),
        "--root-types",
    ]
    if node and cli_js.is_file():
        return [node, str(cli_js), *args]
    pnpm = resolve_executable("pnpm")
    if pnpm:
        return [pnpm, "--dir", str(pnpm_dir), "exec", OPENAPI_TYPESCRIPT_BIN, *args]
    raise RuntimeError(
        "cannot run openapi-typescript: node + "
        f"{OPENAPI_TYPESCRIPT_CLI.as_posix()} or pnpm must be available "
        "(run `pnpm install` in apps/desktop)"
    )


def run_openapi_typescript(output_root: Path, *, pnpm_dir: Path) -> None:
    output = output_root / DESKTOP_TYPES_RELATIVE
    output.parent.mkdir(parents=True, exist_ok=True)
    if not (pnpm_dir / "node_modules").is_dir():
        raise RuntimeError(
            "apps/desktop/node_modules is missing; run `pnpm install` in apps/desktop"
        )
    command = openapi_typescript_command(output_root, pnpm_dir=pnpm_dir)
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        sys.stderr.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        raise RuntimeError("openapi-typescript failed")
    text = output.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not text.endswith("\n"):
        text += "\n"
    output.write_text(text, encoding="utf-8", newline="\n")


def generate_tree(
    output_root: Path,
    *,
    pin_root: Path,
    pnpm_dir: Path,
) -> None:
    pin = desktop_openapi_typescript_pin(pin_root)
    artifacts = write_python_artifacts(output_root)
    run_openapi_typescript(output_root, pnpm_dir=pnpm_dir)
    ts_bytes = (output_root / DESKTOP_TYPES_RELATIVE).read_bytes()
    digests = {relative: sha256_bytes(payload) for relative, payload in artifacts.items()}
    digests[DESKTOP_TYPES_RELATIVE] = sha256_bytes(ts_bytes)
    write_manifest(output_root, file_digests=digests, openapi_typescript=pin)


def generate(repo_root: Path) -> int:
    generate_tree(repo_root, pin_root=repo_root, pnpm_dir=repo_root / "apps/desktop")
    print("Generated shared-contract OpenAPI, JSON Schema, and TypeScript types.")
    return 0


def check(repo_root: Path) -> int:
    with tempfile.TemporaryDirectory(prefix="shared-contracts-") as tmp:
        expected_root = Path(tmp) / "repo"
        generate_tree(
            expected_root,
            pin_root=repo_root,
            pnpm_dir=repo_root / "apps/desktop",
        )
        errors = compare_generated_trees(expected_root, repo_root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print("FAILED: shared-contract generated outputs are stale.", file=sys.stderr)
        return 1
    print("PASS: shared-contract generated outputs match the committed tree.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Regenerate into a temp tree and fail if committed outputs drifted.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repository root (defaults to auto-detect).",
    )
    args = parser.parse_args(argv)
    repo_root = args.root.resolve() if args.root else repo_root_from(Path(__file__).resolve())
    if args.check:
        return check(repo_root)
    return generate(repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
