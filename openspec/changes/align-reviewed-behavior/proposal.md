# Proposal

## Why

The current specs disagree with the product Dave reviewed, and with each other. A fix that followed them would keep case capture, application backup, project copies, a second conversation for Retry, and a second overflow path beside Deep Agents. The contract needs to say what the app actually does before implementation starts.

## What Changes

- **BREAKING** Remove Lab case capture, restore, and recorded-tool replay from the contract. Performance, Memory, Challenges, and the library stay.
- Keep today's one-task Workflows form until the drawing canvas replaces it on the same sidebar button. The canvas still needs Dave's approved layout before its screen is built. Image generation and speech stay future work on the existing delivery change, outside this fix round.
- Name the ten model checks. A chat Thinking change does not run checks or change the saved setup. A saved Thinking change drops only Thinking and Thinking history, which then run after the next healthy load. Sampling and answer length leave all ten results in place. A click retests only that check. Context, cache, GPU layers, flash attention, and MTP do not drop proof. Weight, projector, template, and runtime changes do.
- One model menu on Chat and the one-task page: model, quantization (a known token counts even after a dot), saved setups, the model's own Thinking levels, and a context slider. Sampling, GPU, and the saved setup stay on Models. Everyday screens use a short label and value; explanation is on hover or focus.
- Three agent choices: project files, One window, and This computer. This computer is the Windows account. With no project, commands start in the user profile. The first This-computer use in a chat is one card, in Ask and in Full access. Another chat's Always allow does not skip that first card. After that, Ask pauses unless a matching grant applies, and Full access does not pause for an enabled tool, including Delete of `.git` or a secret file. The standing project-edit permission never covers `.git`, lasts until revoked, starts with secret files excluded, and does not include delete. An approval card may allow one exact excluded edit; each button allows only that edit, and a later identical edit pauses again. Delete is a separate switch.
- **BREAKING** Several chats and helpers may use one folder. One write to a file finishes before the next write to that file. The app does not copy the folder, lock it, create a git branch or worktree to separate the work, or make the second task wait.
- **BREAKING** Remove application backup and restore. Chat can download a Markdown transcript of messages, one activity line per tool, and retained file names. Remove the JSON export.
- **BREAKING** Remove Regenerate and the Branch button. Retry and Edit rewind this chat through its LangGraph checkpoint. They do not restore files. Later messages and waiting follow-ups come off only when the new run is accepted.
- Memory suggestions always wait for Accept or Reject. Remove automatic memory saving. Do not keep a stored copy of the request the model received. Deep Agents compaction, including its scratch history, stays the only compaction. A prompt that still cannot fit fails the send and leaves the chat in place.
- Do not reimplement llama.cpp, Deep Agents, LangGraph, or LangChain. The app coordinates permissions, records, and screens.

## Capabilities

### New Capabilities

### Modified Capabilities

- `lab-evaluation`: Remove case capture, case restore, and recorded-tool replay.
- `agents-workflows`: Rewind in this chat, access and tool choices, file-change grant, delete, helpers, compaction ownership, and no stored request copy.
- `environments-tools`: This computer, One window, project-file tools, and same-file write order.
- `state-recovery`: Remove backup, restore, and project copies. Keep the Markdown transcript, archive, and delete.
- `models`: Named checks, what invalidates proof, Thinking split, quantization display, and Deep Agents overflow.
- `backend-desktop`: One model menu, whole-app density, current sidebar names, connection wording, and the project-edit permission screen.
- `architecture`: The run record and inspector agree on selected, loaded, applied, unsupported, overridden, and unverified facts, and do not require a stored copy of the request the model received.

## Impact

- Backend and desktop behavior, permissions, and retained records. No new inference engine, agent loop, checkpointer, or workflow runtime.
- `consolidate-product-contract` stays the delivery home for the unbuilt canvas, image generation, and speech. This change does not build those.
- APIs and screens for `/v1/lab/cases`, `/v1/backups`, conversation branching, and stored model-request diagnostics are removed from the contract. LangGraph checkpoints remain the rewind authority.
