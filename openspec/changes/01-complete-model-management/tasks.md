# Tasks: Complete model installation, profiles and deployment lifecycle

Before changing an existing path, run its relevant acceptance checks and retain passing behaviour. The implementation tasks below mean verify and complete only missing behaviour; do not rebuild a satisfied requirement. Keep the acceptance checks even when no code change is needed. Import-time source review is not execution evidence, so all tasks remain unchecked until their full scope is verified.

## 1. Verify existing behaviour and implement gaps

- [ ] 1.1 Verify existing metadata-first selection, revision pinning, literal-filename handling and shard/projector protections in `inference/hf_fetch.py` and `inference/bundles.py`; complete only gaps in bounded search/direct entry and shared import verification.
- [ ] 1.2 Implement durable import progress, cancellation confirmation, retry, discard and recorded-revision verify/repair with restart reconciliation.
- [ ] 1.3 Expose future-install location and truthful staging/cache/managed disk use; implement reference-aware cleanup without deleting external imports.
- [ ] 1.4 Verify the existing profile/settings and managed-start paths in `inference/service.py` and `inference/deployments.py`; complete missing profile identity/override wiring, bound-profile validation and immutable launch snapshots.
- [ ] 1.5 Implement selected-model load on demand, coordinated unload/reload, profile rename/duplicate/delete, model deletion previews and endpoint disconnect.
- [ ] 1.6 Finish existing first-use, loading, health/error/log and unavailable-dependency controls; preserve backend lifecycle ownership.

## 2. Verify

- [ ] 2.1 Test ambiguous variants/projectors, missing or mixed shards, literal wildcard filenames, path collisions, interrupted/corrupt files, insufficient space and restart during import.
- [ ] 2.2 Test cancellation versus discard, idempotent retry/repair, shared companions, imported originals, stale process identity and concurrent start-versus-delete/unload.
- [ ] 2.3 Test startup/request/agent bag routing, profile binding, reusable unbound profiles, launch snapshot preservation and missing observations.
- [ ] 2.4 On a real managed setup, reuse/import a complete bundle, start with a selected profile, generate text, inspect startup evidence, unload with confirmed exit, and restart the same configuration. Render the changed Windows controls.

Use the repository validation commands in `AGENTS.md`. Keep actual test outcomes and any blocker in this change/its PR; do not create another tracker. Required real checks stay incomplete when the necessary runtime, endpoint or Windows device is unavailable.
