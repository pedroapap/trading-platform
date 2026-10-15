import { useId, useRef, useState, type FormEvent, type ReactNode } from "react";

import { fieldErrors } from "../api/errors";
import { definitionProblems, type Definition, type Example } from "../strategies";
import Field from "./Field";

export type StrategyFields = { name: string; description: string | null; definition: Definition };

/** A strategy's name, description and definition, the definition edited as JSON, optionally
 * started from one of `examples`. `children` go just before the submit button. */
export default function StrategyForm({
  initial,
  examples,
  submitLabel,
  pending,
  error,
  onSubmit,
  children,
}: {
  initial: StrategyFields;
  examples?: Example[];
  submitLabel: string;
  pending: boolean;
  error: Error | null;
  onSubmit: (fields: StrategyFields) => void;
  children?: ReactNode;
}) {
  const id = useId();
  // The definition last sent, where the API's problems are located; or why it couldn't be.
  const [sent, setSent] = useState<unknown>(null);
  const [notJson, setNotJson] = useState<string | null>(null);
  // Whether an example replaced what was sent, so the problems found in it are gone.
  const [replaced, setReplaced] = useState(false);
  const definitionBox = useRef<HTMLTextAreaElement>(null);
  // The definition as the form last set it: any other text was typed.
  const lastSet = useRef(JSON.stringify(initial.definition, null, 2));
  const errors = fieldErrors(error);
  const problems = notJson
    ? [{ path: "", message: notJson }]
    : definitionProblems(replaced ? null : error, sent);
  const otherError = error && !Object.keys(errors).length;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const text = (name: string) => String(fields.get(name) ?? "").trim();
    let definition: Definition;
    try {
      definition = JSON.parse(text("definition"));
    } catch (problem) {
      setNotJson(`This is not valid JSON: ${(problem as Error).message}`);
      return;
    }
    setNotJson(null);
    setReplaced(false);
    setSent(definition);
    onSubmit({ name: text("name"), description: text("description") || null, definition });
  }

  function startFrom(example: Example) {
    const box = definitionBox.current!;
    const typed = box.value !== lastSet.current;
    if (typed && !window.confirm("Replace your definition with this example?")) return;
    lastSet.current = JSON.stringify(example.definition, null, 2);
    box.value = lastSet.current;
    setNotJson(null);
    setReplaced(true);
  }

  return (
    <form onSubmit={submit} noValidate>
      <Field
        label="Name"
        name="name"
        required
        maxLength={100}
        defaultValue={initial.name}
        error={errors.name}
      />
      <label>
        Description (optional)
        <textarea
          name="description"
          rows={2}
          maxLength={2000}
          defaultValue={initial.description ?? ""}
        />
      </label>
      {examples && (
        <details>
          <summary>Start from an example</summary>
          <ul>
            {examples.map((example, i) => (
              <li key={example.name}>
                <button
                  type="button"
                  className="secondary outline"
                  aria-describedby={`${id}-example-${i}`}
                  onClick={() => startFrom(example)}
                >
                  {example.name}
                </button>{" "}
                <small id={`${id}-example-${i}`}>{example.description}</small>
              </li>
            ))}
          </ul>
        </details>
      )}
      <label htmlFor={id}>Definition</label>
      <textarea
        ref={definitionBox}
        id={id}
        name="definition"
        className="code"
        rows={20}
        spellCheck={false}
        defaultValue={JSON.stringify(initial.definition, null, 2)}
        aria-invalid={problems.length ? true : undefined}
        aria-describedby={`${id}-help ${problems.length ? `${id}-problems` : ""}`.trim()}
      />
      {problems.length > 0 && (
        <ul id={`${id}-problems`} className="problems">
          {problems.map(({ path, message }) => (
            <li key={`${path} ${message}`}>
              {path && <code>{path}</code>} {message}
            </li>
          ))}
        </ul>
      )}
      <small id={`${id}-help`}>
        Rules compare prices, values and indicators (sma, ema, rsi, macd, bbands, atr, lowest,
        highest, swing_low, swing_high) with &lt;, &lt;=, &gt;, &gt;=, crosses_above or
        crosses_below. A price or indicator can look back with bars_ago, and add, subtract, multiply
        or divide combine two operands. Rules group in all, any and not; happened counts how often a
        rule held within some bars; equal_lows and equal_highs find swing lows or highs at the same
        level. An entry_order enters at a limit or stop price. Exits come from the exit rule,
        stop_loss_pct or stop_loss_at, take_profit_pct, take_profit_at or take_profit_r,
        trailing_stop_pct or trailing_stop_at, and exit_after_bars.
      </small>
      {children}
      {otherError && <p role="alert">{error.message}</p>}
      <button type="submit" aria-busy={pending} disabled={pending}>
        {submitLabel}
      </button>
    </form>
  );
}
