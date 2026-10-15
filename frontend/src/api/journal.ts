import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "./client";

// Keys under ["journal"]: invalidating that prefix refreshes lists, entries and histories.

export function useJournalEntry(id: string) {
  return useQuery({
    queryKey: ["journal", id],
    queryFn: () =>
      unwrap(api.GET("/api/journal/{entry_id}", { params: { path: { entry_id: id } } })),
  });
}
