import type { CSSProperties } from "react";
import { MessageCircle, Cpu, BookOpen, Workflow, FlaskConical, Library, SlidersHorizontal, Plus, ArrowUp, Square, ShieldCheck, Files, Ellipsis, X, Pencil, Archive, PanelLeft, Activity, Bell, Folder, Trash2, Search, RotateCcw, Maximize2, Minimize2, Info, Check, Terminal, Minus, Download, Copy, RefreshCw, Settings2, Sparkles, GitBranch } from "lucide-react";

const icons = {
  chat: MessageCircle, models: Cpu, knowledge: BookOpen, "agent-run": Workflow,
  lab: FlaskConical, library: Library, settings: SlidersHorizontal, plus: Plus,
  send: ArrowUp, stop: Square, shield: ShieldCheck, files: Files, more: Ellipsis,
  close: X, edit: Pencil, archive: Archive, panel: PanelLeft, activity: Activity,
  attention: Bell, folder: Folder, trash: Trash2, search: Search, restore: RotateCcw,
  expand: Maximize2, shrink: Minimize2, info: Info, check: Check, terminal: Terminal,
  minus: Minus, download: Download, copy: Copy, refresh: RefreshCw, tune: Settings2,
  sparkles: Sparkles, branch: GitBranch,
} as const;

export type IconName = keyof typeof icons;
export function Icon({ name, size = 20, style }: { name: IconName; size?: number; style?: CSSProperties }) {
  const Component = icons[name];
  return <Component size={size} strokeWidth={1.7} aria-hidden="true" focusable="false" style={style} />;
}
