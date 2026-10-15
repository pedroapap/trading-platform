import { fireEvent, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw/http";
import { expect, test } from "vitest";

import type { components } from "../api/schema";
import { pendingBacktest, STRATEGY } from "../test/fixtures";
import { renderPage } from "../test/render";
import { server } from "../test/server";

type BacktestCreate = components["schemas"]["BacktestCreate"];

const OTHER = { ...STRATEGY, id: "7a1e2b3c-4d5e-4f60-8a1b-2c3d4e5f6a7b", name: "Breakout" };

/** Strategies, stored BTCUSDT bars and a backtests API; POST answers with `refusal` when
 * given. Returns the bodies posted. */
function backtestApi(refusal?: Response, strategies = [OTHER, STRATEGY]) {
  const posted: BacktestCreate[] = [];
  const created = pendingBacktest();
  server.use(
    http.get("/api/strategies", () => HttpResponse.json(strategies)),
    http.get("/api/market-data/symbols", () =>
      HttpResponse.json([
        {
          symbol: "BTCUSDT",
          timeframe: "1h",
          first_ts: "2025-01-01T00:00:00Z",
          last_ts: "2025-12-31T23:00:00Z",
          bars: 8760,
        },
      ]),
    ),
    http.post("/api/backtests", async ({ request }) => {
      posted.push((await request.json()) as BacktestCreate);
      return refusal ?? HttpResponse.json(created, { status: 202 });
    }),
    http.get("/api/backtests/:id", () => HttpResponse.json(created)),
  );
  return posted;
}

test("a backtest runs with the form's settings, then shows its page", async () => {
  const posted = backtestApi();
  const { router, user } = renderPage(`/backtests/new?strategy=${STRATEGY.id}`);
  await screen.findByRole("option", { name: "RSI dip" });

  expect(screen.getByLabelText("Strategy")).toHaveValue(STRATEGY.id);
  expect(screen.getByLabelText("Version")).toHaveAttribute("placeholder", "Current: v2");
  // Stored symbols are suggested.
  await waitFor(() =>
    expect(document.querySelector('datalist option[value="BTCUSDT"]')).toBeInTheDocument(),
  );
  await user.type(screen.getByLabelText("Symbol"), "BTCUSDT");
  await user.selectOptions(screen.getByLabelText("Timeframe"), "4h");
  fireEvent.change(screen.getByLabelText("From (optional)"), {
    target: { value: "2025-01-01T00:00" },
  });
  await user.clear(screen.getByLabelText("Fee %"));
  await user.type(screen.getByLabelText("Fee %"), "0.1");
  await user.click(screen.getByRole("button", { name: "Run backtest" }));

  expect(await screen.findByText(/^Waiting to run/)).toBeInTheDocument();
  expect(router.state.location.pathname).toMatch(/^\/backtests\/[0-9a-f-]{36}$/);
  // Amounts go as typed; the version and the end are left for the API to default.
  expect(posted).toEqual([
    {
      strategy_id: STRATEGY.id,
      symbol: "BTCUSDT",
      timeframe: "4h",
      start: "2025-01-01T00:00:00.000Z",
      initial_capital: "10000",
      position_size_pct: "100",
      fee_pct: "0.1",
      slippage_pct: "0",
      periods_per_year: 365,
    },
  ]);
});

test("without a strategy chosen, the first one runs", async () => {
  const posted = backtestApi();
  const { user } = renderPage("/backtests/new");
  await screen.findByRole("option", { name: "Breakout" });

  await user.type(screen.getByLabelText("Symbol"), "BTCUSDT");
  await user.click(screen.getByRole("button", { name: "Run backtest" }));

  await screen.findByText(/^Waiting to run/);
  expect(posted[0].strategy_id).toBe(OTHER.id);
});

test("a run the API refuses says why", async () => {
  backtestApi(
    HttpResponse.json({ detail: "There are no BTCUSDT bars in this range" }, { status: 422 }),
  );
  const { user } = renderPage("/backtests/new");

  await user.type(screen.getByLabelText("Symbol"), "BTCUSDT");
  await user.click(screen.getByRole("button", { name: "Run backtest" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "There are no BTCUSDT bars in this range",
  );
});

test("a setting the API rejects shows why under it", async () => {
  backtestApi(
    HttpResponse.json(
      {
        detail: [
          {
            loc: ["body", "position_size_pct"],
            msg: "Input should be less than or equal to 100",
            type: "less_than_equal",
          },
        ],
      },
      { status: 422 },
    ),
  );
  const { user } = renderPage("/backtests/new");

  await user.type(screen.getByLabelText("Position size %"), "0");
  await user.click(screen.getByRole("button", { name: "Run backtest" }));

  expect(await screen.findByText("Input should be less than or equal to 100")).toBeInTheDocument();
  expect(screen.getByLabelText("Position size %")).toHaveAttribute("aria-invalid", "true");
});

test("without strategies there is nothing to run yet", async () => {
  backtestApi(undefined, []);

  renderPage("/backtests/new");

  expect(await screen.findByText(/A backtest runs a strategy/)).toHaveTextContent(
    "A backtest runs a strategy: create one first.",
  );
  expect(screen.getByRole("link", { name: "create one" })).toHaveAttribute(
    "href",
    "/strategies/new",
  );
});
