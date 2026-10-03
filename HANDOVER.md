# Current handover

Updated 2026-10-03. **Browser/model-input repair and Qwen trials are complete**, [PR240](https://github.com/Vidcar/thtaib/pull/240), main `f302098`. Dave authorized fixes/live trials/Full access. Preserve weights/runtimes/original setups and unrelated work.

Fixed and independently reviewed: browser startup/background false failures, stale coordinate guidance, repeated stale handoff context/false user boundaries, discovery labels/aliases/repeated descriptions, native content/artifact mixing, missing initial host OS and stale unhealthy-model banner. Authored text and executable names unchanged; no permission guard or native loop weakened. Ordinary answers append no new instruction prompt.

Evidence: [repair-browser-prompt-execution](openspec/changes/archive/2026-10-03-repair-browser-prompt-execution/verification.md). Private traces/artifacts/exports: `.scratch/prompt-uats/`. Immutable manifests separate trial phases. Backend1511 (one declared skip) +204 integration, desktop build/spec18/18, contracts and independent review pass against stable source; UI87+22 controls pass. Run affected gates through `uv run --project apps/backend python scripts/verify.py --tier acceptance --scope shared --scope spec`.

All six original prompts ran. Animation/watch/subway produced browser-checked pages; GoldenGate/Racing repeated writes and were canceled. Racing copied shortened history into a new write; no fresh-execution truncation defect proven. Skateboard lacks GLUT and ended on its chosen command timeout. Separate controls prove two settled helpers, official documentation/retained results, and native C++ compile/run5050. Generated quality/one-shot success is not certified.

Final normal launcher backend10868/Electron16756 runs rebuilt artifacts without observer; healthy unchanged Qwen profile and real READY reply verified. Native stop/start recovery and launcher compatibility pass. Nine created chats/seven projects/evaluation setup removed after private exports; clean new chat is Ready. No outstanding repair task. Preserve other active changes; seven scenario additions only keep an older delta compatible.
