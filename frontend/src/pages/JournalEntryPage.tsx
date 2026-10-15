import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { api, unwrap } from "../api/client";
import { useJournalEntry } from "../api/journal";
import type { components } from "../api/schema";
import JournalEntryForm, { type JournalContent } from "../components/JournalEntryForm";
import { ErrorMessage, Loading } from "../components/Status";
import { formatDateTime } from "../format";
import { ENTRY_TYPES, entryStatus } from "../journal";

type Entry = components["schemas"]["JournalEntryRead"];

const SECTIONS = [
  ["thesis", "Thesis"],
  ["market_context", "Market context"],
  ["risk_assessment", "Risk assessment"],
  ["lessons", "Lessons"],
] as const;

/** A published entry, read-only. */
function EntryView({ entry }: { entry: Entry }) {
  return (
    <>
      <p>
        {ENTRY_TYPES[entry.entry_type]} · {entryStatus(entry)}
        {entry.published_at && `, ${formatDateTime(entry.published_at)}`}
        {entry.emotion && ` · feeling ${entry.emotion}`}
        {entry.tags.length > 0 && ` · ${entry.tags.join(", ")}`}
        {entry.trade_id && (
          <>
            {" · "}
            <Link to={`/trades/${entry.trade_id}`}>the trade</Link>
          </>
        )}
      </p>
      {SECTIONS.filter(([name]) => entry[name]).map(([name, label]) => (
        <section key={name}>
          <h2>{label}</h2>
          <p className="prose">{entry[name]}</p>
        </section>
      ))}
    </>
  );
}

/** A draft, edited in place until it is published. */
function DraftEditor({ entry }: { entry: Entry }) {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["journal"] });
  const path = { params: { path: { entry_id: entry.id } } };
  const save = useMutation({
    mutationFn: (content: JournalContent) =>
      unwrap(api.PATCH("/api/journal/{entry_id}", { ...path, body: content })),
    onSuccess: refresh,
  });
  const publish = useMutation({
    mutationFn: () => unwrap(api.POST("/api/journal/{entry_id}/publish", path)),
    onSuccess: refresh,
  });

  return (
    <>
      <p>Draft: edit it freely. Publishing freezes it as version 1.</p>
      <JournalEntryForm
        initial={entry}
        submitLabel="Save draft"
        pending={save.isPending}
        error={save.error}
        onSubmit={(content) => save.mutate(content)}
      />
      {publish.error && <p role="alert">{publish.error.message}</p>}
      <button
        type="button"
        className="secondary"
        aria-busy={publish.isPending}
        disabled={publish.isPending}
        onClick={() => publish.mutate()}
      >
        Publish
      </button>
    </>
  );
}

export default function JournalEntryPage() {
  const { entryId = "" } = useParams();
  const entry = useJournalEntry(entryId);

  return (
    <>
      <p>
        <Link to="/journal">← Journal</Link>
      </p>
      {entry.isPending && <Loading />}
      {entry.error && <ErrorMessage error={entry.error} />}
      {entry.data && (
        <>
          <h1>{entry.data.title}</h1>
          {entry.data.status === "draft" ? (
            <DraftEditor key={entry.data.updated_at} entry={entry.data} />
          ) : (
            <EntryView entry={entry.data} />
          )}
        </>
      )}
    </>
  );
}
