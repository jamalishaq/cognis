import { useCallback } from "react";
import { api } from "@/lib/api";
import { useIncidentStore } from "@/store/incidentStore";
import type { ChatMessage } from "@/types";

function makeTempId() {
  return `MSG-${Date.now()}`;
}

export function useChat(incident_id: string) {
  const { appendMessage, updateLastMessage, setIsStreaming, isStreaming } = useIncidentStore();

  const sendMessage = useCallback(
    async (content: string) => {
      if (isStreaming || !content.trim()) return;

      const userMessage: ChatMessage = {
        message_id: makeTempId(),
        incident_id,
        role: "user",
        content,
        timestamp: new Date().toISOString(),
      };
      appendMessage(userMessage);

      const assistantMessage: ChatMessage = {
        message_id: makeTempId(),
        incident_id,
        role: "assistant",
        content: "",
        timestamp: new Date().toISOString(),
      };
      appendMessage(assistantMessage);
      setIsStreaming(true);

      try {
        const stream = await api.chatStream(incident_id, content);
        const reader = stream.getReader();
        const decoder = new TextDecoder();
        let accumulated = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          accumulated += decoder.decode(value, { stream: true });
          updateLastMessage(accumulated);
        }
      } catch {
        updateLastMessage("Unable to process your request, please try again.");
      } finally {
        setIsStreaming(false);
      }
    },
    [incident_id, isStreaming, appendMessage, updateLastMessage, setIsStreaming],
  );

  return { sendMessage, isStreaming };
}
