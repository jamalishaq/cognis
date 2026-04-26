import { StatusBadge } from "./StatusBadge";
import type { IncidentRecord } from "@/types";

const SEVERITY_CLASSES: Record<string, string> = {
  critical: "text-red-400",
  high: "text-orange-400",
  medium: "text-yellow-400",
  low: "text-blue-400",
  unknown: "text-muted-foreground",
};

interface IncidentBriefProps {
  incident: IncidentRecord;
}

export function IncidentBrief({ incident }: IncidentBriefProps) {
  return (
    <div className="rounded-lg border bg-card p-6 space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">{incident.title}</h1>
          <p className="text-xs text-muted-foreground mt-1">{incident.incident_id}</p>
        </div>
        <StatusBadge status={incident.status} />
      </div>

      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <span className="text-muted-foreground">Service</span>
          <p className="font-medium mt-0.5">{incident.affected_service}</p>
        </div>
        <div>
          <span className="text-muted-foreground">Severity</span>
          <p className={`font-medium mt-0.5 capitalize ${SEVERITY_CLASSES[incident.severity] ?? ""}`}>
            {incident.severity}
          </p>
        </div>
        <div>
          <span className="text-muted-foreground">Failure class</span>
          <p className="font-medium mt-0.5">{incident.failure_class}</p>
        </div>
        <div>
          <span className="text-muted-foreground">Created</span>
          <p className="font-medium mt-0.5">
            {new Date(incident.created_at).toLocaleString()}
          </p>
        </div>
      </div>

      <div>
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">
          Hypothesis
        </h2>
        <p className="text-sm leading-relaxed">{incident.summary}</p>
      </div>

      {incident.recommended_actions.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">
            Recommended Actions
          </h2>
          <ol className="list-decimal list-inside space-y-1">
            {incident.recommended_actions.map((action, i) => (
              <li key={i} className="text-sm">
                {action}
              </li>
            ))}
          </ol>
        </div>
      )}

      {incident.runbook_references.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">
            Runbooks
          </h2>
          <ul className="space-y-0.5">
            {incident.runbook_references.map((ref, i) => (
              <li key={i} className="text-sm text-blue-400">
                {ref}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
