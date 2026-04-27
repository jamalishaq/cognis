import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useIncidentStore } from "@/store/incidentStore";
import { useQueryClient } from "@tanstack/react-query";
import type { IncidentRecord } from "@/types";

interface ResolveModalProps {
  incident: IncidentRecord;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onResolved: () => void;
}

export function ResolveModal({ incident, open, onOpenChange, onResolved }: ResolveModalProps) {
  const [notes, setNotes] = useState(incident.summary);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const setCurrentIncident = useIncidentStore((s) => s.setCurrentIncident);
  const queryClient = useQueryClient();

  const handleSubmit = async () => {
    if (!notes.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.resolveIncident(incident.incident_id, {
        incident_id: incident.incident_id,
        resolution_notes: notes.trim(),
        resolved_by: null,
      });
      const resolved = { ...incident, status: "resolved" as const };
      setCurrentIncident(resolved);
      queryClient.setQueryData(["incident", incident.incident_id], resolved);
      onOpenChange(false);
      onResolved();
    } catch {
      setError("Failed to resolve incident. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>Mark Incident as Resolved</DialogTitle>
          <DialogDescription>
            Review and edit the resolution notes before submitting. The hypothesis has been
            pre-filled from the incident brief.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          <label className="text-sm font-medium" htmlFor="resolution-notes">
            Resolution notes
          </label>
          <Textarea
            id="resolution-notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={6}
            placeholder="Describe the root cause and resolution steps…"
          />
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={submitting || !notes.trim()}>
            {submitting ? "Resolving…" : "Mark as Resolved"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
