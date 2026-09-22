# Design

## Context

See proposal.md. Baseline is Packet 03 commit 1bb91af on a new `codex/compact-workbench` branch. Existing code already has history deletion, SDK projections, model options and help, but important behavior is hidden or incorrectly projected. Dave supplied ChatGPT references and rejected large text, duplicate branding, prose-heavy surfaces and arrow expanders. His request authorizes implementation and defect repair; this change proceeds through planning into apply without an additional permission round.

## Goals / Non-Goals

Use the existing application, persistence and execution owners; bring all currently exposed surfaces into one compact design. Preserve model weights, project outputs, permissions, recovery and active-run ownership. Do not implement the unrelated future packet feature sets or claim outstanding Packet 03 human acceptance.

## Decisions

- Neutral charcoal/white tokens, 13px base UI, 14px conversation body, 28-32px compact actions, thin borders and modest rounding. Shared icon controls carry accessible names and help. Optional prose moves to help/popovers; errors and required consequences stay visible.
- Keep existing React surfaces and component boundaries, consolidate shell/navigation patterns and reusable resizing/help controls. Retain collapsed icon navigation and compact history; browser-local layout preferences contain no execution authority.
- Join SDK and retained tool projections by stable call ID inside presentation. Consume the pinned SDK's `output` and `error` fields. Reasoning precedes answer; no new event transport or second tool loop.
- Reuse existing deletion/lifecycle APIs, adding missing cache/record cleanup at the owner boundary. Reconcile successful archive/delete locally immediately and protect against stale list responses.
- Persist inspection evidence in the existing application store keyed by file identity/schema. Keep metadata, integrity validation and actual runtime loading distinct. Derive options from model/runtime evidence rather than model display-name guesses.
- Use current configuration descriptors/probes for model controls and display actual launch/observed values in compact readouts. MTP is a normal performance setting, not an advanced JSON-only flag.

## Risks / Trade-offs

- Dense controls can harm usability: preserve focus states, semantic labels, adequate hit areas, scrolling and keyboard resizing; inspect full/half-screen Windows views.
- Caches can become stale: key by resolved files, size/high-resolution timestamps and schema; explicit refresh always available; integrity-sensitive paths remain strict.
- Live and retained events can duplicate: reproduce with installed SDK shapes and regression test transition identity/order.
- Existing Packet 03 PR is unmerged: keep its status and review limitations separate, preserve its tests and coordinate final delivery without fabricating acceptance.

## Validation

Reproduce reported defects before fixing. Run focused component/backend checks, complete default/integration backend suites, desktop build, generated contracts and strict OpenSpec validation. Inspect actual Windows surfaces and exercise archive/delete with isolated data, model selection/refresh/probe and real reasoning/tool output where runtime permits. Record actual outcomes here and in the PR, with concise continuity in HANDOVER.md.

## Executed evidence (2026-09-22)

- Backend default 508 and integration 153 passed after lifecycle, cache, adapter and reload fixes. Subsequent loaded-startup validation and accepted-alias descriptor changes passed focused resolver/configuration checks (18/19). Full final desktop build passed all component, SDK, queue, retained-file, ownership, model, Electron-trust and production stages. Generated contracts, strict OpenSpec 16/16 and diff checks passed.
- Native Windows inspection covered Chat, Models, Library, Knowledge, Workflows, Lab, Attention and Settings. Light and dark rendering, navigation collapse/drag/reset, full and 799px window layouts, split/docked/expanded Files with visible Send, actual model-specific controls, and the compact deletion dialog were inspected. Keyboard resizing, persistence, tooltip positioning/focus/hover/escape and 16 inspector size/state combinations have component/real-Electron geometry coverage.
- A disposable project chat executed actual `read_file` with separate reasoning and answer. Named tool arguments/output were visible; final raw-output regression preserves literal whitespace, underscores, Markdown/HTML and exact copy payload. Archive disappeared from search without navigation. UI deletion removed chat/run/interaction endpoints (404), including after backend restart, while the project proof file retained SHA256 `4f4e6923259942287ce38ba3fb63422a51bf4bc3e4e183d873b996651d270bdc`. Fixture history was removed; its isolated project file remains as preservation evidence.
- Real Qwen inspection: first configuration 16.735s, repeat 0.015s, fresh manager under 0.001s with cold readers blocked. Current restarted application returned all five bundles in 28.6ms and cached configuration in 6.2/5.9ms. Cache invalidation, missing files, refresh, schema changes and strict launch/reload verification are covered.
- Actual Tools and Thinking probes passed on the running model. Captured requests included the selected low effort; tool call ID/arguments/result/final reply were verified. The previous thinking-off request returned 70 reasoning characters; corrected adapter off returned zero and on returned 70, both with the correct answer. MTP tensor evidence/options and numeric draft count transmission are verified; throughput improvement is not benchmarked.
- Exact backend restart retained the existing model PID/creation identity and pending Tea/Coffee interrupt. The rebuilt desktop was reopened with its native menu hidden until requested. These engineering observations do not constitute Dave's final visual acceptance or complete Packet03's outstanding Explorer/tray/notification activation gates; PR118 remains separately pending.
