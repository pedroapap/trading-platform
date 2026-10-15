import { useQuery } from "@tanstack/react-query";
import type { FormEvent, ReactNode } from "react";

import { api, unwrap } from "../api/client";
import { fieldErrors } from "../api/errors";
import type { components } from "../api/schema";
import { formatDateTime } from "../format";
import { EMOTIONS, ENTRY_TYPES } from "../journal";
import Field from "./Field";

type Schemas = components["schemas"];
export type JournalContent = Schemas["JournalContent"];

const LONG_TEXTS = [
  ["thesis", "Thesis"],
  ["market_context", "Market context"],
  ["risk_assessment", "Risk assessment"],
  ["lessons", "Lessons"],
] as const;

function contentFrom(form: HTMLFormElement): JournalContent {
  const fields = new FormData(form);
  const text = (name: string) => String(fields.get(name) ?? "").trim();
  const optional = (name: string) => text(name) || null;
  return {
    entry_type: text("entry_type") as Schemas["EntryType"],
    title: text("title"),
    trade_id: optional("trade_id"),
    thesis: optional("thesis"),
    market_context: optional("market_context"),
    risk_assessment: optional("risk_assessment"),
    lessons: optional("lessons"),
    emotion: optional("emotion") as Schemas["Emotion"] | null,
    tags: text("tags")
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean),
  };
}

/** The recent trades an entry can be about, newest first. */
function useRecentTrades() {
  return useQuery({
    queryKey: ["trades", { recent: true }],
    queryFn: () => unwrap(api.GET("/api/trades", { params: { query: { limit: 50 } } })),
  });
}

/** An entry's content. `children` go just before the submit button, e.g. an edit reason. */
export default function JournalEntryForm({
  initial,
  submitLabel,
  pending,
  error,
  onSubmit,
  children,
}: {
  initial: Partial<JournalContent>;
  submitLabel: string;
  pending: boolean;
  error: Error | null;
  onSubmit: (content: JournalContent, form: HTMLFormElement) => void;
  children?: ReactNode;
}) {
  const trades = useRecentTrades();
  const errors = fieldErrors(error);
  // A bad tag is reported by its position, as tags.2.
  const tagsError =
    errors.tags ?? Object.entries(errors).find(([field]) => field.startsWith("tags."))?.[1];
  const linked = initial.trade_id;
  const linkedIsRecent = trades.data?.items.some((trade) => trade.id === linked);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit(contentFrom(event.currentTarget), event.currentTarget);
  }

  return (
    <form onSubmit={submit} noValidate>
      <div className="grid">
        <label>
          Type
          <select name="entry_type" defaultValue={initial.entry_type ?? "pre_trade"}>
            {Object.entries(ENTRY_TYPES).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Trade
          {/* The options load after the form renders, so the select remounts with them. */}
          <select
            key={trades.data ? "loaded" : "loading"}
            name="trade_id"
            defaultValue={linked ?? ""}
          >
            <option value="">None</option>
            {linked && !linkedIsRecent && <option value={linked}>The linked trade</option>}
            {trades.data?.items.map((trade) => (
              <option key={trade.id} value={trade.id}>
                {trade.symbol} {trade.direction}, {formatDateTime(trade.entry_time)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Emotion
          <select name="emotion" defaultValue={initial.emotion ?? ""}>
            <option value="">None</option>
            {EMOTIONS.map((emotion) => (
              <option key={emotion} value={emotion}>
                {emotion}
              </option>
            ))}
          </select>
        </label>
      </div>
      <Field
        label="Title"
        name="title"
        required
        maxLength={200}
        defaultValue={initial.title}
        error={errors.title}
      />
      {LONG_TEXTS.map(([name, label]) => (
        <label key={name}>
          {label}
          <textarea name={name} rows={3} maxLength={10_000} defaultValue={initial[name] ?? ""} />
        </label>
      ))}
      <Field
        label="Tags, separated by commas"
        name="tags"
        defaultValue={initial.tags?.join(", ")}
        error={tagsError}
      />
      {children}
      {error && !Object.keys(errors).length && <p role="alert">{error.message}</p>}
      <button type="submit" aria-busy={pending} disabled={pending}>
        {submitLabel}
      </button>
    </form>
  );
}
