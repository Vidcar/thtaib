# Design

## Context

The downloader already pins selected files and stores verified bundle records. Model configurations already combine startup and response bags, and the backend resolves effective settings. This change extends those boundaries rather than adding another settings authority.

## Goals / Non-Goals

**Goals:** Make card recommendations available as explicit saved choices, preserve exact variant intent, and present resolved values without changing omission semantics.

**Non-Goals:** Treating card prose as automatic publisher defaults or using sampling recipes to infer GPU, context, cache or MTP launch settings.

## Decisions

- The inspect result carries a validated `show_file_info` hint and pinned card candidates. A candidate has a stable ID tied to repository revision and card hash, normalized request values, mode intent, and section provenance. The parser accepts only labelled recommendation sections and rejects ambiguous or unsupported assignments. The alternative, scanning all README numbers, would confuse copied examples with a selected recipe.
- Import requests and durable jobs retain selected recipe IDs and an optional default recipe ID. The backend validates them against the pinned card before transfer and against the installed card before configuration creation. Card values remain outside `generation_defaults`; only explicit saved configuration values enter request resolution. A separate configuration error can follow a successful weight installation.
- New recipe configurations reuse profile storage. Under the existing configuration lock, validate all choices and selected template support, copy the current default's requested launch and unrelated response settings, replace the recipe fields, create names without overwriting existing profiles, and write an optional default pointer last. Recipe origin identifies retries; edits keep historical origin but do not imply continued equality with the card. A crash between record writes is repaired idempotently on retry.
- Existing-bundle refresh reads a saved README only after its recorded hash and size pass; otherwise it fetches that repository's pinned README. It updates only candidate metadata. The Models UI explicitly offers recipe creation after refresh and invalidates effective previews when bundle or configuration identity changes.
- The desktop uses backend effective setup facts for staged startup and response controls. Requested override, inherited effective value, and loaded observation remain separate labels. Unknown facts appear as unreported; displaying an inherited number does not send it as a new override.

## Risks / Trade-offs

- A conservative parser misses prose layouts without clear labelled assignments → Show no candidate and preserve manual configuration; do not guess.
- A repository card may contain stale advice → Show source and immutable revision, require deliberate selection, and verify thinking support against the selected GGUF template.
- Profiles and the default pointer are stored separately → Validate before writes, write the pointer last, and use origin-based idempotency to finish after interruption without overwriting an edited configuration.

## Migration Plan

Existing bundles, configurations and deployments keep their values. The new optional fields read as empty. Metadata refresh is explicit; no background backfill or weight replacement occurs. The intended LOW-MTP file installs as a separate bundle, retaining the existing standard IQ4_XS weights.
