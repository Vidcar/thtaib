# Design

## Context

See proposal.md for why. The live path today is one token in, one full redraw out.

The desktop paints answers and reasoning with `react-markdown` and `remark-gfm` on the whole string (`AgentMessageFeed`). While a reply runs, the transcript calls `scrollTo({ behavior: "smooth" })` on every change. The transcript element is `aria-live="polite"`. An open reasoning box has its own scroller and does not follow the newest line. An open tool body follows only because it jumps to the bottom and slices the last 4,000 characters.

The backend writes each token as its own SQLite commit. About four times a second a measurement frame deep-copies the snapshot, dumps the run through Pydantic under the harness lock (`projection_run`), and, for a subscriber who joined with `since`, replays every message event since the turn started (`ResumeProjection._values_with_partial`) before the next tokens are forwarded. An earlier fix already stopped copying captured model requests on this path because that copy was slower than generation.

The desktop keeps the stock `@langchain/react` `useStream` client. That client already merges token deltas with `values` snapshots and coalesces a burst into one store update. Tokens that arrive as separate tasks still render one by one, and a `values` snapshot whose text differs from the token stream does not heal the gap.

Opening a chat paints one saved transcript and continues after `interaction_cursor`. The cursor, text and run state are captured consistently, including native messages that finished before their graph update. Replay pages retain their token prefix before completion may compact it. The transport commits only complete received frames to its resume cursor. Approval visibility remains tied to the same observed run state.

## Goals / Non-Goals

**Goals:**

- New tokens show within a frame or two, with the caret on the newest line.
- The full answer, reasoning, and tool text stay reachable by scrolling and by copy.
- A speed update does not redraw bubbles or sit in front of the next token.
- One interaction protocol and one message assembler.

**Non-Goals:**

- A new stream protocol, a second message assembler, or a replacement for `useStream`.
- Typing animation, syntax-highlighting, or diagram rendering.
- Changing execution, permission semantics, checkpoints, or the interaction protocol.
- Virtualizing the Monaco diff or the file tree.

## Decisions

### Paint completed blocks once

Keep the current Markdown rules: safe links, source chips, copy buttons, no raw HTML. Split a streaming answer and a streaming reasoning block into completed blocks plus one open tail. Memoize each completed block by its text so a new token does not parse it again. Parse only the tail. Close an unfinished fence, emphasis mark, or link in that tail so the last block does not flicker. No per-character animation.

Finished bubbles are memoized by message identity and content, including same-length tool output changes. Keep one pending animation frame and publish its latest text; incoming tokens must not cancel and postpone that frame. A bounded timer publishes in background windows whose frames pause. Lists and document-wide references retain their Markdown context instead of splitting every blank line.

Alternative considered: adopt Streamdown. Rejected. Its defaults add Shiki, Mermaid, and a per-word animation, and they would replace the copy and source-link behaviour already in the feed.

### Follow by setting the scroll position

While the person is at the bottom, set `scrollTop` to the bottom once per frame. Do not use smooth scrolling during generation. Smooth scrolling stays for an explicit jump (opening a chat or a notice) and is instant when reduced motion is on. A non-collapsed selection inside the scroller skips the follow.

The open reasoning box and the open tool body use the same rule inside their own scroller. Scrolling up inside that box stops the follow until the person returns to its bottom.

Take `aria-live` off the transcript. The existing running indicator carries one polite status that changes when a reply starts, stops, or waits.

A measurement must not call `updateConversation` in a way that passes new render props into the feed. The incomplete-message set keeps a stable identity when its members have not changed.

### Show the full open body using native geometry

Remove the 4,000-character slice. Keep tool text as a single preformatted text node inside its bounded scroll body and reasoning as memoized Markdown blocks. Native layout determines actual heights. Fixed estimates for arbitrary Markdown blocks or appearance-dependent lines were reproduced to omit text and jump during streaming, so they are not used. Copy and selection retain the full string. Finished history bubbles use `content-visibility: auto` so off-screen messages skip layout. The live bubble stays active.

Alternative considered: keep the character slice. Rejected. It hides the text the person asked to read, and it does not fix the answer or the reasoning panel.

### Keep measurement off the token path

A measurement frame carries counts and speed only. It does not copy the transcript, dump the run through Pydantic, or replay the token log. `display_values` on the live SSE loop does not deep-copy messages or take the harness lock per frame.

Token events stay the durable log. Commits are flushed about once per frame, or after a few dozen tokens, instead of once per token. A subscriber still sees a correct prefix. Resume replay of that log runs once, when a subscriber joins mid-answer, so the next delta is appended to the text already shown. It does not run again on every speed tick.

Message `values` snapshots stay at turn boundaries: the human message, a tool result, and the finish. They are not the speed channel, so they stop racing the token assembler.

Alternative considered: drop the durable token log and paint only from the latest snapshot. Rejected. Reconnect and partial recovery depend on that log.

## Risks / Trade-offs

- [A block split changes Markdown semantics] → Keep lists, tables, reference definitions and unfinished fences in their semantic context; focused checks compare the streamed and finished render.
- [Long bodies become expensive] → Tool text uses one text node; completed Markdown blocks are memoized. Preserve semantic list/reference context rather than parsing each blank-line fragment independently.
- [Batching token commits loses the last tokens on a crash] → The flush interval is one frame, and the finish path flushes before the turn is marked complete. Resume already tolerates a prefix.
- [A `values` snapshot at a turn boundary still replaces a bubble] → That snapshot is the completed message. In-flight measurement frames no longer carry message text, so they cannot pull the bubble backward.

## Migration Plan

No stored-history migration. In-flight runs keep the existing token log. New measurement frames are smaller from the time the backend ships. Rolling back restores the previous paint and the previous per-token commit. Neither direction rewrites checkpoints or replays a turn.

## Open Questions

None. The follow rule, the full-text rule, and the measurement boundary are settled in the spec delta.
