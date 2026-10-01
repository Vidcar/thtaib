# Design

## Context

See proposal.md for why the contract changes. The running app still copies a project around a run, can store the request a model received, branches a chat for Retry, and takes one lock for a whole project folder. llama.cpp, Deep Agents 0.7.19, LangGraph, and LangChain already do the engine work. This design keeps those calls and says which app-owned copies to remove later. It does not add an engine.

## Goals / Non-Goals

**Goals:**

- One owner for each engine job, called by its own API.
- Thin wrappers keep the library's own name, so a second copy is not registered beside it.
- The app keeps permissions, records, and screens.

**Non-Goals:**

- Building the drawing canvas, image generation, or speech. Those stay on `consolidate-product-contract`.
- A new inference server, agent loop, checkpointer, sampler, grammar, tokenizer, or summarizer.
- Requantizing a model file. Quantization on screen is the known token in the filename.
- Changing product code in this planning change.

## Decisions

### 1. llama.cpp stays the inference engine

The context slider becomes that server's context size. The same size is the Deep Agents profile input budget. Thinking levels from the model template go out as the server's existing thinking and thinking-history fields. Sampling values pass through the existing direct request keys. The ten checks are short requests to that same server. Lab speed uses llama-bench and does not invent a score. When the server reports a token count, that count is the one shown. Otherwise the existing LangChain approximate counter is the estimate. The app does not add a tokenizer, grammar, sampler, cache, or thinking parser.

Alternative considered: an app-side context budget and a separate probe runner. Rejected. That is a second engine.

### 2. Deep Agents stays the agent loop

One `create_deep_agent`. One summarization middleware, with no custom trigger, keep count, or prompt. The app sets the profile input budget from the live context size. With that budget set, Deep Agents uses its own trigger fraction 0.85, keep fraction 0.10, and the same fractions for tool-argument trimming. If the profile were missing, Deep Agents would fall back to a fixed large trigger and keep six messages, so the app keeps supplying the real context size. On an overflow from the server, Deep Agents summarizes or clips a trailing tool result and retries once. If it still cannot fit, it raises its context-overflow error. The app maps that to the existing capacity failure, leaves the messages on screen, and does not offer a branch, a new chat, or a second shortener. An approximate estimate must not reject the send before that loop runs. Deep Agents already keeps its own headroom inside its input budget. The app does not add another margin.

Project file tools stay the Deep Agents filesystem tools: `ls`, `read_file`, `write_file`, `edit_file`, `glob`, and `grep`. The upstream delete tool stays the Delete switch. The existing exact multi-hunk tool stays beside `edit_file` and does not replace it. `execute` stays `LocalShellBackend`. The existing job tools, start, status, stop, and skill script, stay beside `execute`. They must not become a second shell.

The compaction scratch note under the product data root stays. It is not copied into the project, and it is not a request inspector.

Accepted memories and skills load through the official `memory` and `skills` parameters. The app writes the versioned record out to the scratch files that middleware reads. `propose_memory` stays a proposal until the person accepts it on the Knowledge page.

Alternative considered: an app summarizer, a homemade editor, or a sandboxed shell. Rejected.

### 3. Thin wrappers keep the library name

- The filesystem middleware subclass keeps the name `FilesystemMiddleware`.
- The memory and skills middleware subclasses keep the names `MemoryMiddleware` and `SkillsMiddleware`.
- The shell subclass exists only to stop a Windows process tree. It remains a `LocalShellBackend`.
- The model dispatch wrapper only adds cancel and the summarizing status. It is not a second chat client.

A renamed wrapper would sit beside the official middleware and register a second tool. Do not rename them.

### 4. LangGraph owns rewind and the future graph

Retry and Edit call the public checkpoint API on the same thread. The app stores checkpoint ids. It does not read or write checkpointer tables, and it does not build a second history store. When the canvas is built under the other change, React Flow only draws the graph. LangGraph runs it. This change does not build that screen.

### 5. The app owns permission, records, and the screen

Ask and Full access, the standing project-edit grant, This computer, and One window stay app policy. So do the Markdown transcript, archive, and delete. Same-file writes are ordered by a per-file lock. A read or later write that is waiting must not hold the worker that has to finish the write. The folder is not locked.

The first This-computer use in a chat is one card, in Ask and in Full access. The stored starting folder is the resolved path, never empty. After that confirmation, Full access does not pause for a later enabled command. A grant from another chat does not skip the first This-computer card in a chat, and an excluded-file approval is only that one edit.

- Stop may show Finishing only for that run-record save.

### 6. What comes out

On apply, remove case-capture routes and project copies, the Settings Backup section, conversation branching and Regenerate, the stored model-request body, the automatic memory switch, and the project-wide file lock. Do not replace them with a new copy, backup, branch, or secret scanner.

The sentence in the records spec about backing up SQLite during a future JSON cutover is that cutover's migration step. It is not the removed Settings backup.

## Risks / Trade-offs

- [A thin wrapper is renamed] → Keep the official middleware and tool names. A test should fail if a second tool is registered for the same job.
- [A per-file lock deadlocks] → The waiter must not occupy the worker that has to finish the in-progress write.
- [Full access looks like it never asks] → The first This-computer card is the exception. Later enabled commands do not pause.
- [Dropping the stored request also drops stream errors] → Keep the partial output and the error. Drop the stored request body.
- [Main specs still describe the old behavior until this change is archived] → Implementation follows these deltas. The purpose lines edited in the lab, agents, and records specs are the only main-spec edits, and a delta cannot carry a purpose.

## Migration Plan

1. This change is the contract only. Product code stays as it is until apply.
2. On apply, remove the retired routes and screens, then change permissions, file order, and rewind to match the deltas.
3. Leave existing chats in place. Do not restore project files. Do not delete project files, model files, or a transcript the person already downloaded.
4. Rolling back this contract, before it is archived, is reverting the change. Rolling back the later code change is a normal code revert. There is no backup restore, because backup is being removed.
5. The canvas, image generation, and speech stay on `consolidate-product-contract`.
