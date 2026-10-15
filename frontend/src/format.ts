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

const cents = new Intl.NumberFormat(undefined, {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const significant = new Intl.NumberFormat(undefined, { maximumSignificantDigits: 8 });

/** A computed amount of money, such as a backtest's P&L: to the cent from 1 up, and to 8
 * significant digits below, where amounts in BTC and the like live. */
export function formatMoney(value: number | string): string {
  const number = Number(value);
  return Math.abs(number) >= 1 ? cents.format(number) : significant.format(number);
}

/** A computed price or size, to 8 significant digits. */
export function formatDecimal(value: number | string): string {
  return significant.format(Number(value));
}

/** A ratio such as Sharpe's, to 2 decimals; "—" when there is none. */
export function formatRatio(value: number | null | undefined): string {
  return value == null ? "—" : cents.format(value);
}

/** The start of a date input's day (yyyy-mm-dd) in the browser's time zone, `daysLater`
 * days on, as an ISO timestamp in UTC: an inclusive "to" date is the next day's start. */
export function dayStart(value: string, daysLater = 0): string {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day + daysLater).toISOString();
}
