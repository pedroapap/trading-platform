import { Link, useSearchParams } from "react-router";

import { usePerformance, useRealizedEquity, type Period } from "../api/analytics";
import { useInstruments } from "../api/instruments";
import type { components } from "../api/schema";
import { useStrategies } from "../api/strategies";
import EquityChart from "../components/EquityChart";
import Money from "../components/Money";
import { ErrorMessage, Loading } from "../components/Status";
import { dayStart, formatMoney, formatPercent } from "../format";
import { ENTRY_TYPES } from "../journal";

type Schemas = components["schemas"];
type GroupBy = Schemas["GroupBy"];

const GROUPINGS: Record<GroupBy, { label: string; none: string }> = {
  strategy: { label: "Strategy", none: "No strategy" },
  symbol: { label: "Symbol", none: "No symbol" },
  emotion: { label: "Emotion", none: "No emotion recorded" },
  tag: { label: "Tag", none: "No tag" },
};

// Groupings that come from journal entries, which can be narrowed to one type of entry.
const FROM_JOURNAL = new Set<string>(["emotion", "tag"]);

/** The page's choices, kept in the URL: the closing dates (inclusive) scope everything. */
function useAnalyticsParams() {
  const [params, setParams] = useSearchParams();
  const by = (Object.keys(GROUPINGS).find((key) => key === params.get("by")) ??
    "strategy") as GroupBy;
  const from = params.get("from") ?? "";
  const to = params.get("to") ?? "";
  const entryType = FROM_JOURNAL.has(by)
    ? (Object.keys(ENTRY_TYPES).find((key) => key === params.get("entry_type")) ?? "")
    : "";
  const symbol = params.get("symbol") ?? "";
  const strategyId = params.get("strategy") ?? "";
  const period: Period = {
    closedFrom: from ? dayStart(from) : undefined,
    closedTo: to ? dayStart(to, 1) : undefined,
  };

  function choose(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    if (name === "by" && !FROM_JOURNAL.has(value)) next.delete("entry_type");
    setParams(next);
  }

  return { by, from, to, entryType, symbol, strategyId, period, choose };
}

/** A group's P&L in each currency it was traded in, with the average per trade. */
function ByCurrency({ totals }: { totals: Schemas["CurrencyPnl"][] }) {
  return totals.map((total) => (
    <div key={total.currency ?? ""}>
      <Money amount={total.total_pnl} currency={total.currency} />{" "}
      <small>
        ({total.num_trades} {total.num_trades === 1 ? "trade" : "trades"}, average{" "}
        {formatMoney(total.average_pnl, total.currency)})
      </small>
    </div>
  ));
}

function Performance({
  by,
  period,
  entryType,
  choose,
}: Pick<ReturnType<typeof useAnalyticsParams>, "by" | "period" | "entryType" | "choose">) {
  const performance = usePerformance(by, period, entryType || undefined);

  return (
    <section>
      <h2>Performance</h2>
      <div className="grid">
        <label>
          Group by
          <select value={by} onChange={(event) => choose("by", event.target.value)}>
            {Object.entries(GROUPINGS).map(([value, { label }]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Journal entries
          <select
            value={entryType}
            disabled={!FROM_JOURNAL.has(by)}
            onChange={(event) => choose("entry_type", event.target.value)}
          >
            <option value="">Any type</option>
            {Object.entries(ENTRY_TYPES).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {performance.isPending && <Loading />}
      {performance.error && <ErrorMessage error={performance.error} />}
      {performance.data?.groups.length === 0 && <p>No closed trades in this period.</p>}
      {performance.data && performance.data.groups.length > 0 && (
        <div className="overflow-auto">
          <table className="striped">
            <thead>
              <tr>
                <th>{GROUPINGS[by].label}</th>
                <th className="number">Trades</th>
                <th className="number">Wins</th>
                <th className="number">Losses</th>
                <th className="number">Win rate</th>
                <th className="number">Average return</th>
                <th>P&amp;L</th>
              </tr>
            </thead>
            <tbody>
              {performance.data.groups.map((group) => (
                <tr key={group.key ?? ""}>
                  <td>
                    {group.key === null ? (
                      <em>{GROUPINGS[by].none}</em>
                    ) : by === "strategy" ? (
                      <Link to={`/strategies/${group.key}`}>{group.label}</Link>
                    ) : (
                      group.label
                    )}
                  </td>
                  <td className="number">{group.num_trades}</td>
                  <td className="number">{group.wins}</td>
                  <td className="number">{group.losses}</td>
                  <td className="number">{formatPercent(group.win_rate_pct)}</td>
                  <td className="number">{formatPercent(group.average_return_pct)}</td>
                  <td>
                    <ByCurrency totals={group.by_currency} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/** Realized P&L accumulated trade by trade, one chart per quote currency. */
function RealizedPnl({
  symbol,
  strategyId,
  period,
  choose,
}: Pick<ReturnType<typeof useAnalyticsParams>, "symbol" | "strategyId" | "period" | "choose">) {
  const equity = useRealizedEquity(symbol, strategyId, period);
  const instruments = useInstruments();
  const strategies = useStrategies();

  return (
    <section>
      <h2>Realized P&amp;L</h2>
      <div className="grid">
        <label>
          Symbol
          <select value={symbol} onChange={(event) => choose("symbol", event.target.value)}>
            <option value="">Any symbol</option>
            {instruments.data?.map((instrument) => (
              <option key={instrument.symbol} value={instrument.symbol}>
                {instrument.symbol}
              </option>
            ))}
          </select>
        </label>
        <label>
          Strategy
          <select value={strategyId} onChange={(event) => choose("strategy", event.target.value)}>
            <option value="">Any strategy</option>
            {strategies.data?.map((strategy) => (
              <option key={strategy.id} value={strategy.id}>
                {strategy.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {equity.isPending && <Loading />}
      {equity.error && <ErrorMessage error={equity.error} />}
      <p>
        Each curve adds up the P&amp;L of its trades in the order they closed, one point per trade:
        the points are evenly spaced, not to scale in time. Point at one to see its date, or open
        the table.
      </p>
      {equity.data?.curves.length === 0 && <p>No closed trades for these choices.</p>}
      {equity.data?.curves.map((curve) => (
        <article
          key={curve.currency ?? ""}
          aria-label={`Realized P&L in ${curve.currency ?? "no set currency"}`}
        >
          <h3>{curve.currency ?? "Currency not set"}</h3>
          <p>
            {/* Without a currency, the heading and the note below already say so. */}
            Total{" "}
            {curve.currency ? (
              <Money amount={curve.total_pnl} currency={curve.currency} />
            ) : (
              curve.total_pnl
            )}{" "}
            over {curve.points.length} {curve.points.length === 1 ? "trade" : "trades"}; max
            drawdown{" "}
            {curve.currency ? (
              <Money amount={curve.max_drawdown} currency={curve.currency} />
            ) : (
              curve.max_drawdown
            )}
            .
          </p>
          {curve.currency === null && (
            <p>
              <small>
                These trades' symbols have no quote currency set, so this curve may add up different
                currencies. <Link to="/instruments">Set their currencies</Link>.
              </small>
            </p>
          )}
          <EquityChart
            points={curve.points.map((point) => ({
              time: point.ts,
              value: Number(point.cumulative_pnl),
            }))}
            label="Realized P&L"
            format={(value) =>
              `${formatMoney(value, curve.currency)}${curve.currency ? ` ${curve.currency}` : ""}`
            }
            reference={{ value: 0, title: "Break-even" }}
            sequence
          />
        </article>
      ))}
    </section>
  );
}

export default function AnalyticsPage() {
  const params = useAnalyticsParams();

  return (
    <>
      <h1>Analytics</h1>
      <p>
        Closed trades only. Money is totalled per quote currency and never converted; returns are on
        each trade's notional, so leverage doesn't skew them.
      </p>
      <div className="grid">
        <label>
          Closed from
          <input
            type="date"
            value={params.from}
            onChange={(event) => params.choose("from", event.target.value)}
          />
        </label>
        <label>
          Closed to (inclusive)
          <input
            type="date"
            value={params.to}
            onChange={(event) => params.choose("to", event.target.value)}
          />
        </label>
      </div>
      <Performance {...params} />
      <RealizedPnl {...params} />
    </>
  );
}
