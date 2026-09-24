import { useEffect, useMemo, useState } from "react";

import { interruptCommand } from "./display";
import { PathBrowseButton } from "./PathField";
import type { PendingInterrupt, PendingInterruptAction, UserQuestion } from "./types";

type ApprovalScope = "once" | "session" | "always";
type Decision =
  | { type: "approve"; scope: ApprovalScope }
  | { type: "reject"; scope: "once"; message?: string }
  | { type: "respond"; message: string };

export type InterruptResponsePayload = { decisions: Decision[] };

function actionTitle(action: PendingInterruptAction): string {
  return action.description?.trim() || action.name;
}

function actionWorkingFolder(action: PendingInterruptAction): string | null {
  const cwd = action.args.cwd ?? action.args.working_directory ?? action.args.workdir;
  return typeof cwd === "string" && cwd.trim() ? cwd : null;
}

function defaultDecision(action: PendingInterruptAction): Decision {
  if (action.question && action.allowed_decisions.includes("respond")) return { type: "respond", message: "" };
  return action.allowed_decisions.includes("approve") ? { type: "approve", scope: "once" } : { type: "reject", scope: "once" };
}

function answerTypeLabel(question: UserQuestion): string {
  switch (question.answer_type) {
    case "choice": return "Choose an answer";
    case "file": return "Select a file";
    case "folder": return "Select a folder";
    case "text": return "Answer";
  }
}

function NativePathSelector(props: {
  answerType: "file" | "folder";
  busy?: boolean;
  onSelect: (selected: string) => void;
}) {
  return <PathBrowseButton kind={props.answerType} label="Browse" disabled={props.busy} onPicked={props.onSelect} />;
}

export function InterruptApproval(props: {
  pending: PendingInterrupt;
  ownerLabel?: string;
  busy?: boolean;
  onRespond: (payload: InterruptResponsePayload) => void;
}) {
  const { pending, busy, onRespond } = props;
  const decisionSignature = useMemo(
    () => pending.action_requests.map(action => `${action.name}:${action.allowed_decisions.join(",")}:${action.question?.prompt ?? ""}`).join("|"),
    [pending.action_requests],
  );
  const [decisions, setDecisions] = useState<Decision[]>(pending.action_requests.map(defaultDecision));

  useEffect(() => {
    setDecisions(pending.action_requests.map(defaultDecision));
  }, [decisionSignature, pending.identity, pending.interrupt_id]);

  function choose(index: number, decision: Decision) {
    setDecisions(current => current.map((item, itemIndex) => itemIndex === index ? decision : item));
  }

  const canSend = !busy && decisions.length === pending.action_requests.length && pending.action_requests.every((action, index) => {
    const decision = decisions[index];
    return decision && action.allowed_decisions.includes(decision.type) && (decision.type !== "respond" || Boolean(decision.message.trim()));
  });

  return (
    <div className="approval-card" role="alertdialog" aria-labelledby="approval-title">
      <h3 id="approval-title">Review requested actions{props.ownerLabel ? ` · ${props.ownerLabel}` : ""}</h3>
      <p className="notice notice-warn">Choose a decision for each action. Saved permissions apply only to matching future actions with the same recorded scope.</p>
      <ol className="plain-list">
        {pending.action_requests.map((action, index) => {
          const command = interruptCommand(action);
          const workingFolder = actionWorkingFolder(action);
          const decision = decisions[index] ?? defaultDecision(action);
          const question = action.question;
          return (
            <li key={`${action.name}-${index}`} className="approval-action">
              <strong>{index + 1}. {question ? answerTypeLabel(question) : actionTitle(action)}</strong>
              {question ? (
                <>
                  <p>{question.prompt}</p>
                  <p className="hint">An answer does not grant file, folder, or tool access.</p>
                  {question.answer_type === "choice" ? (
                    <fieldset className="choice-set">
                      <legend>Choices</legend>
                      {question.choices.map(choice => (
                        <label key={choice} className="check-row">
                          <input type="radio" name={`question-${index}`} checked={decision.type === "respond" && decision.message === choice} disabled={busy} onChange={() => choose(index, { type: "respond", message: choice })} />
                          {choice}
                        </label>
                      ))}
                    </fieldset>
                  ) : (
                    <label>{answerTypeLabel(question)}
                      <input value={decision.type === "respond" ? decision.message : ""} disabled={busy || decision.type === "reject"} onChange={event => choose(index, { type: "respond", message: event.target.value })} />
                    </label>
                  )}
                  {(question.answer_type === "file" || question.answer_type === "folder") && decision.type !== "reject" ? (
                    <NativePathSelector answerType={question.answer_type} busy={busy} onSelect={selected => choose(index, { type: "respond", message: selected })} />
                  ) : null}
                  {action.allowed_decisions.includes("reject") ? (
                    <label className="check-row"><input type="checkbox" checked={decision.type === "reject"} disabled={busy} onChange={event => choose(index, event.target.checked ? { type: "reject", scope: "once", message: "The user cancelled this question. Do not repeat it unless asked." } : { type: "respond", message: "" })} />Cancel this question</label>
                  ) : null}
                </>
              ) : (
                <>
                  {workingFolder ? <p className="hint">Working folder: <code>{workingFolder}</code></p> : null}
                  {command ? <pre className="command">{command}</pre> : null}
                  {!command && Object.keys(action.args).length > 0 ? (
                    <dl className="meta compact">{Object.entries(action.args).map(([key, value]) => (
                      <div key={key}><dt>{key}</dt><dd><code>{typeof value === "string" ? value : JSON.stringify(value)}</code></dd></div>
                    ))}</dl>
                  ) : null}
                  <fieldset className="choice-set">
                    <legend>Decision for action {index + 1}</legend>
                    {action.allowed_decisions.includes("approve") ? (
                      <>
                        {(["once", "session", "always"] as const).map(scope => <label key={scope} className="check-row">
                          <input type="radio" name={`decision-${index}`} checked={decision.type === "approve" && decision.scope === scope} disabled={busy} onChange={() => choose(index, { type: "approve", scope })} />
                          {scope === "once" ? "Approve once" : scope === "session" ? "Allow for this session" : "Always allow"}
                        </label>)}
                      </>
                    ) : null}
                    {action.allowed_decisions.includes("reject") ? (
                      <label className="check-row"><input type="radio" name={`decision-${index}`} checked={decision.type === "reject"} disabled={busy} onChange={() => choose(index, { type: "reject", scope: "once" })} />Reject</label>
                    ) : null}
                  </fieldset>
                </>
              )}
            </li>
          );
        })}
      </ol>
      <div className="actions"><button type="button" disabled={!canSend} onClick={() => onRespond({ decisions })}>Send decisions</button></div>
    </div>
  );
}
