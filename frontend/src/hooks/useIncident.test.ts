import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import React from "react";
import { useIncident } from "./useIncident";
import { mockIncident } from "@/test/fixtures";
import { API_BASE_URL } from "@/lib/api";

const server = setupServer(
  http.get(`${API_BASE_URL}/incidents/:incident_id`, ({ params }) => {
    if (params.incident_id === mockIncident.incident_id) {
      return HttpResponse.json(mockIncident);
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

describe("useIncident", () => {
  it("fetches and returns an incident", async () => {
    const { result } = renderHook(() => useIncident(mockIncident.incident_id), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.incident_id).toBe(mockIncident.incident_id);
    expect(result.current.data?.severity).toBe("critical");
  });

  it("returns error on 404", async () => {
    const { result } = renderHook(() => useIncident("INC-99999999-999"), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("is disabled when incident_id is empty", () => {
    const { result } = renderHook(() => useIncident(""), {
      wrapper: makeWrapper(),
    });

    expect(result.current.fetchStatus).toBe("idle");
  });
});
