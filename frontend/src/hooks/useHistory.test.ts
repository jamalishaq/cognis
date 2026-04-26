import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import React from "react";
import { useHistory } from "./useHistory";
import { mockHistory, mockIncident } from "@/test/fixtures";
import { API_BASE_URL } from "@/lib/api";

const server = setupServer(
  http.get(`${API_BASE_URL}/incidents/:incident_id/history`, ({ params }) => {
    if (params.incident_id === mockIncident.incident_id) {
      return HttpResponse.json(mockHistory);
    }
    return HttpResponse.json({ detail: "incident_not_found" }, { status: 404 });
  }),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function makeWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

describe("useHistory", () => {
  it("fetches and returns chat history", async () => {
    const { result } = renderHook(() => useHistory(mockIncident.incident_id), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.messages).toHaveLength(2);
    expect(result.current.data?.messages[0].role).toBe("user");
    expect(result.current.data?.messages[1].role).toBe("assistant");
  });

  it("returns error on 404", async () => {
    const { result } = renderHook(() => useHistory("INC-99999999-999"), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("is disabled when incident_id is empty", () => {
    const { result } = renderHook(() => useHistory(""), {
      wrapper: makeWrapper(),
    });

    expect(result.current.fetchStatus).toBe("idle");
  });
});
