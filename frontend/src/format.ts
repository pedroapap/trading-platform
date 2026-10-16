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

// The fiat currencies the app recognizes in symbols, and the dollar stablecoins.
const FIAT = new Set(["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "TRY", "BRL"]);
const STABLECOINS = new Set(["USDT", "USDC", "FDUSD", "BUSD", "TUSD"]);
const fixedFormats = new Map<string, Intl.NumberFormat>();

/** How amounts in `currency` are shown when it has a smallest unit: a fiat currency's own
 * (cents; none for JPY), a cent for a dollar stablecoin. None for coins and unset currencies. */
function fixedFormat(currency: string | null): Intl.NumberFormat | undefined {
  if (currency === null || !(FIAT.has(currency) || STABLECOINS.has(currency))) return undefined;
  if (!fixedFormats.has(currency)) {
    const digits = FIAT.has(currency)
      ? new Intl.NumberFormat("en", { style: "currency", currency }).resolvedOptions()
          .maximumFractionDigits
      : 2;
    fixedFormats.set(
      currency,
      new Intl.NumberFormat(undefined, {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
        signDisplay: "negative",
      }),
    );
  }
  return fixedFormats.get(currency);
}

/** A computed amount of money in `currency`, such as a backtest's P&L. In a fiat currency it
 * shows to its smallest unit, and in a dollar stablecoin to the cent. In a coin such as BTC,
 * or without a set currency, it shows to the cent from 1 up and to 8 significant digits below,
 * where amounts in BTC and the like live. */
export function formatMoney(value: number | string, currency: string | null): string {
  const number = Number(value);
  const fixed = fixedFormat(currency);
  if (fixed) return fixed.format(number);
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
