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
  default: ({ points, label, format, reference, compared }: EquityChartProps) => {
    const curve = (name: string, curvePoints: typeof points) =>
      `${name}: ${curvePoints.length} points, ${format(curvePoints[0].value)} to ` +
      format(curvePoints.at(-1)!.value);
    return (
      <figure>
        {curve(label, points)}
        {reference && `; ${reference.title} at ${reference.value}`}
        {compared && `; ${curve(compared.label, compared.points)}`}
      </figure>
    );
  },
}));

const DONE = backtest();

const EQUITY = [
  { ts: "2025-01-01T00:00:00Z", equity: 10_000, benchmark: 9_985 },
  { ts: "2025-06-01T00:00:00Z", equity: 9_150.5, benchmark: 8_100 },
  { ts: "2025-12-31T23:00:00Z", equity: 11_234.5, benchmark: 10_810 },
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

/** A backtest that goes through `states`, then stays in the last; its `equity`, `total`
 * trades and `comparison` with live trades. Returns the trade pages and comparisons asked
 * for. */
function backtestApi(
  states: Backtest[],
  { total = 2, comparison = COMPARISON, equity = EQUITY as Schemas["EquityPoint"][] } = {},
) {
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
    http.get("/api/backtests/:id/equity", () => HttpResponse.json(equity)),
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
  expect(setting("Finer bars")).toHaveTextContent("None: inside a bar, the worst case counts");
  expect(setting("Out-of-sample from")).toHaveTextContent("Not set");
  // Return, CAGR and drawdown are compared with buy and hold over the same bars.
  expect(tile("Total return")).toHaveTextContent(/^Total return12.35%Buy and hold 8.10%$/);
  expect(tile("CAGR")).toHaveTextContent(/^CAGR12.35%Buy and hold 8.10%$/);
  expect(tile("Max drawdown")).toHaveTextContent(/^Max drawdown8.50%Buy and hold 22.40%$/);
  expect(tile("Sharpe ratio")).toHaveTextContent(/^Sharpe ratio1.23$/);
  expect(tile("Win rate")).toHaveTextContent("57.14%");
  expect(tile("Average loss")).toHaveTextContent("-80.25 USDT");
  expect(await screen.findByRole("figure")).toHaveTextContent(
    "Equity: 3 points, 10,000.00 USDT to 11,234.50 USDT; Initial capital at 10000; " +
      "Buy and hold: 3 points, 9,985.00 USDT to 10,810.00 USDT",
  );
  const [first] = (await screen.findAllByRole("row", { name: /^1 long/ })).slice(0, 1);
  expect(first).toHaveTextContent(
    "1longJan 11, 2025, 1:00 AM@ 44,047.773Jan 23, 2025, 8:00 AM@ 42,704.977" +
      "0.2267994329.51-324.22 USDT-3.25%stop-loss",
  );
  // 42 trades are enough to judge, and there is no out-of-sample start.
  expect(screen.queryByText(/Too few trades/)).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "In-sample and out-of-sample" })).toBeNull();
});

test("the average trade comes with its 95% range", async () => {
  const done = backtest({
    metrics: { ...DONE.metrics!, average_trade_pct: 0.45, average_trade_margin_pct: 0.24 },
  });
  backtestApi([done]);

  renderPage(`/backtests/${done.id}`);

  await screen.findByRole("heading", { name: "Results" });
  expect(tile("Average trade")).toHaveTextContent(/^Average trade0.45%95% range 0.21% to 0.69%$/);
});

test.each([
  { trades: 29, says: "With 29 trades, under 30," },
  { trades: 1, says: "With 1 trade, under 30," },
])("$trades trades are too few to judge", async ({ trades, says }) => {
  const few = backtest({ metrics: { ...DONE.metrics!, num_trades: trades } });
  backtestApi([few]);

  renderPage(`/backtests/${few.id}`);

  const warning = await screen.findByText("Too few trades to judge.");
  expect(warning.closest("p")).toHaveTextContent(says);
});

test("finer bars and an out-of-sample start are shown, with each side's results", async () => {
  const side = (overrides: Partial<Schemas["Metrics"]>): Schemas["Metrics"] => ({
    ...DONE.metrics!,
    average_trade_pct: 0.45,
    average_trade_margin_pct: 0.24,
    ...overrides,
  });
  const split = backtest({
    detail_timeframe: "1m",
    out_of_sample_from: "2025-10-01T00:00:00Z",
    split_metrics: {
      in_sample: side({ total_return_pct: 15.5, num_trades: 33 }),
      out_of_sample: side({
        total_return_pct: -2.75,
        buy_and_hold_return_pct: 1.5,
        num_trades: 9,
        average_trade_pct: -0.3,
        average_trade_margin_pct: null,
      }),
    },
  });
  backtestApi([split]);

  renderPage(`/backtests/${split.id}`);

  await screen.findByRole("heading", { name: "Results" });
  expect(setting("Finer bars")).toHaveTextContent("1m, to settle what came first inside a bar");
  expect(setting("Out-of-sample from")).toHaveTextContent("Oct 1, 2025, 12:00 AM");
  const heading = screen.getByRole("heading", { name: "In-sample and out-of-sample" });
  const explained = heading.nextElementSibling!;
  expect(explained).toHaveTextContent(/^Bars before Oct 1, 2025, 12:00 AM are in-sample/);
  const rows = within(explained.nextElementSibling as HTMLElement).getAllByRole("row");
  expect(rows.map((row) => row.textContent)).toEqual([
    "In-sampleOut-of-sample",
    "Total return15.50%-2.75%",
    "Buy and hold return8.10%1.50%",
    "CAGR12.35%12.35%",
    "Max drawdown8.50%8.50%",
    "Sharpe ratio1.231.23",
    "Trades33⚠ 9, too few to judge",
    "Win rate57.14%57.14%",
    "Profit factor1.601.60",
    "Expectancy29.39 USDT29.39 USDT",
    "Average trade0.45%-0.30%",
    "Its 95% range0.21% to 0.69%—",
    "Exposure35.50%35.50%",
  ]);
});

test("trailing stops, time exits, the end of the day and margin calls are named", async () => {
  backtestApi([DONE]);
  const reasons = ["trailing_stop", "time_exit", "end_of_day", "margin_call"] as const;
  server.use(
    http.get("/api/backtests/:id/trades", () =>
      HttpResponse.json({
        items: reasons.map((reason, i) => ({ ...trade(i + 1), exit_reason: reason })),
        total: reasons.length,
        limit: 50,
        offset: 0,
      }),
    ),
  );

  renderPage(`/backtests/${DONE.id}`);

  expect(await screen.findByRole("row", { name: /^1 long/ })).toHaveTextContent(/trailing stop$/);
  expect(screen.getByRole("row", { name: /^2 long/ })).toHaveTextContent(/time exit$/);
  expect(screen.getByRole("row", { name: /^3 long/ })).toHaveTextContent(/end of day$/);
  expect(screen.getByRole("row", { name: /^4 long/ })).toHaveTextContent(/margin call$/);
});

test("a backtest run before buy and hold was measured shows its results without it", async () => {
  const older = backtest({
    metrics: {
      ...DONE.metrics!,
      buy_and_hold_return_pct: undefined,
      buy_and_hold_cagr_pct: undefined,
      buy_and_hold_max_drawdown_pct: undefined,
    },
  });
  backtestApi([older], { equity: EQUITY.map(({ ts, equity }) => ({ ts, equity })) });

  renderPage(`/backtests/${older.id}`);

  expect(await screen.findByRole("figure")).toHaveTextContent(
    /^Equity: 3 points, 10,000.00 USDT to 11,234.50 USDT; Initial capital at 10000$/,
  );
  expect(tile("Total return")).toHaveTextContent(/^Total return12.35%$/);
  expect(screen.queryByText(/Buy and hold/)).not.toBeInTheDocument();
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
