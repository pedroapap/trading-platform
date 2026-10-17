import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw/http";
import { expect, test } from "vitest";

import type { components } from "../api/schema";
import { openTrade, STRATEGY, trade } from "../test/fixtures";
import { renderPage } from "../test/render";
import { server } from "../test/server";

type Trade = components["schemas"]["TradeRead"];

/** Serves `trades` as one page of `total`; returns the query of each request it got. */
function tradesEndpoint(trades: Trade[], total = trades.length) {
  const queries: URLSearchParams[] = [];
  server.use(
    http.get("/api/trades", ({ request }) => {
      const query = new URL(request.url).searchParams;
      queries.push(query);
      return HttpResponse.json({
        items: trades,
        total,
        limit: Number(query.get("limit")),
        offset: Number(query.get("offset")),
      });
    }),
    http.get("/api/strategies", () => HttpResponse.json([STRATEGY])),
  );
  return queries;
}

function rows() {
  return screen.getAllByRole("row").slice(1);
}

test("trades show their P&L in their quote currency", async () => {
  tradesEndpoint([
    trade({ strategy_id: STRATEGY.id, strategy_version: 2 }),
    trade({ symbol: "AAPL", quote_currency: null, pnl: "-5", pnl_pct: "-0.25" }),
    openTrade({ symbol: "ETHBTC", quote_currency: "BTC", entry_size: "2", entry_price: "0.05" }),
  ]);

  renderPage("/trades");

  expect(await screen.findByText("RSI dip v2")).toBeInTheDocument();
  const [btc, aapl, eth] = rows();
  expect(btc).toHaveTextContent("BTCUSDTlongclosed1 @ 500001 @ 50120120.00 USDT0.24%RSI dip v2");
  expect(within(aapl).getByRole("link", { name: "currency not set" })).toHaveAttribute(
    "href",
    "/instruments",
  );
  expect(aapl).toHaveTextContent("-5 currency not set-0.25%");
  expect(eth).toHaveTextContent("ETHBTClongopen2 @ 0.05——");
  expect(btc).toHaveTextContent("Jan 5, 2026, 2:30 PM");
});

test("filters go to the API and into the URL", async () => {
  const queries = tradesEndpoint([trade()]);
  const { router, user } = renderPage("/trades?page=3");
  await screen.findByText("120.00 USDT");

  await user.type(screen.getByLabelText("Symbol"), "btcusdt");
  await user.selectOptions(screen.getByLabelText("Status"), "closed");
  await user.click(screen.getByRole("button", { name: "Filter" }));

  await screen.findByText("120.00 USDT");
  expect(router.state.location.search).toBe("?symbol=btcusdt&status=closed");
  expect(Object.fromEntries(queries.at(-1)!)).toEqual({
    symbol: "btcusdt",
    status: "closed",
    limit: "50",
    offset: "0",
  });
});

test("pages step through the trades fifty at a time", async () => {
  const queries = tradesEndpoint([trade()], 120);
  const { user } = renderPage("/trades");
  expect(await screen.findByText("1–50 of 120")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();

  await user.click(screen.getByRole("button", { name: "Next" }));
  await user.click(await screen.findByRole("button", { name: "Next" }));

  expect(await screen.findByText("101–120 of 120")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  expect(queries.map((query) => query.get("offset"))).toEqual(["0", "50", "100"]);
});

test("without trades there is nothing to list", async () => {
  tradesEndpoint([]);

  renderPage("/trades");

  expect(await screen.findByText("No trades.")).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});
