import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw/http";
import { expect, test } from "vitest";

import type { components } from "../api/schema";
import { auditEvent, STRATEGY, trade } from "../test/fixtures";
import { renderPage } from "../test/render";
import { server } from "../test/server";

type Trade = components["schemas"]["TradeRead"];
type AuditEvent = components["schemas"]["AuditEventRead"];

function tradeEndpoints(detail: Trade, events: AuditEvent[] = []) {
  server.use(
    http.get("/api/trades/:id", () => HttpResponse.json(detail)),
    http.get("/api/trades/:id/audit-log", () => HttpResponse.json(events)),
    http.get("/api/strategies", () => HttpResponse.json([STRATEGY])),
  );
}

const CLOSED = trade({ strategy_id: STRATEGY.id, strategy_version: 2, stop_loss: "49000" });

const HISTORY = [
  auditEvent({
    event_type: "entry",
    new_values: { symbol: "BTCUSDT", entry_price: "50000", stop_loss: "49000", take_profit: null },
    created_at: "2026-01-05T14:30:00Z",
  }),
  auditEvent({
    event_type: "exit",
    old_values: { status: "open", exit_price: null, exit_time: null },
    new_values: { status: "closed", exit_price: "50100", exit_time: "2026-01-05T16:00:00Z" },
    created_at: "2026-01-05T16:00:00Z",
  }),
  auditEvent({
    event_type: "correction",
    old_values: { exit_price: "50100", pnl: "100" },
    new_values: { exit_price: "50120", pnl: "120" },
    change_reason: "Typed the exit price wrong",
    created_at: "2026-01-06T09:00:00Z",
  }),
];

test("a trade shows its details", async () => {
  tradeEndpoints(CLOSED, HISTORY);

  renderPage(`/trades/${CLOSED.id}`);

  expect(await screen.findByRole("heading", { name: "BTCUSDT long" })).toBeInTheDocument();
  const details = screen.getAllByRole("table")[0];
  expect(within(details).getByRole("row", { name: /^P&L/ })).toHaveTextContent("120.00 USDT");
  expect(within(details).getByRole("row", { name: /^Stop-loss/ })).toHaveTextContent("49000");
  expect(await within(details).findByText("RSI dip v2")).toBeInTheDocument();
});

test("its history lists each change oldest first, with reasons", async () => {
  tradeEndpoints(CLOSED, HISTORY);

  renderPage(`/trades/${CLOSED.id}`);

  const history = (await screen.findAllByRole("table"))[1];
  const [entered, closed, corrected] = within(history).getAllByRole("row").slice(1);
  // The entry lists the values set; a value left empty isn't listed.
  expect(entered).toHaveTextContent("Jan 5, 2026, 2:30 PMEntered");
  expect(entered).toHaveTextContent("entry price: 50000");
  expect(entered).not.toHaveTextContent("take profit");
  expect(closed).toHaveTextContent("status: open → closed");
  expect(closed).toHaveTextContent("exit price: — → 50100");
  expect(closed).toHaveTextContent("exit time: — → Jan 5, 2026, 4:00 PM");
  expect(corrected).toHaveTextContent("Corrected");
  expect(corrected).toHaveTextContent("exit price: 50100 → 50120");
  expect(corrected).toHaveTextContent("Typed the exit price wrong");
});

test("the trades list links to each trade", async () => {
  tradeEndpoints(CLOSED, HISTORY);
  server.use(
    http.get("/api/trades", () =>
      HttpResponse.json({ items: [CLOSED], total: 1, limit: 50, offset: 0 }),
    ),
  );
  const { router, user } = renderPage("/trades");

  await user.click(await screen.findByRole("link", { name: "BTCUSDT" }));

  expect(await screen.findByRole("heading", { name: "BTCUSDT long" })).toBeInTheDocument();
  expect(router.state.location.pathname).toBe(`/trades/${CLOSED.id}`);
});

test("an unknown trade says so", async () => {
  server.use(
    http.get("/api/trades/:id", () =>
      HttpResponse.json({ detail: "Trade not found" }, { status: 404 }),
    ),
    http.get("/api/trades/:id/audit-log", () =>
      HttpResponse.json({ detail: "Trade not found" }, { status: 404 }),
    ),
    http.get("/api/strategies", () => HttpResponse.json([])),
  );

  renderPage(`/trades/${CLOSED.id}`);

  expect(await screen.findByRole("alert")).toHaveTextContent("Trade not found");
});
