# Design

## Context

See proposal.md. The private worker publishes the Chrome context before its initial pages have records. An overlapping state read dereferences an unrecorded page; the backend interprets that observation failure as loss and terminates the owned browser. Native isolated reproductions match the user's aborted first navigation and empty worker log.

## Goals / Non-Goals

Restore reliable first navigation while the live Browser rail observes the same context. Preserve real worker-loss reporting, profile retention, takeover, scoped effects and no replay. Do not change the agent loop, impose hidden model limits, repair generated sample code manually, or claim model mistakes as application bugs.

## Decisions

- Observation joins the worker's existing startup promise before reading pages. This preserves one initialization owner and avoids publishing partial state. A global action queue or suppressed state errors would add ownership or conceal the cause.
- Background stream promises are marked handled immediately while callers that await the original promise still receive its rejection. Existing worker error metadata reaches the Browser status view, so a frame failure remains visible without falsifying a successful foreground action. Native negative controls retain direct-stream and genuine navigation failures.
- Recover a genuinely lost session through the existing Close/start boundary, retaining its profile. Reset remains a separate confirmed profile deletion; completed or uncertain actions are not replayed automatically.
- Project a pending browser handoff as marked, untrusted tool context once. Native model-response Command updates retain its message and private delivery identity only after successful generation. Failed/cancelled requests retain the pending observation for retry. Root run/revision/content identify a handoff, so a genuinely new handoff can deliver even when its page text is identical. Successful newer browser results explicitly supersede the older observation; failures and helper-local results cannot falsely establish a newer parent page. Count, dispatch and checkpoint history use identical content. No synthetic user message becomes a new task boundary.
- Include advertised presentation labels in discovery metadata and treat exact labels like exact executable-name lookups within the accepted envelope. Add precise browser URL/scroll aliases; keep executable names, schema loading limits, cursor identity and access checks unchanged. Successful discovery returns descriptions once in its structured results; actionable setup/failure notices remain.
- Use sensible defaults in the built-in core instruction, reserving ask_user for essential missing information. Preserve saved authored instructions and original prompts verbatim. Ordinary answers remain paired native tool results, with no appended instruction or tool-information prompt.
- Browser MCP tools return native content and a separate artifact. Text projection consumes only native content from that contract; it must not stringify a missing artifact as "None" or expose separate artifact data as additional model text. Existing text/image acquisition, redaction and retained-result identity remain with their current owners.
- Initial accepted context states the actual host operating system through the shared prompt owner, before platform-dependent file work. This is a fact, not a tool instruction or permission grant. Preview, accounting and root/helper composition agree; accepted snapshots remain frozen on resume. Live Racing inputs lacked the known Windows environment until shell discovery, which never occurred. Linux build instructions were observed, but their causal relationship to the omitted fact is not established.
- A retained conversation health message is an older observation. Suppress only its generic unhealthy notice when the diagnostic, conversation binding and selected deployment all match, and the current catalogue confirms running/healthy. Preserve missing, unreachable, unknown/false health and other-deployment errors; actual readiness and Send guards remain unchanged. This restores existing model-health truthfulness, without adding a new lifecycle contract.
- Keep the six prompt texts unchanged and use separate disposable project-bound conversations. A reusable evaluation setup selects available tools, four existing reviewer/validator/research helpers, Full access and appropriate desktop authority. The model chooses tools and filenames. Required host-command first-use cards are answered by the test operator under Dave's authorization, without weakening runtime policy.
- Run the existing preferred Qwen setup first, sequentially because the native engine has one inference slot. Record actual frozen selections, errors, tool outcomes and output bytes. Missing watch photo/corrupted bridge prose and native compiler availability are distinct from application faults. Focus on correct model-input content/timing and faithful tool results, with proportionate browser/native checks. A launcher-only private observer captures exact outgoing serialized request bytes without altering transport; remove it from final local delivery. A completed run alone does not establish functional output quality.

## Risks / Trade-offs

- Waiting on startup must propagate real launch failure and settle cancellation rather than hang observation; bounded native regression and loss/cleanup tests cover these paths.
- The installed worker must match reviewed source; explicitly refresh the pinned worker and verify source/process/build identity before live trials.
- Model loops or weak generated code may still fail prompt acceptance; retain evidence, use a bounded diagnostic stopping decision, and do not add heuristic runtime caps to obtain success.

## Migration Plan

No record migration. Freeze source, run affected native/default/integration checks and independent review, refresh the existing worker/application, execute all prompt cases, then deliver reviewed Git changes and the result matrix. Existing profiles and model weights remain intact; test records are removed after evidence is retained.
