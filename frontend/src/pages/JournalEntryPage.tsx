import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { api, unwrap } from "../api/client";
import { fieldErrors } from "../api/errors";
import { useJournalEntry, useJournalVersions } from "../api/journal";
import type { components } from "../api/schema";
import Field from "../components/Field";
import JournalEntryForm, { type JournalContent } from "../components/JournalEntryForm";
import { ErrorMessage, Loading } from "../components/Status";
import { formatDateTime } from "../format";
import { ENTRY_TYPES, entryStatus } from "../journal";

type Schemas = components["schemas"];
type Entry = Schemas["JournalEntryRead"];

const SECTIONS = [
  ["thesis", "Thesis"],
  ["market_context", "Market context"],
  ["risk_assessment", "Risk assessment"],
  ["lessons", "Lessons"],
] as const;

// How a version's changed fields are named.
const FIELD_NAMES: Record<keyof JournalContent, string> = {
  entry_type: "type",
  trade_id: "trade",
  title: "title",
  thesis: "thesis",
  market_context: "market context",
  risk_assessment: "risk assessment",
  lessons: "lessons",
  emotion: "emotion",
  tags: "tags",
};

/** What the content is: its type, then `status`, feeling, tags and trade when there are any. */
function About({ content, status }: { content: JournalContent; status?: string }) {
  return (
    <p>
      {ENTRY_TYPES[content.entry_type]}
      {status && ` · ${status}`}
      {content.emotion && ` · feeling ${content.emotion}`}
      {content.tags.length > 0 && ` · ${content.tags.join(", ")}`}
      {content.trade_id && (
        <>
          {" · "}
          <Link to={`/trades/${content.trade_id}`}>the trade</Link>
        </>
      )}
    </p>
  );
}

/** The long texts written, each under a heading. */
function Sections({ content, Heading }: { content: JournalContent; Heading: "h2" | "h3" }) {
  return SECTIONS.filter(([name]) => content[name]).map(([name, label]) => (
    <section key={name}>
      <Heading>{label}</Heading>
      <p className="prose">{content[name]}</p>
    </section>
  ));
}

function useEntryChange<Body>(change: (body: Body) => Promise<Entry>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: change,
    // Refreshes the entry, its versions and the lists.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["journal"] }),
  });
}

function patchEntry(id: string, body: Schemas["JournalEntryUpdate"]) {
  return unwrap(api.PATCH("/api/journal/{entry_id}", { params: { path: { entry_id: id } }, body }));
}

/** A draft, edited in place until it is published. */
function DraftEditor({ entry }: { entry: Entry }) {
  const save = useEntryChange((content: JournalContent) => patchEntry(entry.id, content));
  const publish = useEntryChange(() =>
    unwrap(
      api.POST("/api/journal/{entry_id}/publish", { params: { path: { entry_id: entry.id } } }),
    ),
  );

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

/** Editing a published entry saves its next version, with the reason for the edit. */
function EditEntry({ entry }: { entry: Entry }) {
  const edit = useEntryChange((body: Schemas["JournalEntryUpdate"]) => patchEntry(entry.id, body));
  const errors = fieldErrors(edit.error);
  // An edit that changes nothing is not a version. One that does remounts this form.
  const unchanged = edit.data?.current_version === entry.current_version;

  return (
    <details>
      <summary role="button" className="secondary outline">
        Edit entry
      </summary>
      <JournalEntryForm
        initial={entry}
        submitLabel={`Save as version ${entry.current_version + 1}`}
        pending={edit.isPending}
        error={edit.error}
        onSubmit={(content, form) => {
          const reason = String(new FormData(form).get("edit_reason") ?? "").trim();
          edit.mutate({ ...content, edit_reason: reason });
        }}
      >
        <Field
          label="Reason for the edit"
          name="edit_reason"
          required
          maxLength={500}
          error={errors.edit_reason}
        />
        {unchanged && <p role="alert">Nothing changed: edit at least one field.</p>}
      </JournalEntryForm>
    </details>
  );
}

/** Every published version, oldest first, each opening to what it said. */
function VersionHistory({ entryId }: { entryId: string }) {
  const versions = useJournalVersions(entryId);
  if (versions.isPending) return <Loading />;
  if (versions.error) return <ErrorMessage error={versions.error} />;
  return versions.data.map((version) => (
    <details key={version.version} className="version">
      <summary>
        v{version.version}, {formatDateTime(version.created_at)}:{" "}
        {version.changed_fields
          ? `changed ${version.changed_fields
              .map((field) => FIELD_NAMES[field as keyof JournalContent] ?? field)
              .join(", ")}`
          : "published"}
        {version.edit_reason && ` (${version.edit_reason})`}
      </summary>
      <p>
        <strong>{version.content.title}</strong>
      </p>
      <About content={version.content} />
      <Sections content={version.content} Heading="h3" />
    </details>
  ));
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
            <>
              <article>
                <About content={entry.data} status={entryStatus(entry.data)} />
                <Sections content={entry.data} Heading="h2" />
              </article>
              <EditEntry key={entry.data.updated_at} entry={entry.data} />
              <h2>History</h2>
              <VersionHistory entryId={entry.data.id} />
            </>
          )}
        </>
      )}
    </>
  );
}
