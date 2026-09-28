# Native allocation helper

`planner.cpp` is the protocol 1 adapter for the managed Windows llama.cpp
b11045 release (`2b1847030`). It links that runtime's exported libraries.
The adapter delegates tensor placement, fitting and buffer sizing to native
APIs. It does not read weight data or evaluate tensors.

Delivery builds use `build.py` with the exact source checkout, installed
runtime directory and an output directory under the repository `.scratch`.
MSVC BuildTools is a delivery dependency; customers do not compile the helper.
The script verifies pinned headers and the runtime version, derives import
libraries from the installed DLL exports and embeds their digest. The backend
wheel includes the build script and C++ source. `RuntimeService.install_memory_planner`
verifies the resulting executable before replacing the installed helper and
atomically updating the existing runtime manifest. An unsupported runtime
continues to work with an explicitly unavailable preview.

The helper accepts the native server's local loading arguments and writes one
JSON object. `--workbench-version` returns protocol/build/commit/library identity.
All byte fields are exact native static allocations. `speculation_bytes` is
a labelled subset of the weights/context/compute categories, so callers must
not add it twice. Projector totals include native weights and compute without
inventing an internal UI breakdown. Shared MTP weights are counted once.

`effective_context` is the shared context pool. `effective_context_per_slot`
is the native maximum capacity for one request after the server's slot and
training-capacity rules. Unified KV does not reserve that full amount for every
slot. A missing selected component yields `partial` and null totals; known
allocations remain a lower bound. Dynamic driver, operating-system, host
output-buffer and prompt-cache costs are outside the measured static totals.
Complete measurements do not promise that loading will fit.

The backend verifies the helper/library fingerprints and selected artifacts,
sanitizes ambient native controls, caps combined output, and terminates only
the helper on timeout. A preview does not use the residency lifecycle.

The exact pinned mtmd API's `no_alloc` still requests backend buffers. The
adapter temporarily substitutes metadata-only buffers inside its isolated
process while retaining native alignment, tensor sizes, placement and graph
reservation. Tensor access fails explicitly; original callbacks are restored.
This uses the pinned backend ABI and therefore requires recompilation and
native parity validation when the runtime changes.
