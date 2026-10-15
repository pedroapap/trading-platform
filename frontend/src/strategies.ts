import { ApiError } from "./api/client";
import type { components } from "./api/schema";
import examples from "./examples.json";

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

/** A definition to start from, with what it does in words. */
export type Example = { name: string; description: string; definition: Definition };

/** The definition editor's examples, the double-bottom rule first. The backend's tests check that
 * each one is a valid definition that trades. */
export const EXAMPLES = examples as Example[];

type Problem = { loc?: (string | number)[]; msg?: string; type?: string };
type Step = string | number;

function contains(value: unknown, step: Step): boolean {
  if (Array.isArray(value)) return typeof step === "number" && step < value.length;
  return typeof value === "object" && value !== null && Object.hasOwn(value, step);
}

function inside(value: unknown, step: Step): unknown {
  return (value as Record<Step, unknown>)[step];
}

function isObject(value: unknown): boolean {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Where a problem is in `sent`, as entry.all[0].left.period. Pydantic's location also
 * names the tag of each tagged union it went through, which may also be a key
 * (entry.not.not.left, entry.op.left) or a value (entry.op.left.indicator.rsi.period,
 * entry_order.limit.price). So a step only counts when the value has it and one of the next
 * two steps is inside it. The last step counts when the value has it or the problem is that
 * it is missing, and a missing last step is also inside an object one tag away. */
function jsonPath(loc: Step[], sent: unknown, type?: string): string {
  const last = loc.length - 1;
  const missing = type === "missing";
  const path: Step[] = [];
  let value = sent;
  loc.forEach((step, i) => {
    const next = contains(value, step) ? inside(value, step) : undefined;
    const counts =
      i === last
        ? next !== undefined || missing
        : contains(next, loc[i + 1]) ||
          (i + 2 <= last &&
            (contains(next, loc[i + 2]) || (i + 2 === last && missing && isObject(next))));
    if (counts) {
      path.push(step);
      value = next;
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
