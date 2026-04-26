import { Badge } from "@/components/ui/badge";
import type { IncidentStatus } from "@/types";

interface StatusBadgeProps {
  status: IncidentStatus;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  return (
    <Badge variant={status === "open" ? "amber" : "green"}>
      {status === "open" ? "Open" : "Resolved"}
    </Badge>
  );
}
