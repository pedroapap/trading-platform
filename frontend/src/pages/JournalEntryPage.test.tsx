import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw/http";
import { expect, test } from "vitest";

import type { components } from "../api/schema";
import { journalEntry, trade } from "../test/fixtures";
import { renderPage } from "../test/render";
import { server } from "../test/server";

type Entry = components["schemas"]["JournalEntryRead"];

const TRADE = trade();

const DRAFT = journalEntry({
  entry_type: "pre_trade",
  title: "Buying the dip",
  thesis: "RSI under 30",
  lessons: null,
  emotion: "fomo",
  tags: ["dip"],
  trade_id: TRADE.id,
  status: "draft",
  current_version: 0,
  published_at: null,
});

/** An entry the API edits and publishes. Returns what it was sent; publishing answers with
 * `refusal` when given. */
function entryApi(initial: Entry, refusal?: Response) {
  let current = initial;
  const sent = { patches: [] as unknown[], publications: 0 };
  server.use(
    http.get("/api/trades", () =>
      HttpResponse.json({ items: [TRADE], total: 1, limit: 50, offset: 0 }),
    ),
    http.get("/api/journal/:id", () => HttpResponse.json(current)),
    http.patch("/api/journal/:id", async ({ request }) => {
      const changes = (await request.json()) as Partial<Entry>;
      sent.patches.push(changes);
      current = { ...current, ...changes, updated_at: "2026-01-05T17:30:00Z" };
      return HttpResponse.json(current);
    }),
    http.post("/api/journal/:id/publish", () => {
      sent.publications += 1;
      if (refusal) return refusal;
      current = {
        ...current,
        status: "published",
        current_version: 1,
        published_at: "2026-01-05T18:00:00Z",
        updated_at: "2026-01-05T18:00:00Z",
      };
      return HttpResponse.json(current);
    }),
  );
  return sent;
}

test("a draft is edited in place", async () => {
  const sent = entryApi(DRAFT);
  const { user } = renderPage(`/journal/${DRAFT.id}`);
  await screen.findByRole("option", { name: /^BTCUSDT long/ });
  expect(screen.getByLabelText("Trade")).toHaveValue(TRADE.id);

  const title = screen.getByLabelText("Title");
  await user.clear(title);
  await user.type(title, "Buying the second dip");
  await user.type(screen.getByLabelText("Lessons"), "Too early");
  await user.click(screen.getByRole("button", { name: "Save draft" }));

  expect(await screen.findByRole("heading", { name: "Buying the second dip" })).toBeInTheDocument();
  // A draft is saved whole, with no edit reason: only published entries keep versions.
  expect(sent.patches).toEqual([
    {
      entry_type: "pre_trade",
      title: "Buying the second dip",
      trade_id: TRADE.id,
      thesis: "RSI under 30",
      market_context: null,
      risk_assessment: null,
      lessons: "Too early",
      emotion: "fomo",
      tags: ["dip"],
    },
  ]);
  expect(screen.getByLabelText("Lessons")).toHaveValue("Too early");
});

test("publishing freezes a draft as version 1", async () => {
  const sent = entryApi(DRAFT);
  const { user } = renderPage(`/journal/${DRAFT.id}`);

  await user.click(await screen.findByRole("button", { name: "Publish" }));

  expect(await screen.findByText(/published v1/)).toBeInTheDocument();
  expect(sent.publications).toBe(1);
  expect(screen.queryByRole("button", { name: "Save draft" })).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Thesis" })).toBeInTheDocument();
  expect(screen.getByText("RSI under 30")).toBeInTheDocument();
});

test("a published entry is shown with its trade, feeling and tags", async () => {
  const entry = journalEntry({ trade_id: TRADE.id, tags: ["breakout", "late"] });
  entryApi(entry);

  renderPage(`/journal/${entry.id}`);

  expect(await screen.findByRole("heading", { name: "Breakout review" })).toBeInTheDocument();
  expect(screen.getByText(/^Post-trade · published v1/)).toHaveTextContent(
    "feeling calm · breakout, late · the trade",
  );
  expect(screen.getByRole("link", { name: "the trade" })).toHaveAttribute(
    "href",
    `/trades/${TRADE.id}`,
  );
  // Only the sections written are shown.
  expect(screen.getByText("Waited for the retest")).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Market context" })).not.toBeInTheDocument();
});

test("a refused publication says why", async () => {
  entryApi(DRAFT, HttpResponse.json({ detail: "The entry is already published" }, { status: 409 }));
  const { user } = renderPage(`/journal/${DRAFT.id}`);

  await user.click(await screen.findByRole("button", { name: "Publish" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("The entry is already published");
});
