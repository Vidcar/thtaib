/** One-line Chat activity derived from a tool call and its observed file change. */

export interface TodoItem {
  content: string;
  status: "pending" | "in_progress" | "completed";
}

export interface ObservedFileChange {
  id: string;
  toolCallId: string;
  path: string;
  destination?: string | null;
  addedLines?: number | null;
  removedLines?: number | null;
}

export interface ActivityGroup<T> { label: string | null; items: T[]; }

/** Group only neighbouring successes; a running or failed call is always a boundary. */
export function groupActivity<T>(items: T[], describe: (item: T) => { label: string; finished: boolean; failed: boolean }): ActivityGroup<T>[] {
  const groups: Array<ActivityGroup<T> & { verb: string | null }> = [];
  for (const item of items) {
    const state = describe(item);
    const verb = state.finished && !state.failed ? state.label.split(" ")[0] : null;
    const last = groups.at(-1);
    if (verb && last?.verb === verb) last.items.push(item);
    else groups.push({ label: null, items: [item], verb });
  }
  return groups.map(({ items: grouped, verb }) => ({ items: grouped, label: grouped.length < 2 ? null : `${verb} ${grouped.length} ${verb === "Read" ? "files" : verb === "Edited" || verb === "Created" || verb === "Deleted" || verb === "Renamed" ? "changes" : "items"}` }));
}

const TODO_STATUSES = new Set(["pending", "in_progress", "completed"]);

export function parseTodoList(args: unknown): TodoItem[] | null {
  const value = typeof args === "string" ? parsedJson(args) : args;
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const todos = (value as { todos?: unknown }).todos;
  if (!Array.isArray(todos)) return null;
  const items: TodoItem[] = [];
  for (const item of todos) {
    if (!item || typeof item !== "object" || Array.isArray(item)) return null;
    const content = (item as { content?: unknown }).content;
    const status = (item as { status?: unknown }).status;
    if (typeof content !== "string" || typeof status !== "string" || !TODO_STATUSES.has(status)) return null;
    items.push({ content, status: status as TodoItem["status"] });
  }
  return items;
}

export function activityLine(input: {
  name: string;
  args: unknown;
  finished: boolean;
  failed: boolean;
  change?: ObservedFileChange | null;
}): string {
  const path = stringField(input.args, "file_path") || stringField(input.args, "path");
  const done = input.finished;
  const file = path ? displayPath(path) : "";
  const counts = done && !input.failed ? lineCounts(input.change) : "";
  switch (input.name) {
    case "read_file":
      return joinLabel(done ? "Read" : "Reading", file, lineRange(input.args));
    case "write_file":
      return joinLabel(done ? "Created" : "Creating", file, counts);
    case "edit_file":
      return joinLabel(done ? "Edited" : "Editing", file, counts);
    case "delete_file":
      return joinLabel(done ? "Deleted" : "Deleting", file);
    case "rename_file": {
      const destination = stringField(input.args, "destination");
      const pair = file && destination ? `${file} → ${displayPath(destination)}` : file || displayPath(destination);
      return joinLabel(done ? "Renamed" : "Renaming", pair);
    }
    case "ls":
      return joinLabel(done ? "Listed" : "Listing", file);
    case "glob":
      return joinLabel(done ? "Found files matching" : "Finding files matching", stringField(input.args, "pattern") || stringField(input.args, "glob") || file);
    case "grep":
      return joinLabel(done ? "Searched for" : "Searching for", stringField(input.args, "pattern") || stringField(input.args, "query") || stringField(input.args, "q"));
    case "execute":
      return joinLabel(done ? "Ran" : "Running", oneLine(stringField(input.args, "command")));
    case "propose_memory":
      return done ? "Proposed a memory" : "Proposing a memory";
    default:
      return joinLabel(done ? "Called" : "Calling", input.name === "Tool" ? "" : input.name);
  }
}

export function lineCounts(change: ObservedFileChange | null | undefined): string {
  if (!change || change.addedLines == null || change.removedLines == null) return "";
  if (change.addedLines === 0 && change.removedLines === 0) return "";
  return `+${change.addedLines} -${change.removedLines}`;
}

function joinLabel(verb: string, detail: string, extra = ""): string {
  return [verb, detail, extra].filter(Boolean).join(" ");
}

function displayPath(path: string): string {
  return path.replace(/\\/g, "/").replace(/^\/+/, "");
}

function lineRange(args: unknown): string {
  const offset = numberField(args, "offset");
  const limit = numberField(args, "limit");
  if (offset == null || limit == null || limit <= 0) return "";
  const start = offset + 1;
  return `lines ${start}–${start + limit - 1}`;
}

function stringField(args: unknown, key: string): string {
  const value = field(args, key);
  return typeof value === "string" ? value.replace(/\s+/g, " ").trim() : "";
}

function numberField(args: unknown, key: string): number | null {
  const value = field(args, key);
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function field(args: unknown, key: string): unknown {
  if (typeof args === "string") {
    const parsed = parsedJson(args);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed) && key in parsed) {
      return (parsed as Record<string, unknown>)[key];
    }
    return jsonStringField(args, key);
  }
  if (args && typeof args === "object" && !Array.isArray(args)) {
    return (args as Record<string, unknown>)[key];
  }
  return undefined;
}

function parsedJson(source: string): unknown {
  try {
    return JSON.parse(source);
  } catch {
    return null;
  }
}

function jsonStringField(source: string, key: string): string {
  const marker = `"${key}"`;
  const at = source.indexOf(marker);
  if (at < 0) return "";
  const colon = source.indexOf(":", at + marker.length);
  if (colon < 0) return "";
  let index = colon + 1;
  while (index < source.length && /\s/.test(source[index])) index += 1;
  if (source[index] !== '"') return "";
  let out = "";
  for (index += 1; index < source.length; index += 1) {
    const character = source[index];
    if (character === '"') return out;
    if (character !== "\\") {
      out += character;
      continue;
    }
    const next = source[index + 1];
    if (next === undefined) break;
    out += next === "n" ? "\n" : next;
    index += 1;
  }
  return out;
}

function oneLine(value: string): string {
  const line = value.split("\n")[0] ?? "";
  return line.length > 80 ? `${line.slice(0, 79)}…` : line;
}
