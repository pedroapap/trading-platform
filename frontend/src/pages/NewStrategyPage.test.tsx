import { fireEvent, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw/http";
import { expect, test } from "vitest";

import type { components } from "../api/schema";
import { STARTER_DEFINITION } from "../strategies";
import { STRATEGY } from "../test/fixtures";
import { renderPage } from "../test/render";
import { server } from "../test/server";

type StrategyCreate = components["schemas"]["StrategyCreate"];

/** A strategies API that lists what was created; POST answers with `refusal` when given.
 * Returns the bodies posted. */
function strategiesApi(refusal?: Response) {
  const posted: StrategyCreate[] = [];
  const strategies: components["schemas"]["StrategyRead"][] = [];
  server.use(
    http.get("/api/strategies", () => HttpResponse.json(strategies)),
    http.post("/api/strategies", async ({ request }) => {
      const body = (await request.json()) as StrategyCreate;
      posted.push(body);
      if (refusal) return refusal;
      strategies.push({ ...STRATEGY, name: body.name, current_version: 1 });
      return HttpResponse.json(strategies.at(-1), { status: 201 });
    }),
  );
  return posted;
}

const definitionBox = () => screen.getByRole("textbox", { name: "Definition" });

function typeDefinition(definition: unknown) {
  fireEvent.change(definitionBox(), { target: { value: JSON.stringify(definition) } });
}

test("a strategy starts from a working definition", async () => {
  const posted = strategiesApi();
  const { router, user } = renderPage("/strategies/new");

  expect(JSON.parse((definitionBox() as HTMLTextAreaElement).value)).toEqual(STARTER_DEFINITION);
  await user.type(screen.getByLabelText("Name"), "RSI dip");
  await user.type(screen.getByLabelText("Description (optional)"), "Buys oversold dips");
  await user.click(screen.getByRole("button", { name: "Create strategy" }));

  expect(await screen.findByRole("cell", { name: "RSI dip" })).toBeInTheDocument();
  expect(router.state.location.pathname).toBe("/strategies");
  expect(posted).toEqual([
    { name: "RSI dip", description: "Buys oversold dips", definition: STARTER_DEFINITION },
  ]);
});

test("a definition that is not JSON is caught before it is sent", async () => {
  const posted = strategiesApi();
  const { user } = renderPage("/strategies/new");

  await user.type(screen.getByLabelText("Name"), "Broken");
  fireEvent.change(definitionBox(), { target: { value: '{"direction": "long",' } });
  await user.click(screen.getByRole("button", { name: "Create strategy" }));

  expect(screen.getByText(/^This is not valid JSON:/)).toBeInTheDocument();
  expect(definitionBox()).toHaveAttribute("aria-invalid", "true");
  expect(posted).toEqual([]);
});

test("the API's problems with a definition are shown where they are", async () => {
  // As the API reports a period of 0 at entry.left.period, and a missing exit.
  strategiesApi(
    HttpResponse.json(
      {
        detail: [
          {
            loc: ["body", "definition", "entry", "op", "left", "indicator", "rsi", "period"],
            msg: "Input should be greater than or equal to 2",
            type: "greater_than_equal",
          },
          {
            loc: ["body", "definition"],
            msg: "Value error, a strategy needs an exit rule, a stop-loss or a take-profit",
            type: "value_error",
          },
        ],
      },
      { status: 422 },
    ),
  );
  const { user } = renderPage("/strategies/new");

  await user.type(screen.getByLabelText("Name"), "Too short");
  typeDefinition({
    ...STARTER_DEFINITION,
    entry: { left: { indicator: "rsi", period: 0 }, op: "<", right: { value: 30 } },
    exit: null,
    stop_loss_pct: null,
  });
  await user.click(screen.getByRole("button", { name: "Create strategy" }));

  const period = (await screen.findByText("entry.left.period")).closest("li");
  expect(period).toHaveTextContent("entry.left.period Input should be greater than or equal to 2");
  // A problem with the whole definition has no path.
  expect(
    screen.getByText("a strategy needs an exit rule, a stop-loss or a take-profit"),
  ).toBeInTheDocument();
  expect(definitionBox()).toHaveAttribute("aria-invalid", "true");
  expect(definitionBox()).toHaveAccessibleDescription(
    expect.stringContaining("entry.left.period Input should be greater than or equal to 2"),
  );
});

test("a name already used is refused", async () => {
  strategiesApi(
    HttpResponse.json({ detail: "You already have a strategy named 'RSI dip'" }, { status: 409 }),
  );
  const { user } = renderPage("/strategies/new");

  await user.type(screen.getByLabelText("Name"), "RSI dip");
  await user.click(screen.getByRole("button", { name: "Create strategy" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "You already have a strategy named 'RSI dip'",
  );
});
