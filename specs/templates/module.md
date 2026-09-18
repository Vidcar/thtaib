# REPLACE_WITH_MODULE_NAME

## Ownership, scope and source

State the one responsibility boundary this module owns and what it explicitly does not own. Link source requirements or the approved decision. Label proposed additions rather than attributing them to a source that does not support them.

## Public contracts and collaboration

Name semantic inputs, outputs, events, errors and effects. Link canonical contract paths through the repository map instead of reproducing a second exact schema. State allowed dependencies and which component executes each operation.

## Lifecycle and failure

Describe startup, execution, progress, intervention, cancellation, shutdown, recovery and relevant failure handling. State data ownership, persistence, compatibility, policy and observability. Cover successful and unsuccessful paths.

## Requirements and acceptance checks

Assign unique requirement IDs using the project's existing prefixes or an explicitly registered new prefix. The checker recognises the ID shape of two to eight uppercase letters, a hyphen and three digits. Put each normative requirement in this exact form, with its real lowercase ID anchor:

```text
<a id="replace-with-lowercase-id"></a>
### REPLACE_WITH_ID: Concise requirement title

Required behaviour, without restating another module's authoritative rule.

**Acceptance:** Specific observable/executable evidence that would demonstrate it.
```

Register each real ID in the catalogue with its implementation status and actual pointers. Do not put example numbered IDs in a live specification where they could be mistaken for requirements.

## Unresolved details

Link each blocking open question and say what cannot safely proceed until it is resolved. Do not hide design choices behind unspecified defaults.
