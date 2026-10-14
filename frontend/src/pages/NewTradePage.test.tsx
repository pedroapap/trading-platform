import { fireEvent, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw/http";
import { expect, test } from "vitest";

import { openTrade, STRATEGY } from "../test/fixtures";
import { renderPage } from "../test/render";
import { server } from "../test/server";

const CREATED = openTrade({ symbol: "ETHUSDT", direction: "short" });

/** The API's trade endpoints; POST answers with `response`. Returns the bodies posted. */
function tradeEndpoints(response = HttpResponse.json(CREATED, { status: 201 })) {
  const posted: unknown[] = [];
  server.use(
    http.get("/api/strategies", () => HttpResponse.json([STRATEGY])),
    http.post("/api/trades", async ({ request }) => {
      posted.push(await request.json());
      return response;
    }),
    http.get("/api/trades/:id", () => HttpResponse.json(CREATED)),
    http.get("/api/trades/:id/audit-log", () => HttpResponse.json([])),
  );
  return posted;
}

test("a new trade is logged and then shown", async () => {
  const posted = tradeEndpoints();
  const { router, user } = renderPage("/trades/new");
  await screen.findByRole("option", { name: "RSI dip (v2)" });

  await user.type(screen.getByLabelText("Symbol"), "ethusdt");
  await user.selectOptions(screen.getByLabelText("Direction"), "short");
  await user.type(screen.getByLabelText("Entry price"), "2500.123456789012");
  await user.type(screen.getByLabelText("Size"), "2");
  fireEvent.change(screen.getByLabelText("Entry time"), { target: { value: "2026-10-14T09:30" } });
  await user.type(screen.getByLabelText("Stop-loss"), "2600");
  await user.selectOptions(screen.getByLabelText("Strategy"), STRATEGY.id);
  await user.click(screen.getByRole("button", { name: "Log trade" }));

  expect(await screen.findByRole("heading", { name: "ETHUSDT short" })).toBeInTheDocument();
  expect(router.state.location.pathname).toBe(`/trades/${CREATED.id}`);
  // Prices go as typed, exactly; empty optional fields are left out.
  expect(posted).toEqual([
    {
      symbol: "ethusdt",
      direction: "short",
      entry_price: "2500.123456789012",
      entry_size: "2",
      entry_time: "2026-10-14T09:30:00.000Z",
      entry_fee: "0",
      stop_loss: "2600",
      leverage: "1",
      strategy_id: STRATEGY.id,
    },
  ]);
});

test("a field the API rejects shows why", async () => {
  tradeEndpoints(
    HttpResponse.json(
      {
        detail: [
          {
            loc: ["body", "entry_price"],
            msg: "Input should be greater than 0",
            type: "greater_than",
          },
        ],
      },
      { status: 422 },
    ),
  );
  const { user } = renderPage("/trades/new");

  await user.type(screen.getByLabelText("Entry price"), "-1");
  await user.click(screen.getByRole("button", { name: "Log trade" }));

  const price = screen.getByLabelText("Entry price");
  expect(await screen.findByText("Input should be greater than 0")).toBeInTheDocument();
  expect(price).toHaveAttribute("aria-invalid", "true");
  expect(price).toHaveAccessibleDescription("Input should be greater than 0");
});

test("an error about the whole trade is shown above the button", async () => {
  tradeEndpoints(HttpResponse.json({ detail: "The strategy has no version 7" }, { status: 422 }));
  const { user } = renderPage("/trades/new");

  await user.click(screen.getByRole("button", { name: "Log trade" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("The strategy has no version 7");
});

test("the trades list leads to the form", async () => {
  tradeEndpoints();
  server.use(
    http.get("/api/trades", () => HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 })),
  );
  const { user } = renderPage("/trades");

  await user.click(await screen.findByRole("button", { name: "New trade" }));

  expect(screen.getByRole("heading", { name: "New trade" })).toBeInTheDocument();
});
