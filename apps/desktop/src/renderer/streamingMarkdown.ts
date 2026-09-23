/** Split a streaming Markdown string into blocks that will not change and one open tail. */

const FENCE = /^ {0,3}(`{3,}|~{3,})(.*)$/;

function closingFence(line: string, fence: string): boolean {
  const marker = FENCE.exec(line);
  return Boolean(marker && marker[1][0] === fence[0] && marker[1].length >= fence.length && !marker[2].trim());
}

export function splitStreamingMarkdown(text: string): { blocks: string[]; tail: string } {
  const normalized = text.replace(/\r\n?/g, "\n");
  const lines = normalized.split("\n");
  const blocks: string[] = [];
  let current: string[] = [];
  let fence: string | null = null;

  const flush = () => {
    if (current.some((line) => line.trim().length > 0)) {
      blocks.push(current.join("\n"));
    }
    current = [];
  };

  for (const line of lines) {
    const marker = FENCE.exec(line);
    if (marker && fence === null) {
      flush();
      fence = marker[1];
      current = [line];
      continue;
    }
    if (fence !== null && closingFence(line, fence)) {
      current.push(line);
      flush();
      fence = null;
      continue;
    }
    // Blank lines do not end list/quote containers. Link definitions apply to
    // the whole document, including paragraphs received before the definition.
    // Keep those documents together instead of changing their meaning while
    // streaming. Ordinary paragraphs and fenced blocks can still be retained.
    if (fence === null && /^(?: {0,3}(?:[-+*]\s|\d+[.)]\s|>|\[[^\]]+\]:|<)| {4}|\t)/.test(line)) {
      return { blocks: [], tail: normalized };
    }
    if (fence === null && line.trim() === "") {
      flush();
      continue;
    }
    current.push(line);
  }

  const tail = current.join("\n");
  if (fence !== null || tail.trim().length > 0) {
    return { blocks, tail };
  }
  return { blocks, tail: "" };
}

/** Close an open fence, emphasis mark, or link so the tail can render. The source text is unchanged. */
export function closeUnfinishedMarks(tail: string): string {
  let closed = tail;
  let fence: string | null = null;
  const prose: string[] = [];
  for (const line of tail.split("\n")) {
    const marker = FENCE.exec(line);
    if (fence) {
      if (closingFence(line, fence)) fence = null;
    } else if (marker && !(marker[1][0] === "`" && marker[2].includes("`"))) {
      fence = marker[1];
    } else {
      prose.push(line);
    }
  }
  if (fence) return `${closed}\n${fence}`;
  // Repair prose only. Literal stars inside code must never become extra
  // characters after a closing fence or inside an unfinished code block.
  const proseText = prose.join("\n").replace(/(`+)[\s\S]*?\1/g, "").replace(/\\./g, "");
  const bold = proseText.split("**").length - 1;
  if (bold % 2 === 1) {
    closed += "**";
  }
  if (/\[[^\]]*\]\([^)\n]*$/.test(closed)) {
    closed += ")";
  }
  return closed;
}
