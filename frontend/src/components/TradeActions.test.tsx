import { fireEvent, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw/http";
import { expect, test } from "vitest";

import type { components } from "../api/schema";
import { openTrade, trade } from "../test/fixtures";
import { renderPage } from "../test/render";
import { server } from "../test/server";

type Trade = components["schemas"]["TradeRead"];

const OPEN = openTrade();

/** A trade the API changes when it is closed or cancelled; returns the bodies it was sent. */
function tradeApi(initial: Trade, refusal?: Response) {
  let current = initial;
  const sent: Record<string, unknown> = {};
  server.use(
    http.get("/api/trades/:id", () => HttpResponse.json(current)),
    http.get("/api/trades/:id/audit-log", () => HttpResponse.json([])),
    http.get("/api/strategies", () => HttpResponse.json([])),
    http.post("/api/trades/:id/close", async ({ request }) => {
      sent.close = await request.json();
      if (refusal) return refusal;
      current = trade({ id: current.id });
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

test("a closed trade can't be closed or cancelled again", async () => {
  const closed = trade();
  tradeApi(closed);

  renderPage(`/trades/${closed.id}`);

  expect(await screen.findByText("120 USDT")).toBeInTheDocument();
  expect(screen.queryByText("Close trade")).not.toBeInTheDocument();
  expect(screen.queryByText("Cancel trade")).not.toBeInTheDocument();
});
