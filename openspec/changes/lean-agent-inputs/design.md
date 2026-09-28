# Design

## Context

See proposal.md. Deep Agents 0.7.19 and LangChain 1.4.2 already support replacing feature middleware text, request tool filtering and dynamic native ToolNode execution. Existing setup resolution freezes authored versions, while selected tools currently double as the entire model-visible set and dependency preflight. Keep one backend, graph, knowledge store and permission authority.

## Goals / Non-Goals

Deliver the approved shared inspector and progressive inputs without automatically changing authored text, adding a selector LLM, another dispatcher, or a second context store. Keep explicit images, native formatting, context guards, helper restrictions, confirmed outcomes and deterministic retained image placement.

## Decisions

- Add a versioned `input_policy` to reusable/setup/start/frozen records: `tool_loading` (when_needed/always), `pinned_tools`, entry-keyed `reference_loading` (off/when_needed/always), stable `excluded_sources`, and nullable `instruction_override` (empty means replace with no agent text). New resolution produces v1; historical run policy absence preserves eager behaviour. Higher-scope item choices override inherited ones; exclusions apply after inherited selection, before latest-version resolution.
- Extend existing resolved/effective/request records with `input_sources`; readiness receives a shared `input_preview`. Rows identify title, kind, origin, inclusion reason, mode, cost method, content/path, immutable version, editability/required status and historical limits. Final adapter capture remains actual-request authority. Preview and actual views are explicitly distinct; inspect lazily under existing redaction policy.
- Maintain the accepted enabled capability envelope separately from the per-step disclosed set. Bootstrap `find_tools`, selected `ask_user`, selected/scoped context readers and pins. Discovery searches bounded name/description matches and activates only admitted names. Native state retains disclosure through resume but resets at the next new turn. Deferred service adapters are run-owned; native ToolNode wrappers supply the matching tool without another execution loop.
- Freeze connection IDs and saved tool manifests at admission, including each parent's bounded helper connection selection. Accepted preflight, dependency checks and native execution consume that same catalogue; live identity/readiness checks occur before disclosure or effects without refreshing it from later connection edits.
- Register deferred tools with the existing run-local native approval map before exposure. Workbench policy wrappers remain outside dynamic resolution. Plan, access, window scope, grants, context capacity and cancellation remain backend gates. Setup repair cannot enlarge frozen tool identity.
- Always include memories use official middleware; deferred memories use a compact index and a thin `read_reference(entry_id)` backed only by their frozen original native version paths. Skills retain native metadata-first reading with short guidance. Guided/Source declared required tools/connections/project context round-trip as immutable metadata and never supply authorization.
- Native setup interrupts use typed `CapabilitySetupRequest` attached to an action (capability/id/tool names/code/message/action/navigation target/requires-new-input), existing respond/reject decisions and checkpoint resume. Checks are repeatable; no business action precedes setup. Credentials and live objects stay outside state. Explicit requirements remain preflight checks, optional dependencies pause on use.
- Deferred screenshots use the existing retained-asset hydration and model-bound capability probes. Browser/Windows capture text cannot announce an unsupported model before those probes; failed probes retain the existing truthful fallback and asset/session access checks.
- The shared inspector opens from Chat context and Agents preview. Existing editors own durable content. Chat local replacement/exclusion defaults do not save agents; Save to agent is explicit. Earlier retained context is identified and Fresh chat copies current choices. Models gets an optional authored-prompt edit/reset control in its existing setup editor.

## Risks / Trade-offs

- Discovery adds a model step and changing schema prefixes can reduce cache reuse: measure entire task tokens/latency and support pins/eager mode.
- Dynamic native tools absent from the static approval map could auto-approve: add before exposure and regress Ask/Plan/recovery paths.
- Interrupts restart their node: preserve resume identity/order, repeat only checks and never replay uncertain effects.
- Exclusion cannot erase historical quotations/derived answers: explain retained context and provide deliberate fresh start.
- Inaccessible deferred references with tools off: readiness provides Include now/Remove/Enable reading; no automatic grant.

## Migration Plan

Apply v1 defaults only to future admissions. Preserve saved selections and all historical frozen records, weights and product data. Implement policy/inspection foundation, compact guidance, deferred tools/references/setup and shared UI as one coherent delivery; validate in isolated product data, then update the established local deployment. An explicit eager policy remains available for comparison and recovery without a runtime rollback shim.
