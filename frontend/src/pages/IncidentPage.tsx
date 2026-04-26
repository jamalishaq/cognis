import { useState } from "react";
import { useParams, Navigate } from "react-router-dom";
import { IncidentBrief } from "@/components/IncidentBrief";
import { ChatWindow } from "@/components/ChatWindow";
import { ResolveModal } from "@/components/ResolveModal";
import { Button } from "@/components/ui/button";
import { useIncident } from "@/hooks/useIncident";
import { useHistory } from "@/hooks/useHistory";

export function IncidentPage() {
  const { incident_id } = useParams<{ incident_id: string }>();
  const [resolveOpen, setResolveOpen] = useState(false);

  const {
    data: incident,
    isLoading: incidentLoading,
    isError: incidentError,
  } = useIncident(incident_id ?? "");

  useHistory(incident_id ?? "");

  if (!incident_id) return <Navigate to="/404" replace />;

  if (incidentLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-muted-foreground animate-pulse">Loading incident…</p>
      </div>
    );
  }

  if (incidentError || !incident) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen gap-2">
        <p className="text-destructive font-medium">Incident not found.</p>
        <p className="text-sm text-muted-foreground">{incident_id}</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen p-4 md:p-8 max-w-5xl mx-auto space-y-6">
      <IncidentBrief incident={incident} />

      {incident.status === "open" && (
        <div className="flex justify-end">
          <Button variant="outline" onClick={() => setResolveOpen(true)}>
            Mark as Resolved
          </Button>
        </div>
      )}

      <div className="h-[60vh]">
        <ChatWindow incident_id={incident_id} />
      </div>

      <ResolveModal
        incident={incident}
        open={resolveOpen}
        onOpenChange={setResolveOpen}
        onResolved={() => setResolveOpen(false)}
      />
    </div>
  );
}
