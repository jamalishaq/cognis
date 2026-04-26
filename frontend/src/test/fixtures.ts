import type { ChatHistoryResponse, ChatMessage, IncidentRecord } from "@/types";

export const mockIncident: IncidentRecord = {
  incident_id: "INC-20240101-001",
  title: "High error rate on payment-service",
  summary: "Connection pool exhaustion causing cascading failures in payment-service",
  severity: "critical",
  affected_service: "payment-service",
  failure_class: "resource_exhaustion",
  recommended_actions: ["Scale the connection pool", "Check upstream dependencies"],
  runbook_references: ["runbooks/payment-service.md"],
  retrieval_context_available: true,
  created_at: "2024-01-01T10:00:00Z",
  status: "open",
  resolved_at: null,
  resolution_notes: null,
  resolved_by: null,
};

export const mockMessages: ChatMessage[] = [
  {
    message_id: "MSG-001",
    incident_id: "INC-20240101-001",
    role: "user",
    content: "What is causing this?",
    timestamp: "2024-01-01T10:01:00Z",
  },
  {
    message_id: "MSG-002",
    incident_id: "INC-20240101-001",
    role: "assistant",
    content: "The connection pool is exhausted due to a recent deployment.",
    timestamp: "2024-01-01T10:01:05Z",
  },
];

export const mockHistory: ChatHistoryResponse = {
  incident_id: "INC-20240101-001",
  messages: mockMessages,
};
