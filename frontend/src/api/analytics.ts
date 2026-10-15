import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import type { components } from "./schema";

type Schemas = components["schemas"];

// Keys under ["analytics"].

export type Period = { closedFrom?: string; closedTo?: string };

/** Closed trades grouped by `by`, best average return first. */
export function usePerformance(by: Schemas["GroupBy"], period: Period, entryType?: string) {
  return useQuery({
    queryKey: ["analytics", "performance", { by, period, entryType }],
    queryFn: () =>
      unwrap(
        api.GET("/api/analytics/performance", {
          params: {
            query: {
              by,
              closed_from: period.closedFrom,
              closed_to: period.closedTo,
              entry_type: entryType as Schemas["EntryType"] | undefined,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

/** Realized P&L over time from closed trades: one curve per quote currency. */
export function useRealizedEquity(symbol: string, strategyId: string, period: Period) {
  return useQuery({
    queryKey: ["analytics", "equity", { symbol, strategyId, period }],
    queryFn: () =>
      unwrap(
        api.GET("/api/analytics/equity", {
          params: {
            query: {
              symbol: symbol || undefined,
              strategy_id: strategyId || undefined,
              closed_from: period.closedFrom,
              closed_to: period.closedTo,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}
