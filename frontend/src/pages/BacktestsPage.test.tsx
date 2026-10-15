import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw/http";
import { expect, test } from "vitest";

import type { components } from "../api/schema";
import { backtest, pendingBacktest, STRATEGY } from "../test/fixtures";
import { renderPage } from "../test/render";
import { server } from "../test/server";

type Backtest = components["schemas"]["BacktestRead"];

/** Lists the backtests `pages` returns in turn, the last one from then on. Returns the
 * queries asked. */
function backtestsEndpoint(...pages: Backtest[][]) {
  const queries: URLSearchParams[] = [];
  server.use(
    http.get("/api/strategies", () => HttpResponse.json([STRATEGY])),
    http.get("/api/backtests", ({ request }) => {
      queries.push(new URL(request.url).searchParams);
      const items = pages[Math.min(queries.length, pages.length) - 1];
      return HttpResponse.json({ items, total: items.length, limit: 50, offset: 0 });
    }),
  );
  return queries;
}

test("backtests show their strategy, bars, status and result", async () => {
  backtestsEndpoint([
    backtest(),
    backtest({
      status: "failed",
      error_message: "There are no BTCUSDT bars in this range",
      start: "2027-01-01T00:00:00Z",
      bars_count: null,
      first_bar_ts: null,
      last_bar_ts: null,
      metrics: null,
    }),
  ]);

  renderPage("/backtests");

  const [completed, failed] = (await screen.findAllByRole("row")).slice(1);
  expect(completed).toHaveTextContent(
    "Jan 10, 2026, 9:00 AMRSI dip v2BTCUSDT1hJan 1, 2025 – Dec 31, 2025completed12.35%42",
  );
  expect(failed).toHaveTextContent("Jan 1, 2027 – last barfailed——");
  expect(within(completed).getByRole("link", { name: "Jan 10, 2026, 9:00 AM" })).toHaveAttribute(
    "href",
    expect.stringMatching(/^\/backtests\/[0-9a-f-]{36}$/),
  );
  expect(screen.getByText("failed")).toHaveAttribute(
    "title",
    "There are no BTCUSDT bars in this range",
  );
});

test("the list refreshes while a backtest runs, and stops once it is done", async () => {
  const run = pendingBacktest({ status: "running" });
  const queries = backtestsEndpoint(
    [run],
    [{ ...run, status: "running" }],
    [backtest({ id: run.id })],
  );

  renderPage("/backtests");

  expect(await screen.findByText("running")).toBeInTheDocument();
  expect(await screen.findByText("completed", {}, { timeout: 4_000 })).toBeInTheDocument();
  expect(screen.getByText("12.35%")).toBeInTheDocument();
  const asked = queries.length;
  await new Promise((resolve) => setTimeout(resolve, 1_500));
  expect(queries).toHaveLength(asked);
}, 10_000);

test("the strategy filter goes to the API and into the URL", async () => {
  const queries = backtestsEndpoint([backtest()]);
  const { router, user } = renderPage("/backtests");
  await screen.findByRole("option", { name: "RSI dip" });

  await user.selectOptions(screen.getByLabelText("Strategy"), STRATEGY.id);
  await user.click(screen.getByRole("button", { name: "Filter" }));

  await screen.findByText("completed");
  expect(router.state.location.search).toBe(`?strategy_id=${STRATEGY.id}`);
  expect(queries.at(-1)?.get("strategy_id")).toBe(STRATEGY.id);
});
