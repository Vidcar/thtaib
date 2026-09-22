# Design

## Context

See proposal.md. The current contract already loads Deep Agents, Monaco, and a file tree, and it draws Chat as a conversation with one dock. This change adds the screens and behaviour that lived only in older plan folders.

## Goals / Non-Goals

**Goals:**

- Each new area has a specified screen: what is on it, what is empty, what a failure looks like, and what stays out of the way.
- Lab, helpers, Workflows, and media reuse runners and engines that already exist. The app owns configuration, records, and presentation.
- Later features have an obvious place to land.

**Non-Goals:**

- Building the screens in this change.
- The memory-proposal review journey, document-source inspection, the skill walkthrough, or a claim that half-screen review was accepted.
- Shipping ComfyUI, Whisper, Kokoro, Piper, or a chart engine inside the app.
- Requiring Inspect, RULER, voice cloning, always-on listening, or automatic schedules now.
- Saying those later features are forbidden.

## Decisions

### Screens are part of the requirement

Every new area specifies the surface a person uses: layout, primary control, empty state, progress, failure, and the thing that must not be mixed in. Raw JSON, internal ids, and backend words are not the way through the main path. Technical detail opens on demand.

Shared visual rules: the compact type and spacing already used by Chat, Windows light and dark, readable labels, visible focus, and help on hover or keyboard focus. A disclosure may use a chevron. Motion follows the system setting.

### Lab is three screens, one reservation

Measurements is the front door. A settings column shows the model, the probed context as a fact, and editable prompt sizes and depths. The chart is a loaded chart component with prefill and decode as separate series. Saved runs compare on that chart and can be deleted after confirmation.

The needle test is its own screen. Depths are chips the person can edit. The default set is 0, 25, 50, 75, and 100 percent, with room left to answer. Results are one row per depth, pass or fail, not a single blended score.

Challenges are a short list on a third screen. Each card shows the task in plain language and the exact check. Adding one later is a new versioned card, not a new product. Vision, when the bundle already has it, uses the same image control as Chat.

A reservation banner is visible on Chat, Workflows, and media while Lab holds the machine. It says what is running and how to stop it. It is not an error toast after the fact.

llama-bench is the speed runner. The shared agent runs challenges. Inspect is not required.

### Helpers and workflows are opt-in pictures

The setup popover gains a Helpers section. Empty copy says this chat will not hand work to another agent. Chosen helpers are named rows, removable, with their model visible. The general-purpose helper stays off.

The activity list uses the agent's name, a plain status (working, waiting for approval, waiting for the model, failed), and the same one-line tool rows. Child rows are indented under the parent. Stopping says what will stop.

Changing or unloading a model opens a confirmation that names the conversation being kept and any work that must finish or be stopped. It does not happen from a silent menu.

The Workflows screen is a canvas: a step palette, the graph, and an inspector for the selected step. Steps use ordinary names (Ask a person, Run an agent, Grade with a workflow, Branch, Repeat). Invalid steps show the reason on the step. Run and history sit above the canvas. Nothing on the palette runs until it is placed and the workflow is started.

### Media is a configured plug

Image generation calls a ComfyUI address the person saved, using a workflow they already created there. Progress and the image appear in the reply and in the library.

Dictation and speech use an OpenAI-compatible base address, model, and voice. The settings screen states when that address is not on this machine. Dictation writes into the composer and leaves the message unsent. Speak is a button on a finished answer.

Example engines named in the spec are plugs, not bundled products: whisper.cpp or faster-whisper, Kokoro, Piper, and later Chatterbox for cloning. MCP may point at the same engines.

## Risks / Trade-offs

- [A beautiful chart becomes a custom drawing] → Require a loaded chart component and specify the series, axes, and comparison. Do not specify pixel geometry.
- [Lab's three screens feel like three products] → One Lab destination, three clearly named views, one reservation.
- [OpenAI-compatible speech is mistaken for a cloud requirement] → The default copy assumes a local address. A non-local address is labelled on the screen.
- [Deleting the old plan folders drops nuance] → The deltas below carry the behaviour that is still wanted. Archived changes stay.

## Migration Plan

Sync these deltas into `openspec/specs/`, then remove the seven open plan folders named in the proposal. No product-data migration. Rollback is restoring those folders from git and reverting the spec commit.

## Open Questions

None. Voice cloning, always-on listening, phone-call conversation, RULER, Inspect, and schedules are deferred extensions, not open product choices.
