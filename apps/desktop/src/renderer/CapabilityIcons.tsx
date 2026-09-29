import type { ReactNode } from "react";
import { HoverHelp } from "./HoverHelp";
import { Icon, type IconName } from "./Icon";

export type CapabilityIconState = "absent" | "untested" | "passed" | "failed" | "inconclusive";

export type CapabilityIconItem = {
  id: string;
  label: string;
  icon: IconName;
  state: CapabilityIconState;
  detail: ReactNode;
  onRetest?: () => void;
  retestDisabled?: boolean;
  retesting?: boolean;
};

export function CapabilityIconRow({ items, label = "Capabilities" }: { items: CapabilityIconItem[]; label?: string }) {
  return <div className="capability-icons" role="list" aria-label={label}>{items.map(item => <span key={item.id} role="listitem">
    <HoverHelp title={item.label} interactive={Boolean(item.onRetest)} triggerClassName="capability-icon" triggerContent={<span className="capability-icon-mark" data-state={item.state}><Icon name={item.icon} size={16} /></span>}>
      <div className="capability-icon-detail"><p>{item.detail}</p>{item.onRetest ? <button type="button" disabled={item.retestDisabled} onClick={item.onRetest}>{item.retesting ? "Checking…" : "Retest"}</button> : null}</div>
    </HoverHelp>
  </span>)}</div>;
}
