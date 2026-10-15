const dateTime = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

/** A timestamp from the API, in the browser's time zone. */
export function formatDateTime(iso: string): string {
  return dateTime.format(new Date(iso));
}

const date = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });

/** The day of a timestamp from the API, in the browser's time zone. */
export function formatDate(iso: string): string {
  return date.format(new Date(iso));
}

/** `date` as the value of a datetime-local input, in the browser's time zone. */
export function toLocalInput(date: Date): string {
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

/** A datetime-local input's value (the browser's time zone) as an ISO timestamp in UTC. */
export function fromLocalInput(value: string): string {
  return new Date(value).toISOString();
}

const count = new Intl.NumberFormat();

/** A whole number with the browser's digit grouping, as 525,600. */
export function formatCount(value: number): string {
  return count.format(value);
}

const percent = new Intl.NumberFormat(undefined, {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** A percentage the API computed as a float, to 2 decimals, as -12.34%; "—" when there is
 * none. */
export function formatPercent(value: number | string | null | undefined): string {
  return value == null ? "—" : `${percent.format(Number(value))}%`;
}
