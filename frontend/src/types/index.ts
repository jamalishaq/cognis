export type Severity = "critical" | "high" | "medium" | "low" | "unknown";
export type IncidentStatus = "open" | "resolved";
export type MessageRole = "user" | "assistant";

export interface IncidentBrief {
  incident_id: string;
  title: string;
  summary: string;
  severity: Severity;
  affected_service: string;
  failure_class: string;
  recommended_actions: string[];
  runbook_references: string[];
  retrieval_context_available: boolean;
  created_at: string;
}

export interface IncidentRecord extends IncidentBrief {
  status: IncidentStatus;
  resolved_at: string | null;
  resolution_notes: string | null;
  resolved_by: string | null;
}

export interface ChatMessage {
  message_id: string;
  incident_id: string;
  role: MessageRole;
  content: string;
  timestamp: string;
}

export interface ChatHistoryResponse {
  incident_id: string;
  messages: ChatMessage[];
}

export interface ChatRequest {
  incident_id: string;
  message: string;
}

export interface ResolveRequest {
  incident_id: string;
  resolution_notes: string;
  resolved_by: string | null;
}

export interface ResolveResponse {
  incident_id: string;
  status: "resolved";
  resolved_at: string;
  message: string;
}
