import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw/http";
import { expect, test, vi } from "vitest";

import type { components } from "../api/schema";
import type { EquityChartProps } from "../components/EquityChart";
import { backtest, pendingBacktest, STRATEGY } from "../test/fixtures";
import { renderPage } from "../test/render";
import { server } from "../test/server";

type Schemas = components["schemas"];
type Backtest = Schemas["BacktestRead"];
type BacktestTrade = Schemas["BacktestTradeRead"];

// jsdom has no canvas: the chart says what it was given instead.
vi.mock("../components/EquityChart", () => ({
  default: ({ points, label, format, reference }: EquityChartProps) => (
    <figure>
      {label}: {points.length} points, {format(points[0].value)} to {format(points.at(-1)!.value)}
      {reference && `; ${reference.title} at ${reference.value}`}
    </figure>
  ),
}));

const DONE = backtest();

const EQUITY = [
  { ts: "2025-01-01T00:00:00Z", equity: 10_000 },
  { ts: "2025-06-01T00:00:00Z", equity: 9_150.5 },
  { ts: "2025-12-31T23:00:00Z", equity: 11_234.5 },
];

function trade(number: number): BacktestTrade {
  return {
    number,
    direction: "long",
    entry_time: "2025-01-11T01:00:00Z",
    entry_price: "44047.77288",
    exit_time: "2025-01-23T08:00:00Z",
    exit_price: "42704.9765237532",
    size: "0.226799434723",
    entry_fee: "9.99000999001",
    exit_fee: "9.685464535465",
    slippage: "9.837663585787",
    pnl: "-324.220929070927",
    pnl_pct: "-3.2456",
    exit_reason: "stop_loss",
  };
}

const COMPARISON: Schemas["BacktestComparison"] = {
  backtest_id: DONE.id,
  strategy_id: STRATEGY.id,
  strategy_version: 2,
  symbol: "BTCUSDT",
  quote_currency: "USDT",
  period_start: "2025-01-01T00:00:00Z",
  period_end: "2026-01-01T00:00:00Z",
  backtest: {
    num_trades: 42,
    win_rate_pct: 57.142857,
    average_return_pct: "0.8123",
    total_pnl: "1234.567891",
  },
  live: { num_trades: 2, win_rate_pct: 50, average_return_pct: "1.2", total_pnl: "120" },
};

/** A backtest that goes through `states`, then stays in the last; its equity, `total` trades
 * and `comparison` with live trades. Returns the trade pages and comparisons asked for. */
function backtestApi(states: Backtest[], { total = 2, comparison = COMPARISON } = {}) {
  let asked = 0;
  const tradePages: number[] = [];
  const comparisons: string[] = [];
  server.use(
    http.get("/api/analytics/backtests/:id/comparison", ({ params }) => {
      comparisons.push(String(params.id));
      return HttpResponse.json(comparison);
    }),
    http.get("/api/strategies", () => HttpResponse.json([STRATEGY])),
    http.get("/api/backtests/:id", () => {
      asked += 1;
      return HttpResponse.json(states[Math.min(asked, states.length) - 1]);
    }),
    http.get("/api/backtests/:id/equity", () => HttpResponse.json(EQUITY)),
    http.get("/api/backtests/:id/trades", ({ request }) => {
      const offset = Number(new URL(request.url).searchParams.get("offset"));
      tradePages.push(offset);
      const items = Array.from({ length: Math.min(50, total - offset) }, (_, i) =>
        trade(offset + i + 1),
      );
      return HttpResponse.json({ items, total, limit: 50, offset });
    }),
  );
  return { tradePages, comparisons };
}

const setting = (label: string) => screen.getByRole("row", { name: new RegExp(`^${label}`) });
const tile = (label: string) => screen.getByText(label, { selector: "dt" }).parentElement;

test("a completed backtest shows what ran, its results, equity and trades", async () => {
  backtestApi([DONE]);

  renderPage(`/backtests/${DONE.id}`);

  expect(
    await screen.findByRole("heading", { name: "RSI dip v2 on BTCUSDT 1h" }),
  ).toBeInTheDocument();
  expect(setting("Bars used")).toHaveTextContent(
    "8,760, Jan 1, 2025, 12:00 AM – Dec 31, 2025, 11:00 PM",
  );
  expect(setting("Asked for")).toHaveTextContent("All stored bars");
  expect(setting("Initial capital")).toHaveTextContent("10000 USDT");
  expect(setting("Costs")).toHaveTextContent("0.1% fee and 0.05% slippage per fill");
  expect(setting("Data fingerprint")).toHaveTextContent("9f2c4e0a7b1d");
  expect(tile("Total return")).toHaveTextContent("12.35%");
  expect(tile("Max drawdown")).toHaveTextContent("8.50%");
  expect(tile("Sharpe ratio")).toHaveTextContent("1.23");
  expect(tile("Win rate")).toHaveTextContent("57.14%");
  expect(tile("Average loss")).toHaveTextContent("-80.25 USDT");
  expect(await screen.findByRole("figure")).toHaveTextContent(
    "Equity: 3 points, 10,000.00 USDT to 11,234.50 USDT; Initial capital at 10000",
  );
  const [first] = (await screen.findAllByRole("row", { name: /^1 long/ })).slice(0, 1);
  expect(first).toHaveTextContent(
    "1longJan 11, 2025, 1:00 AM@ 44,047.773Jan 23, 2025, 8:00 AM@ 42,704.977" +
      "0.2267994329.51-324.22 USDT-3.25%stop-loss",
  );
});

test("a running backtest is followed until it completes", async () => {
  const running = pendingBacktest({ id: DONE.id, status: "running" });
  backtestApi([running, running, DONE]);

  renderPage(`/backtests/${DONE.id}`);

  expect(
    await screen.findByText("Running. This page updates when it is done."),
  ).toBeInTheDocument();
  expect(
    await screen.findByRole("heading", { name: "Results" }, { timeout: 4_000 }),
  ).toBeInTheDocument();
  expect(screen.getByText(/^Completed/)).toBeInTheDocument();
}, 10_000);

test("a failed backtest says why, and has no results", async () => {
  backtestApi([
    backtest({
      status: "failed",
      error_message: "There are no BTCUSDT bars in this range",
      metrics: null,
    }),
  ]);

  renderPage(`/backtests/${DONE.id}`);

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Failed: There are no BTCUSDT bars in this range",
  );
  expect(screen.queryByRole("heading", { name: "Results" })).not.toBeInTheDocument();
});

test("trades come a page at a time", async () => {
  const { tradePages } = backtestApi([DONE], { total: 120 });
  const { router, user } = renderPage(`/backtests/${DONE.id}`);
  const pages = await screen.findByRole("navigation", { name: "Pages" });
  expect(within(pages).getByText("1–50 of 120")).toBeInTheDocument();

  await user.click(within(pages).getByRole("button", { name: "Next" }));

  expect(await within(pages).findByText("51–100 of 120")).toBeInTheDocument();
  expect(router.state.location.search).toBe("?page=2");
  expect(tradePages).toEqual([0, 50]);
});

test("a completed backtest is set beside the live trades that followed it", async () => {
  backtestApi([DONE]);

  renderPage(`/backtests/${DONE.id}`);

  expect(await screen.findByText(/^Live trades of/)).toHaveTextContent(
    "Live trades of RSI dip v2 on BTCUSDT were entered between Jan 1, 2025, 12:00 AM and " +
      "Jan 1, 2026, 12:00 AM.",
  );
  const table = screen.getByText(/^Live trades of/).nextElementSibling as HTMLElement;
  const rows = within(table).getAllByRole("row");
  expect(rows.map((row) => row.textContent)).toEqual([
    "BacktestLive",
    "Trades422",
    "Win rate57.14%50.00%",
    "Average return on notional0.81%1.20%",
    "Total P&L1,234.57 USDT120.00 USDT",
  ]);
});

test("without live trades, the comparison says so", async () => {
  backtestApi([DONE], {
    comparison: {
      ...COMPARISON,
      live: { num_trades: 0, win_rate_pct: null, average_return_pct: null, total_pnl: "0" },
    },
  });

  renderPage(`/backtests/${DONE.id}`);

  expect(await screen.findByText(/^No live trades of RSI dip v2 on BTCUSDT/)).toBeInTheDocument();
});

test("nothing is compared before the backtest completes", async () => {
  const { comparisons } = backtestApi([pendingBacktest({ id: DONE.id, status: "running" })]);

  renderPage(`/backtests/${DONE.id}`);

  await screen.findByText("Running. This page updates when it is done.");
  expect(comparisons).toEqual([]);
});
