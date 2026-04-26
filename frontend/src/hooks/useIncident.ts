import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useIncidentStore } from "@/store/incidentStore";
import type { IncidentRecord } from "@/types";

export function useIncident(incident_id: string) {
  const setCurrentIncident = useIncidentStore((s) => s.setCurrentIncident);

  return useQuery<IncidentRecord, Error>({
    queryKey: ["incident", incident_id],
    queryFn: async () => {
      const incident = await api.getIncident(incident_id);
      setCurrentIncident(incident);
      return incident;
    },
    enabled: Boolean(incident_id),
    staleTime: 30_000,
  });
}
