# Current handover

Updated 2026-09-25. Selected installed Hugging Face model-card work is complete on `main`, delivered in [PR #160](https://github.com/Vidcar/thtaib/pull/160), and running locally. The completed OpenSpec change is archived at `openspec/changes/archive/2026-09-25-selected-hf-model-card/`, and the updated Models contract is in `openspec/specs/models/spec.md`.

The old UI exposed only extracted recipes, which made DavidAU look like the only model with a card. The new read-only bundle card endpoint verifies the saved root README by size and SHA-256 or fetches that same installed revision. The desktop displays the full card on demand with inert Markdown and a pinned source link; late results cannot replace another selection. The recipe parser now offers one mode-neutral set for the installed Gemma and jica98 cards, labels guidance not copied, and preserves thinking and unrelated default settings until a user explicitly creates a configuration.

Checks passed: 821 backend default tests (one skipped), 192 integration tests, desktop build and Models checks, generated-contract check, OpenSpec validation, `git diff --check`, and read-only hash/source/value checks of both installed cards. No live configurations or weights were changed. With zero active runs/imports, Workbench was deliberately restarted; the new live card endpoint returned the installed Gemma and jica98 cards correctly, and Electron reopened from the new build. The managed Gemma instance unloaded during restart; its weights and saved setup remain intact.

No work remains for this change. The managed Gemma instance can be loaded again when selected. Prior completed setup simplification: [PR #159](https://github.com/Vidcar/thtaib/pull/159).
