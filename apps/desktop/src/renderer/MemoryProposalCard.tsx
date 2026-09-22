import type { ReactNode } from "react";
import type { KnowledgeProposal } from "./knowledgeApi";
import { StatusBadge } from "./StatusBadge";

export function MemoryProposalCard(props: {
  proposal: KnowledgeProposal;
  destination: string;
  meta?: ReactNode;
  currentContent?: string | null;
  origin?: ReactNode;
  existingHint?: boolean;
  acceptLabel: string;
  rejectLabel: string;
  busy?: boolean;
  onAccept: () => void;
  onReject: () => void;
  className?: string;
  headingClassName?: string;
  contentClassName?: string;
}) {
  const title = props.proposal.display_name || "Memory suggestion";
  const pending = props.proposal.status === "pending";
  return (
    <li className={props.className ?? "entity"}>
      <div className={props.headingClassName ?? "entity-head"}>
        <strong>{title}</strong>
        <StatusBadge label={props.proposal.status} />
      </div>
      <p className="hint">
        {props.destination}
        {props.meta}
        {props.proposal.automatic ? " · saved automatically" : ""}
      </p>
      {props.currentContent != null ? (
        <details>
          <summary>Current saved content</summary>
          <pre className={props.contentClassName ?? "wrapped-text"}>{props.currentContent}</pre>
        </details>
      ) : null}
      <pre className={props.contentClassName ?? "wrapped-text"}>{props.proposal.content}</pre>
      {props.origin ? <details><summary>Origin</summary><p className="hint">{props.origin}</p></details> : null}
      {props.existingHint ? <p className="hint">Updates an existing memory. A newer saved version will block acceptance.</p> : null}
      {pending ? (
        <div className="actions">
          <button type="button" disabled={props.busy} onClick={props.onAccept}>{props.acceptLabel}</button>
          <button type="button" disabled={props.busy} onClick={props.onReject}>{props.rejectLabel}</button>
        </div>
      ) : null}
    </li>
  );
}
