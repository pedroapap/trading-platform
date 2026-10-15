import { fireEvent, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw/http";
import { expect, test } from "vitest";

import type { components } from "../api/schema";
import { auditEvent, openTrade, trade } from "../test/fixtures";
import { renderPage } from "../test/render";
import { server } from "../test/server";

type Trade = components["schemas"]["TradeRead"];
type AuditEvent = components["schemas"]["AuditEventRead"];

const OPEN = openTrade();

/** A trade the API changes when it is closed or cancelled; returns the bodies it was sent. */
function tradeApi(initial: Trade, refusal?: Response) {
  let current = initial;
  const events: AuditEvent[] = [];
  const sent: Record<string, unknown> = {};
  server.use(
    http.get("/api/trades/:id", () => HttpResponse.json(current)),
    http.get("/api/trades/:id/audit-log", () => HttpResponse.json(events)),
    http.get("/api/strategies", () => HttpResponse.json([])),
    http.post("/api/trades/:id/close", async ({ request }) => {
      sent.close = await request.json();
      if (refusal) return refusal;
      current = trade({ id: current.id });
      return HttpResponse.json(current);
    }),
    http.post("/api/trades/:id/correct", async ({ request }) => {
      const body = (await request.json()) as { exit_price?: string; reason: string };
      sent.correct = body;
      if (refusal) return refusal;
      events.push(
        auditEvent({
          event_type: "correction",
          old_values: { exit_price: current.exit_price, pnl: current.pnl },
          new_values: { exit_price: body.exit_price, pnl: "100" },
          change_reason: body.reason,
        }),
      );
      current = {
        ...current,
        exit_price: body.exit_price ?? null,
        pnl: "100",
        updated_at: "2026-01-06T09:00:00Z",
      };
      return HttpResponse.json(current);
    }),
    http.post("/api/trades/:id/cancel", async ({ request }) => {
      sent.cancel = await request.json();
      current = { ...current, status: "cancelled" };
      return HttpResponse.json(current);
    }),
  );
  return sent;
}

function detailRow(label: RegExp) {
  return within(screen.getAllByRole("table")[0]).getByRole("row", { name: label });
}

test("an open trade can be closed", async () => {
  const sent = tradeApi(OPEN);
  const { user } = renderPage(`/trades/${OPEN.id}`);

  await user.click(await screen.findByText("Close trade"));
  await user.type(screen.getByLabelText("Exit price"), "50120");
  fireEvent.change(screen.getByLabelText("Exit time"), { target: { value: "2026-01-05T16:00" } });
  await user.click(screen.getByRole("button", { name: "Save exit" }));

  expect(await screen.findByText("120 USDT")).toBeInTheDocument();
  expect(detailRow(/^Status/)).toHaveTextContent("closed");
  expect(screen.queryByText("Close trade")).not.toBeInTheDocument();
  expect(sent.close).toEqual({
    exit_price: "50120",
    exit_time: "2026-01-05T16:00:00.000Z",
    exit_fee: "0",
  });
});

test("an open trade can be cancelled, with a reason", async () => {
  const sent = tradeApi(OPEN);
  const { user } = renderPage(`/trades/${OPEN.id}`);

  await user.click(await screen.findByText("Cancel trade"));
  await user.type(screen.getByLabelText("Why it never happened (optional)"), "Limit never filled");
  await user.click(screen.getByRole("button", { name: "Confirm cancellation" }));

  await screen.findByText("cancelled");
  expect(sent.cancel).toEqual({ reason: "Limit never filled" });
});

test("a refused close says why", async () => {
  tradeApi(OPEN, HttpResponse.json({ detail: "Cannot close a closed trade" }, { status: 409 }));
  const { user } = renderPage(`/trades/${OPEN.id}`);

  await user.click(await screen.findByText("Close trade"));
  await user.type(screen.getByLabelText("Exit price"), "50120");
  await user.click(screen.getByRole("button", { name: "Save exit" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Cannot close a closed trade");
});

test("a correction sends only what changed, with its reason, and is kept in the history", async () => {
  const closed = trade({ stop_loss: "49000" });
  const sent = tradeApi(closed);
  const { user } = renderPage(`/trades/${closed.id}`);

  await user.click(await screen.findByText("Correct trade"));
  const exitPrice = screen.getByRole("textbox", { name: "Exit price" });
  await user.clear(exitPrice);
  await user.type(exitPrice, "50100");
  await user.clear(screen.getByRole("textbox", { name: "Stop-loss" }));
  await user.type(screen.getByLabelText("Reason for the correction"), "Typed the exit price wrong");
  await user.click(screen.getByRole("button", { name: "Save correction" }));

  expect(await screen.findByText("100 USDT")).toBeInTheDocument();
  expect(sent.correct).toEqual({
    exit_price: "50100",
    stop_loss: null,
    reason: "Typed the exit price wrong",
  });
  const history = screen.getAllByRole("table")[1];
  expect(within(history).getByText("Typed the exit price wrong")).toBeInTheDocument();
  expect(within(history).getByText("exit price: 50120 → 50100")).toBeInTheDocument();
});

test("a correction must change something", async () => {
  const closed = trade();
  const sent = tradeApi(closed);
  const { user } = renderPage(`/trades/${closed.id}`);

  await user.click(await screen.findByText("Correct trade"));
  await user.type(screen.getByLabelText("Reason for the correction"), "Checking");
  await user.click(screen.getByRole("button", { name: "Save correction" }));

  expect(screen.getByRole("alert")).toHaveTextContent("Nothing to correct");
  expect(sent.correct).toBeUndefined();
});

test("an open trade is closed, not corrected", async () => {
  tradeApi(OPEN);

  renderPage(`/trades/${OPEN.id}`);

  expect(await screen.findByText("Close trade")).toBeInTheDocument();
  expect(screen.queryByText("Correct trade")).not.toBeInTheDocument();
});

test("a closed trade can't be closed or cancelled again", async () => {
  const closed = trade();
  tradeApi(closed);

  renderPage(`/trades/${closed.id}`);

  expect(await screen.findByText("120 USDT")).toBeInTheDocument();
  expect(screen.queryByText("Close trade")).not.toBeInTheDocument();
  expect(screen.queryByText("Cancel trade")).not.toBeInTheDocument();
});
