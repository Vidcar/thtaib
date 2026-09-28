"""Build the thin pinned native planner; never rebuild llama.cpp/CUDA.

The release ships exported DLLs without import libraries. MSVC's own dumpbin
and lib reconstruct those link-time indexes from the exact installed DLLs.
Only the adapter is compiled. Build output belongs under the root .scratch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

PINNED_HEADERS = {
    "include/llama.h": "83d623056ca033924fd7e00db8ae9382e1900f63295e8d8bd660ee38c52666fa",
    "src/llama-ext.h": "522eed344e1765506f30da25002d92d354572951153ba67504f05d5cccdea7f6",
    "common/common.h": "7cfcc6a57122702ea35d04ed20861aef162bd94f55cfbbf9fd23ee3127fe6cb4",
    "common/fit.h": "907048c4fb974c0b405ffd4400d338c70e19f54f6983bc1ac3ec17174fcf3347",
    "tools/mtmd/mtmd.h": "b0f1ba884e8688980789f0547147d2b7330d65772ebac8f36c0dbb8ece7cf7d0",
    "ggml/include/ggml-backend.h": "46d84cb998105f871240864fd0f55446939a2fe86c5c281afa63a010fb1f65a2",
    "ggml/src/ggml-backend-impl.h": "683e0583268e91e1f50b4ffc416b6523e0cec2dfdb3984c89792bda29e32566b",
    "common/arg.h": "c9407f95ef30f8060ea9daffb24bf8e15ea1bde6d2df66389ff5c84f391e8c77",
    "common/speculative.h": "d9ed2612f3635949473c1b1c61ddcc427cb74056afa80f1d31c2c2940565ccba",
}


def _msvc_environment() -> dict[str, str]:
    vswhere = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft Visual Studio/Installer/vswhere.exe"
    installation = subprocess.check_output([str(vswhere), "-latest", "-products", "*",
        "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"], text=True).strip()
    if not installation:
        raise RuntimeError("MSVC BuildTools with the x64 compiler is required for delivery.")
    vcvars = Path(installation) / "VC/Auxiliary/Build/vcvarsall.bat"
    output = subprocess.check_output(f'cmd.exe /d /s /c ""{vcvars}" x64 >nul && set"', text=True)
    environment = {key.upper(): value for key, value in os.environ.items()}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            environment[key.upper()] = value
    return environment


def build(source: Path, runtime: Path, output: Path) -> Path:
    if sys.platform != "win32":
        raise RuntimeError("This pinned delivery build currently supports the managed Windows runtime.")
    source, runtime, output = source.resolve(), runtime.resolve(), output.resolve()
    if not (source / "include/llama.h").is_file() or not (source / "tools/mtmd/mtmd.h").is_file():
        raise RuntimeError("Supply the exact pinned llama.cpp b11045 source tree.")
    for name, expected in PINNED_HEADERS.items():
        if hashlib.sha256((source / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"Pinned native header mismatch: {name}.")
    output.mkdir(parents=True, exist_ok=True)
    environment = _msvc_environment()
    native_version = subprocess.run([str(runtime / "llama-server.exe"), "--version"],
        capture_output=True, text=True, timeout=15, check=True)
    if not re.search(r"\(build 11045, commit 2b1847030\)", native_version.stdout + native_version.stderr):
        raise RuntimeError("The installed runtime is not llama.cpp b11045 / 2b1847030.")
    native_files = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(runtime.glob("*.dll"))}
    fingerprint = hashlib.sha256(json.dumps(native_files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    (output / "planner-pin.h").write_text(f'#define WB_NATIVE_FINGERPRINT "{fingerprint}"\n', encoding="utf-8")
    dumpbin = shutil.which("dumpbin.exe", path=environment["PATH"])
    librarian = shutil.which("lib.exe", path=environment["PATH"])
    compiler = shutil.which("cl.exe", path=environment["PATH"])
    libraries = []
    for name in ("llama", "llama-common", "mtmd", "ggml", "ggml-base"):
        dll = runtime / f"{name}.dll"
        if not dll.is_file():
            raise RuntimeError(f"The installed native runtime is missing {dll.name}.")
        exports = subprocess.check_output([dumpbin, "/nologo", "/exports", str(dll)], env=environment, text=True)
        symbols = re.findall(r"^\s*\d+\s+[0-9A-F]+\s+[0-9A-F]+\s+(\S+)", exports, flags=re.MULTILINE)
        if not symbols:
            raise RuntimeError(f"No native API exports found in {dll.name}.")
        definition = output / f"{name}.def"
        definition.write_text(f"LIBRARY {dll.name}\nEXPORTS\n" + "\n".join(symbols) + "\n", encoding="utf-8")
        library = output / f"{name}.lib"
        subprocess.run([librarian, "/nologo", f"/def:{definition}", "/machine:x64", f"/out:{library}"],
            env=environment, check=True, capture_output=True, text=True)
        libraries.append(str(library))
    executable = output / "workbench-memory-planner.exe"
    includes = [source / directory for directory in ("include", "src", "common", "ggml/include", "ggml/src", "tools/mtmd", "vendor/nlohmann")]
    subprocess.run([compiler, "/nologo", "/std:c++17", "/EHsc", "/O2", "/MD", "/DGGML_SHARED", "/DLLAMA_SHARED",
        "/DMTMD_SHARED", "/DNOMINMAX", "/D_CRT_SECURE_NO_WARNINGS", f"/I{output}", *[f"/I{directory}" for directory in includes],
        str(Path(__file__).with_name("planner.cpp")), f"/Fo{output / 'planner.obj'}", f"/Fe{executable}",
        "/link", "/Brepro", *libraries], env=environment, cwd=output, check=True)
    # Test alongside its libraries, but do not overwrite any installed planner
    # until the native protocol and exact upstream fingerprint have been checked.
    environment["PATH"] = str(runtime) + os.pathsep + environment["PATH"]
    version = json.loads(subprocess.check_output([str(executable), "--workbench-version"], env=environment, text=True))
    if version.get("protocol") != 1 or version.get("native_build") != 11045 or not str(version.get("native_commit", "")).startswith("2b1847030"):
        raise RuntimeError("The adapter/native fingerprint did not match the pinned runtime.")
    (output / "version.json").write_text(json.dumps(version, indent=2) + "\n", encoding="utf-8")
    return executable


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(build(args.source, args.runtime, args.output))


if __name__ == "__main__":
    main()
