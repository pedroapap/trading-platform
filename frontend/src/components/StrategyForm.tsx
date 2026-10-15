import { useId, useState, type FormEvent, type ReactNode } from "react";

import { fieldErrors } from "../api/errors";
import { definitionProblems, type Definition } from "../strategies";
import Field from "./Field";

export type StrategyFields = { name: string; description: string | null; definition: Definition };

/** A strategy's name, description and definition, the definition edited as JSON. `children`
 * go just before the submit button. */
export default function StrategyForm({
  initial,
  submitLabel,
  pending,
  error,
  onSubmit,
  children,
}: {
  initial: StrategyFields;
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
  const errors = fieldErrors(error);
  const problems = notJson ? [{ path: "", message: notJson }] : definitionProblems(error, sent);
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
    setSent(definition);
    onSubmit({ name: text("name"), description: text("description") || null, definition });
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
      <label htmlFor={id}>Definition</label>
      <textarea
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
        Rules compare prices, values and indicators (sma, ema, rsi, macd, bbands) with &lt;, &lt;=,
        &gt;, &gt;=, crosses_above or crosses_below, and combine in "all" or "any" groups. Exits
        come from the exit rule, stop_loss_pct or take_profit_pct.
      </small>
      {children}
      {otherError && <p role="alert">{error.message}</p>}
      <button type="submit" aria-busy={pending} disabled={pending}>
        {submitLabel}
      </button>
    </form>
  );
}
