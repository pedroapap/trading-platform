import { useMemo, type ReactNode } from "react";
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
type Metrics = Schemas["Metrics"];

// Fewer trades than this say little about a strategy: the result could be luck.
const ENOUGH_TRADES = 30;

const EXIT_REASONS: Record<Schemas["ExitReason"], string> = {
  signal: "exit rule",
  stop_loss: "stop-loss",
  take_profit: "take-profit",
  end_of_data: "end of data",
  trailing_stop: "trailing stop",
  time_exit: "time exit",
  end_of_day: "end of day",
  margin_call: "margin call",
};

/** A computed amount in the backtest's currency. */
function Amount({ value, currency }: { value: number | string | null; currency: string | null }) {
  return <Money amount={value == null ? null : formatMoney(value, currency)} currency={currency} />;
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
    {
      label: "Finer bars",
      value: backtest.detail_timeframe
        ? `${backtest.detail_timeframe}, to settle what came first inside a bar`
        : "None: inside a bar, the worst case counts",
    },
    {
      label: "Out-of-sample from",
      value: backtest.out_of_sample_from ? formatDateTime(backtest.out_of_sample_from) : "Not set",
    },
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

/** The 95% range of the average trade's return, "" when it has none (under 2 trades). */
function tradeRange(metrics: Metrics): string {
  const average = metrics.average_trade_pct;
  const margin = metrics.average_trade_margin_pct;
  if (average == null || margin == null) return "";
  return `${formatPercent(average - margin)} to ${formatPercent(average + margin)}`;
}

/** A caution that so few trades can't tell skill from luck. */
function FewTrades({ trades }: { trades: number }) {
  return (
    <p className="warning">
      <span aria-hidden="true">⚠</span> <strong>Too few trades to judge.</strong> With{" "}
      {formatCount(trades)} {trades === 1 ? "trade" : "trades"}, under {ENOUGH_TRADES}, results like
      these can come from luck alone: test on more bars, or another period, before trusting them.
    </p>
  );
}

/** The headline numbers. The return, CAGR and drawdown each have buy and hold's, over the same
 * bars, under them (runs made before it was measured have none); the average trade has its
 * 95% range. */
function MetricTiles({ backtest }: { backtest: Backtest }) {
  const metrics = backtest.metrics!;
  const amount = (value: number | null) => (
    <Amount value={value} currency={backtest.quote_currency} />
  );
  const measured = metrics.buy_and_hold_return_pct != null;
  const held = (value: number | null | undefined) =>
    measured ? `Buy and hold ${formatPercent(value)}` : undefined;
  const range = tradeRange(metrics);
  const tiles: (Labelled & { note?: string })[] = [
    {
      label: "Total return",
      value: formatPercent(metrics.total_return_pct),
      note: held(metrics.buy_and_hold_return_pct),
    },
    {
      label: "CAGR",
      value: formatPercent(metrics.cagr_pct),
      note: held(metrics.buy_and_hold_cagr_pct),
    },
    {
      label: "Max drawdown",
      value: formatPercent(metrics.max_drawdown_pct),
      note: held(metrics.buy_and_hold_max_drawdown_pct),
    },
    { label: "Sharpe ratio", value: formatRatio(metrics.sharpe_ratio) },
    { label: "Sortino ratio", value: formatRatio(metrics.sortino_ratio) },
    { label: "Trades", value: formatCount(metrics.num_trades) },
    { label: "Win rate", value: formatPercent(metrics.win_rate_pct) },
    { label: "Profit factor", value: formatRatio(metrics.profit_factor) },
    { label: "Expectancy", value: amount(metrics.expectancy) },
    {
      label: "Average trade",
      value: formatPercent(metrics.average_trade_pct),
      note: range && `95% range ${range}`,
    },
    { label: "Average win", value: amount(metrics.average_win) },
    { label: "Average loss", value: amount(metrics.average_loss) },
    { label: "Exposure", value: formatPercent(metrics.exposure_pct) },
  ];
  return (
    <dl className="metrics">
      {tiles.map(({ label, value, note }) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
          {note && <dd className="note">{note}</dd>}
        </div>
      ))}
    </dl>
  );
}

/** The bars before the out-of-sample start next to the bars from it on, each measured on its
 * own: trades count on the side they were entered, the out-of-sample equity counts from its
 * value at the start, and each side has its own buy and hold. */
function SplitResults({ backtest }: { backtest: Backtest }) {
  const { in_sample: before, out_of_sample: after } = backtest.split_metrics!;
  const sides = { "In-sample": before, "Out-of-sample": after };
  const amount = (value: number | null | undefined) => (
    <Amount value={value ?? null} currency={backtest.quote_currency} />
  );
  const rows: { label: string; cell: (metrics: Metrics) => ReactNode }[] = [
    { label: "Total return", cell: (metrics) => formatPercent(metrics.total_return_pct) },
    {
      label: "Buy and hold return",
      cell: (metrics) => formatPercent(metrics.buy_and_hold_return_pct),
    },
    { label: "CAGR", cell: (metrics) => formatPercent(metrics.cagr_pct) },
    { label: "Max drawdown", cell: (metrics) => formatPercent(metrics.max_drawdown_pct) },
    { label: "Sharpe ratio", cell: (metrics) => formatRatio(metrics.sharpe_ratio) },
    {
      label: "Trades",
      cell: (metrics) =>
        metrics.num_trades < ENOUGH_TRADES ? (
          <>
            <span aria-hidden="true">⚠</span> {formatCount(metrics.num_trades)}, too few to judge
          </>
        ) : (
          formatCount(metrics.num_trades)
        ),
    },
    { label: "Win rate", cell: (metrics) => formatPercent(metrics.win_rate_pct) },
    { label: "Profit factor", cell: (metrics) => formatRatio(metrics.profit_factor) },
    { label: "Expectancy", cell: (metrics) => amount(metrics.expectancy) },
    { label: "Average trade", cell: (metrics) => formatPercent(metrics.average_trade_pct) },
    { label: "Its 95% range", cell: (metrics) => tradeRange(metrics) || "—" },
    { label: "Exposure", cell: (metrics) => formatPercent(metrics.exposure_pct) },
  ];
  return (
    <>
      <p>
        Bars before {formatDateTime(backtest.out_of_sample_from!)} are in-sample, those from then on
        out-of-sample. A strategy shaped on the in-sample bars should hold up on the others.
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

/** The equity curve next to buy and hold's, over the same bars. */
function Equity({ backtest }: { backtest: Backtest }) {
  const equity = useBacktestEquity(backtest.id);
  const currency = backtest.quote_currency;
  // Built once per response, so the chart is drawn again only when the data changes.
  const curves = useMemo(() => {
    const points = equity.data ?? [];
    // Runs made before buy and hold was measured have none.
    const held = points.filter((point) => point.benchmark != null);
    return {
      points: points.map((point) => ({ time: point.ts, value: point.equity })),
      compared: held.length
        ? {
            label: "Buy and hold",
            points: held.map((point) => ({ time: point.ts, value: point.benchmark! })),
          }
        : undefined,
    };
  }, [equity.data]);
  if (equity.isPending) return <Loading />;
  if (equity.error) return <ErrorMessage error={equity.error} />;
  return (
    <EquityChart
      points={curves.points}
      compared={curves.compared}
      label="Equity"
      format={(value) => `${formatMoney(value, currency)}${currency ? ` ${currency}` : ""}`}
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
                    title={`Fees ${formatMoney(fees, currency)}, slippage ${formatMoney(trade.slippage, currency)}`}
                  >
                    {formatMoney(fees + Number(trade.slippage), currency)}
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
              {backtest.data.metrics.num_trades < ENOUGH_TRADES && (
                <FewTrades trades={backtest.data.metrics.num_trades} />
              )}
              <MetricTiles backtest={backtest.data} />
              {backtest.data.split_metrics && (
                <>
                  <h2>In-sample and out-of-sample</h2>
                  <SplitResults backtest={backtest.data} />
                </>
              )}
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
