import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw/http";
import { expect, test } from "vitest";

import type { components } from "../api/schema";
import { renderPage } from "../test/render";
import { server } from "../test/server";

type Instrument = components["schemas"]["InstrumentRead"];

/** Instruments the API updates as the real one does, normalizing the code. Returns each PUT's
 * path and body; a code that isn't 2-10 letters or digits is refused. */
function instrumentsApi(initial: Instrument[]) {
  const instruments = [...initial];
  const puts: { path: string; body: unknown }[] = [];
  server.use(
    http.get("/api/instruments", () => HttpResponse.json(instruments)),
    http.put("/api/instruments/*", async ({ request }) => {
      const body = (await request.json()) as { quote_currency: string };
      const path = new URL(request.url).pathname;
      puts.push({ path, body });
      const code = body.quote_currency.toUpperCase();
      if (!/^[A-Z0-9]{2,10}$/.test(code)) {
        return HttpResponse.json(
          {
            detail: [
              {
                loc: ["body", "quote_currency"],
                msg: "String should match pattern '^[A-Z0-9]{2,10}$'",
                type: "string_pattern_mismatch",
              },
            ],
          },
          { status: 422 },
        );
      }
      const symbol = decodeURIComponent(path.slice("/api/instruments/".length)).toUpperCase();
      const instrument = instruments.find((each) => each.symbol === symbol)!;
      instrument.quote_currency = code;
      return HttpResponse.json(instrument);
    }),
  );
  return puts;
}

const row = (symbol: string) => screen.getByRole("row", { name: new RegExp(`^${symbol}`) });
const input = (symbol: string) => screen.getByLabelText(`Quote currency of ${symbol}`);

test("each symbol shows its quote currency, and unset ones are marked", async () => {
  instrumentsApi([
    { symbol: "AAPL", quote_currency: null },
    { symbol: "BTCUSDT", quote_currency: "USDT" },
  ]);

  renderPage("/instruments");

  expect(await screen.findByText("currency not set")).toBeInTheDocument();
  expect(within(row("AAPL")).getByText("currency not set")).toBeInTheDocument();
  expect(input("AAPL")).toHaveValue("");
  expect(within(row("BTCUSDT")).queryByText("currency not set")).not.toBeInTheDocument();
  expect(input("BTCUSDT")).toHaveValue("USDT");
});

test("a currency is set in place, as the API normalizes it", async () => {
  const puts = instrumentsApi([{ symbol: "AAPL", quote_currency: null }]);
  const { user } = renderPage("/instruments");

  await user.type(await screen.findByLabelText("Quote currency of AAPL"), " usd ");
  await user.click(within(row("AAPL")).getByRole("button", { name: "Save" }));

  expect(await screen.findByDisplayValue("USD")).toBe(input("AAPL"));
  expect(screen.queryByText("currency not set")).not.toBeInTheDocument();
  expect(puts).toEqual([{ path: "/api/instruments/AAPL", body: { quote_currency: "usd" } }]);
});

test("a symbol with a slash goes in the path encoded", async () => {
  const puts = instrumentsApi([{ symbol: "BTC/EUR", quote_currency: "USD" }]);
  const { user } = renderPage("/instruments");

  const currency = await screen.findByLabelText("Quote currency of BTC/EUR");
  await user.clear(currency);
  await user.type(currency, "eur");
  await user.click(screen.getByRole("button", { name: "Save" }));

  // The row shows what the API saved once it remounts.
  expect(await screen.findByDisplayValue("EUR")).toBeInTheDocument();
  expect(puts.map(({ path }) => path)).toEqual(["/api/instruments/BTC%2FEUR"]);
});

test("a code the API refuses is explained on its row", async () => {
  instrumentsApi([{ symbol: "AAPL", quote_currency: null }]);
  const { user } = renderPage("/instruments");

  await user.type(await screen.findByLabelText("Quote currency of AAPL"), "US dollar");
  await user.click(screen.getByRole("button", { name: "Save" }));

  const message = "String should match pattern '^[A-Z0-9]{2,10}$'";
  expect(await within(row("AAPL")).findByText(message)).toBeInTheDocument();
  expect(input("AAPL")).toHaveAttribute("aria-invalid", "true");
  expect(input("AAPL")).toHaveAccessibleDescription(message);
});
