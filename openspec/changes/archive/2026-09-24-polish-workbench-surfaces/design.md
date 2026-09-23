# Design

## Context

See proposal.md. The current desktop resolves parts of inheritance independently from the backend. Saved profiles and deployment snapshots overlap, and saving creates new runtime records. The production resolver reproduces the null-access display mismatch and the lost literal xhigh default. Native inspection confirms duplicate Qwen deployments share port 8080, navigation loses the selected chat, and opening a details-backed composer menu adds the global summary margin.

## Goals / Non-Goals

Make all existing functions reliable with one configuration authority and compact stable UI. Preserve weights, ScratchArea chats, user customization, unrelated files, immutable queued settings and historical runtime evidence. Do not implement the future Lab suite/canvas/media, persistent goals, recursive delegation or remote agent servers.

## Decisions

1. Reuse versioned profiles for model configurations, bound to a model with one default reference and optional variants. Deployments represent actual runtime instances with immutable loaded snapshots. Saving updates a configuration; Save as variant alone creates another. New model configurations contain startup and response settings; instruction composition remains in application/project/agent/chat setup.
2. Extend POST /v1/setup-resolution as the shared display/dispatch authority. Return effective value, explicit override, named source, known default, support, reset target, reload need and unavailable reason. Preserve configured/sent/server-reported/recognized-template facts. Unknown defaults stay unknown. Remove override means inherit; explicit model default masks an inherited request key; an empty selected list means None.
3. Chat overrides remain local. Unpinned new chats use the loaded model; explicit model choices win. Settings edits never rewrite submitted/queued snapshots. Models exposes Save changes, Load/Unload and Apply & reload; Chat Apply is separate from Save to model.
4. Reconfiguration validates expected revision, settings, history fit, ownership and consumers before stop. Running, queued, waiting, cancelling, Lab and helper users block it. Automatic ports are selected at launch; fixed conflicts fail before spawn. Persist the target and prior configuration; commit loaded state only after observed readiness. Attempt one safe restoration on failure, and reconcile interrupted operations truthfully.
5. A quiet, idempotent consolidation selects the healthy owned configuration as default (otherwise most recent saved), merges exact equivalent legacy configurations ignoring automatically assigned ports, and preserves distinct variants and historical snapshots. Backend-owned origin metadata distinguishes legacy duplicates from recovered owners and explicitly named variants; an intentional variant retains its identity even when its settings match another configuration. Merged records retain their original identity and bags for history, with one canonical owner for live resolution. Existing profile instructions remain preserved and named in effective setup; ordinary model saves cannot erase them. New configurations accept loading and response settings only, with new instruction authoring in Agents/setup. This preserves authored behaviour without inventing synthetic agents or a second live resolver.
6. Ask pauses mutations, shell and external side effects except explicitly saved matching grants. Approve for me auto-allows edits only when actual recovery covers them. Full skips approvals for enabled tools. Questions and durable memory policy remain separate. Host shell uses the Windows account, not a project sandbox.
7. Persist work_mode (work/plan), helper_agent_ids and review options through setup resolution and queued snapshots. Plan is enforced at dispatch (including restored/child calls), allows scoped reads/questions/write_todos, and forbids shell, writes, memory saving and effectful/unknown tools. Internal checkpoints/context housekeeping are allowed. An explicit switch and new submission enter Work.
8. Compile selected frozen named helper versions through the shared application enforcement path into upstream subagents. Intersect authority, retain child identity/approvals/cancellation and isolate context. No general-purpose or recursive helpers. Serialize calls sharing a managed runtime; alternate models cannot silently unload the parent. An explicit tool budget is atomic across the operation; unset means no invented cap.
9. Review is off by default. Requested Review before finishing shows criteria and up to two revisions, uses the conversation model with a read-only grader and upstream RubricMiddleware as sole cycle owner. Keep executable checks, artifacts and judgement separate; limit reached is visible.
10. Overlay menus have stable trigger dimensions and keyboard focus/Escape handling; inline disclosures are separate. Use compact switches and notched numeric sliders with exact entry. Chat remains about 860px wide, form columns about 720px; list/detail workspaces adapt while tables/diffs use useful width. Preserve current appearance customizations and open advanced preview deliberately.
11. Keep Chat mounted/restorable across destinations without creating another execution observer. Explicit New chat alone resets selection. Restore draft/attachments/reading position; sidebar and header consume the same display title. Contextual project panels open from the existing rail rather than a duplicate destination.
12. Retain original activity polish: successful adjacent calls group by verb, live/failed/waiting calls remain individual, first disclosure shows readable results, task state uses marks, incoming turn occupies its eventual answer position, saved grants are attributed, and grouped changes preserve each exact stored diff/reverse.

## Risks / Trade-offs

- Configuration migration changing behaviour: compare effective values before/after and keep historical snapshots; test idempotence and explicit empty/default/reset cases.
- Unsafe helper inheritance: compile each child with app policy, scoped backend, one summarizer, capture and shared cancellation/budgets; never rely on upstream automatic inheritance.
- Green tests preserving bad behaviour: replace markup/source locks with rendered geometry, receiver-side effects and actual model requests; retain safety tests.
- Overlapping deltas: preserve current streaming requirements and reconcile affected requirements before archive; do not mark future Lab/canvas/media work complete.

## Migration Plan

Ship one coordinated branch/PR, internally staged. Validate isolated fixtures under .scratch and existing model weights by path. Run default/integration backend suites, desktop build, contract freshness and strict OpenSpec validation, then native Windows and real-model journeys. Update the established local deployment after those gates and keep HANDOVER.md current. Do not merge/archive while a required acceptance gate is unresolved.
