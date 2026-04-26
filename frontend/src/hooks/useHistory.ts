import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useIncidentStore } from "@/store/incidentStore";
import type { ChatHistoryResponse } from "@/types";

export function useHistory(incident_id: string) {
  const setMessages = useIncidentStore((s) => s.setMessages);

  return useQuery<ChatHistoryResponse, Error>({
    queryKey: ["history", incident_id],
    queryFn: async () => {
      const data = await api.getHistory(incident_id);
      setMessages(data.messages);
      return data;
    },
    enabled: Boolean(incident_id),
    staleTime: 0,
  });
}
