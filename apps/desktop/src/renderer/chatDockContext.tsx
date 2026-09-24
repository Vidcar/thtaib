import { createContext, useContext } from "react";

export interface ChatDockControls {
  openFile: (path: string) => void;
}

export const ChatDockContext = createContext<ChatDockControls | null>(null);

export function useChatDock(): ChatDockControls | null {
  return useContext(ChatDockContext);
}
