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

/** The published versions of an entry, oldest first; none for a draft. */
export function useJournalVersions(id: string) {
  return useQuery({
    queryKey: ["journal", id, "versions"],
    queryFn: () =>
      unwrap(api.GET("/api/journal/{entry_id}/versions", { params: { path: { entry_id: id } } })),
  });
}
