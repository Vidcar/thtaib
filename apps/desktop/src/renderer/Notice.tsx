import type { ReactNode } from "react";

export type NoticeTone = "info" | "warn" | "error" | "ok";

export function Notice(props: { tone?: NoticeTone; children: ReactNode; action?: ReactNode; role?: "alert" | "status" }) {
  const tone = props.tone ?? "info";
  const className = `notice notice-${tone}`;
  if (props.action) {
    return (
      <div className={`${className} notice-with-action`} role={props.role}>
        <span>{props.children}</span>
        {props.action}
      </div>
    );
  }
  return <p className={className} role={props.role}>{props.children}</p>;
}
