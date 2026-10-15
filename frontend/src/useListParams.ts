import { useSearchParams } from "react-router";

const PAGE_SIZE = 50;

/** A paged list's filters and page, kept in the URL so they survive a reload and the back
 * button. `filters` holds each named filter's value, "" when unset. */
export function useListParams<const Name extends string>(names: readonly Name[]) {
  const [params, setParams] = useSearchParams();
  const filters = Object.fromEntries(names.map((name) => [name, params.get(name) ?? ""])) as Record<
    Name,
    string
  >;
  const offset = (Math.max(1, Number(params.get("page")) || 1) - 1) * PAGE_SIZE;

  /** Filters by the non-empty values of the form's fields with these names, from page 1. */
  function applyFilters(form: HTMLFormElement) {
    const fields = new FormData(form);
    const next = new URLSearchParams();
    for (const name of names) {
      const value = String(fields.get(name) ?? "").trim();
      if (value) next.set(name, value);
    }
    setParams(next);
  }

  function showPage(newOffset: number) {
    const next = new URLSearchParams(params);
    next.set("page", String(newOffset / PAGE_SIZE + 1));
    setParams(next);
  }

  return { filters, offset, limit: PAGE_SIZE, applyFilters, showPage };
}
