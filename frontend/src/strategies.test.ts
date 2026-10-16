import { expect, test } from "vitest";

import { ApiError } from "./api/client";
import { definitionProblems } from "./strategies";

const rsi = { indicator: "rsi", period: 0 };
const condition = { left: rsi, op: "<", right: { value: 30 } };
const two = { value: 2 };

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
    sent: { entry: { all: [{ ...condition, left: { indicator: "supertrend" } }] } },
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
  {
    loc: ["entry", "op", "left", "price", "bars_ago"],
    sent: { entry: { ...condition, left: { price: "low", bars_ago: -1 } } },
    path: "entry.left.bars_ago",
  },
  {
    loc: ["entry", "op", "left", "multiply", "multiply", 0, "indicator", "sma", "period"],
    sent: { entry: { ...condition, left: { multiply: [{ indicator: "sma", period: 0 }, two] } } },
    path: "entry.left.multiply[0].period",
  },
  {
    loc: ["entry", "op", "left", "divide", "divide", 1, "add", "add"],
    sent: { entry: { ...condition, left: { divide: [two, { add: [{ price: "close" }] }] } } },
    path: "entry.left.divide[1].add",
  },
  {
    loc: ["entry", "happened", "happened", "op", "left", "indicator", "rsi", "period"],
    sent: { entry: { happened: condition, within: 48 } },
    path: "entry.happened.left.period",
  },
  {
    loc: ["entry", "not", "not", "op", "left", "indicator"],
    sent: { entry: { not: { ...condition, left: { indicator: "supertrend" } } } },
    path: "entry.not.left.indicator",
  },
  {
    loc: ["entry", "not", "not", "not", "not", "op", "left", "indicator", "rsi", "period"],
    sent: { entry: { not: { not: condition } } },
    path: "entry.not.not.left.period",
  },
  {
    loc: ["entry", "all", "all", 0, "pattern", "equal_lows", "strength"],
    sent: { entry: { all: [{ pattern: "equal_lows", strength: 0, within: 48 }] } },
    path: "entry.all[0].strength",
  },
  {
    loc: [
      "entry_order",
      "limit",
      "price",
      "multiply",
      "multiply",
      0,
      "indicator",
      "swing_low",
      "strength",
    ],
    sent: {
      entry_order: {
        type: "limit",
        price: { multiply: [{ indicator: "swing_low", strength: 0 }, two] },
      },
    },
    path: "entry_order.price.multiply[0].strength",
  },
  {
    loc: ["stop_loss_at", "subtract", "subtract", 0, "price", "price"],
    sent: { stop_loss_at: { subtract: [{ price: "closer" }, two] } },
    path: "stop_loss_at.subtract[0].price",
  },
  {
    loc: ["trailing_stop_at", "indicator", "atr", "period"],
    sent: { trailing_stop_at: { indicator: "atr", period: 0 } },
    path: "trailing_stop_at.period",
  },
  {
    loc: ["entry", "all", "all", 0, "time", "time", 0],
    sent: { entry: { all: [{ time: ["9:30", "11:00"] }, condition] } },
    path: "entry.all[0].time[0]",
  },
  { loc: ["entry", "time", "time"], sent: { entry: { time: ["09:30"] } }, path: "entry.time" },
  {
    loc: ["entry", "not", "not", "time", "time", 1],
    sent: { entry: { not: { time: ["09:30", "25:00"] } } },
    path: "entry.not.time[1]",
  },
  {
    loc: ["session", "timezone"],
    sent: { session: { timezone: "Mars/Olympus", start: "09:30", end: "16:00" } },
    path: "session.timezone",
  },
  {
    loc: ["session", "start"],
    sent: { session: { timezone: "America/New_York", start: "9:30", end: "16:00" } },
    path: "session.start",
  },
  {
    loc: ["session"],
    sent: { session: { timezone: "America/New_York", start: "16:00", end: "09:30" } },
    path: "session",
  },
  { loc: ["flat_at"], sent: { flat_at: "4pm" }, path: "flat_at" },
  {
    loc: ["entry", "op", "left", "timeframe", "of", "indicator", "sma", "period"],
    sent: {
      entry: { ...condition, left: { timeframe: "1d", of: { indicator: "sma", period: 0 } } },
    },
    path: "entry.left.of.period",
  },
  {
    loc: ["entry", "op", "left", "timeframe", "timeframe"],
    sent: { entry: { ...condition, left: { timeframe: "2d", of: { price: "close" } } } },
    path: "entry.left.timeframe",
  },
  {
    loc: ["entry", "op", "left", "timeframe", "of"],
    sent: { entry: { ...condition, left: { timeframe: "1d", of: { indicator: "vwap" } } } },
    path: "entry.left.of",
  },
  {
    loc: ["entry", "op", "left", "multiply", "multiply", 0, "timeframe", "of"],
    sent: {
      entry: {
        ...condition,
        left: { multiply: [{ timeframe: "4h", of: { indicator: "day", output: "high" } }, two] },
      },
    },
    path: "entry.left.multiply[0].of",
  },
  {
    loc: ["stop_loss_at", "timeframe", "of"],
    sent: { stop_loss_at: { timeframe: "1h", of: { indicator: "vwap" } } },
    path: "stop_loss_at.of",
  },
  {
    loc: ["entry", "op", "left", "indicator", "opening_range", "minutes"],
    sent: {
      entry: { ...condition, left: { indicator: "opening_range", minutes: 0, output: "high" } },
    },
    path: "entry.left.minutes",
  },
  {
    loc: ["entry", "op", "left", "indicator", "day", "days_ago"],
    sent: { entry: { ...condition, left: { indicator: "day", output: "high", days_ago: 11 } } },
    path: "entry.left.days_ago",
  },
])("$path", ({ loc, sent, path }) => {
  expect(pathOf(loc, sent)).toBe(path);
});

// A missing field is named where it should be.
test.each([
  { loc: ["entry", "op", "right"], sent: { entry: { left: rsi, op: "<" } }, path: "entry.right" },
  {
    loc: ["entry", "happened", "within"],
    sent: { entry: { happened: condition } },
    path: "entry.within",
  },
  {
    loc: ["entry", "happened", "happened", "op", "right"],
    sent: { entry: { happened: { left: rsi, op: "<" }, within: 4 } },
    path: "entry.happened.right",
  },
  {
    loc: ["entry", "all", "all", 0, "pattern", "equal_lows", "strength"],
    sent: { entry: { all: [{ pattern: "equal_lows", within: 48, tolerance_pct: 0.5 }] } },
    path: "entry.all[0].strength",
  },
  {
    loc: ["stop_loss_at", "indicator", "swing_low", "strength"],
    sent: { stop_loss_at: { indicator: "swing_low" } },
    path: "stop_loss_at.strength",
  },
  {
    loc: ["entry_order", "limit", "price"],
    sent: { entry_order: { type: "limit" } },
    path: "entry_order.price",
  },
  {
    loc: ["entry", "op", "left", "timeframe", "of"],
    sent: { entry: { ...condition, left: { timeframe: "1d" } } },
    path: "entry.left.of",
  },
  {
    loc: ["entry", "op", "left", "indicator", "day", "output"],
    sent: { entry: { ...condition, left: { indicator: "day" } } },
    path: "entry.left.output",
  },
  {
    loc: ["entry", "op", "left", "indicator", "opening_range", "minutes"],
    sent: { entry: { ...condition, left: { indicator: "opening_range", output: "high" } } },
    path: "entry.left.minutes",
  },
])("missing: $path", ({ loc, sent, path }) => {
  expect(pathOf(loc, sent, "missing")).toBe(path);
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
