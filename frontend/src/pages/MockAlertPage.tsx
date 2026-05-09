import { useState } from "react";
import { Button } from "@/components/ui/button";
import { API_BASE_URL } from "@/lib/api";

type AlertSource = "grafana" | "pagerduty" | "generic";

interface AnalyseResponse {
  incident_id: string;
}

const PAYLOADS: Record<AlertSource, unknown> = {
  grafana: {
    alerts: [
      {
        status: "firing",
        labels: {
          alertname: "HighLatency",
          severity: "critical",
          service: "payments-api",
          namespace: "production",
          instance: "payments-api-7d9f8b-xk2p",
        },
        annotations: {
          description:
            "p99 latency for payments-api has exceeded 2000ms for the past 5 minutes",
          summary: "High latency detected on payments-api",
        },
        startsAt: "2026-04-23T10:15:00Z",
        endsAt: "0001-01-01T00:00:00Z",
        generatorURL: "http://grafana.internal/alerting/payments-latency",
      },
    ],
    version: "4",
    groupKey: "{}:{alertname=HighLatency}",
    status: "firing",
    receiver: "cognis-webhook",
  },

  pagerduty: {
    messages: [
      {
        type: "trigger",
        data: {
          incident: {
            id: "P1234567",
            title: "High latency on payments-api",
            status: "triggered",
            urgency: "high",
            severity: "critical",
            service: { id: "SVC001", name: "payments-api" },
            body: {
              details:
                "p99 latency exceeded 2000ms threshold. Active DB connections at 98 of 100.",
            },
            created_at: "2026-04-23T10:15:00Z",
          },
        },
      },
    ],
  },

  generic: {
    service: "payments-api",
    severity: "critical",
    alert_name: "HighLatency",
    description:
      "p99 latency exceeded 2000ms for the past 5 minutes. Active DB connections at 98 of 100.",
    triggered_at: "2026-04-23T10:15:00Z",
    metadata: {
      region: "us-east-1",
      cluster: "prod-eks",
      namespace: "production",
    },
  },
};

const SOURCE_LABELS: Record<AlertSource, string> = {
  grafana: "Grafana / Alertmanager",
  pagerduty: "PagerDuty",
  generic: "Generic",
};

export function MockAlertPage() {
  const [source, setSource] = useState<AlertSource>("grafana");
  const [loading, setLoading] = useState(false);
  const [incidentId, setIncidentId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setIncidentId(null);
    setError(null);

    try {
      const res = await fetch(`${API_BASE_URL}/analyse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(PAYLOADS[source]),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        const detail =
          (data as Record<string, unknown>)?.detail;
        const msg =
          typeof detail === "object" && detail !== null
            ? JSON.stringify(detail)
            : String(detail ?? `HTTP ${res.status}`);
        setError(`${res.status}: ${msg}`);
      } else {
        setIncidentId((data as AnalyseResponse).incident_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Network error");
    } finally {
      setLoading(false);
    }
  }

  function handleCopy() {
    if (!incidentId) return;
    navigator.clipboard.writeText(incidentId).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="min-h-screen p-4 md:p-8 max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-lg font-semibold">
          Cognis Mock Alert Firing{" "}
          <span className="text-xs font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full bg-amber-950 text-amber-400 border border-amber-800 ml-2 align-middle">
            Demo Only
          </span>
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          POST a hardcoded alert payload to the backend /analyse endpoint and
          inspect the response.
        </p>
      </div>

      <div className="rounded-md border bg-card p-6 space-y-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Fire Alert
        </p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="source" className="text-sm font-medium">
              Alert Source
            </label>
            <select
              id="source"
              value={source}
              onChange={(e) => setSource(e.target.value as AlertSource)}
              className="w-full bg-background border border-input rounded-md text-sm px-3 py-2 text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {(Object.keys(PAYLOADS) as AlertSource[]).map((s) => (
                <option key={s} value={s}>
                  {SOURCE_LABELS[s]}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <p className="text-sm font-medium">Payload Preview</p>
            <pre className="bg-background border border-input rounded-md p-3 text-xs font-mono text-muted-foreground overflow-y-auto max-h-52">
              {JSON.stringify(PAYLOADS[source], null, 2)}
            </pre>
          </div>

          <Button type="submit" disabled={loading}>
            {loading ? "Firing…" : "Fire Alert"}
          </Button>
        </form>
      </div>

      {incidentId && (
        <div className="rounded-md border bg-card p-6 space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Result
          </p>
          <div className="flex items-center gap-3 rounded-md bg-green-950/40 border border-green-800/50 px-4 py-3">
            <span className="text-xs font-semibold uppercase tracking-wide text-green-400 flex-shrink-0">
              Incident ID
            </span>
            <span className="font-mono text-base font-bold text-green-300 flex-grow tracking-wide">
              {incidentId}
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleCopy}
              className="flex-shrink-0"
            >
              {copied ? "Copied!" : "Copy"}
            </Button>
          </div>
        </div>
      )}

      {error && (
        <div className="rounded-md border bg-card p-6 space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Result
          </p>
          <div className="rounded-md bg-destructive/10 border border-destructive/50 px-4 py-3 font-mono text-sm text-destructive">
            {error}
          </div>
        </div>
      )}
    </div>
  );
}
