import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw/http";
import { expect, test } from "vitest";

import type { components } from "../api/schema";
import { journalEntry } from "../test/fixtures";
import { renderPage } from "../test/render";
import { server } from "../test/server";

type Entry = components["schemas"]["JournalEntryRead"];

function journalEndpoint(entries: Entry[], total = entries.length) {
  const queries: URLSearchParams[] = [];
  server.use(
    http.get("/api/journal", ({ request }) => {
      const query = new URL(request.url).searchParams;
      queries.push(query);
      return HttpResponse.json({ items: entries, total, limit: 50, offset: 0 });
    }),
  );
  return queries;
}

test("entries show their type, status, emotion, tags and trade", async () => {
  const tradeId = "6a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d";
  journalEndpoint([
    journalEntry({ current_version: 2, tags: ["breakout", "late"], trade_id: tradeId }),
    journalEntry({
      title: "Watching BTC",
      entry_type: "note",
      status: "draft",
      current_version: 0,
      emotion: null,
      tags: [],
    }),
  ]);

  renderPage("/journal");

  await screen.findByText("Breakout review");
  const [review, note] = screen.getAllByRole("row").slice(1);
  expect(review).toHaveTextContent("Breakout reviewPost-tradepublished v2calmbreakout, late");
  expect(within(review).getByRole("link", { name: "trade" })).toHaveAttribute(
    "href",
    `/trades/${tradeId}`,
  );
  expect(note).toHaveTextContent("Watching BTCNotedraft——");
});

test("filters go to the API and into the URL", async () => {
  const queries = journalEndpoint([journalEntry()]);
  const { router, user } = renderPage("/journal");
  await screen.findByText("Breakout review");

  await user.selectOptions(screen.getByLabelText("Type"), "post_trade");
  await user.selectOptions(screen.getByLabelText("Status"), "published");
  await user.selectOptions(screen.getByLabelText("Emotion"), "fomo");
  await user.type(screen.getByLabelText("Tag"), "breakout");
  await user.click(screen.getByRole("button", { name: "Filter" }));

  await screen.findByText("Breakout review");
  expect(router.state.location.search).toBe(
    "?entry_type=post_trade&status=published&emotion=fomo&tag=breakout",
  );
  expect(Object.fromEntries(queries.at(-1)!)).toEqual({
    entry_type: "post_trade",
    status: "published",
    emotion: "fomo",
    tag: "breakout",
    limit: "50",
    offset: "0",
  });
});

test("without entries there is nothing to list", async () => {
  journalEndpoint([]);

  renderPage("/journal");

  expect(await screen.findByText("No journal entries.")).toBeInTheDocument();
});
