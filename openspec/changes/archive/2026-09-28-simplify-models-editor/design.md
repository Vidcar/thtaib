# Design

## Context

See proposal.md. ModelsPanel owns model selection/files/card; DeploymentsPanel owns saved setup drafts and runtime actions. Shared controls currently nest optional prose inside content-sized rows. Descriptor and effective-value requests clear current presentation while checking. Existing profile deletion and pinned-card refresh services already provide the required ownership boundaries.

## Goals / Non-Goals

Deliver the approved editor flow without changing native residency, inference, import selections or stored setup meaning. Preserve existing configurations rather than infer origins, rename or clean them automatically.

## Decisions

- ModelsPanel hosts one 420px contextual inspector, docked when 720px remains, otherwise modal overlay. Editor inspector content uses a React portal into the host so draft/async state remains owned by DeploymentsPanel; card/files remain owned by ModelsPanel. Reuse existing help/popover/dialog primitives.
- One sticky setup toolbar contains Save, Load/Unload and Check settings. Setup actions expose rename/copy/default/revert/delete. Existing deletion previews/services retain guards; default/last-setup reasons appear before deletion.
- Presets have a diff/apply panel and recorded-source badge, rather than a second selector. Applying merges supplied response fields and stated reasoning only; saves stay explicit.
- Store hidden_response_recipe_ids alongside existing bundle guidance (empty by default). PUT /v1/bundles/{bundle_id}/response-recipes/{recipe_id}/visibility accepts visible:boolean and returns ModelBundle. Existing refresh accepts optional restore_hidden:boolean=false; successful restore clears visibility exclusions atomically with refreshed pinned recipes. Original recipe records remain available for provenance validation.
- Shared controls gain an opt-in Models layout with separate label/control/readout, reserved Reset and two-line status space, and fixed custom-entry geometry. Response defaults/control kinds use a scoped presentation snapshot during requests; matching current resolver results alone establish authority. Keep the authoritative preview hook unchanged.
- Hardware estimate gains compact presentation plus a details callback. The compact skeleton remains mounted through pending/error/success; details consume the same result, not a second estimator.
- Checked settings are keyed to bundle/setup/full startup+response candidate and marked stale when edited. Display both startup and response reports in the inspector. Move runtime details/history and bundle-level vision/template actions out of the form. Consolidate reasoning_budget alias under reasoning_budget_tokens and response format/history under Advanced response.

## Risks / Trade-offs

Pending descriptors or results could misrepresent another selection: scope snapshots and cancellation to exact identities, mark pending/stale, and never use presentation snapshots for load validity. Inspector docking intentionally reflows on opening; ordinary value/status updates must leave subsequent rows within one CSS pixel. Existing callers retain the shared control default layout.

## Migration Plan

Additive bundle metadata and route contracts require regenerated shared contracts. Existing setups/weights/preset origins remain intact. Validate isolated Windows runs before merging and refreshing the established deployment.
