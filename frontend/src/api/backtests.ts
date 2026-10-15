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

/** One backtest, refreshed until it is done. */
export function useBacktest(id: string) {
  return useQuery({
    queryKey: ["backtests", id],
    queryFn: () =>
      unwrap(api.GET("/api/backtests/{backtest_id}", { params: { path: { backtest_id: id } } })),
    refetchInterval: (query) => (query.state.data && isRunning(query.state.data) ? POLL_MS : false),
  });
}

/** A completed backtest's equity curve, downsampled by the API. */
export function useBacktestEquity(id: string) {
  return useQuery({
    queryKey: ["backtests", id, "equity"],
    queryFn: () =>
      unwrap(
        api.GET("/api/backtests/{backtest_id}/equity", {
          params: { path: { backtest_id: id } },
        }),
      ),
  });
}

/** A page of a completed backtest's trades, in the order they were made. */
export function useBacktestTrades(id: string, offset: number, limit: number) {
  return useQuery({
    queryKey: ["backtests", id, "trades", { offset }],
    queryFn: () =>
      unwrap(
        api.GET("/api/backtests/{backtest_id}/trades", {
          params: { path: { backtest_id: id }, query: { limit, offset } },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}
