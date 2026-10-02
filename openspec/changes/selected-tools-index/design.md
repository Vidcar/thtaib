# Design

## Context

See proposal.md. With an input policy, admission composes Workbench core, authored instructions, access text, reference context, and one discovery sentence. The discovery sentence does not name the accepted tools. `compose_system_prompt` does not see the accepted list. `harness_admission.py` appends access, plan, reference context, and discovery after that composition. Helper setup repeats the policy branch without the discovery sentence. Inputs reads `build_input_sources` and does not call the model.

Catalogue groups and screen labels already live in `TOOL_PRESENTATIONS` and the group titles used by the tool catalogue. `model_description` is the schema handbook and is sent only when that schema is loaded.

## Goals / Non-Goals

**Goals:**

- One function builds the index from the accepted names and the catalogue.
- Chat admission, helper setup, and the Inputs preview of that next message all use it.
- Starter drafts carry job text and do not select the nine repository-development skills.

**Non-Goals:**

- Changing who may call a tool, when-needed bootstrap, pins, or automatic `find_tools`, `read_reference`, or `task`.
- Storing the index, filling model prompts, restoring a Deep Agents base prompt, or editing live product data.
- Changing desktop labels.

## Decisions

1. **Generate at the admission boundary, not in the agent record.** The accepted list exists only after disclosure and plan filtering. A queued snapshot replaces the composed prompt first. The index is appended after that replacement, beside discovery and before that sentence, and is skipped when that exact text is already present. An empty discovery sentence does not skip the index. No input policy means no index.
   Alternative: paste the list into agent instructions. Rejected because the job would have to be rewritten every time the selection changes, and the index would be stored.

2. **One formatter, three callers.** `selected_tools_index` returns the text. Admission and helper setup append that text to the prompt they already send. The Inputs row uses the names `gate_presented_names` has accepted, including exclusions applied after `find_tools`, `read_reference`, and `task` are added. That gate receives the helper's saved memory and skill ids plus the project memory and skill ids helper freeze merges, so either source adds `read_reference` on the preview index. The preview does not resolve or validate the helper. The helper's own tools are not copied onto the parent. Helpers format their own narrowed list after `task` is removed, so a parent helper selection cannot add `task`.
   Alternative: a second copy of the lines in the preview. Rejected because the preview would drift from the request.

3. **Names and labels only, catalogue order.** Items are `call_name (Screen label)`, grouped with the catalogue's group titles, in the order groups and tools already appear in the catalogue. Tools with no presentation are omitted. The closing line tells the model to call `find_tools` with the label or the call name. `model_description` stays on the schema.
   Alternative: include the one-line description. Rejected because the approved shape is the call name and the screen label, and the handbook is the part a small model should not see until the schema is loaded.

4. **Starter drafts stay data, not records.** `setup_templates.py` gains `general` and replaces the job text and tool pins of the five existing starter ids. Those drafts do not look up the nine repository skills. Trusted project builder keeps its skill lookup and Full-access suggestion. `helper_agent_ids` stay empty because live helper ids do not exist on a draft. Evidence researcher keeps its projectless document pins and adds the three unpinned browser tools. Work plus Always include makes those browser tools eager, so that path still requires the browser worker. Plan and When needed do not.

## Risks / Trade-offs

- [A cold preview built from the saved list can name a tool admission drops] → The Inputs index calls the same gate functions admission uses. It reads the helper's saved memory and skill ids and the project ids helper freeze merges, without validating the helper. An excluded tool can remain a mode-off row. A helper tool stays off the parent index. A turn those gates refuse has an empty index.
- [A queued snapshot frozen before this change does not contain the index] → Dispatch appends it when it is missing, the same way discovery is appended, and does not duplicate it when it is already there.
- [Evidence researcher in Work with Always include now needs the browser worker] → The tools are not pinned, so When needed and Plan still admit a projectless document read. The spec says the Work plus Always case requires the worker.

## Migration Plan

No stored prompt migration. Saved agents, including Permission check, are not rewritten. Rollback is reverting the branch. Live Qwen checks are not part of this change.

## Open Questions

None. Live checks against the installed Qwen setup stay for a later pass and must not unload the model or edit product data.
