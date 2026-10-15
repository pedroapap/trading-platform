import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { FormEvent } from "react";

import { api, unwrap } from "../api/client";
import { fieldErrors } from "../api/errors";
import { useCoverage } from "../api/marketData";
import type { components } from "../api/schema";
import Field from "../components/Field";
import { ErrorMessage, Loading } from "../components/Status";
import { formatCount, formatDateTime } from "../format";

type Schemas = components["schemas"];
type ImportResult = Schemas["ImportResult"];

const TIMEFRAMES: Schemas["Timeframe"][] = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"];

const FORMATS = [
  ["generic_ohlcv", "OHLCV with a header row (Yahoo, TradingView…)"],
  ["binance_klines", "Binance klines"],
] as const;

/** The upload as multipart form data. The file is appended from its input, and empty
 * optional fields are left out, for the API to infer the timeframe and detect the format. */
function uploadFrom(form: HTMLFormElement): FormData {
  const fields = new FormData(form);
  const body = new FormData();
  const file = (form.elements.namedItem("file") as HTMLInputElement).files?.[0];
  if (file) body.append("file", file);
  for (const name of ["symbol", "timeframe", "format"]) {
    const value = String(fields.get(name) ?? "").trim();
    if (value) body.append(name, value);
  }
  return body;
}

function ImportSummary({ result }: { result: ImportResult }) {
  const { rejections } = result;
  return (
    <article aria-label="Import summary">
      <p>
        <strong>
          {result.symbol} {result.timeframe}
        </strong>{" "}
        ({result.format}): {formatCount(result.inserted)} bars added,{" "}
        {formatCount(result.duplicates)} already stored, {formatCount(result.rejected)} rejected.
        {result.first_ts &&
          result.last_ts &&
          ` The file's bars run from ${formatDateTime(result.first_ts)} to ${formatDateTime(result.last_ts)}.`}
      </p>
      {rejections.length > 0 && (
        <>
          <p>
            {result.rejected > rejections.length
              ? `The first ${formatCount(rejections.length)} rejected rows:`
              : "Rejected rows:"}
          </p>
          <div className="overflow-auto">
            <table>
              <thead>
                <tr>
                  <th className="number">Line</th>
                  <th>Why</th>
                </tr>
              </thead>
              <tbody>
                {rejections.map((rejection) => (
                  <tr key={rejection.line}>
                    <td className="number">{rejection.line}</td>
                    <td className="wrap">{rejection.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </article>
  );
}

function ImportBars() {
  const queryClient = useQueryClient();
  const upload = useMutation({
    mutationFn: (body: FormData) =>
      unwrap(
        api.POST("/api/market-data/import", {
          // openapi-fetch sends FormData as it is; the generated type has the file as a string.
          body: body as unknown as Schemas["Body_import_file_api_market_data_import_post"],
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["market-data"] }),
  });
  const errors = fieldErrors(upload.error);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    upload.mutate(uploadFrom(event.currentTarget));
  }

  return (
    <section>
      <h2>Import a price file</h2>
      <form onSubmit={submit} noValidate>
        <div className="grid">
          <Field
            label="CSV file"
            name="file"
            type="file"
            accept=".csv,.txt,text/csv"
            required
            error={errors.file}
          />
          <Field
            label="Symbol"
            name="symbol"
            required
            placeholder="BTCUSDT"
            autoCapitalize="characters"
            error={errors.symbol}
          />
        </div>
        <div className="grid">
          <label>
            Timeframe
            <select name="timeframe" defaultValue="">
              <option value="">From the spacing of the bars</option>
              {TIMEFRAMES.map((timeframe) => (
                <option key={timeframe} value={timeframe}>
                  {timeframe}
                </option>
              ))}
            </select>
          </label>
          <label>
            Format
            <select name="format" defaultValue="">
              <option value="">Detect it</option>
              {FORMATS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>
        {/* Problems with the file or symbol show under them. */}
        {upload.error && !errors.file && !errors.symbol && (
          <p role="alert">{upload.error.message}</p>
        )}
        <button type="submit" aria-busy={upload.isPending} disabled={upload.isPending}>
          Import
        </button>
      </form>
      {upload.data && <ImportSummary result={upload.data} />}
    </section>
  );
}

export default function MarketDataPage() {
  const coverage = useCoverage();

  return (
    <>
      <h1>Market data</h1>
      <ImportBars />
      <h2>Stored bars</h2>
      {coverage.isPending && <Loading />}
      {coverage.error && <ErrorMessage error={coverage.error} />}
      {coverage.data?.length === 0 && <p>No bars stored yet.</p>}
      {coverage.data && coverage.data.length > 0 && (
        <div className="overflow-auto">
          <table className="striped">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Timeframe</th>
                <th>First bar</th>
                <th>Last bar</th>
                <th className="number">Bars</th>
              </tr>
            </thead>
            <tbody>
              {coverage.data.map((entry) => (
                <tr key={`${entry.symbol} ${entry.timeframe}`}>
                  <td>{entry.symbol}</td>
                  <td>{entry.timeframe}</td>
                  <td>{formatDateTime(entry.first_ts)}</td>
                  <td>{formatDateTime(entry.last_ts)}</td>
                  <td className="number">{formatCount(entry.bars)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
