# Known deviations from the intended design

The application repository has been inspected through Issues #1, #3, #12, #15 and #17 (Issue #23 audit). Implementation gaps are recorded as `planned` / `partial` catalogue rows and [open questions](open-questions.md), not as deviations, unless running code is known to contradict intended design.

There are **no recorded deviations** at this audit. Issue #27 moved run/chat linkage into `application.sqlite` with a separate `checkpoints.sqlite`. Remaining JSON stores (model-manager bundles/profiles/deployments, Lab cases, knowledge versions) belong to those modules and are not an approved waiver of [STATE-001](modules/state-recovery.md#state-001). Identities, event reconciliation, exactly-once and external-effect remainder stay [OQ-004](open-questions.md#oq-004). That is not a claim that the implementation conforms.

Use this file for observed divergence. Use [open questions](open-questions.md) for unresolved design, not for known bugs hidden as questions. Keep the affected requirements' actual implementation status in [the catalogue](catalog.json).

## Entry format

For each new entry, assign an unused `DEV-NNN` identifier and record:

```text
Identifier and concise title:
Affected requirement IDs:
Observed behaviour and inspected revision:
Intended behaviour (link, do not duplicate the requirement):
Risk and affected users/data/environments:
Owner:
Disposition: fix / propose design change / approved temporary deviation
Approval reference (required for a temporary deviation):
Scope and compensating controls:
Review or expiry trigger (a date, release or explicit milestone):
Reproduction and tracking reference:
Resolution evidence and date:
```

Temporary approval does not mark the requirement verified. Keep its status `partial` until full compliance is evidenced or the requirement is formally changed. Do not silently extend an expired deviation, remove its test, or rewrite the specification to match it. Record closure with its evidence and retain the entry for history.

<a id="dev-001"></a>
## DEV-001: Diagnostic captures and case export bypassed Knowledge capture policy

**Affected requirement IDs:** AGT-002, STATE-005, LAB-003; related OQ-006.

**Observed behaviour and inspected revision:** At [`55e6c50a7c419d28ee6915d6cf98f83c53a595d1`](https://github.com/Vidcar/thtaib/tree/55e6c50a7c419d28ee6915d6cf98f83c53a595d1) (filing-time main `ea683db`), `KnowledgeService.capture()` applied retention/redaction/discard, but harness middleware appended raw messages/HTTP payloads to `run.model_requests` and `put_run()` persisted them. `LabService.export_case()` returned the unchanged case with a `secret_scan_clean` flag based on three literal strings and did not sanitize or refuse a dirty payload. Recorded in [Issue #58](https://github.com/Vidcar/thtaib/issues/58) finding 6 / [Issue #64](https://github.com/Vidcar/thtaib/issues/64).

**Intended behaviour:** [STATE-005](modules/state-recovery.md#state-005) configurable capture policy; [AGT-002](modules/agents-workflows.md#agt-002) redaction/gaps; [LAB-003](modules/lab-evaluation.md#lab-003) exclude or redact secrets before case export.

**Risk:** Persisted diagnostics and shareable exports could retain detectable credentials.

**Owner:** Knowledge / Lab / harness persist boundary.

**Disposition:** fix (Issue #64). Not an approved temporary deviation.

**Scope and compensating controls:** Synthetic credentials only in tests. Detector remains pattern-based and incomplete.

**Review or expiry trigger:** Merge of the Issue #64 fix.

**Reproduction and tracking reference:** [Issue #64](https://github.com/Vidcar/thtaib/issues/64).

**Resolution evidence and date:** Fixed in the Issue #64 change: diagnostic copies use the Knowledge capture policy before persist; export sanitizes or blocks. Executable regression: `apps/backend/tests/test_privacy_diagnostics.py`. Not catalogue `verified`.
