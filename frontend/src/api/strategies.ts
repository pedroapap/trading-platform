import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "./client";

// Keys under ["strategies"]: invalidating that prefix refreshes the list, each strategy and
// its versions.

export function useStrategies() {
  return useQuery({ queryKey: ["strategies"], queryFn: () => unwrap(api.GET("/api/strategies")) });
}

export function useStrategy(id: string) {
  return useQuery({
    queryKey: ["strategies", id],
    queryFn: () =>
      unwrap(api.GET("/api/strategies/{strategy_id}", { params: { path: { strategy_id: id } } })),
  });
}

/** Every version of a strategy's definition, oldest first. */
export function useStrategyVersions(id: string) {
  return useQuery({
    queryKey: ["strategies", id, "versions"],
    queryFn: () =>
      unwrap(
        api.GET("/api/strategies/{strategy_id}/versions", {
          params: { path: { strategy_id: id } },
        }),
      ),
  });
}
