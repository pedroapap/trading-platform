import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { api, unwrap } from "../api/client";
import { fieldErrors } from "../api/errors";
import { useCoverage } from "../api/marketData";
import type { components } from "../api/schema";
import { useStrategies } from "../api/strategies";
import Field from "../components/Field";
import { fromLocalInput } from "../format";

type Schemas = components["schemas"];
type BacktestCreate = Schemas["BacktestCreate"];
type Timeframe = Schemas["Timeframe"];

// Each bar size in seconds, finest first.
const SECONDS: Record<Timeframe, number> = {
  "1m": 60,
  "5m": 300,
  "15m": 900,
  "30m": 1800,
  "1h": 3600,
  "4h": 14400,
  "1d": 86400,
};
const TIMEFRAMES = Object.keys(SECONDS) as Timeframe[];

/** The timeframes stored for `symbol` that can settle fills inside `timeframe` bars: finer,
 * and dividing it. Finest first. */
function finerStored(
  coverage: Schemas["CoverageRead"][],
  symbol: string,
  timeframe: Timeframe,
): Timeframe[] {
  const stored = coverage.filter((entry) => entry.symbol === symbol.trim().toUpperCase());
  return TIMEFRAMES.filter(
    (finer) =>
      SECONDS[finer] < SECONDS[timeframe] &&
      SECONDS[timeframe] % SECONDS[finer] === 0 &&
      stored.some((entry) => entry.timeframe === finer),
  );
}

/** The form's text, with optional fields left out when empty. Amounts stay strings, so they
 * reach the API exactly as typed, and an emptied one goes as "" for the API to refuse. */
function backtestFrom(form: FormData): BacktestCreate {
  const text = (name: string) => String(form.get(name) ?? "").trim();
  const time = (name: string) => (text(name) ? fromLocalInput(text(name)) : undefined);
  return {
    strategy_id: text("strategy_id"),
    strategy_version: text("strategy_version") ? Number(text("strategy_version")) : undefined,
    symbol: text("symbol"),
    timeframe: text("timeframe") as Timeframe,
    detail_timeframe: (text("detail_timeframe") || undefined) as Timeframe | undefined,
    start: time("start"),
    end: time("end"),
    out_of_sample_from: time("out_of_sample_from"),
    initial_capital: text("initial_capital"),
    position_size_pct: text("position_size_pct"),
    fee_pct: text("fee_pct"),
    slippage_pct: text("slippage_pct"),
    periods_per_year: Number(text("periods_per_year")),
  };
}

export default function NewBacktestPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  // A strategy's page links here with ?strategy=<id>.
  const [params] = useSearchParams();
  const strategies = useStrategies();
  const coverage = useCoverage();
  const [chosen, setChosen] = useState(params.get("strategy") ?? "");
  const [symbol, setSymbol] = useState("");
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");
  // The finer bars picked: until then, or once they no longer fit, the finest stored.
  const [detailPicked, setDetailPicked] = useState<string>();
  const run = useMutation({
    mutationFn: (backtest: BacktestCreate) =>
      unwrap(api.POST("/api/backtests", { body: backtest })),
    onSuccess: async (backtest) => {
      await queryClient.invalidateQueries({ queryKey: ["backtests"] });
      navigate(`/backtests/${backtest.id}`);
    },
  });
  const errors = fieldErrors(run.error);
  // The strategy asked for, or else the first one.
  const strategy = strategies.data?.find((each) => each.id === chosen) ?? strategies.data?.[0];
  const symbols = [...new Set(coverage.data?.map((entry) => entry.symbol))];
  const finer = finerStored(coverage.data ?? [], symbol, timeframe);
  const detail = [...finer, ""].find((each) => each === detailPicked) ?? finer[0] ?? "";

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    run.mutate(backtestFrom(new FormData(event.currentTarget)));
  }

  return (
    <>
      <p>
        <Link to="/backtests">← Backtests</Link>
      </p>
      <h1>New backtest</h1>
      {strategies.data?.length === 0 && (
        <p>
          A backtest runs a strategy: <Link to="/strategies/new">create one</Link> first.
        </p>
      )}
      <form onSubmit={submit} noValidate>
        <div className="grid">
          <label>
            Strategy
            <select
              name="strategy_id"
              value={strategy?.id ?? ""}
              onChange={(event) => setChosen(event.target.value)}
            >
              {strategies.data?.map((each) => (
                <option key={each.id} value={each.id}>
                  {each.name}
                </option>
              ))}
            </select>
          </label>
          <Field
            label="Version"
            name="strategy_version"
            type="number"
            min={1}
            placeholder={strategy ? `Current: v${strategy.current_version}` : "Current"}
            error={errors.strategy_version}
          />
        </div>
        <div className="grid">
          <Field
            label="Symbol"
            name="symbol"
            list="stored-symbols"
            autoCapitalize="characters"
            required
            onChange={(event) => setSymbol(event.target.value)}
            error={errors.symbol}
          />
          <datalist id="stored-symbols">
            {symbols.map((symbol) => (
              <option key={symbol} value={symbol} />
            ))}
          </datalist>
          <label>
            Timeframe
            <select
              name="timeframe"
              value={timeframe}
              onChange={(event) => setTimeframe(event.target.value as Timeframe)}
            >
              {TIMEFRAMES.map((each) => (
                <option key={each} value={each}>
                  {each}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="grid">
          <Field label="From (optional)" name="start" type="datetime-local" error={errors.start} />
          <Field label="To (optional)" name="end" type="datetime-local" error={errors.end} />
        </div>
        <div className="grid">
          <Field
            label="Out-of-sample from (optional)"
            name="out_of_sample_from"
            type="datetime-local"
            hint="Bars from then on are reported apart: a test on bars the strategy wasn't tuned on."
            error={errors.out_of_sample_from}
          />
          <div>
            <label htmlFor="detail-timeframe">Finer bars for fills</label>
            <select
              id="detail-timeframe"
              name="detail_timeframe"
              value={detail}
              onChange={(event) => setDetailPicked(event.target.value)}
              aria-describedby="detail-timeframe-hint"
            >
              {finer.map((each) => (
                <option key={each} value={each}>
                  {each} bars
                </option>
              ))}
              <option value="">None: assume the worst case</option>
            </select>
            <small id="detail-timeframe-hint">
              They settle what came first inside a bar that reaches both the stop and the target, or
              fills an entry order. Stored timeframes that divide this one are offered.
            </small>
          </div>
        </div>
        <div className="grid">
          <Field
            label="Initial capital"
            name="initial_capital"
            inputMode="decimal"
            defaultValue="10000"
            error={errors.initial_capital}
          />
          <Field
            label="Position size %"
            name="position_size_pct"
            inputMode="decimal"
            defaultValue="100"
            error={errors.position_size_pct}
          />
          <Field
            label="Fee %"
            name="fee_pct"
            inputMode="decimal"
            defaultValue="0"
            error={errors.fee_pct}
          />
          <Field
            label="Slippage %"
            name="slippage_pct"
            inputMode="decimal"
            defaultValue="0"
            error={errors.slippage_pct}
          />
        </div>
        <Field
          label="Periods per year (365 for crypto, 252 for stock exchanges)"
          name="periods_per_year"
          type="number"
          min={1}
          max={366}
          defaultValue="365"
          error={errors.periods_per_year}
        />
        {run.error && !Object.keys(errors).length && <p role="alert">{run.error.message}</p>}
        <button type="submit" aria-busy={run.isPending} disabled={run.isPending}>
          Run backtest
        </button>
      </form>
    </>
  );
}
