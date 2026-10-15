import { fireEvent, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw/http";
import { expect, test } from "vitest";

import type { components } from "../api/schema";
import { STRATEGY } from "../test/fixtures";
import { renderPage } from "../test/render";
import { server } from "../test/server";

type Schemas = components["schemas"];
type Strategy = Schemas["StrategyRead"];
type Update = Schemas["StrategyUpdate"];

const aMinuteLater = (time: string) => new Date(Date.parse(time) + 60_000).toISOString();

/** A strategy the API edits and versions as the real one does: its v1 had a 3% stop.
 * Returns the bodies it was sent. */
function strategyApi(initial: Strategy) {
  let current = initial;
  const versions: Schemas["StrategyVersionRead"][] = [
    {
      version: 1,
      definition: { ...initial.definition, stop_loss_pct: 3 },
      changed_fields: null,
      created_at: initial.created_at,
    },
    {
      version: 2,
      definition: initial.definition,
      changed_fields: ["stop_loss_pct"],
      created_at: initial.updated_at,
    },
  ];
  const patches: Update[] = [];
  server.use(
    http.get("/api/strategies/:id", () => HttpResponse.json(current)),
    http.get("/api/strategies/:id/versions", () => HttpResponse.json(versions)),
    http.patch("/api/strategies/:id", async ({ request }) => {
      const body = (await request.json()) as Update;
      patches.push(body);
      const before: Record<string, unknown> = current.definition;
      const after: Record<string, unknown> = body.definition ?? before;
      const changed = Object.keys({ ...before, ...after })
        .filter((key) => JSON.stringify(before[key]) !== JSON.stringify(after[key]))
        .sort();
      const name = body.name ?? current.name;
      const description = body.description === undefined ? current.description : body.description;
      if (!changed.length && name === current.name && description === current.description) {
        return HttpResponse.json(current);
      }
      current = {
        ...current,
        name,
        description,
        definition: after as Strategy["definition"],
        current_version: current.current_version + (changed.length ? 1 : 0),
        updated_at: aMinuteLater(current.updated_at),
      };
      if (changed.length) {
        versions.push({
          version: current.current_version,
          definition: current.definition,
          changed_fields: changed,
          created_at: current.updated_at,
        });
      }
      return HttpResponse.json(current);
    }),
  );
  return patches;
}

const definitionBox = () => screen.getByRole("textbox", { name: "Definition" });

test("a strategy shows its definition and how it got there", async () => {
  strategyApi(STRATEGY);

  renderPage(`/strategies/${STRATEGY.id}`);

  expect(await screen.findByRole("heading", { name: "RSI dip" })).toBeInTheDocument();
  expect(screen.getByText("v2 · long")).toBeInTheDocument();
  expect(screen.getAllByText(/"indicator": "rsi"/)[0].closest("pre")).toBeInTheDocument();
  expect(await screen.findByText(/^v1,/)).toHaveTextContent("v1, Jan 1, 2026, 9:00 AM: created");
  expect(screen.getByText(/^v2,/)).toHaveTextContent(
    "v2, Jan 2, 2026, 9:00 AM: changed stop_loss_pct",
  );
});

test("a changed definition is saved as the next version", async () => {
  const patches = strategyApi(STRATEGY);
  const { user } = renderPage(`/strategies/${STRATEGY.id}`);
  const exit = {
    left: { indicator: "rsi", period: 14, source: "close" },
    op: ">",
    right: { value: 70 },
  } as const;

  await user.click(await screen.findByText("Edit strategy"));
  fireEvent.change(definitionBox(), {
    target: { value: JSON.stringify({ ...STRATEGY.definition, exit }) },
  });
  await user.click(screen.getByRole("button", { name: "Save changes" }));

  expect(await screen.findByText("v3 · long")).toBeInTheDocument();
  expect(await screen.findByText(/^v3,/)).toHaveTextContent(/: changed exit$/);
  expect(patches).toEqual([
    { name: "RSI dip", description: null, definition: { ...STRATEGY.definition, exit } },
  ]);
});

test("renaming keeps the version", async () => {
  strategyApi(STRATEGY);
  const { user } = renderPage(`/strategies/${STRATEGY.id}`);

  await user.click(await screen.findByText("Edit strategy"));
  const name = screen.getByLabelText("Name");
  await user.clear(name);
  await user.type(name, "RSI dip, daily");
  await user.type(screen.getByLabelText("Description (optional)"), "Daily bars only");
  await user.click(screen.getByRole("button", { name: "Save changes" }));

  expect(await screen.findByRole("heading", { name: "RSI dip, daily" })).toBeInTheDocument();
  expect(screen.getByText("Daily bars only", { selector: "p" })).toBeInTheDocument();
  expect(screen.getByText("v2 · long")).toBeInTheDocument();
  expect(screen.queryByText(/^v3,/)).not.toBeInTheDocument();
});

test("a save that changes nothing says so", async () => {
  strategyApi(STRATEGY);
  const { user } = renderPage(`/strategies/${STRATEGY.id}`);

  await user.click(await screen.findByText("Edit strategy"));
  await user.click(screen.getByRole("button", { name: "Save changes" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Nothing changed.");
});
