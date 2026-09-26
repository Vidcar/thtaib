# Spec Delta

## ADDED Requirements

### Requirement: API-046 - Keep uninterrupted Chat chronological and stable

Chat SHALL retain chronological turn, response and tool placement while the same conversation remains open across successive replies. Every call and result SHALL have one visible location owned by its originating turn, including when different runs reuse a call identifier. Retained activity MUST NOT become current activity merely because it is absent from the newest turn. Intermediate assistant responses and tools SHALL remain ordered before the final answer for that turn. Refreshing SHALL produce equivalent visible chronology and content, not repair an incorrect live order.

Historical row identity, disclosure state, readable content and text selection SHALL survive asynchronous run-detail loading and admission of later replies. Queued-run handoffs SHALL keep verified history visible continuously. New output SHALL grow below its originating user message; run or measurement metadata changes MUST NOT remount or collapse previous output. The transcript SHALL follow latest output when already at the bottom and preserve manual reading position when scrolled away.

The interaction boundary SHALL attribute native tool activity to its actual run, originating input and namespace before displaying it. Partial-response reconstruction SHALL reset at run boundaries while preserving cursor/snapshot consistency. Internal bookkeeping MUST NOT leak into public output or become execution authority.

#### Scenario: Successive replies without reopening

- **WHEN** three or more replies with intermediate responses and tool calls complete in one continuously open conversation
- **THEN** the visible rows remain chronological, every scoped tool appears once, and earlier turns remain unchanged as the newest turn grows
- **AND** refreshing yields the same visible content and order.

#### Scenario: Delayed metadata and queued handoff

- **WHEN** a later reply is admitted before its stream catches up and historical details are loading
- **THEN** verified history stays visible, existing disclosures and rows retain identity, and active controls target only the admitted owned run.

#### Scenario: Tool identity reused after cancellation

- **WHEN** a stopped turn retains partial tool activity and a later run emits a call with the same identifier before its assistant message arrives
- **THEN** each call stays under its own input, the later call does not inherit the older result, and live/replayed output stays equivalent.

#### Scenario: Read earlier output during another reply

- **WHEN** the person scrolls away or selects earlier text while another reply streams
- **THEN** new output and metadata leave that reading position and selection in place
- **AND** returning to the bottom resumes following the newest line.
