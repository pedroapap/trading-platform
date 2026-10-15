import { ApiError } from "./api/client";
import type { components } from "./api/schema";

// As sent: the API fills in defaults, such as an indicator's source, when it reads one back.
export type Definition = components["schemas"]["StrategyDefinition-Input"];

/** What the definition editor starts with: buy an RSI dip, sell the recovery, 2% stop. */
export const STARTER_DEFINITION: Definition = {
  direction: "long",
  entry: {
    left: { indicator: "rsi", period: 14, source: "close" },
    op: "<",
    right: { value: 30 },
  },
  exit: {
    left: { indicator: "rsi", period: 14, source: "close" },
    op: ">",
    right: { value: 70 },
  },
  stop_loss_pct: 2,
  take_profit_pct: null,
};

type Problem = { loc?: (string | number)[]; msg?: string; type?: string };
type Step = string | number;

function contains(value: unknown, step: Step): boolean {
  if (Array.isArray(value)) return typeof step === "number" && step < value.length;
  return typeof value === "object" && value !== null && Object.hasOwn(value, step);
}

function inside(value: unknown, step: Step): unknown {
  return (value as Record<Step, unknown>)[step];
}

/** Where a problem is in `sent`, as entry.all[0].left.period. Pydantic's location also
 * names the tag of each tagged union it went through (entry.op.left.indicator.rsi.period),
 * so a step only counts when the value has it and the next step is inside it. The last
 * step counts when the value has it or the problem is that it is missing. */
function jsonPath(loc: Step[], sent: unknown, type?: string): string {
  const path: Step[] = [];
  let value = sent;
  loc.forEach((step, i) => {
    const counts =
      i === loc.length - 1
        ? contains(value, step) || type === "missing"
        : contains(value, step) && contains(inside(value, step), loc[i + 1]);
    if (counts) {
      path.push(step);
      value = inside(value, step);
    }
  });
  return path
    .map((step, i) => (typeof step === "number" ? `[${step}]` : i ? `.${step}` : step))
    .join("");
}

/** The problems a validation error (422) found in the definition that was sent, each with
 * where it is in that definition ("" for the whole definition). */
export function definitionProblems(
  error: unknown,
  sent: unknown,
): { path: string; message: string }[] {
  if (!(error instanceof ApiError) || !Array.isArray(error.detail)) return [];
  return (error.detail as Problem[])
    .filter(({ loc }) => loc?.[0] === "body" && loc[1] === "definition")
    .map(({ loc = [], msg = "", type }) => ({
      path: jsonPath(loc.slice(2), sent, type),
      message: msg.replace(/^Value error, /, ""),
    }));
}
