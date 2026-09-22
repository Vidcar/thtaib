import type { CSSProperties } from "react";

const paths = {
  chat: "M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9H13a8.5 8.5 0 0 1 8 8v.5Z",
  models: "M9 3h6v4H9z M5 7h14v14H5z M9 11h6v6H9z M2 11h3m14 0h3M2 17h3m14 0h3",
  knowledge: "M12 6c-3-3-7-3-10-2v15c3-1 7-1 10 2 3-3 7-3 10-2V4c-3-1-7-1-10 2Zm0 0v15",
  "agent-run": "m8 5 11 7-11 7V5Z",
  lab: "M9 3h6m-5 0v7L4 20h16l-6-10V3M7 15h10",
  library: "M4 4h4v16H4z M11 4h4v16h-4z m7 0 4 15",
  settings: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm0-6v3m0 14v3M2 12h3m14 0h3M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2",
  plus: "M12 5v14M5 12h14",
  send: "M12 19V5m-7 7 7-7 7 7",
  stop: "M6 6h12v12H6z",
  shield: "M12 3 3 7v5c0 5 9 9 9 9s9-4 9-9V7l-9-4Zm-4 9 3 3 5-6",
  files: "M14 2H6v20h14V8l-6-6Zm0 0v6h6M9 13h8m-8 4h8",
  more: "M4 12h.01M12 12h.01M20 12h.01",
  close: "m6 6 12 12M6 18 18 6",
  edit: "m16 3 5 5-12 12-6 1 1-6L16 3Z",
  archive: "M3 3h18v5H3z M5 8v13h14V8m-9 4h4",
  panel: "M3 4h18v16H3z M9 4v16",
  chevron: "m9 5 7 7-7 7",
  activity: "M2 12h5l3-9 4 18 3-9h5",
  attention: "M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M9 21h6",
  folder: "M3 5h6l2 3h10v12H3V5Z",
} as const;

export type IconName = keyof typeof paths;
export function Icon({ name, size = 20, style }: { name: IconName; size?: number; style?: CSSProperties }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" style={style}><path d={paths[name]} /></svg>;
}
