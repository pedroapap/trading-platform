import type { ReactNode } from "react";
import { Link, useParams } from "react-router";

import type { components } from "../api/schema";
import { useStrategies } from "../api/strategies";
import { useAuditLog, useTrade } from "../api/trades";
import AuditLog from "../components/AuditLog";
import Money from "../components/Money";
import { ErrorMessage, Loading } from "../components/Status";
import { formatDateTime } from "../format";

type Trade = components["schemas"]["TradeRead"];

function Summary({ trade, strategyName }: { trade: Trade; strategyName?: string }) {
  const rows: [string, ReactNode][] = [
    ["Status", trade.status],
    ["Entry", `${trade.entry_size} @ ${trade.entry_price} on ${formatDateTime(trade.entry_time)}`],
    ["Entry fee", trade.entry_fee],
    [
      "Exit",
      trade.exit_price && trade.exit_time
        ? `${trade.exit_size ?? trade.entry_size} @ ${trade.exit_price} on ${formatDateTime(trade.exit_time)}`
        : "—",
    ],
    ["Exit fee", trade.exit_fee],
    ["Stop-loss", trade.stop_loss ?? "—"],
    ["Take-profit", trade.take_profit ?? "—"],
    ["Leverage", trade.leverage],
    ["P&L", <Money key="pnl" amount={trade.pnl} currency={trade.quote_currency} />],
    ["Return on margin", trade.pnl_pct == null ? "—" : `${trade.pnl_pct}%`],
    ["Strategy", trade.strategy_id ? `${strategyName ?? "…"} v${trade.strategy_version}` : "—"],
  ];
  return (
    <table className="details">
      <tbody>
        {rows.map(([label, value]) => (
          <tr key={label}>
            <th scope="row">{label}</th>
            <td>{value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function TradeDetailPage() {
  const { tradeId = "" } = useParams();
  const trade = useTrade(tradeId);
  const events = useAuditLog(tradeId);
  const strategies = useStrategies();

  return (
    <>
      <p>
        <Link to="/trades">← Trades</Link>
      </p>
      {trade.isPending && <Loading />}
      {trade.error && <ErrorMessage error={trade.error} />}
      {trade.data && (
        <>
          <h1>
            {trade.data.symbol} {trade.data.direction}
          </h1>
          <Summary
            trade={trade.data}
            strategyName={strategies.data?.find((s) => s.id === trade.data.strategy_id)?.name}
          />
          <h2>History</h2>
          {events.error && <ErrorMessage error={events.error} />}
          {events.data && <AuditLog events={events.data} />}
        </>
      )}
    </>
  );
}
