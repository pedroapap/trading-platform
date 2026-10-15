import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw/http";
import { expect, test } from "vitest";

import type { components } from "../api/schema";
import { journalEntry, trade } from "../test/fixtures";
import { renderPage } from "../test/render";
import { server } from "../test/server";

type Content = components["schemas"]["JournalContent"];

const TRADE = trade({ symbol: "ETHUSDT", entry_time: "2026-01-05T14:30:00Z" });

/** The recent trades, and a journal that stores what is posted as a draft. Returns the bodies
 * posted; POST answers with `refusal` when given. */
function journalEndpoints(refusal?: Response) {
  const posted: Content[] = [];
  let created = journalEntry();
  server.use(
    http.get("/api/trades", () =>
      HttpResponse.json({ items: [TRADE], total: 1, limit: 50, offset: 0 }),
    ),
    http.post("/api/journal", async ({ request }) => {
      const content = (await request.json()) as Content;
      posted.push(content);
      if (refusal) return refusal;
      created = journalEntry({
        ...content,
        status: "draft",
        current_version: 0,
        published_at: null,
      });
      return HttpResponse.json(created, { status: 201 });
    }),
    http.get("/api/journal/:id", () => HttpResponse.json(created)),
  );
  return posted;
}

test("a new entry is saved as a draft and opened", async () => {
  const posted = journalEndpoints();
  const { router, user } = renderPage("/journal/new");
  await screen.findByRole("option", { name: /^ETHUSDT long/ });

  await user.selectOptions(screen.getByLabelText("Trade"), TRADE.id);
  await user.selectOptions(screen.getByLabelText("Emotion"), "fomo");
  await user.type(screen.getByLabelText("Title"), "  Buying the dip ");
  await user.type(screen.getByLabelText("Thesis"), "RSI under 30{Enter}on the 1h");
  await user.type(screen.getByLabelText("Tags, separated by commas"), "Dip, rsi ,");
  await user.click(screen.getByRole("button", { name: "Save draft" }));

  expect(await screen.findByRole("heading", { name: "Buying the dip" })).toBeInTheDocument();
  expect(router.state.location.pathname).toMatch(/^\/journal\/[0-9a-f-]{36}$/);
  expect(screen.getByRole("button", { name: "Publish" })).toBeInTheDocument();
  // Text is trimmed and empty sections are null; the API lowercases the tags.
  expect(posted).toEqual([
    {
      entry_type: "pre_trade",
      title: "Buying the dip",
      trade_id: TRADE.id,
      thesis: "RSI under 30\non the 1h",
      market_context: null,
      risk_assessment: null,
      lessons: null,
      emotion: "fomo",
      tags: ["Dip", "rsi"],
    },
  ]);
});

test("writing about a trade starts a post-trade review of it", async () => {
  journalEndpoints();

  renderPage(`/journal/new?trade=${TRADE.id}`);

  await screen.findByRole("option", { name: /^ETHUSDT long/ });
  expect(screen.getByLabelText("Trade")).toHaveValue(TRADE.id);
  expect(screen.getByLabelText("Type")).toHaveValue("post_trade");
});

test("a tag the API rejects shows why", async () => {
  const problem = "String should match pattern '^[a-z0-9][a-z0-9_-]*$'";
  journalEndpoints(
    HttpResponse.json(
      { detail: [{ loc: ["body", "tags", 1], msg: problem, type: "string_pattern_mismatch" }] },
      { status: 422 },
    ),
  );
  const { user } = renderPage("/journal/new");

  await user.type(screen.getByLabelText("Title"), "Notes");
  await user.type(screen.getByLabelText("Tags, separated by commas"), "fine, not fine!");
  await user.click(screen.getByRole("button", { name: "Save draft" }));

  const tags = screen.getByLabelText("Tags, separated by commas");
  expect(await screen.findByText(problem)).toBeInTheDocument();
  expect(tags).toHaveAttribute("aria-invalid", "true");
  expect(tags).toHaveAccessibleDescription(problem);
});

test("the journal leads to a new entry and to each entry", async () => {
  const entry = journalEntry();
  journalEndpoints();
  server.use(
    http.get("/api/journal", () =>
      HttpResponse.json({ items: [entry], total: 1, limit: 50, offset: 0 }),
    ),
  );
  const { user } = renderPage("/journal");

  expect(await screen.findByRole("link", { name: "Breakout review" })).toHaveAttribute(
    "href",
    `/journal/${entry.id}`,
  );
  await user.click(screen.getByRole("button", { name: "New entry" }));

  expect(screen.getByRole("heading", { name: "New journal entry" })).toBeInTheDocument();
});
