import { useRef, useEffect, useState, type KeyboardEvent } from "react";
import { Send } from "lucide-react";
import { ChatMessage } from "./ChatMessage";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useChat } from "@/hooks/useChat";
import { useIncidentStore } from "@/store/incidentStore";

interface ChatWindowProps {
  incident_id: string;
}

export function ChatWindow({ incident_id }: ChatWindowProps) {
  const messages = useIncidentStore((s) => s.messages);
  const isStreaming = useIncidentStore((s) => s.isStreaming);
  const { sendMessage } = useChat(incident_id);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput("");
    await sendMessage(text);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full rounded-lg border bg-card">
      <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-0">
        {messages.length === 0 && (
          <p className="text-center text-sm text-muted-foreground pt-8">
            Ask the AI assistant about this incident.
          </p>
        )}
        {messages.map((msg) => (
          <ChatMessage key={msg.message_id} message={msg} />
        ))}
        {isStreaming && (
          <div className="flex justify-start">
            <div className="bg-secondary rounded-lg px-4 py-3">
              <span className="inline-flex gap-1">
                <span className="animate-bounce delay-0">·</span>
                <span className="animate-bounce delay-150">·</span>
                <span className="animate-bounce delay-300">·</span>
              </span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="border-t p-4 flex gap-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about this incident…"
          disabled={isStreaming}
          className="flex-1"
          aria-label="Chat input"
        />
        <Button
          onClick={() => void handleSend()}
          disabled={isStreaming || !input.trim()}
          size="icon"
          aria-label="Send message"
        >
          <Send className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
