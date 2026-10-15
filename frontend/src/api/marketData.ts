import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "./client";

// Keys under ["market-data"]: an import invalidates that prefix.

/** What is stored: one entry per symbol and timeframe. */
export function useCoverage() {
  return useQuery({
    queryKey: ["market-data", "coverage"],
    queryFn: () => unwrap(api.GET("/api/market-data/symbols")),
  });
}
