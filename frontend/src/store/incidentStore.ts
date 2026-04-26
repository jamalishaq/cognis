import { create } from "zustand";
import type { ChatMessage, IncidentRecord } from "@/types";

interface IncidentState {
  currentIncident: IncidentRecord | null;
  messages: ChatMessage[];
  isStreaming: boolean;
  setCurrentIncident: (incident: IncidentRecord) => void;
  setMessages: (messages: ChatMessage[]) => void;
  appendMessage: (message: ChatMessage) => void;
  updateLastMessage: (content: string) => void;
  setIsStreaming: (streaming: boolean) => void;
  reset: () => void;
}

export const useIncidentStore = create<IncidentState>((set) => ({
  currentIncident: null,
  messages: [],
  isStreaming: false,

  setCurrentIncident: (incident) => set({ currentIncident: incident }),

  setMessages: (messages) => set({ messages }),

  appendMessage: (message) =>
    set((state) => ({ messages: [...state.messages, message] })),

  updateLastMessage: (content) =>
    set((state) => {
      const messages = [...state.messages];
      const last = messages[messages.length - 1];
      if (last) messages[messages.length - 1] = { ...last, content };
      return { messages };
    }),

  setIsStreaming: (isStreaming) => set({ isStreaming }),

  reset: () => set({ currentIncident: null, messages: [], isStreaming: false }),
}));
