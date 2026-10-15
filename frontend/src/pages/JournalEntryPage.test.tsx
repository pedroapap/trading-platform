import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw/http";
import { expect, test } from "vitest";

import type { components } from "../api/schema";
import { journalEntry, trade } from "../test/fixtures";
import { renderPage } from "../test/render";
import { server } from "../test/server";

type Schemas = components["schemas"];
type Entry = Schemas["JournalEntryRead"];
type Content = Schemas["JournalContent"];
type Update = Schemas["JournalEntryUpdate"];

const CONTENT_FIELDS = [
  "entry_type",
  "trade_id",
  "title",
  "thesis",
  "market_context",
  "risk_assessment",
  "lessons",
  "emotion",
  "tags",
] as const;

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

function contentOf(entry: Entry): Content {
  return Object.fromEntries(CONTENT_FIELDS.map((field) => [field, entry[field]])) as Content;
}

const aMinuteLater = (time: string) => new Date(Date.parse(time) + 60_000).toISOString();

/** An entry the API edits, publishes and versions as the real one does. Returns the bodies it
 * was sent; publishing answers with `refusal` when given. */
function entryApi(initial: Entry, refusal?: Response) {
  let current = initial;
  const versions: Schemas["JournalVersionRead"][] = [];
  const addVersion = (changed: string[] | null, reason: string | null) =>
    versions.push({
      version: current.current_version,
      content: contentOf(current),
      changed_fields: changed,
      edit_reason: reason,
      created_at: current.updated_at,
    });
  if (initial.status === "published") addVersion(null, null);
  const sent = { patches: [] as Update[], publications: 0 };

  server.use(
    http.get("/api/trades", () =>
      HttpResponse.json({ items: [TRADE], total: 1, limit: 50, offset: 0 }),
    ),
    http.get("/api/journal/:id", () => HttpResponse.json(current)),
    http.get("/api/journal/:id/versions", () => HttpResponse.json(versions)),
    http.patch("/api/journal/:id", async ({ request }) => {
      const body = (await request.json()) as Update;
      sent.patches.push(body);
      const { edit_reason: reason, ...changes } = body;
      const edited = { ...current, ...changes, updated_at: aMinuteLater(current.updated_at) };
      if (current.status === "draft") {
        current = edited as Entry;
        return HttpResponse.json(current);
      }
      if (!reason) {
        return HttpResponse.json(
          {
            detail: [
              {
                loc: ["body", "edit_reason"],
                msg: "String should have at least 1 character",
                type: "string_too_short",
              },
            ],
          },
          { status: 422 },
        );
      }
      const changed = CONTENT_FIELDS.filter(
        (field) => JSON.stringify(edited[field]) !== JSON.stringify(current[field]),
      );
      if (changed.length === 0) return HttpResponse.json(current);
      current = { ...(edited as Entry), current_version: current.current_version + 1 };
      addVersion(changed.toSorted(), reason);
      return HttpResponse.json(current);
    }),
    http.post("/api/journal/:id/publish", () => {
      sent.publications += 1;
      if (refusal) return refusal;
      const now = aMinuteLater(current.updated_at);
      current = {
        ...current,
        status: "published",
        current_version: 1,
        published_at: now,
        updated_at: now,
      };
      addVersion(null, null);
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

  const entry = await screen.findByRole("article");
  expect(sent.publications).toBe(1);
  expect(within(entry).getByText(/published v1/)).toBeInTheDocument();
  expect(within(entry).getByRole("heading", { name: "Thesis" })).toBeInTheDocument();
  expect(within(entry).getByText("RSI under 30")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Save draft" })).not.toBeInTheDocument();
  expect(await screen.findByText(/^v1,/)).toHaveTextContent(/: published$/);
});

test("a refused publication says why", async () => {
  entryApi(DRAFT, HttpResponse.json({ detail: "The entry is already published" }, { status: 409 }));
  const { user } = renderPage(`/journal/${DRAFT.id}`);

  await user.click(await screen.findByRole("button", { name: "Publish" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("The entry is already published");
});

test("a published entry is shown with its trade, feeling and tags", async () => {
  const published = journalEntry({ trade_id: TRADE.id, tags: ["breakout", "late"] });
  entryApi(published);

  renderPage(`/journal/${published.id}`);

  expect(await screen.findByRole("heading", { name: "Breakout review" })).toBeInTheDocument();
  const entry = screen.getByRole("article");
  expect(within(entry).getByText(/^Post-trade/)).toHaveTextContent(
    "Post-trade · published v1 · feeling calm · breakout, late · the trade",
  );
  expect(within(entry).getByRole("link", { name: "the trade" })).toHaveAttribute(
    "href",
    `/trades/${TRADE.id}`,
  );
  // Only the sections written are shown.
  expect(within(entry).getByText("Waited for the retest")).toBeInTheDocument();
  expect(within(entry).queryByRole("heading", { name: "Market context" })).not.toBeInTheDocument();
});

test("editing a published entry saves its next version, with the reason", async () => {
  const published = journalEntry();
  const sent = entryApi(published);
  const { user } = renderPage(`/journal/${published.id}`);

  await user.click(await screen.findByText("Edit entry"));
  const lessons = screen.getByLabelText("Lessons");
  await user.clear(lessons);
  await user.type(lessons, "Wait for the retest, then size up");
  await user.type(screen.getByLabelText("Reason for the edit"), "Added what I learned");
  await user.click(screen.getByRole("button", { name: "Save as version 2" }));

  const v2 = await screen.findByText(/^v2,/);
  expect(v2).toHaveTextContent("v2, Jan 5, 2026, 6:01 PM: changed lessons (Added what I learned)");
  expect(sent.patches.at(-1)).toMatchObject({
    lessons: "Wait for the retest, then size up",
    edit_reason: "Added what I learned",
  });
  const entry = screen.getByRole("article");
  expect(within(entry).getByText(/published v2/)).toBeInTheDocument();
  expect(within(entry).getByText("Wait for the retest, then size up")).toBeInTheDocument();
  // Each version opens to what it said.
  const v1 = screen.getByText(/^v1,/);
  expect(v1).toHaveTextContent("v1, Jan 5, 2026, 6:00 PM: published");
  const firstLessons = within(v1.closest("details")!).getByText("Waited for the retest");
  expect(firstLessons).not.toBeVisible();
  await user.click(v1);
  expect(firstLessons).toBeVisible();
});

test("a published entry is not edited without a reason", async () => {
  const published = journalEntry();
  const sent = entryApi(published);
  const { user } = renderPage(`/journal/${published.id}`);

  await user.click(await screen.findByText("Edit entry"));
  await user.type(screen.getByLabelText("Lessons"), " Twice.");
  await user.click(screen.getByRole("button", { name: "Save as version 2" }));

  const reason = screen.getByLabelText("Reason for the edit");
  expect(await screen.findByText("String should have at least 1 character")).toBeInTheDocument();
  expect(reason).toHaveAttribute("aria-invalid", "true");
  expect(reason).toHaveAccessibleDescription("String should have at least 1 character");
  expect(sent.patches).toMatchObject([
    { lessons: "Waited for the retest Twice.", edit_reason: "" },
  ]);
  expect(within(screen.getByRole("article")).getByText(/published v1/)).toBeInTheDocument();
});

test("an edit that changes nothing adds no version", async () => {
  const published = journalEntry();
  entryApi(published);
  const { user } = renderPage(`/journal/${published.id}`);

  await user.click(await screen.findByText("Edit entry"));
  await user.type(screen.getByLabelText("Reason for the edit"), "Just checking");
  await user.click(screen.getByRole("button", { name: "Save as version 2" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Nothing changed: edit at least one field.",
  );
  expect(screen.getByText(/^v1,/)).toBeInTheDocument();
  expect(screen.queryByText(/^v2,/)).not.toBeInTheDocument();
});
