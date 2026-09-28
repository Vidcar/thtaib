"""Isolation and fingerprint regressions for the bounded native subprocess."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from workbench_backend.errors import ManagerError
from workbench_backend.inference.hashes import sha256_file
from workbench_backend.inference.memory_estimates import _bounded_native
from workbench_backend.inference.native_memory import native_fingerprint, planner_manifest_fields, preview_environment, require_planner
from workbench_backend.inference.runtime import RuntimeService
from workbench_backend.inference.schemas import RuntimeManifest
from workbench_backend.inference.store import RecordStore
from workbench_backend.paths import WorkbenchPaths


class NativeMemoryPlannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ("llama.dll", "llama-common.dll", "mtmd.dll", "ggml.dll", "ggml-base.dll", "ggml-cuda.dll"):
            (self.root/name).write_bytes(name.encode())
        self.helper = self.root/"workbench-memory-planner.exe"
        self.helper.write_bytes(b"fixture-helper")
        self.manifest = RuntimeManifest(platform="win-x64", flavor="cuda-13.4", release_tag="b11045",
            install_dir=str(self.root), executable=str(self.root/"llama-server.exe"), memory_planner_path=str(self.helper),
            memory_planner_protocol=1, memory_planner_sha256=sha256_file(self.helper),
            memory_planner_native_fingerprint=native_fingerprint(self.root))

    def test_exact_helper_and_native_libraries_are_required(self):
        self.assertEqual(require_planner(self.manifest), self.helper)
        (self.root/"ggml-cuda.dll").write_bytes(b"changed-compiler-or-backend")
        with self.assertRaisesRegex(ValueError, "libraries changed"):
            require_planner(self.manifest)

    def test_missing_changed_or_outside_helper_does_not_execute(self):
        for key, value in (("memory_planner_protocol", 2), ("memory_planner_sha256", "wrong"),
                           ("release_tag", "unrelated"), ("memory_planner_path", str(self.root/'missing.exe'))):
            with self.subTest(key=key), self.assertRaises(ValueError):
                require_planner(self.manifest.model_copy(update={key:value}))

    def test_ambient_native_args_backends_and_tokens_are_removed(self):
        with patch.dict(os.environ, {"LLAMA_ARG_CTX_SIZE":"800000", "GGML_BACKEND_PATH":"outside",
                "GGML_CUDA_DISABLE_GRAPHS":"1", "MTMD_DEBUG_EMBEDDINGS":"outside", "HF_TOKEN":"fixture-private", "CUDA_VISIBLE_DEVICES":"0"}):
            env = preview_environment()
            self.assertNotIn("LLAMA_ARG_CTX_SIZE",env)
            self.assertNotIn("GGML_BACKEND_PATH",env)
            self.assertNotIn("HF_TOKEN",env)
            self.assertNotIn("MTMD_DEBUG_EMBEDDINGS",env)
            self.assertEqual(env["CUDA_VISIBLE_DEVICES"], "0")

    def test_subprocess_receives_sanitized_environment_and_utf8_output(self):
        with patch.dict(os.environ, {"LLAMA_ARG_CTX_SIZE":"800000"}):
            output = _bounded_native([sys.executable, "-c", "import os; print(os.environ.get('LLAMA_ARG_CTX_SIZE', 'clean'))"])
        self.assertEqual(output.strip(), "clean")

    def test_timeout_kills_only_the_owned_preview_process(self):
        with self.assertRaisesRegex(ValueError, "time budget"):
            _bounded_native([sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.1)

    def test_combined_output_cap_rejects_stdout_and_stderr_flood(self):
        with patch("workbench_backend.inference.memory_estimates.MAX_NATIVE_OUTPUT", 1024), \
                self.assertRaisesRegex(ValueError, "unavailable"):
            _bounded_native([sys.executable, "-c", "import sys; sys.stdout.write('x'*900); sys.stderr.write('y'*900)"])

    def test_verified_protocol_records_exact_path_digest_and_native_identity(self):
        version = {"protocol":1,"native_build":11045,"native_commit":"2b1847030",
                   "native_fingerprint":native_fingerprint(self.root)}
        result = subprocess.CompletedProcess([],0,stdout=json.dumps(version),stderr="")
        with patch("workbench_backend.inference.native_memory.subprocess.run",return_value=result):
            fields = planner_manifest_fields(self.helper,self.root)
        self.assertEqual(fields["memory_planner_path"],str(self.helper))
        self.assertEqual(fields["memory_planner_sha256"],sha256_file(self.helper))
        version["native_fingerprint"] = "wrong"
        result.stdout = json.dumps(version)
        with patch("workbench_backend.inference.native_memory.subprocess.run",return_value=result), self.assertRaises(ValueError):
            planner_manifest_fields(self.helper,self.root)

    def test_failed_helper_delivery_preserves_previous_helper_and_manifest(self):
        paths = WorkbenchPaths(self.root/'data').ensure()
        store = RecordStore(paths)
        store.write_runtime_manifest(self.manifest)
        service = RuntimeService(paths,store)
        replacement = self.root/'unverified.exe'
        replacement.write_bytes(b"not-compatible")
        with patch("workbench_backend.inference.runtime.planner_manifest_fields",side_effect=ValueError("wrong ABI")), \
                self.assertRaises(ManagerError):
            service.install_memory_planner(replacement)
        self.assertEqual(self.helper.read_bytes(),b"fixture-helper")
        self.assertEqual(store.read_runtime_manifest(),self.manifest)
        self.assertFalse(self.root.joinpath('workbench-memory-planner.candidate.exe').exists())


if __name__ == "__main__":
    unittest.main()
