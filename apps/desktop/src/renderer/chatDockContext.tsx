import { createContext, useContext } from "react";
import type { ObservedFileChange } from "./activityLine";

export interface ChatDockControls {
  fileChanges: ObservedFileChange[];
  openChange: (changeId: string) => void;
  openFile: (path: string) => void;
}

export const ChatDockContext = createContext<ChatDockControls | null>(null);

export function useChatDock(): ChatDockControls | null {
  return useContext(ChatDockContext);
}
