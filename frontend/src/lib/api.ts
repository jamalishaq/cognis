import type { ChatHistoryResponse, IncidentRecord, ResolveRequest, ResolveResponse } from "@/types";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL as string ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail?.detail?.message ?? detail?.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  getIncident: (incident_id: string) =>
    request<IncidentRecord>(`/incidents/${incident_id}`),

  getHistory: (incident_id: string) =>
    request<ChatHistoryResponse>(`/incidents/${incident_id}/history`),

  resolveIncident: (incident_id: string, body: ResolveRequest) =>
    request<ResolveResponse>(`/incidents/${incident_id}/resolve`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  chatStream: (incident_id: string, message: string): Promise<ReadableStream<Uint8Array>> =>
    fetch(`${API_BASE_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ incident_id, message }),
    }).then((res) => {
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
      return res.body;
    }),
};
