# Design

## Context

The Models panel already has a library selection, Hugging Face importer, durable import jobs and shared backend configuration resolution. The current importer treats every non-projector GGUF as a primary variant; the desktop uses a long native select. Discard currently marks a job discarded but leaves it in history. The existing response editor omits several supported controls.

## Goals / Non-Goals

**Goals:** Keep the everyday model workflow on three stable tabs, preserve exact import selection and model-setting provenance, and clear terminal history without weakening ownership checks.

**Non-Goals:** Estimate RAM/VRAM fit from repository filenames, auto-configure separate MTP draft files, or change conversation-level overrides.

## Decisions

- ModelsPanel owns one import-job polling hook for tab counts and completion refreshes. Add models stays mounted while another tab is shown so search and selection survive navigation. Starting a job opens Downloads; completion never steals focus.
- Hugging Face inspection returns an `auxiliary_ggufs` collection for files under an `MTP/` path or with an `mtp-` or `imatrix` basename. Only `variants` enter primary selection and server-side exact-file validation. The desktop parses recognized quantization suffixes for display only, groups by nominal bit family, and leaves unknown hints unclassified.
- The variant picker is a semantic, radio-selectable table with sticky headers and bounded height. Narrow containers show stacked rows with the same fields and keyboard operation. Projector choices remain explicit outside the table. Color indicates selection or actual status, not speculative quality.
- The My models editor uses the existing configuration/options and effective-settings authority. Frequently used startup and response controls are visible; low-frequency runtime controls and diagnostics remain in one secondary area. The shared response editor adds `top_k`, `presence_penalty`, and `repeat_penalty`, with the existing saved/observed source display. Existing Save, Save as variant and safe Apply & reload operations remain separate.
- Discard runs under the import-job lock, rejects active and complete jobs, cleans only eligible owned content and deletes the terminal job record after successful cleanup. A discarded legacy record can run the same operation again. Shared staging remains referenced by its surviving completed job. The UI removes the row on success and keeps it with an error on failure.

## Risks / Trade-offs

- Filename hints can be wrong or absent -> label them as filename-derived and show Unknown instead of asserting actual model precision.
- Moving Downloads into a tab can stop its old component-local polling -> lift polling to the Models parent and refresh the library on terminal completion.
- Legacy discarded jobs may share staging -> preserve references and delete only the terminal record when the storage cleanup rules allow it.

## Migration Plan

No bundle or configuration migration is needed. After validation, safely clear the three existing discarded records through the fixed operation and confirm the completed installation and shared staging remain. Rebuild and reload the established desktop/backend deployment; rollback is the previous application build with model data intact.
