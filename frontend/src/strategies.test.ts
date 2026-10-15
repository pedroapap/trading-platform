import { expect, test } from "vitest";

import { ApiError } from "./api/client";
import { definitionProblems } from "./strategies";

const rsi = { indicator: "rsi", period: 0 };
const condition = { left: rsi, op: "<", right: { value: 30 } };

/** The path the API's problem at `loc` (as it reports it, under body.definition) gets. */
function pathOf(loc: (string | number)[], sent: unknown, type = "value_error") {
  const error = new ApiError(422, {
    detail: [{ loc: ["body", "definition", ...loc], msg: "Problem", type }],
  });
  const [problem] = definitionProblems(error, sent);
  return problem.path;
}

// Each location below is what the API answered for the definition beside it.
test.each([
  {
    loc: ["entry", "op", "left", "indicator", "rsi", "period"],
    sent: { entry: condition },
    path: "entry.left.period",
  },
  {
    loc: ["entry", "all", "all", 0, "op", "left", "indicator"],
    sent: { entry: { all: [{ ...condition, left: { indicator: "vwap" } }] } },
    path: "entry.all[0].left.indicator",
  },
  {
    loc: ["entry", "any", "any", 0, "op", "left", "indicator", "macd"],
    sent: { entry: { any: [{ ...condition, left: { indicator: "macd", fast: 26, slow: 12 } }] } },
    path: "entry.any[0].left",
  },
  {
    loc: ["entry", "op", "left", "price", "price"],
    sent: { entry: { ...condition, left: { price: "closer" } } },
    path: "entry.left.price",
  },
  { loc: ["entry", "op", "op"], sent: { entry: { ...condition, op: "<<" } }, path: "entry.op" },
  {
    loc: ["entry", "op", "right", "value", "extra"],
    sent: { entry: { ...condition, right: { value: 30, extra: 1 } } },
    path: "entry.right.extra",
  },
  {
    loc: ["entry", "all", "all", 0, "all", "all"],
    sent: { entry: { all: [{ all: [] }, condition] } },
    path: "entry.all[0].all",
  },
  { loc: ["direction"], sent: { direction: "sideways" }, path: "direction" },
])("$path", ({ loc, sent, path }) => {
  expect(pathOf(loc, sent)).toBe(path);
});

test("a missing field is named where it should be", () => {
  const sent = { entry: { left: rsi, op: "<" } };

  expect(pathOf(["entry", "op", "right"], sent, "missing")).toBe("entry.right");
});

test("a problem with the whole definition has no path, and no pydantic prefix", () => {
  const error = new ApiError(422, {
    detail: [
      {
        loc: ["body", "definition"],
        msg: "Value error, a strategy needs an exit rule, a stop-loss or a take-profit",
        type: "value_error",
      },
      { loc: ["body", "name"], msg: "String should have at least 1 character", type: "too_short" },
    ],
  });

  expect(definitionProblems(error, {})).toEqual([
    { path: "", message: "a strategy needs an exit rule, a stop-loss or a take-profit" },
  ]);
});

test("other errors have no definition problems", () => {
  expect(definitionProblems(new ApiError(409, { detail: "Taken" }), {})).toEqual([]);
  expect(definitionProblems(new Error("offline"), {})).toEqual([]);
});
