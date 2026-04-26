import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { useChat } from "./useChat";
import { useIncidentStore } from "@/store/incidentStore";
import { API_BASE_URL } from "@/lib/api";

const INCIDENT_ID = "INC-20240101-001";

const server = setupServer(
  http.post(`${API_BASE_URL}/chat`, async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode("Hello "));
        controller.enqueue(encoder.encode("world"));
        controller.close();
      },
    });
    return new HttpResponse(stream, {
      headers: { "Content-Type": "text/plain" },
    });
  }),
);

beforeAll(() => server.listen());
afterEach(() => {
  server.resetHandlers();
  useIncidentStore.getState().reset();
});
afterAll(() => server.close());

describe("useChat", () => {
  it("appends user and assistant messages on sendMessage", async () => {
    const { result } = renderHook(() => useChat(INCIDENT_ID));

    await act(async () => {
      await result.current.sendMessage("What is happening?");
    });

    const messages = useIncidentStore.getState().messages;
    expect(messages).toHaveLength(2);
    expect(messages[0].role).toBe("user");
    expect(messages[0].content).toBe("What is happening?");
    expect(messages[1].role).toBe("assistant");
    expect(messages[1].content).toBe("Hello world");
  });

  it("does not send when already streaming", async () => {
    useIncidentStore.getState().setIsStreaming(true);
    const { result } = renderHook(() => useChat(INCIDENT_ID));

    await act(async () => {
      await result.current.sendMessage("ignored");
    });

    expect(useIncidentStore.getState().messages).toHaveLength(0);
  });

  it("does not send empty messages", async () => {
    const { result } = renderHook(() => useChat(INCIDENT_ID));

    await act(async () => {
      await result.current.sendMessage("   ");
    });

    expect(useIncidentStore.getState().messages).toHaveLength(0);
  });

  it("shows error message on stream failure", async () => {
    server.use(
      http.post(`${API_BASE_URL}/chat`, () => {
        return HttpResponse.error();
      }),
    );

    const { result } = renderHook(() => useChat(INCIDENT_ID));

    await act(async () => {
      await result.current.sendMessage("trigger error");
    });

    const messages = useIncidentStore.getState().messages;
    expect(messages[1].content).toContain("Unable to process");
    expect(useIncidentStore.getState().isStreaming).toBe(false);
  });

  it("resets isStreaming after completion", async () => {
    const { result } = renderHook(() => useChat(INCIDENT_ID));

    await act(async () => {
      await result.current.sendMessage("test");
    });

    expect(useIncidentStore.getState().isStreaming).toBe(false);
  });
});
