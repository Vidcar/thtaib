import type { ReactNode } from "react";

export function EmptyState(props: { title: string; children: ReactNode }) {
  return (
    <div className="empty-state">
      <h3>{props.title}</h3>
      <div className="hint">{props.children}</div>
    </div>
  );
}
