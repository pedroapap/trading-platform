import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "./client";

// Keys under ["trades"]: invalidating that prefix refreshes lists, details and audit logs.

export function useTrade(id: string) {
  return useQuery({
    queryKey: ["trades", id],
    queryFn: () =>
      unwrap(api.GET("/api/trades/{trade_id}", { params: { path: { trade_id: id } } })),
  });
}

export function useAuditLog(id: string) {
  return useQuery({
    queryKey: ["trades", id, "audit-log"],
    queryFn: () =>
      unwrap(api.GET("/api/trades/{trade_id}/audit-log", { params: { path: { trade_id: id } } })),
  });
}
