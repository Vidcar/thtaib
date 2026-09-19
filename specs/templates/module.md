# REPLACE_WITH_MODULE_NAME

[Architecture](../architecture.md) · [Status and evidence](../catalog.json) · [Decisions](../decisions/changelog.md)

## Purpose

One or two sentences: what this module lets the user do.

## Boundaries and ownership

What this module owns, which upstream framework owns the rest, and what it explicitly does not own. Link the source or approved decision.

## Interfaces and contracts

Record families, routes, events, settings keys. Name what is module-local versus generated shared contract. Point at the repository map; do not paste a second schema.

## Behaviour

Current intended behaviour, including failure paths, as short bullets or labelled paragraphs. Decided defaults belong here; the history of how they were decided belongs in the changelog.

## Requirements

Each requirement uses exactly this form, with a lowercase anchor equal to the ID:

```text
<a id="replace-with-lowercase-id"></a>
### REPLACE_WITH_ID: Concise requirement title

Required behaviour, without restating another module's rule.

**Acceptance:** Specific observable or executable evidence that would demonstrate it.
```

Register every ID in the catalogue in the same change.

## Status and evidence

One line pointing at the catalogue rows, plus what has and has not been seen live.

## Open questions

Links to the open questions that block work in this module, one line.
