# ADR-0005: Application record storage

Status: accepted, technical owner decision on 2026-09-20 under Dave's agent-owned delivery instruction.

## Decision

Use the existing `application.sqlite` for new mutable application records. Keep LangGraph checkpoints in its separately owned `checkpoints.sqlite`. Files remain the home for model weights, project workspaces, snapshots, artifacts and knowledge content bodies. Application metadata and version provenance belong to the application store.

The existing JSON families are not migrated by this decision. Their current readers remain authoritative until each family has a tested import and cutover. Do not dual-write two authorities or introduce another database framework.

## Reason

The application already has SQLite, transactions, schema metadata and a migration log. Whole-list JSON replacement requires additional concurrency protection and scales poorly as mutable records grow. Reusing SQLite provides one transaction and recovery mechanism without a new dependency. The harness and model integration boundaries do not change.

## Migration and rollback

Inventory inference, compatibility, Lab and knowledge records, including references and content files. Back up SQLite through its backup API and retain the original JSON. Import and validate a copied data root first, compare every record and reference, test interrupted imports and restart, and make cutover explicit and idempotent. Until validated, existing data stays in its current store. Rollback must restore the pre-cutover database and original JSON without discarding writes; do not claim rollback is safe after new writes unless replay/export has been tested.

The remaining work is tracked once in [OQ-017](../open-questions.md#oq-017). This settles the storage choice; it does not claim migration has shipped.
