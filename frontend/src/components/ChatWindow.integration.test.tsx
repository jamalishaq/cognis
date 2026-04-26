import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { ChatWindow } from "./ChatWindow";
import { useIncidentStore } from "@/store/incidentStore";
import { API_BASE_URL } from "@/lib/api";

const INCIDENT_ID = "INC-20240101-001";

const server = setupServer(
  http.post(`${API_BASE_URL}/chat`, async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode("AI response here"));
        controller.close();
      },
    });
    return new HttpResponse(stream, { headers: { "Content-Type": "text/plain" } });
  }),
);

beforeAll(() => server.listen());
afterEach(() => {
  server.resetHandlers();
  useIncidentStore.getState().reset();
});
afterAll(() => server.close());

describe("ChatWindow", () => {
  it("renders the empty state prompt", () => {
    render(<ChatWindow incident_id={INCIDENT_ID} />);
    expect(screen.getByText(/Ask the AI assistant/i)).toBeInTheDocument();
  });

  it("renders the chat input and send button", () => {
    render(<ChatWindow incident_id={INCIDENT_ID} />);
    expect(screen.getByRole("textbox", { name: /chat input/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /send message/i })).toBeInTheDocument();
  });

  it("send button is disabled when input is empty", () => {
    render(<ChatWindow incident_id={INCIDENT_ID} />);
    expect(screen.getByRole("button", { name: /send message/i })).toBeDisabled();
  });

  it("sends a message and appends it on Enter key", async () => {
    render(<ChatWindow incident_id={INCIDENT_ID} />);
    const input = screen.getByRole("textbox", { name: /chat input/i });
    fireEvent.change(input, { target: { value: "What is wrong?" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => {
      expect(screen.getByText("What is wrong?")).toBeInTheDocument();
    });
  });

  it("renders existing messages from the store", () => {
    useIncidentStore.getState().setMessages([
      {
        message_id: "MSG-001",
        incident_id: INCIDENT_ID,
        role: "user",
        content: "Previous message",
        timestamp: "2024-01-01T10:00:00Z",
      },
    ]);
    render(<ChatWindow incident_id={INCIDENT_ID} />);
    expect(screen.getByText("Previous message")).toBeInTheDocument();
  });
});
