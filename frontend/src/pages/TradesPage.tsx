import { keepPreviousData, useQuery } from "@tanstack/react-query";
import type { FormEvent } from "react";
import { Link, useSearchParams } from "react-router";

import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { useStrategies } from "../api/strategies";
import Money from "../components/Money";
import Pagination from "../components/Pagination";
import { ErrorMessage, Loading } from "../components/Status";
import { formatDateTime } from "../format";

type TradeStatus = components["schemas"]["TradeStatus"];

const PAGE_SIZE = 50;
const STATUSES: TradeStatus[] = ["open", "closed", "cancelled"];

export default function TradesPage() {
  // Filters and page live in the URL, so they survive a reload and the back button.
  const [params, setParams] = useSearchParams();
  const symbol = params.get("symbol") ?? "";
  const status = STATUSES.find((value) => value === params.get("status"));
  const offset = (Math.max(1, Number(params.get("page")) || 1) - 1) * PAGE_SIZE;

  const trades = useQuery({
    queryKey: ["trades", { symbol, status, offset }],
    queryFn: () =>
      unwrap(
        api.GET("/api/trades", {
          params: { query: { symbol: symbol || undefined, status, limit: PAGE_SIZE, offset } },
        }),
      ),
    placeholderData: keepPreviousData,
  });
  const strategies = useStrategies();
  const strategyNames = new Map(strategies.data?.map((strategy) => [strategy.id, strategy.name]));

  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const next = new URLSearchParams();
    for (const name of ["symbol", "status"]) {
      const value = String(fields.get(name) ?? "").trim();
      if (value) next.set(name, value);
    }
    setParams(next);
  }

  function showPage(newOffset: number) {
    const next = new URLSearchParams(params);
    next.set("page", String(newOffset / PAGE_SIZE + 1));
    setParams(next);
  }

  return (
    <>
      <h1>Trades</h1>
      <p>
        <Link to="/trades/new" role="button">
          New trade
        </Link>
      </p>
      <form onSubmit={filter} role="search">
        <fieldset role="group">
          <input name="symbol" placeholder="Symbol" aria-label="Symbol" defaultValue={symbol} />
          <select name="status" aria-label="Status" defaultValue={status ?? ""}>
            <option value="">Any status</option>
            {STATUSES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
          <button type="submit">Filter</button>
        </fieldset>
      </form>
      {trades.isPending && <Loading />}
      {trades.error && <ErrorMessage error={trades.error} />}
      {trades.data && trades.data.total === 0 && <p>No trades.</p>}
      {trades.data && trades.data.total > 0 && (
        <>
          <div className="overflow-auto">
            <table>
              <thead>
                <tr>
                  <th>Entered</th>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Status</th>
                  <th>Entry</th>
                  <th>Exit</th>
                  <th>P&amp;L</th>
                  <th>Return</th>
                  <th>Strategy</th>
                </tr>
              </thead>
              <tbody>
                {trades.data.items.map((trade) => (
                  <tr key={trade.id}>
                    <td>{formatDateTime(trade.entry_time)}</td>
                    <td>
                      <Link to={`/trades/${trade.id}`}>{trade.symbol}</Link>
                    </td>
                    <td>{trade.direction}</td>
                    <td>{trade.status}</td>
                    <td>
                      {trade.entry_size} @ {trade.entry_price}
                    </td>
                    <td>
                      {trade.exit_price
                        ? `${trade.exit_size ?? trade.entry_size} @ ${trade.exit_price}`
                        : "—"}
                    </td>
                    <td>
                      <Money amount={trade.pnl} currency={trade.quote_currency} />
                    </td>
                    <td>{trade.pnl_pct == null ? "—" : `${trade.pnl_pct}%`}</td>
                    <td>
                      {trade.strategy_id
                        ? `${strategyNames.get(trade.strategy_id) ?? "…"} v${trade.strategy_version}`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            offset={offset}
            limit={PAGE_SIZE}
            total={trades.data.total}
            onPage={showPage}
          />
        </>
      )}
    </>
  );
}
