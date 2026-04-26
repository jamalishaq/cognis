import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChatMessage } from "./ChatMessage";
import type { ChatMessage as ChatMessageType } from "@/types";

const userMsg: ChatMessageType = {
  message_id: "MSG-001",
  incident_id: "INC-20240101-001",
  role: "user",
  content: "What is happening?",
  timestamp: "2024-01-01T10:00:00Z",
};

const assistantMsg: ChatMessageType = {
  message_id: "MSG-002",
  incident_id: "INC-20240101-001",
  role: "assistant",
  content: "The **connection pool** is exhausted.",
  timestamp: "2024-01-01T10:00:05Z",
};

describe("ChatMessage", () => {
  it("renders user message content", () => {
    render(<ChatMessage message={userMsg} />);
    expect(screen.getByText("What is happening?")).toBeInTheDocument();
  });

  it("renders assistant message through react-markdown", () => {
    render(<ChatMessage message={assistantMsg} />);
    const strong = screen.getByText("connection pool");
    expect(strong.tagName).toBe("STRONG");
  });

  it("user message is right-aligned", () => {
    const { container } = render(<ChatMessage message={userMsg} />);
    expect(container.firstChild).toHaveClass("justify-end");
  });

  it("assistant message is left-aligned", () => {
    const { container } = render(<ChatMessage message={assistantMsg} />);
    expect(container.firstChild).toHaveClass("justify-start");
  });
});
