import { useEffect, useMemo, useState, type KeyboardEvent as ReactKeyboardEvent, type MouseEvent as ReactMouseEvent, type RefObject } from "react";
import { createPortal } from "react-dom";
import { AttentionButton } from "./AttentionPanel";
import { api } from "./api";
import { ConversationRename } from "./ConversationRename";
import { areaKey, areaKind, areaLabel, newestConversationFirst } from "./conversationAreas";
import { DeleteChatDialog } from "./DeleteChatDialog";
import { conversationTitle, formatWhen } from "./display";
import { errorMessage } from "./errors";
import { Icon } from "./Icon";
import { PanelResize } from "./PanelResize";
import type { ChatConversation, WorkbenchTab } from "./types";
import { tabIcons, tabLabel, workbenchTabs } from "./workspaceNavigation";
import { workspaceApi, type ProjectRecord } from "./workspaceApi";

export interface ChatLaunch {
  id: string;
  kind: "fresh" | "open";
  conversationId?: string;
  conversation?: ChatConversation;
}

export interface ConversationListActions {
  forget: (id: string) => void;
}

export interface HistoryNotice {
  token: string;
  conversation?: ChatConversation;
  deletedId?: string;
  leave?: boolean;
}

export function WorkbenchSidebar(props: {
  tab: WorkbenchTab;
  collapsed: boolean;
  width: number;
  onCollapsedChange: (value: boolean) => void;
  onWidthChange: (value: number) => void;
  onNavigate: (tab: WorkbenchTab) => void;
  backendOk: boolean | null;
  backendStatus: string;
  activeConversationId: string | null;
  historyRevision: number;
  projectRevision: number;
  onOpenConversation: (conversation: ChatConversation) => void;
  conversationListRef?: RefObject<ConversationListActions | null>;
  onNewChat: () => void;
  onAddProject: () => void;
  onNewChatInProject?: (project: ProjectRecord) => void;
  onEditProject?: (projectId: string) => void;
  onProjectChanged?: () => void;
  onHistoryNotice: (notice: HistoryNotice) => void;
  onBeforeConversationChange?: () => Promise<unknown>;
  dotReady?: boolean;
  dotTitle?: string;
  onListsReady?: (ready: boolean) => void;
}) {
  const [conversations, setConversations] = useState<ChatConversation[]>([]);
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<ChatConversation[] | null>(null);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<ChatConversation | null>(null);
  const [listError, setListError] = useState("");
  const [chatsLoaded, setChatsLoaded] = useState(false);
  const [projectsLoaded, setProjectsLoaded] = useState(false);
  const [closedFolders, setClosedFolders] = useState<Set<string>>(() => new Set());
  const [projectMenu, setProjectMenu] = useState<{ projectId: string; x: number; y: number } | null>(null);

  useEffect(() => {
    if (!props.conversationListRef) return;
    props.conversationListRef.current = {
      forget: (id: string) => {
        setConversations(current => current.filter(item => item.id !== id));
        setSearchResults(current => current?.filter(item => item.id !== id) ?? null);
      },
    };
    return () => {
      if (props.conversationListRef) props.conversationListRef.current = null;
    };
  }, [props.conversationListRef]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      for (let attempt = 0; attempt < 30 && !cancelled; attempt += 1) {
        try {
          const next = await api.chatConversations(includeArchived);
          if (cancelled) return;
          setConversations(newestConversationFirst(next));
          setChatsLoaded(true);
          setListError("");
          return;
        } catch (error: unknown) {
          if (attempt === 29 && !cancelled) {
            setListError(errorMessage(error));
            setChatsLoaded(true);
            return;
          }
          await new Promise(resolve => setTimeout(resolve, 1000));
        }
      }
    })();
    return () => { cancelled = true; };
  }, [includeArchived, props.historyRevision]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      for (let attempt = 0; attempt < 30 && !cancelled; attempt += 1) {
        try {
          const next = await workspaceApi.projects();
          if (cancelled) return;
          setProjects(next);
          setProjectsLoaded(true);
          setListError("");
          return;
        } catch (error: unknown) {
          if (attempt === 29 && !cancelled) {
            setListError(errorMessage(error));
            setProjectsLoaded(true);
            return;
          }
          await new Promise(resolve => setTimeout(resolve, 1000));
        }
      }
    })();
    return () => { cancelled = true; };
  }, [props.projectRevision]);

  useEffect(() => {
    props.onListsReady?.(chatsLoaded && projectsLoaded);
  }, [chatsLoaded, projectsLoaded, props.onListsReady]);

  const searchableRevision = useMemo(() => conversations.map(item => `${item.id}:${item.title ?? ""}:${item.archived ? 1 : 0}`).join("|"), [conversations]);
  useEffect(() => {
    const query = searchQuery.trim();
    if (!query) { setSearchResults(null); return; }
    let cancelled = false;
    const timer = setTimeout(() => {
      void api.searchChatConversations(query, includeArchived).then(results => {
        if (!cancelled) setSearchResults(newestConversationFirst(results.map(item => item.conversation as ChatConversation)));
      }).catch((error: unknown) => { if (!cancelled) setListError(errorMessage(error)); });
    }, 250);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [includeArchived, searchQuery, searchableRevision]);

  const searching = searchQuery.trim().length > 0;
  const visible = (searchResults ?? conversations).filter(item => includeArchived || !item.archived);
  const searchMiss = searching && searchResults !== null && visible.length === 0;
  const loose = newestConversationFirst(visible.filter(item => areaKind(item) !== "project"));
  const projectChats = newestConversationFirst(visible.filter(item => areaKind(item) === "project"));
  const usedKeys = new Set<string>();
  const projectFolders = projects.map(project => {
    const items = projectChats.filter(item => chatInProject(item, project));
    usedKeys.add(project.id);
    items.forEach(item => usedKeys.add(areaKey(item)));
    return { key: project.id, label: project.name, missing: Boolean(project.missing), items, project };
  });
  const orphans = [...projectChats.reduce((groups, item) => {
    const key = areaKey(item);
    if (usedKeys.has(key)) return groups;
    groups.set(key, [...(groups.get(key) ?? []), item]);
    return groups;
  }, new Map<string, ChatConversation[]>()).entries()].map(([key, items]) => ({
    key,
    label: areaLabel(items[0] ?? null),
    missing: false,
    items,
    project: null as ProjectRecord | null,
  }));

  function chatInProject(item: ChatConversation, project: ProjectRecord): boolean {
    return item.project_id === project.id || item.area_id === project.id || areaKey(item) === project.id;
  }

  function notice(next: Omit<HistoryNotice, "token">) {
    props.onHistoryNotice({ token: crypto.randomUUID(), ...next });
  }

  function renderConversation(item: ChatConversation) {
    const active = item.id === props.activeConversationId;
    return (
      <li key={item.id}>
        <div className={item.archived ? "conversation-row archived" : "conversation-row"}>
          {renamingId === item.id ? <ConversationRename conversation={item} onRename={async title => {
            const next = await api.renameChatConversation(item.id, title);
            const replace = (current: ChatConversation[]) => current.map(value => value.id === next.id ? next : value);
            setConversations(replace);
            setSearchResults(current => current ? replace(current) : null);
            setRenamingId(null);
            notice({ conversation: next });
          }} onCancel={() => setRenamingId(null)} /> : <>
            <button type="button" className={active ? "nav-item active" : "nav-item"} title={`${conversationTitle(item)} · ${formatWhen(item.updated_at)}`} onClick={() => props.onOpenConversation(item)}>
              <span className="nav-item-title">{conversationTitle(item)}</span>
            </button>
            <div className="conversation-actions" aria-label={`${conversationTitle(item)} actions`}>
              <button type="button" className="icon-button" aria-label="Rename chat" title="Rename chat" onClick={() => setRenamingId(item.id)}><Icon name="edit" size={14} /></button>
              {item.archived ? (
                <button type="button" className="icon-button" aria-label="Reopen chat" title="Reopen chat" onClick={() => void changeArchive(item, false)}><Icon name="restore" size={14} /></button>
              ) : (
                <button type="button" className="icon-button" aria-label="Archive chat" title="Archive chat" onClick={() => void changeArchive(item, true)}><Icon name="archive" size={14} /></button>
              )}
              <button type="button" className="icon-button" aria-label="Delete chat" title="Delete chat" onClick={() => setDeleting(item)}><Icon name="trash" size={14} /></button>
            </div>
          </>}
        </div>
      </li>
    );
  }

  async function changeArchive(item: ChatConversation, archived: boolean) {
    try {
      if (props.activeConversationId === item.id) await props.onBeforeConversationChange?.();
      const next = archived ? await api.archiveChatConversation(item.id, true) : await api.reopenChatConversation(item.id);
      const replace = (current: ChatConversation[]) => current.map(value => value.id === next.id ? next : value);
      setConversations(replace);
      setSearchResults(current => current ? replace(current) : null);
      if (!archived) setIncludeArchived(true);
      notice({ conversation: next, leave: archived && props.activeConversationId === item.id && !includeArchived });
    } catch (error) {
      setListError(errorMessage(error));
    }
  }

  function openProjectMenu(event: ReactMouseEvent<HTMLElement> | ReactKeyboardEvent<HTMLElement>, projectId: string) {
    event.preventDefault();
    const box = event.currentTarget.getBoundingClientRect();
    const x = "clientX" in event ? event.clientX : box.left;
    const y = "clientY" in event ? event.clientY : box.bottom;
    setProjectMenu({
      projectId,
      x: Math.max(8, Math.min(x, window.innerWidth - 240)),
      y: Math.max(8, Math.min(y, window.innerHeight - 150)),
    });
  }

  async function archiveProjectChats(project: ProjectRecord) {
    const targets = conversations.filter(item => chatInProject(item, project) && !item.archived);
    setProjectMenu(null);
    if (!targets.length) return;
    if (!window.confirm(`Archive every chat in ${project.name}? They stay saved and can be shown again.`)) return;
    try {
      if (targets.some(item => item.id === props.activeConversationId)) await props.onBeforeConversationChange?.();
      const nextItems: ChatConversation[] = [];
      for (const item of targets) nextItems.push(await api.archiveChatConversation(item.id, true));
      const byId = new Map(nextItems.map(item => [item.id, item]));
      const replace = (current: ChatConversation[]) => current.map(item => byId.get(item.id) ?? item);
      setConversations(replace);
      setSearchResults(current => current ? replace(current) : null);
      const active = nextItems.find(item => item.id === props.activeConversationId);
      notice(active ? { conversation: active, leave: !includeArchived } : { conversation: nextItems[0] });
    } catch (error) {
      setListError(errorMessage(error));
    }
  }

  async function removeFromSidebar(project: ProjectRecord) {
    setProjectMenu(null);
    if (!window.confirm(`Remove ${project.name} from the sidebar? The folder stays on disk.`)) return;
    try {
      await workspaceApi.removeProject(project.id);
      setProjects(current => current.filter(item => item.id !== project.id));
      props.onProjectChanged?.();
    } catch (error) {
      setListError(errorMessage(error));
    }
  }

  useEffect(() => {
    if (!projectMenu) return;
    function close(event: MouseEvent) {
      const target = event.target;
      if (target instanceof Node && document.querySelector(".project-menu")?.contains(target)) return;
      setProjectMenu(null);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setProjectMenu(null);
    }
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", onKey);
    };
  }, [projectMenu]);

  const menuProject = projects.find(project => project.id === projectMenu?.projectId) ?? null;

  return (
    <aside className="app-nav" aria-label="Workbench">
      {deleting ? <DeleteChatDialog key={deleting.id} conversation={deleting} onClose={() => setDeleting(null)} onDeleted={id => { setConversations(current => current.filter(item => item.id !== id)); notice({ deletedId: id }); }} /> : null}
      <div className="app-nav-head">
        <div><h1>Workbench</h1></div>
        <button type="button" className="nav-collapse" aria-label={props.collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!props.collapsed} onClick={() => props.onCollapsedChange(!props.collapsed)}>
          <Icon name="panel" size={18} />
        </button>
      </div>
      <button type="button" className="new-chat-button" aria-label="New chat" title="New chat" onClick={props.onNewChat}><Icon name="edit" size={18} /><span>New chat</span></button>
      <div className="sidebar-tools">
        <label className="chat-search">
          <span className="sr-only">Search chats</span><Icon name="search" size={15} />
          <input value={searchQuery} onChange={event => setSearchQuery(event.target.value)} placeholder="Search chats" />
        </label>
        <button type="button" className="icon-button" aria-label="Add project" title="New project" onClick={props.onAddProject}><Icon name="plus" size={14} /></button>
        <label className="archive-filter" title="Include archived chats"><input type="checkbox" aria-label="Show archived" checked={includeArchived} onChange={event => setIncludeArchived(event.target.checked)} /><Icon name="archive" size={14} /></label>
      </div>
      <nav className="side-tabs" aria-label="Destinations">
        {workbenchTabs.map(item => item === "attention" ? <AttentionButton key={item} active={props.tab === item} collapsed={props.collapsed} onOpen={() => props.onNavigate("attention")} /> : (
          <button key={item} type="button" className={item === props.tab ? "tab destination-current" : "tab"} aria-label={tabLabel(item)} title={tabLabel(item)} onClick={() => props.onNavigate(item)}>
            <Icon name={tabIcons[item]} size={18} />
            {props.collapsed ? <span className="sr-only">{tabLabel(item)}</span> : <span>{tabLabel(item)}</span>}
          </button>
        ))}
      </nav>
      <div className="sidebar-scroll">
        {listError ? <p className="hint">{listError}</p> : null}
        {searchMiss ? <p className="hint">No matching conversations</p> : null}
        <div className="chat-groups">
          {[...projectFolders, ...orphans].map(folder => {
            const open = !closedFolders.has(folder.key);
            const project = folder.project;
            return (
              <section key={folder.key} className="chat-group">
                <div className="chat-group-row" onContextMenu={project ? event => openProjectMenu(event, project.id) : undefined}>
                  <button type="button" className="chat-group-toggle" aria-expanded={open} onClick={() => setClosedFolders(current => { const next = new Set(current); if (next.has(folder.key)) next.delete(folder.key); else next.add(folder.key); return next; })} onKeyDown={project ? event => { if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) openProjectMenu(event, project.id); } : undefined}>
                    <Icon name="folder" size={14} />
                    <span>{folder.label}{folder.missing ? " · folder unavailable" : ""}</span>
                  </button>
                  {project ? <button type="button" className="icon-button" aria-label={`New chat in ${folder.label}`} title={`New chat in ${folder.label}`} disabled={folder.missing} onClick={() => props.onNewChatInProject?.(project)}><Icon name="plus" size={14} /></button> : null}
                </div>
                {open ? folder.items.length ? <ul className="nav-list">{folder.items.map(renderConversation)}</ul> : chatsLoaded ? <p className="hint">No chats yet</p> : null : null}
              </section>
            );
          })}
          {!searchMiss && projectsLoaded && !projectFolders.length && !orphans.length ? <p className="hint">No projects yet</p> : null}
        </div>
        <section className="sidebar-loose" aria-label="No project">
          <h3>No project</h3>
          {searchMiss ? null : loose.length ? <ul className="nav-list">{loose.map(renderConversation)}</ul> : chatsLoaded ? <p className="hint">No chats yet</p> : null}
        </section>
      </div>
      {menuProject && projectMenu ? createPortal(
        <div className="project-menu" role="menu" style={{ top: projectMenu.y, left: projectMenu.x }}>
          <button type="button" role="menuitem" onClick={() => { setProjectMenu(null); props.onEditProject?.(menuProject.id); }}><Icon name="edit" size={15} />Edit project</button>
          <button type="button" role="menuitem" disabled={!conversations.some(item => chatInProject(item, menuProject) && !item.archived)} onClick={() => void archiveProjectChats(menuProject)}><Icon name="archive" size={15} />Archive chats</button>
          <button type="button" role="menuitem" onClick={() => void removeFromSidebar(menuProject)}><Icon name="close" size={15} />Remove from sidebar</button>
        </div>,
        document.body,
      ) : null}
      <div className="service-indicator" title={props.dotTitle ?? props.backendStatus}><span className={`status-dot${props.dotReady ? " ready" : ""}`} /><span>{props.backendOk === false ? "Service unavailable" : "Local"}</span></div>
      {!props.collapsed ? <PanelResize label="Resize navigation" width={props.width} onResize={props.onWidthChange} reset={232} /> : null}
    </aside>
  );
}
