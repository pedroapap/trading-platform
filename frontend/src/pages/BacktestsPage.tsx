import type { FormEvent } from "react";
import { Link } from "react-router";

import { useBacktests } from "../api/backtests";
import type { components } from "../api/schema";
import { useStrategies } from "../api/strategies";
import Pagination from "../components/Pagination";
import { ErrorMessage, Loading } from "../components/Status";
import { formatDate, formatDateTime, formatPercent } from "../format";
import { useListParams } from "../useListParams";

type Backtest = components["schemas"]["BacktestRead"];

/** The days of the bars a backtest ran on, or of the range it asked for until it has run. */
function period(backtest: Backtest): string {
  const first = backtest.first_bar_ts ?? backtest.start;
  const last = backtest.last_bar_ts ?? backtest.end;
  return `${first ? formatDate(first) : "first bar"} – ${last ? formatDate(last) : "last bar"}`;
}

export default function BacktestsPage() {
  const { filters, offset, limit, applyFilters, showPage } = useListParams([
    "strategy_id",
  ] as const);
  const backtests = useBacktests(filters.strategy_id, offset, limit);
  const strategies = useStrategies();
  const strategyNames = new Map(strategies.data?.map((strategy) => [strategy.id, strategy.name]));

  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    applyFilters(event.currentTarget);
  }

  return (
    <>
      <h1>Backtests</h1>
      <p>
        <Link to="/backtests/new" role="button">
          New backtest
        </Link>
      </p>
      <form onSubmit={filter} role="search">
        <fieldset role="group">
          {/* Remounts once the strategies arrive, to show the one filtered by. */}
          <select
            key={strategies.data ? "loaded" : "loading"}
            name="strategy_id"
            aria-label="Strategy"
            defaultValue={filters.strategy_id}
          >
            <option value="">Any strategy</option>
            {strategies.data?.map((strategy) => (
              <option key={strategy.id} value={strategy.id}>
                {strategy.name}
              </option>
            ))}
          </select>
          <button type="submit">Filter</button>
        </fieldset>
      </form>
      {backtests.isPending && <Loading />}
      {backtests.error && <ErrorMessage error={backtests.error} />}
      {backtests.data?.total === 0 && <p>No backtests.</p>}
      {backtests.data && backtests.data.total > 0 && (
        <>
          <div className="overflow-auto">
            <table className="striped">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Strategy</th>
                  <th>Symbol</th>
                  <th>Timeframe</th>
                  <th>Bars</th>
                  <th>Status</th>
                  <th className="number">Return</th>
                  <th className="number">Trades</th>
                </tr>
              </thead>
              <tbody>
                {backtests.data.items.map((backtest) => (
                  <tr key={backtest.id}>
                    <td>
                      <Link to={`/backtests/${backtest.id}`}>
                        {formatDateTime(backtest.created_at)}
                      </Link>
                    </td>
                    <td>
                      {strategyNames.get(backtest.strategy_id) ?? "…"} v{backtest.strategy_version}
                    </td>
                    <td>{backtest.symbol}</td>
                    <td>{backtest.timeframe}</td>
                    <td>{period(backtest)}</td>
                    <td title={backtest.error_message ?? undefined}>{backtest.status}</td>
                    <td className="number">{formatPercent(backtest.metrics?.total_return_pct)}</td>
                    <td className="number">{backtest.metrics?.num_trades ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            offset={offset}
            limit={limit}
            total={backtests.data.total}
            onPage={showPage}
          />
        </>
      )}
    </>
  );
}
