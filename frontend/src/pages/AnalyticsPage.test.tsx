import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw/http";
import { expect, test } from "vitest";

import type { components } from "../api/schema";
import { STRATEGY } from "../test/fixtures";
import { renderPage } from "../test/render";
import { server } from "../test/server";

type Schemas = components["schemas"];

const BY_STRATEGY: Schemas["PerformanceGroup"][] = [
  {
    key: STRATEGY.id,
    label: "RSI dip",
    num_trades: 4,
    wins: 3,
    losses: 1,
    win_rate_pct: 75,
    average_return_pct: "1.5",
    by_currency: [
      { currency: "BTC", num_trades: 1, total_pnl: "0.01", average_pnl: "0.01" },
      { currency: "USDT", num_trades: 2, total_pnl: "120", average_pnl: "60" },
      { currency: null, num_trades: 1, total_pnl: "-25", average_pnl: "-25" },
    ],
  },
  {
    key: null,
    label: null,
    num_trades: 3,
    wins: 1,
    losses: 2,
    win_rate_pct: 33.333333,
    average_return_pct: "-0.4",
    by_currency: [{ currency: "USDT", num_trades: 3, total_pnl: "-10.5", average_pnl: "-3.5" }],
  },
];

/** Performance in `groups` whatever is asked; returns the queries asked. */
function performanceEndpoint(groups = BY_STRATEGY) {
  const queries: URLSearchParams[] = [];
  server.use(
    http.get("/api/analytics/performance", ({ request }) => {
      const query = new URL(request.url).searchParams;
      queries.push(query);
      return HttpResponse.json({ by: query.get("by"), groups });
    }),
  );
  return queries;
}

test("performance is grouped by strategy, with money per currency", async () => {
  performanceEndpoint();

  renderPage("/analytics");

  const [dip, none] = (await screen.findAllByRole("row")).slice(1);
  expect(dip).toHaveTextContent(
    "RSI dip43175.00%1.50%" +
      "0.01 BTC (1 trade, average 0.01)" +
      "120 USDT (2 trades, average 60.00)" +
      "-25 currency not set (1 trade, average -25.00)",
  );
  expect(within(dip).getByRole("link", { name: "RSI dip" })).toHaveAttribute(
    "href",
    `/strategies/${STRATEGY.id}`,
  );
  expect(within(dip).getByRole("link", { name: "currency not set" })).toHaveAttribute(
    "href",
    "/instruments",
  );
  expect(none).toHaveTextContent("No strategy31233.33%-0.40%-10.5 USDT (3 trades, average -3.50)");
});

test("the grouping, journal entry type and closing dates go to the API and the URL", async () => {
  const queries = performanceEndpoint();
  const { router, user } = renderPage("/analytics");
  await screen.findByText("RSI dip");
  expect(screen.getByLabelText("Journal entries")).toBeDisabled();

  await user.selectOptions(screen.getByLabelText("Group by"), "emotion");
  await user.selectOptions(screen.getByLabelText("Journal entries"), "pre_trade");
  fireEvent.change(screen.getByLabelText("Closed from"), { target: { value: "2026-01-01" } });
  fireEvent.change(screen.getByLabelText("Closed to (inclusive)"), {
    target: { value: "2026-01-31" },
  });

  await screen.findByRole("columnheader", { name: "Emotion" });
  expect(
    Object.fromEntries(
      router.state.location.search
        .slice(1)
        .split("&")
        .map((pair) => pair.split("=")),
    ),
  ).toEqual({
    by: "emotion",
    entry_type: "pre_trade",
    from: "2026-01-01",
    to: "2026-01-31",
  });
  // The "to" date is inclusive: trades closed before the next day count. (Requests can reach
  // the API out of order, so the last one recorded isn't necessarily the last one made.)
  await waitFor(() =>
    expect(queries.map((query) => Object.fromEntries(query))).toContainEqual({
      by: "emotion",
      entry_type: "pre_trade",
      closed_from: "2026-01-01T00:00:00.000Z",
      closed_to: "2026-02-01T00:00:00.000Z",
    }),
  );
});

test("the entry type only narrows groupings that come from the journal", async () => {
  const queries = performanceEndpoint();
  const { router, user } = renderPage("/analytics?by=tag&entry_type=post_trade");
  await screen.findByRole("columnheader", { name: "Tag" });
  expect(queries.at(-1)?.get("entry_type")).toBe("post_trade");

  await user.selectOptions(screen.getByLabelText("Group by"), "symbol");

  await screen.findByRole("columnheader", { name: "Symbol" });
  expect(router.state.location.search).toBe("?by=symbol");
  expect(queries.at(-1)?.has("entry_type")).toBe(false);
  expect(screen.getByLabelText("Journal entries")).toBeDisabled();
});

test("without closed trades there is nothing to show", async () => {
  performanceEndpoint([]);

  renderPage("/analytics");

  expect(await screen.findByText("No closed trades in this period.")).toBeInTheDocument();
});
