import type { CSSProperties } from "react";
import { MessageCircle, Cpu, BookOpen, Workflow, FlaskConical, Library, SlidersHorizontal, Plus, ArrowUp, Square, ShieldCheck, Files, Ellipsis, X, Pencil, Archive, PanelLeft, PanelRight, Activity, Bell, Folder, Trash2, Search, RotateCcw, Maximize2, Minimize2, Info, Check, Terminal, Minus, Download, Copy, RefreshCw, Settings2, Sparkles, GitBranch, Brain, Navigation2 } from "lucide-react";

const icons = {
  chat: MessageCircle, models: Cpu, knowledge: BookOpen, "agent-run": Workflow,
  lab: FlaskConical, library: Library, settings: SlidersHorizontal, plus: Plus,
  send: ArrowUp, stop: Square, shield: ShieldCheck, files: Files, more: Ellipsis,
  close: X, edit: Pencil, archive: Archive, panel: PanelLeft, panelRight: PanelRight, activity: Activity, reasoning: Brain, steer: Navigation2,
  attention: Bell, folder: Folder, trash: Trash2, search: Search, restore: RotateCcw,
  expand: Maximize2, shrink: Minimize2, info: Info, check: Check, terminal: Terminal,
  minus: Minus, download: Download, copy: Copy, refresh: RefreshCw, tune: Settings2,
  sparkles: Sparkles, branch: GitBranch,
} as const;

export type IconName = keyof typeof icons;
function iconVariable(size: number): string {
  if (size <= 18) return "--icon-md";
  if (size <= 24) return "--icon-lg";
  return "--icon-xl";
}

export function Icon({ name, size = 20, style }: { name: IconName; size?: number; style?: CSSProperties }) {
  const Component = icons[name];
  const variable = iconVariable(size);
  return <Component size={size} strokeWidth={1.7} aria-hidden="true" focusable="false" style={{ width: `var(${variable})`, height: `var(${variable})`, strokeWidth: "var(--icon-stroke)", ...style }} />;
}
