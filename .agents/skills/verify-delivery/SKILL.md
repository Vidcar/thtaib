---
name: verify-delivery
description: Verify evidence before claiming completion, merging or refreshing a deployment. Select proportionate project checks and distinguish automated results, independent review and live outcomes; trivial edits need only relevant lightweight checks.
---

# Verify delivery

Find the project's verification entry point and scope rules in its instructions. Use them to select applicable checks, expanding to affected consumers for shared changes; filenames alone cannot establish adequate scope. Run required checks with the correct working directories and propagate failures. Do not invent another runner when one exists.

Tie evidence to the revision, relevant working-tree content and dependencies actually tested. Later relevant edits invalidate corresponding results. Distinguish passed, failed, skipped, unavailable and not-run checks. Mandatory failures or unavailable checks prevent a complete acceptance claim; established optional skips remain visible. A success message or test count alone does not prove the outcome.

Track these claims separately:

- Automated checks: what behaviour and inputs they cover, including meaningful negative controls for new guards.
- Independent review: who independently inspected which change, findings and resolution. Arrange fresh-context review for consequential changes and changes to verification or mandatory checks; routine low-risk edits need no ceremony.
- Live validation: the actual service, model or application exercised, its build/process identity and observed outcome. Mocked tests are not live tests; an older open window cannot validate new artifacts.

Refresh a deployment only when authorized and needed. Verify the relevant build is actually running, without disturbing unrelated processes or data. Documentation and workflow changes alone do not require a model load or application restart.

Finish with the usable outcome, checks and truthful limits, and update the project's existing handover when warranted. Keep temporary evidence in the project's disposable location. Trusted local checks are not an external security boundary. Stop when acceptance is satisfied.

When a defect escapes, improve its regression or executable boundary where feasible. Change skills only for a workflow defect. For setup or meaningful skill/model changes, use the small [agent exercises](references/exercises.md); these are not required on ordinary source edits.
