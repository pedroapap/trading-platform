const dateTime = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

/** A timestamp from the API, in the browser's time zone. */
export function formatDateTime(iso: string): string {
  return dateTime.format(new Date(iso));
}

/** `date` as the value of a datetime-local input, in the browser's time zone. */
export function toLocalInput(date: Date): string {
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

/** A datetime-local input's value (the browser's time zone) as an ISO timestamp in UTC. */
export function fromLocalInput(value: string): string {
  return new Date(value).toISOString();
}
