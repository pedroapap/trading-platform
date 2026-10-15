import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import type { components } from "./schema";

type Backtest = components["schemas"]["BacktestRead"];

// Keys under ["backtests"]: invalidating that prefix refreshes lists and results.

/** How often a page with a backtest still to finish asks again, in milliseconds. */
export const POLL_MS = 1_000;

export function isRunning(backtest: Backtest): boolean {
  return backtest.status === "pending" || backtest.status === "running";
}

/** A page of backtests, newest first, refreshed while any of them is still to finish. */
export function useBacktests(strategyId: string, offset: number, limit: number) {
  return useQuery({
    queryKey: ["backtests", { strategyId, offset }],
    queryFn: () =>
      unwrap(
        api.GET("/api/backtests", {
          params: { query: { strategy_id: strategyId || undefined, limit, offset } },
        }),
      ),
    placeholderData: keepPreviousData,
    refetchInterval: (query) => (query.state.data?.items.some(isRunning) ? POLL_MS : false),
  });
}
