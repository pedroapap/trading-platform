import type { ReactNode } from "react";
import { Link, useParams } from "react-router";

import {
  useBacktest,
  useBacktestComparison,
  useBacktestEquity,
  useBacktestTrades,
} from "../api/backtests";
import type { components } from "../api/schema";
import { useStrategies } from "../api/strategies";
import EquityChart from "../components/EquityChart";
import Money from "../components/Money";
import Pagination from "../components/Pagination";
import { ErrorMessage, Loading } from "../components/Status";
import {
  formatCount,
  formatDateTime,
  formatDecimal,
  formatMoney,
  formatPercent,
  formatRatio,
} from "../format";
import { useListParams } from "../useListParams";

type Schemas = components["schemas"];
type Backtest = Schemas["BacktestRead"];

const EXIT_REASONS: Record<Schemas["ExitReason"], string> = {
  signal: "exit rule",
  stop_loss: "stop-loss",
  take_profit: "take-profit",
  end_of_data: "end of data",
};

/** A computed amount in the backtest's currency. */
function Amount({ value, currency }: { value: number | string | null; currency: string | null }) {
  return <Money amount={value == null ? null : formatMoney(value)} currency={currency} />;
}

function range(first: string | null, last: string | null): string {
  return `${first ? formatDateTime(first) : "first bar"} – ${last ? formatDateTime(last) : "last bar"}`;
}

/** The range a backtest asked for; either end may be open. */
function requested(start: string | null, end: string | null): string {
  if (start && end) return range(start, end);
  if (start) return `From ${formatDateTime(start)}`;
  if (end) return `Until ${formatDateTime(end)}`;
  return "All stored bars";
}

type Labelled = { label: string; value: ReactNode };

/** What was run, on which data. */
function Settings({ backtest, strategyName }: { backtest: Backtest; strategyName: string }) {
  const rows: Labelled[] = [
    {
      label: "Strategy",
      value: (
        <>
          <Link to={`/strategies/${backtest.strategy_id}`}>{strategyName}</Link> v
          {backtest.strategy_version}
        </>
      ),
    },
    { label: "Market", value: `${backtest.symbol}, ${backtest.timeframe} bars` },
    { label: "Asked for", value: requested(backtest.start, backtest.end) },
    {
      label: "Bars used",
      value:
        backtest.bars_count === null
          ? "—"
          : `${formatCount(backtest.bars_count)}, ${range(backtest.first_bar_ts, backtest.last_bar_ts)}`,
    },
    {
      label: "Initial capital",
      value: <Money amount={backtest.initial_capital} currency={backtest.quote_currency} />,
    },
    { label: "Position size", value: `${backtest.position_size_pct}% of equity` },
    {
      label: "Costs",
      value: `${backtest.fee_pct}% fee and ${backtest.slippage_pct}% slippage per fill`,
    },
    { label: "Periods per year", value: String(backtest.periods_per_year) },
  ];
  if (backtest.data_hash) {
    rows.push({
      label: "Data fingerprint",
      value: <code title={backtest.data_hash}>{backtest.data_hash.slice(0, 12)}</code>,
    });
  }
  return (
    <table className="details">
      <tbody>
        {rows.map(({ label, value }) => (
          <tr key={label}>
            <th scope="row">{label}</th>
            <td className="wrap">{value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function MetricTiles({ backtest }: { backtest: Backtest }) {
  const metrics = backtest.metrics!;
  const amount = (value: number | null) => (
    <Amount value={value} currency={backtest.quote_currency} />
  );
  const tiles: Labelled[] = [
    { label: "Total return", value: formatPercent(metrics.total_return_pct) },
    { label: "CAGR", value: formatPercent(metrics.cagr_pct) },
    { label: "Max drawdown", value: formatPercent(metrics.max_drawdown_pct) },
    { label: "Sharpe ratio", value: formatRatio(metrics.sharpe_ratio) },
    { label: "Sortino ratio", value: formatRatio(metrics.sortino_ratio) },
    { label: "Trades", value: formatCount(metrics.num_trades) },
    { label: "Win rate", value: formatPercent(metrics.win_rate_pct) },
    { label: "Profit factor", value: formatRatio(metrics.profit_factor) },
    { label: "Expectancy", value: amount(metrics.expectancy) },
    { label: "Average win", value: amount(metrics.average_win) },
    { label: "Average loss", value: amount(metrics.average_loss) },
    { label: "Exposure", value: formatPercent(metrics.exposure_pct) },
  ];
  return (
    <dl className="metrics">
      {tiles.map(({ label, value }) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** The backtest next to the live trades that followed the same strategy version on the same
 * symbol, entered while its bars ran. */
function Comparison({ backtest, strategyName }: { backtest: Backtest; strategyName: string }) {
  const comparison = useBacktestComparison(backtest.id);
  if (comparison.isPending) return <Loading />;
  if (comparison.error) return <ErrorMessage error={comparison.error} />;
  const { live, period_start: start, period_end: end, quote_currency: currency } = comparison.data;
  const sides = { Backtest: comparison.data.backtest, Live: live };
  const rows: { label: string; cell: (side: Schemas["ComparisonSide"]) => ReactNode }[] = [
    { label: "Trades", cell: (side) => formatCount(side.num_trades) },
    { label: "Win rate", cell: (side) => formatPercent(side.win_rate_pct) },
    {
      label: "Average return on notional",
      cell: (side) => formatPercent(side.average_return_pct),
    },
    {
      label: "Total P&L",
      cell: (side) => <Amount value={side.total_pnl} currency={currency} />,
    },
  ];
  return (
    <>
      <p>
        {live.num_trades === 0 ? "No live trades" : "Live trades"} of {strategyName} v
        {comparison.data.strategy_version} on {comparison.data.symbol} were entered between{" "}
        {formatDateTime(start)} and {formatDateTime(end)}.
      </p>
      <div className="overflow-auto">
        <table className="details">
          <thead>
            <tr>
              <td />
              {Object.keys(sides).map((name) => (
                <th key={name} scope="col" className="number">
                  {name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(({ label, cell }) => (
              <tr key={label}>
                <th scope="row" className="wrap">
                  {label}
                </th>
                {Object.entries(sides).map(([name, side]) => (
                  <td key={name} className="number">
                    {cell(side)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Equity({ backtest }: { backtest: Backtest }) {
  const equity = useBacktestEquity(backtest.id);
  const currency = backtest.quote_currency;
  if (equity.isPending) return <Loading />;
  if (equity.error) return <ErrorMessage error={equity.error} />;
  return (
    <EquityChart
      points={equity.data.map((point) => ({ time: point.ts, value: point.equity }))}
      label="Equity"
      format={(value) => `${formatMoney(value)}${currency ? ` ${currency}` : ""}`}
      reference={{ value: Number(backtest.initial_capital), title: "Initial capital" }}
    />
  );
}

function Trades({ backtest }: { backtest: Backtest }) {
  const { offset, limit, showPage } = useListParams([]);
  const trades = useBacktestTrades(backtest.id, offset, limit);
  const currency = backtest.quote_currency;
  if (trades.isPending) return <Loading />;
  if (trades.error) return <ErrorMessage error={trades.error} />;
  if (trades.data.total === 0) return <p>The strategy made no trades.</p>;
  return (
    <>
      <div className="overflow-auto">
        <table className="striped">
          <thead>
            <tr>
              <th className="number">#</th>
              <th>Direction</th>
              <th>Entry</th>
              <th>Exit</th>
              <th className="number">Size</th>
              <th className="number">Costs</th>
              <th className="number">P&amp;L</th>
              <th className="number">P&amp;L %</th>
              <th>Exit by</th>
            </tr>
          </thead>
          <tbody>
            {trades.data.items.map((trade) => {
              const fees = Number(trade.entry_fee) + Number(trade.exit_fee);
              return (
                <tr key={trade.number}>
                  <td className="number">{trade.number}</td>
                  <td>{trade.direction}</td>
                  <td>
                    {formatDateTime(trade.entry_time)}
                    <br />@ {formatDecimal(trade.entry_price)}
                  </td>
                  <td>
                    {formatDateTime(trade.exit_time)}
                    <br />@ {formatDecimal(trade.exit_price)}
                  </td>
                  <td className="number">{formatDecimal(trade.size)}</td>
                  <td
                    className="number"
                    title={`Fees ${formatMoney(fees)}, slippage ${formatMoney(trade.slippage)}`}
                  >
                    {formatMoney(fees + Number(trade.slippage))}
                  </td>
                  <td className="number">
                    <Amount value={trade.pnl} currency={currency} />
                  </td>
                  <td className="number">{formatPercent(trade.pnl_pct)}</td>
                  <td>{EXIT_REASONS[trade.exit_reason]}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <Pagination offset={offset} limit={limit} total={trades.data.total} onPage={showPage} />
    </>
  );
}

function Status({ backtest }: { backtest: Backtest }) {
  switch (backtest.status) {
    case "pending":
      return <p aria-busy="true">Waiting to run. This page updates when it is done.</p>;
    case "running":
      return <p aria-busy="true">Running. This page updates when it is done.</p>;
    case "failed":
      return <p role="alert">Failed: {backtest.error_message}</p>;
    case "completed":
      return <p>Completed {backtest.completed_at && formatDateTime(backtest.completed_at)}.</p>;
  }
}

export default function BacktestPage() {
  const { backtestId = "" } = useParams();
  const backtest = useBacktest(backtestId);
  const strategies = useStrategies();
  const strategy = strategies.data?.find((each) => each.id === backtest.data?.strategy_id);

  return (
    <>
      <p>
        <Link to="/backtests">← Backtests</Link>
      </p>
      {backtest.isPending && <Loading />}
      {backtest.error && <ErrorMessage error={backtest.error} />}
      {backtest.data && (
        <>
          <h1>
            {strategy?.name ?? "Backtest"} v{backtest.data.strategy_version} on{" "}
            {backtest.data.symbol} {backtest.data.timeframe}
          </h1>
          <Status backtest={backtest.data} />
          <Settings backtest={backtest.data} strategyName={strategy?.name ?? "…"} />
          {backtest.data.status === "completed" && backtest.data.metrics && (
            <>
              <h2>Results</h2>
              <MetricTiles backtest={backtest.data} />
              <h2>Backtest and live</h2>
              <Comparison
                backtest={backtest.data}
                strategyName={strategy?.name ?? "the strategy"}
              />
              <h2>Equity</h2>
              <Equity backtest={backtest.data} />
              <h2>Trades</h2>
              <Trades backtest={backtest.data} />
            </>
          )}
        </>
      )}
    </>
  );
}
