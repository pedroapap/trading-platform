import { screen, within } from "@testing-library/react";
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

const CSV = "time,open,high,low,close,volume\n2026-01-05T00:00:00Z,1,2,0.5,1.5,10\n";

type ImportResult = components["schemas"]["ImportResult"];

/** An import endpoint answering with `response`, and the coverage it leaves. Returns each
 * upload's fields, files as their text. */
function importEndpoint(response: Response, after: Coverage[] = []) {
  const uploads: Record<string, string>[] = [];
  let coverage: Coverage[] = [];
  server.use(
    http.get("/api/market-data/symbols", () => HttpResponse.json(coverage)),
    http.post("/api/market-data/import", async ({ request }) => {
      const fields: Record<string, string> = {};
      for (const [name, value] of await request.formData()) {
        fields[name] = typeof value === "string" ? value : await value.text();
      }
      uploads.push(fields);
      coverage = after;
      return response;
    }),
  );
  return uploads;
}

function imported(overrides: Partial<ImportResult> = {}): ImportResult {
  return {
    symbol: "BTCUSDT",
    timeframe: "1h",
    format: "generic_ohlcv",
    inserted: 2,
    duplicates: 1,
    rejected: 2,
    first_ts: "2026-01-05T00:00:00Z",
    last_ts: "2026-01-05T02:00:00Z",
    rejections: [
      { line: 4, reason: "low/high do not bracket open and close" },
      { line: 5, reason: "volume cannot be negative" },
    ],
    ...overrides,
  };
}

async function importFile(user: ReturnType<typeof renderPage>["user"], timeframe?: string) {
  await user.upload(
    screen.getByLabelText("CSV file"),
    new File([CSV], "btc.csv", { type: "text/csv" }),
  );
  await user.type(screen.getByLabelText("Symbol"), " btcusdt ");
  if (timeframe) await user.selectOptions(screen.getByLabelText("Timeframe"), timeframe);
  await user.click(screen.getByRole("button", { name: "Import" }));
}

test("an imported file is summed up, with its rejected rows, and the stored bars refresh", async () => {
  const uploads = importEndpoint(HttpResponse.json(imported()), [
    {
      symbol: "BTCUSDT",
      timeframe: "1h",
      first_ts: "2026-01-05T00:00:00Z",
      last_ts: "2026-01-05T02:00:00Z",
      bars: 3,
    },
  ]);
  const { user } = renderPage("/market-data");
  await screen.findByText("No bars stored yet.");

  await importFile(user, "1h");

  const summary = await screen.findByRole("article", { name: "Import summary" });
  expect(summary).toHaveTextContent(
    "BTCUSDT 1h (generic_ohlcv): 2 bars added, 1 already stored, 2 rejected. " +
      "The file's bars run from Jan 5, 2026, 12:00 AM to Jan 5, 2026, 2:00 AM.",
  );
  expect(within(summary).getByText("Rejected rows:")).toBeInTheDocument();
  const rejected = within(summary).getAllByRole("row").slice(1);
  expect(rejected.map((row) => row.textContent)).toEqual([
    "4low/high do not bracket open and close",
    "5volume cannot be negative",
  ]);
  expect(await screen.findByRole("row", { name: /^BTCUSDT 1h/ })).toHaveTextContent(/3$/);
  // The format is left for the API to detect.
  expect(uploads).toEqual([{ file: CSV, symbol: "btcusdt", timeframe: "1h" }]);
});

test("only the first rejected rows are listed when the API reports some", async () => {
  importEndpoint(HttpResponse.json(imported({ inserted: 0, duplicates: 0, rejected: 1_500 })));
  const { user } = renderPage("/market-data");

  await importFile(user);

  const summary = await screen.findByRole("article", { name: "Import summary" });
  expect(summary).toHaveTextContent("1,500 rejected.");
  expect(within(summary).getByText("The first 2 rejected rows:")).toBeInTheDocument();
});

test("a file the API refuses says why", async () => {
  const uploads = importEndpoint(
    HttpResponse.json({ detail: "The file is larger than 200 MB" }, { status: 413 }),
  );
  const { user } = renderPage("/market-data");

  await importFile(user);

  expect(await screen.findByRole("alert")).toHaveTextContent("The file is larger than 200 MB");
  expect(uploads).toHaveLength(1);
  expect(screen.queryByRole("article")).not.toBeInTheDocument();
});

test("a missing file is pointed out", async () => {
  importEndpoint(
    HttpResponse.json(
      { detail: [{ loc: ["body", "file"], msg: "Field required", type: "missing" }] },
      { status: 422 },
    ),
  );
  const { user } = renderPage("/market-data");

  await user.type(screen.getByLabelText("Symbol"), "BTCUSDT");
  await user.click(screen.getByRole("button", { name: "Import" }));

  expect(await screen.findByText("Field required")).toBeInTheDocument();
  expect(screen.getByLabelText("CSV file")).toHaveAccessibleDescription("Field required");
});
