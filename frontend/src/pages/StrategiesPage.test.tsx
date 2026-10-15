import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw/http";
import { expect, test } from "vitest";

import type { components } from "../api/schema";
import { STRATEGY } from "../test/fixtures";
import { renderPage } from "../test/render";
import { server } from "../test/server";

type Strategy = components["schemas"]["StrategyRead"];

function strategiesEndpoint(strategies: Strategy[]) {
  server.use(http.get("/api/strategies", () => HttpResponse.json(strategies)));
}

test("strategies show their direction, version, last change and description", async () => {
  strategiesEndpoint([
    { ...STRATEGY, name: "Breakout", description: "Range breaks on volume" },
    STRATEGY,
  ]);

  renderPage("/strategies");

  await screen.findByText("Breakout");
  const [breakout, dip] = screen.getAllByRole("row").slice(1);
  expect(breakout).toHaveTextContent("Breakoutlongv2Jan 2, 2026, 9:00 AMRange breaks on volume");
  expect(dip).toHaveTextContent("RSI diplongv2Jan 2, 2026, 9:00 AM—");
  expect(screen.getByRole("link", { name: "RSI dip" })).toHaveAttribute(
    "href",
    `/strategies/${STRATEGY.id}`,
  );
});

test("without strategies there is nothing to list, but one can be made", async () => {
  strategiesEndpoint([]);
  const { user } = renderPage("/strategies");

  expect(await screen.findByText("No strategies yet.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "New strategy" }));

  expect(screen.getByRole("heading", { name: "New strategy" })).toBeInTheDocument();
});
