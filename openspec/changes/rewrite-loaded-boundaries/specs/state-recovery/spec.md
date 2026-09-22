# Spec Delta

## ADDED Requirements

### Requirement: STATE-017 - Render file changes from the stored images

A project-file change SHALL keep its before and after images, including text when the existing capture rules can read it, keyed by the tool call that made the change. The Changes page and the activity-line counts SHALL use those images. Added and removed counts are the added and removed content lines of that observed difference, excluding diff headers. A pre-rendered unified-diff string remains available to copy. It MUST NOT be the view and MUST NOT be a second record. When the text is unavailable, the view says so and the counts are omitted. Presenting the change MUST NOT call the model, write the file, or treat the diff as a rollback of anything beyond the existing single-file reverse.

#### Scenario: Counts match the stored texts

- **WHEN** a change has before and after text and the activity line shows added and removed counts
- **THEN** those counts are the observed difference of those two texts
- **AND** a copied unified diff is not stored as another change.

#### Scenario: No text

- **WHEN** a change has no captured text
- **THEN** the diff view explains that the difference is unavailable and the activity line omits added and removed counts.
