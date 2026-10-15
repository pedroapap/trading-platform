import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw/http";
import { expect, test } from "vitest";

import type { components } from "../api/schema";
import { renderPage } from "../test/render";
import { server } from "../test/server";

type Coverage = components["schemas"]["CoverageRead"];

function coverageEndpoint(coverage: Coverage[]) {
  server.use(http.get("/api/market-data/symbols", () => HttpResponse.json(coverage)));
}

test("stored bars are listed by symbol and timeframe", async () => {
  coverageEndpoint([
    {
      symbol: "BTCUSDT",
      timeframe: "1m",
      first_ts: "2026-01-01T00:00:00Z",
      last_ts: "2026-12-31T23:59:00Z",
      bars: 525_600,
    },
    {
      symbol: "BTCUSDT",
      timeframe: "1d",
      first_ts: "2025-01-01T00:00:00Z",
      last_ts: "2025-12-31T00:00:00Z",
      bars: 365,
    },
  ]);

  renderPage("/market-data");

  await screen.findByText("525,600");
  const [minutes, days] = screen.getAllByRole("row").slice(1);
  expect(minutes).toHaveTextContent("BTCUSDT1mJan 1, 2026, 12:00 AMDec 31, 2026, 11:59 PM525,600");
  expect(days).toHaveTextContent("BTCUSDT1dJan 1, 2025, 12:00 AMDec 31, 2025, 12:00 AM365");
});

test("without bars there is nothing to list", async () => {
  coverageEndpoint([]);

  renderPage("/market-data");

  expect(await screen.findByText("No bars stored yet.")).toBeInTheDocument();
});
