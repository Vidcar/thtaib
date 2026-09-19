"""Assets for the real-model smoke tier: pinned llama-server + tiny GGUF.

The llama.cpp release is the one the product already pins
(``LLAMA_CPP_RELEASE_TAG``); this module only selects the Linux x64 CPU
asset of that same release. The model is a tiny instruct GGUF pinned to a
Hugging Face revision. Both are cached under ``.scratch/real-model-smoke``
(gitignored) unless ``WORKBENCH_SMOKE_ASSETS_DIR`` overrides it.

Tiny models prove plumbing (tool call round-trip, thread continuity,
applied settings), not model capability. Capability UAT stays on David-PC
with the preferred capability UAT model. Weights are never committed.

Run ``python -m tests_integration.assets`` to fetch, ``--cache-key`` to
print a cache key derived from the pins, ``--show`` to print resolved paths.
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path

import httpx
from huggingface_hub import hf_hub_download

from workbench_backend.inference.hashes import sha256_file
from workbench_backend.inference.runtime import LLAMA_CPP_RELEASE_TAG

LINUX_X64_CPU_ASSET = f"llama-{LLAMA_CPP_RELEASE_TAG}-bin-ubuntu-x64.tar.gz"
LINUX_X64_CPU_URL = (
    "https://github.com/ggml-org/llama.cpp/releases/download/"
    f"{LLAMA_CPP_RELEASE_TAG}/{LINUX_X64_CPU_ASSET}"
)
# A release tag fixes the name, not the bytes (assets can be re-uploaded).
# Digest of the asset as published on 2026-09-19 (16,865,765 bytes).
LINUX_X64_CPU_SHA256 = "4226ee2f241b38a08f63c93929b1064e425af8209628abfa644d0bb7ed768ce5"

SMOKE_MODEL_REPO = "Qwen/Qwen2.5-0.5B-Instruct-GGUF"
SMOKE_MODEL_FILE = "qwen2.5-0.5b-instruct-q4_k_m.gguf"
SMOKE_MODEL_REVISION = "9217f5db79a29953eb74d5343926648285ec7e67"

ASSETS_DIR_ENV = "WORKBENCH_SMOKE_ASSETS_DIR"
LLAMA_SERVER_ENV = "WORKBENCH_SMOKE_LLAMA_SERVER"
MODEL_PATH_ENV = "WORKBENCH_SMOKE_MODEL_PATH"

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ASSETS_DIR = _REPO_ROOT / ".scratch" / "real-model-smoke"


@dataclass(frozen=True)
class SmokeAssets:
    llama_server: Path
    model: Path


class SmokeAssetsUnavailable(RuntimeError):
    """Assets are missing or this platform has no pinned CPU asset."""


def assets_dir() -> Path:
    override = os.environ.get(ASSETS_DIR_ENV)
    return Path(override).expanduser().resolve() if override else DEFAULT_ASSETS_DIR


def cache_key() -> str:
    """Key for CI caches: changes whenever a pin changes."""

    return (
        f"real-model-smoke-{platform.system().lower()}-{platform.machine().lower()}-"
        f"{LLAMA_CPP_RELEASE_TAG}-{SMOKE_MODEL_REVISION[:12]}-{Path(SMOKE_MODEL_FILE).stem}"
    )


def linux_x64_supported() -> bool:
    return platform.system() == "Linux" and platform.machine() in {"x86_64", "AMD64"}


def runtime_dir(base: Path | None = None) -> Path:
    return (base or assets_dir()) / "llama.cpp" / LLAMA_CPP_RELEASE_TAG


def hf_cache_dir(base: Path | None = None) -> Path:
    return (base or assets_dir()) / "hf"


def _bundled_llama_server(base: Path | None = None) -> Path | None:
    root = runtime_dir(base)
    if not root.is_dir():
        return None
    for candidate in root.rglob("llama-server"):
        if candidate.is_file():
            return candidate
    return None


def _cached_model(base: Path | None = None) -> Path | None:
    snapshot = (
        hf_cache_dir(base)
        / f"models--{SMOKE_MODEL_REPO.replace('/', '--')}"
        / "snapshots"
        / SMOKE_MODEL_REVISION
        / SMOKE_MODEL_FILE
    )
    return snapshot if snapshot.is_file() else None


def resolve_assets(base: Path | None = None) -> SmokeAssets:
    """Resolve already-present assets. Never downloads."""

    server_override = os.environ.get(LLAMA_SERVER_ENV)
    model_override = os.environ.get(MODEL_PATH_ENV)
    server = Path(server_override).expanduser() if server_override else _bundled_llama_server(base)
    model = Path(model_override).expanduser() if model_override else _cached_model(base)
    problems: list[str] = []
    if server is None or not server.is_file():
        problems.append(
            f"llama-server for {LLAMA_CPP_RELEASE_TAG} not found under {runtime_dir(base)} "
            f"(or set {LLAMA_SERVER_ENV})"
        )
    if model is None or not model.is_file():
        problems.append(
            f"{SMOKE_MODEL_REPO}@{SMOKE_MODEL_REVISION[:12]} {SMOKE_MODEL_FILE} not found under "
            f"{hf_cache_dir(base)} (or set {MODEL_PATH_ENV})"
        )
    if problems:
        raise SmokeAssetsUnavailable(
            "; ".join(problems) + ". Fetch with: uv run python -m tests_integration.assets"
        )
    assert server is not None and model is not None
    return SmokeAssets(llama_server=server.resolve(), model=model.absolute())


def fetch_llama_server(base: Path | None = None) -> Path:
    existing = _bundled_llama_server(base)
    if existing is not None:
        return existing
    if not linux_x64_supported():
        raise SmokeAssetsUnavailable(
            f"No pinned CPU asset is selected for {platform.system()}/{platform.machine()}; "
            f"set {LLAMA_SERVER_ENV} to a llama-server binary of release {LLAMA_CPP_RELEASE_TAG}."
        )
    target = runtime_dir(base)
    target.mkdir(parents=True, exist_ok=True)
    archive = target / LINUX_X64_CPU_ASSET
    with httpx.stream("GET", LINUX_X64_CPU_URL, follow_redirects=True, timeout=120.0) as response:
        response.raise_for_status()
        with archive.open("wb") as handle:
            for chunk in response.iter_bytes():
                handle.write(chunk)
    actual = sha256_file(archive)
    if actual != LINUX_X64_CPU_SHA256:
        archive.unlink()
        raise SmokeAssetsUnavailable(
            f"{LINUX_X64_CPU_ASSET} sha256 mismatch: expected {LINUX_X64_CPU_SHA256}, got {actual}. "
            "The release asset changed since it was pinned; not extracting it."
        )
    with tarfile.open(archive) as tar:
        tar.extractall(target, filter="data")
    archive.unlink()
    server = _bundled_llama_server(base)
    if server is None:
        raise SmokeAssetsUnavailable(f"{LINUX_X64_CPU_ASSET} did not contain llama-server")
    server.chmod(server.stat().st_mode | 0o111)
    return server


def fetch_model(base: Path | None = None) -> Path:
    existing = _cached_model(base)
    if existing is not None:
        return existing
    path = hf_hub_download(
        SMOKE_MODEL_REPO,
        SMOKE_MODEL_FILE,
        revision=SMOKE_MODEL_REVISION,
        cache_dir=str(hf_cache_dir(base)),
    )
    return Path(path)


def fetch_assets(base: Path | None = None) -> SmokeAssets:
    server = fetch_llama_server(base)
    model = fetch_model(base)
    return SmokeAssets(llama_server=server.resolve(), model=model.absolute())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch or inspect real-model smoke assets")
    parser.add_argument("--cache-key", action="store_true", help="print the pin-derived cache key")
    parser.add_argument("--show", action="store_true", help="print resolved asset paths without downloading")
    args = parser.parse_args(argv)
    if args.cache_key:
        print(cache_key())
        return 0
    try:
        assets = resolve_assets() if args.show else fetch_assets()
    except SmokeAssetsUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"llama-server: {assets.llama_server}")
    print(f"model: {assets.model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
