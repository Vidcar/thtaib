# Design

## Context

See proposal.md. One `create_deep_agent` harness serves project and project-free Chat. Native project `read_file` can already produce image blocks; attachments and tool image rendering exist. The current model profile and compatibility probe do not establish tool-image delivery to llama.cpp. Generic MCP adapters close at each run, public page reading blocks localhost, and host `execute` does not own a persistent preview process. The retained asset store already owns immutable uploads and verified outputs.

## Goals / Non-Goals

**Goals:** Keep browser/window workers optional; give both Chat variants bounded visual evidence and honest model capability; retain captures and enforce one setup/permission path across parent and named helper runs.

**Non-Goals:** Attach a personal browser profile, expose arbitrary Playwright or WinApp command execution, add a second agent loop or asset store, or infer visual understanding from text-only page structure.

## Decisions

1. Keep native `read_file` and add an image-read guard at its backend boundary. Record a separate tool-image probe for the selected deployment. The model adapter projects a bounded tool image into the provider-supported request shape while keeping the original tool result identity and an artifact reference in durable history. This avoids a parallel reader and avoids raw image payloads in public replay.
2. Use pinned Playwright MCP through `langchain.mcp.MCPAdapter`; a Workbench session owner holds one isolated, visible browser per conversation across turns. A fixed tool allowlist and server flags disable unsafe code, page-defined tools and uncontrolled output paths. Captures are copied into retained assets and then exposed through a read-only virtual `read_file` path. The generic public-web reader keeps its current network policy. A project preview owner tracks process identity, port, logs, stop and uncertainty separately from a one-shot shell command.
3. Use the optional pinned WinApp CLI worker for structured UI Automation and window capture. The backend owns a conversation-scoped selected HWND/process identity or explicit all-window grant and checks it at every typed call. The worker captures to a controlled path; its CLI is never a general-purpose model tool. Prefer Windows.Graphics.Capture without foregrounding the window.
4. Extend the existing effective setup and asset contracts. The desktop edits setup and session selection, while backend dispatch remains authority. Browser/window worker tools share the existing approval interrupt, helper intersection, budget and run-effect records. Browser navigation can access the network; origin labels and tool approval are honest policy, not a claim that Playwright's `allowed-origins` flag is a security boundary.
5. Optional runtime installation is explicit and product managed. Pin Node and `@playwright/mcp` with checked dependencies and launch by absolute path; pin and verify the WinApp CLI release. Missing runtimes disable only their capability and show the exact setup reason.

## Risks / Trade-offs

- [Local vision setup may lack a suitable model] → Keep structural inspection usable, show a truthful unverified/unsupported result, and validate pixels on an isolated known fixture with a real vision deployment before claiming success.
- [Browser or native action can have an uncertain effect at cancellation/restart] → Record dispatched/confirmed/unknown outcomes and never reconstruct worker actions from retained screenshots.
- [Large captures can overwhelm context or replay] → Enforce existing image limits, use retained references and a bounded model image derivative, and never stream raw base64 capture data as an event.
- [WinApp CLI is a public preview and accessibility varies by application] → Pin and verify it, run Windows fixture acceptance, and report per-window unsupported or elevated access rather than silently broadening scope.

## Migration Plan

Add optional setup fields with Off defaults and an additive retained-asset origin. Existing conversations, model settings and assets retain their current meaning. Generated desktop contracts update from backend schemas. After implementation and live checks, sync the deltas into current OpenSpec specs and archive the completed change.
