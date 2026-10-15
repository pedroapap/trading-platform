import { keepPreviousData, useQuery } from "@tanstack/react-query";
import type { FormEvent } from "react";
import { Link } from "react-router";

import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import Pagination from "../components/Pagination";
import { ErrorMessage, Loading } from "../components/Status";
import { formatDateTime } from "../format";
import { EMOTIONS, ENTRY_TYPES, entryStatus } from "../journal";
import { useListParams } from "../useListParams";

type Schemas = components["schemas"];

function oneOf<T extends string>(values: readonly T[], value: string): T | undefined {
  return values.find((candidate) => candidate === value);
}

export default function JournalPage() {
  const { filters, offset, limit, applyFilters, showPage } = useListParams([
    "entry_type",
    "status",
    "emotion",
    "tag",
  ] as const);
  const query = {
    entry_type: oneOf(Object.keys(ENTRY_TYPES) as Schemas["EntryType"][], filters.entry_type),
    status: oneOf<Schemas["JournalStatus"]>(["draft", "published"], filters.status),
    emotion: oneOf(EMOTIONS, filters.emotion),
    tag: filters.tag || undefined,
  };

  const entries = useQuery({
    queryKey: ["journal", { ...query, offset }],
    queryFn: () =>
      unwrap(api.GET("/api/journal", { params: { query: { ...query, limit, offset } } })),
    placeholderData: keepPreviousData,
  });

  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    applyFilters(event.currentTarget);
  }

  return (
    <>
      <h1>Journal</h1>
      <p>
        <Link to="/journal/new" role="button">
          New entry
        </Link>
      </p>
      <form onSubmit={filter} role="search">
        <fieldset role="group">
          <select name="entry_type" aria-label="Type" defaultValue={filters.entry_type}>
            <option value="">Any type</option>
            {Object.entries(ENTRY_TYPES).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <select name="status" aria-label="Status" defaultValue={filters.status}>
            <option value="">Any status</option>
            <option value="draft">draft</option>
            <option value="published">published</option>
          </select>
          <select name="emotion" aria-label="Emotion" defaultValue={filters.emotion}>
            <option value="">Any emotion</option>
            {EMOTIONS.map((emotion) => (
              <option key={emotion} value={emotion}>
                {emotion}
              </option>
            ))}
          </select>
          <input name="tag" placeholder="Tag" aria-label="Tag" defaultValue={filters.tag} />
          <button type="submit">Filter</button>
        </fieldset>
      </form>
      {entries.isPending && <Loading />}
      {entries.error && <ErrorMessage error={entries.error} />}
      {entries.data && entries.data.total === 0 && <p>No journal entries.</p>}
      {entries.data && entries.data.total > 0 && (
        <>
          <div className="overflow-auto">
            <table>
              <thead>
                <tr>
                  <th>Written</th>
                  <th>Title</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Emotion</th>
                  <th>Tags</th>
                  <th>Trade</th>
                </tr>
              </thead>
              <tbody>
                {entries.data.items.map((entry) => (
                  <tr key={entry.id}>
                    <td>{formatDateTime(entry.created_at)}</td>
                    <td>
                      <Link to={`/journal/${entry.id}`}>{entry.title}</Link>
                    </td>
                    <td>{ENTRY_TYPES[entry.entry_type]}</td>
                    <td>{entryStatus(entry)}</td>
                    <td>{entry.emotion ?? "—"}</td>
                    <td>{entry.tags.join(", ") || "—"}</td>
                    <td>
                      {entry.trade_id ? <Link to={`/trades/${entry.trade_id}`}>trade</Link> : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination offset={offset} limit={limit} total={entries.data.total} onPage={showPage} />
        </>
      )}
    </>
  );
}
