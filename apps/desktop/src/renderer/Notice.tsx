import type { ReactNode } from "react";

export type NoticeTone = "info" | "warn" | "error" | "ok";

export function Notice(props: { tone?: NoticeTone; children: ReactNode }) {
  const tone = props.tone ?? "info";
  return <p className={`notice notice-${tone}`}>{props.children}</p>;
}
