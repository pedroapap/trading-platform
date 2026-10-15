import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useId, type FormEvent } from "react";

import { api, unwrap } from "../api/client";
import { fieldErrors } from "../api/errors";
import { useInstruments } from "../api/instruments";
import type { components } from "../api/schema";
import { ErrorMessage, Loading } from "../components/Status";

type Instrument = components["schemas"]["InstrumentRead"];

/** A symbol's quote currency, edited in place. */
function CurrencyForm({ instrument }: { instrument: Instrument }) {
  const id = useId();
  const queryClient = useQueryClient();
  const save = useMutation({
    mutationFn: (quoteCurrency: string) =>
      unwrap(
        api.PUT("/api/instruments/{symbol}", {
          params: { path: { symbol: instrument.symbol } },
          body: { quote_currency: quoteCurrency },
        }),
      ),
    // Trades, backtests and analytics show money in this currency: refresh them all.
    onSuccess: () => queryClient.invalidateQueries(),
  });
  const error = save.error && (fieldErrors(save.error).quote_currency ?? save.error.message);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = new FormData(event.currentTarget).get("quote_currency");
    save.mutate(String(value ?? "").trim());
  }

  return (
    <form onSubmit={submit} noValidate>
      <fieldset role="group">
        <input
          name="quote_currency"
          aria-label={`Quote currency of ${instrument.symbol}`}
          defaultValue={instrument.quote_currency ?? ""}
          placeholder="Not set"
          autoCapitalize="characters"
          maxLength={10}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
        />
        <button type="submit" aria-busy={save.isPending} disabled={save.isPending}>
          Save
        </button>
      </fieldset>
      {error && <small id={`${id}-error`}>{error}</small>}
    </form>
  );
}

export default function InstrumentsPage() {
  const instruments = useInstruments();

  return (
    <>
      <h1>Instruments</h1>
      <p>
        A symbol's quote currency is the currency of its prices, fees and P&amp;L. Totals are kept
        per currency, never converted. Each symbol's currency is guessed from its name when it is
        first used: set the ones that couldn't be guessed, or were guessed wrong. A currency is 2 to
        10 letters or digits, such as USD, USDT or BTC.
      </p>
      {instruments.isPending && <Loading />}
      {instruments.error && <ErrorMessage error={instruments.error} />}
      {instruments.data?.length === 0 && <p>No symbols in use yet.</p>}
      {instruments.data && instruments.data.length > 0 && (
        <table className="instruments">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Quote currency</th>
            </tr>
          </thead>
          <tbody>
            {instruments.data.map((instrument) => (
              <tr key={instrument.symbol}>
                <td>
                  {instrument.symbol}
                  {instrument.quote_currency === null && (
                    <>
                      {" "}
                      <mark>currency not set</mark>
                    </>
                  )}
                </td>
                <td>
                  {/* Remounts with the saved currency, as the API normalized it. */}
                  <CurrencyForm key={instrument.quote_currency ?? ""} instrument={instrument} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
