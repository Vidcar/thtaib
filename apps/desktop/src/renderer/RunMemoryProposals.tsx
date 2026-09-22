import { useEffect, useRef, useState } from "react";
import { knowledgeApi, type KnowledgeProposal, type KnowledgeScopeOption } from "./knowledgeApi";
import { errorMessage } from "./errors";
import { MemoryProposalCard } from "./MemoryProposalCard";
import { Notice } from "./Notice";

export function RunMemoryProposals({ runId, status, onOpenKnowledge }: { runId: string; status: string; onOpenKnowledge: () => void }) {
  const [proposals, setProposals] = useState<KnowledgeProposal[]>([]);
  const [scopes, setScopes] = useState<KnowledgeScopeOption[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const pending = useRef(false);
  const generation = useRef(0);
  useEffect(() => {
    const owner = ++generation.current;
    setProposals([]); setError("");
    void Promise.all([knowledgeApi.proposals(runId), knowledgeApi.scopes()]).then(([next, nextScopes]) => { if (generation.current === owner) { setProposals(next); setScopes(nextScopes); } }).catch(failure => { if (generation.current === owner) setError(errorMessage(failure)); });
    return () => { generation.current += 1; };
  }, [runId, status, revision]);
  async function review(proposal: KnowledgeProposal, decision: "accept" | "reject") {
    if (pending.current) return;
    const owner = generation.current;
    pending.current = true; setBusy(true); setError("");
    try { const next = await knowledgeApi.review(proposal.id, decision); if (owner === generation.current) setProposals(current => current.map(item => item.id === next.id ? next : item)); }
    catch (failure) { if (owner === generation.current) setError(errorMessage(failure)); }
    finally { pending.current = false; setBusy(false); }
  }
  return <section className="file-changes-panel"><div className="file-changes-heading"><h4>Suggested memories</h4><button type="button" disabled={busy} onClick={() => setRevision(value => value + 1)}>Refresh suggestions</button></div>{error ? <Notice tone="error">{error}</Notice> : null}{proposals.length ? <ul className="plain-list">{proposals.map(proposal => <MemoryProposalCard key={proposal.id} proposal={proposal} className="file-change-detail" headingClassName="file-changes-heading" contentClassName="file-change-diff" destination={scopes.find(option => option.scope === proposal.scope && (option.scope_id ?? null) === (proposal.scope_id ?? null))?.label ?? "Unavailable destination"} existingHint={Boolean(proposal.entry_id)} acceptLabel="Accept memory" rejectLabel="Reject memory" busy={busy} onAccept={() => void review(proposal, "accept")} onReject={() => void review(proposal, "reject")} />)}</ul> : <p className="hint">No memory suggestions from this turn.</p>}<button type="button" onClick={onOpenKnowledge}>Open Knowledge</button></section>;
}
