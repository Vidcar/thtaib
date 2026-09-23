# Tasks

## 1. Desktop paint

- [x] 1.1 Split a streaming answer and a streaming reasoning block into memoized completed blocks plus one parsed tail, keeping the existing link, source-chip, and copy behaviour, and verify a fence that is still open stays in the tail while a finished paragraph is not parsed again.
- [x] 1.2 Cap live-bubble paints at one animation frame, memoize finished bubbles, and keep the incomplete-message set stable when its members do not change. Verify a parent render that does not change message text does not rebuild finished bubbles.
- [x] 1.3 Follow the transcript, the open reasoning box, and the open tool body by setting the scroll position directly while the person is at the bottom. Leave a text selection alone, and use smooth scrolling only for an explicit jump. Verify reduced motion stays immediate.
- [x] 1.4 Remove the live-region announcement from the transcript and announce writing, stopped, or waiting once on the existing running indicator. Verify the transcript element is not `aria-live`.

## 2. Full text in an open body

- [x] 2.1 Remove the 4,000-character slice. Paint a tall open tool or reasoning body as the visible lines plus overscan, with the copy control still copying the full string. Verify scrolling reaches the first line and the last line of a long write.
- [x] 2.2 Skip layout for off-screen finished bubbles with `content-visibility: auto`, leaving the live bubble active. Verify a finished bubble still shows its text when scrolled into view.

## 3. Backend hot path

- [x] 3.1 Make a measurement frame carry counts and speed only. It must not copy the transcript, dump the run under the harness lock, or replay the token log. Verify a focused telemetry test that a speed sample does not rewrite messages.
- [x] 3.2 Flush token commits about once per frame, and flush again before the turn is marked complete. Verify resume from a cursor still appends the next delta to the text already shown, and a completed turn contains the full text.
- [x] 3.3 Keep message snapshots at the human message, the tool result, and the finish. Verify a measurement tick during generation does not replace the in-flight answer.

## 4. Check

- [x] 4.1 Run `pnpm run build` from `apps/desktop`, `uv run python -m tests.run` from `apps/backend`, and `openspec validate --all` from the repo root. Record any failure instead of weakening a check.
- [ ] 4.2 On a live local model, in an isolated scratch project, stream a long reasoning trace and a long file write. Confirm the open panels show the newest lines while tokens are still arriving, scrolling up shows the earlier lines, and the speed readout keeps updating. Do not delete ScratchArea chats. Update `HANDOVER.md` with what is usable and the check results.
