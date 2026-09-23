/** Split a streaming Markdown string into blocks that will not change and one open tail. */

const FENCE = /^(```+|~~~+)/;

export function splitStreamingMarkdown(text: string): { blocks: string[]; tail: string } {
  const lines = text.split("\n");
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
    const marker = FENCE.exec(line.trim());
    if (marker && fence === null) {
      flush();
      fence = marker[1];
      current = [line];
      continue;
    }
    if (marker && fence !== null && line.trim().startsWith(fence)) {
      current.push(line);
      flush();
      fence = null;
      continue;
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
  const fences = closed.match(/```/g)?.length ?? 0;
  if (fences % 2 === 1) {
    closed += "\n```";
  }
  const bold = closed.split("**").length - 1;
  if (bold % 2 === 1) {
    closed += "**";
  }
  if (/\[[^\]]*\]\([^)\n]*$/.test(closed)) {
    closed += ")";
  }
  return closed;
}

export const VIRTUAL_LINE_HEIGHT = 16;
export const VIRTUAL_OVERSCAN = 8;

export function visibleLineRange(lineCount: number, scrollTop: number, viewport: number, lineHeight = VIRTUAL_LINE_HEIGHT, overscan = VIRTUAL_OVERSCAN): { start: number; end: number } {
  if (lineCount <= 0) {
    return { start: 0, end: 0 };
  }
  const view = Math.max(viewport, lineHeight);
  const maxScroll = Math.max(0, lineCount * lineHeight - view);
  const top = Math.min(Math.max(0, scrollTop), maxScroll);
  const start = Math.max(0, Math.floor(top / lineHeight) - overscan);
  const end = Math.min(lineCount, Math.ceil((top + view) / lineHeight) + overscan);
  return { start, end: Math.max(end, start) };
}
