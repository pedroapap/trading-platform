import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, unwrap } from "../api/client";
import { fieldErrors } from "../api/errors";
import type { components } from "../api/schema";
import { fromLocalInput, toLocalInput } from "../format";
import Field from "./Field";

type Schemas = components["schemas"];
type Trade = Schemas["TradeRead"];

function texts(form: HTMLFormElement) {
  const fields = new FormData(form);
  return (name: string) => String(fields.get(name) ?? "").trim();
}

/** A change to a trade; afterwards everything under ["trades"] (lists, the trade, its
 * history) is fetched again. */
function useTradeChange<Body>(change: (body: Body) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: change,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["trades"] }),
  });
}

export function CloseTrade({ trade }: { trade: Trade }) {
  const [openedAt] = useState(() => toLocalInput(new Date()));
  const close = useTradeChange((body: Schemas["TradeClose"]) =>
    unwrap(
      api.POST("/api/trades/{trade_id}/close", { params: { path: { trade_id: trade.id } }, body }),
    ),
  );
  const errors = fieldErrors(close.error);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = texts(event.currentTarget);
    close.mutate({
      exit_price: text("exit_price"),
      exit_time: text("exit_time") && fromLocalInput(text("exit_time")),
      exit_size: text("exit_size") || undefined,
      exit_fee: text("exit_fee") || "0",
    });
  }

  return (
    <details>
      <summary role="button">Close trade</summary>
      <form onSubmit={submit} noValidate>
        <div className="grid">
          <Field
            label="Exit price"
            name="exit_price"
            inputMode="decimal"
            required
            error={errors.exit_price}
          />
          <Field
            label="Exit time"
            name="exit_time"
            type="datetime-local"
            defaultValue={openedAt}
            required
            error={errors.exit_time}
          />
        </div>
        <div className="grid">
          <Field
            label="Exit size"
            name="exit_size"
            inputMode="decimal"
            placeholder={`${trade.entry_size} (all)`}
            error={errors.exit_size}
          />
          <Field
            label="Exit fee"
            name="exit_fee"
            inputMode="decimal"
            placeholder="0"
            error={errors.exit_fee}
          />
        </div>
        {close.error && Object.keys(errors).length === 0 && (
          <p role="alert">{close.error.message}</p>
        )}
        <button type="submit" aria-busy={close.isPending} disabled={close.isPending}>
          Save exit
        </button>
      </form>
    </details>
  );
}

export function CancelTrade({ trade }: { trade: Trade }) {
  const cancel = useTradeChange((body: Schemas["TradeCancel"]) =>
    unwrap(
      api.POST("/api/trades/{trade_id}/cancel", { params: { path: { trade_id: trade.id } }, body }),
    ),
  );

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    cancel.mutate({ reason: texts(event.currentTarget)("reason") || undefined });
  }

  return (
    <details>
      <summary role="button" className="secondary outline">
        Cancel trade
      </summary>
      <form onSubmit={submit}>
        <Field label="Why it never happened (optional)" name="reason" maxLength={500} />
        {cancel.error && <p role="alert">{cancel.error.message}</p>}
        <button
          type="submit"
          className="secondary"
          aria-busy={cancel.isPending}
          disabled={cancel.isPending}
        >
          Confirm cancellation
        </button>
      </form>
    </details>
  );
}

const CORRECTABLE = [
  "symbol",
  "direction",
  "entry_price",
  "entry_size",
  "entry_time",
  "entry_fee",
  "exit_price",
  "exit_size",
  "exit_time",
  "exit_fee",
  "stop_loss",
  "take_profit",
  "leverage",
  "strategy_id",
  "strategy_version",
] as const;
type Correctable = (typeof CORRECTABLE)[number];

// Fields a correction can empty; any other emptied field goes as "" for the API to refuse.
const CLEARABLE = new Set<Correctable>([
  "stop_loss",
  "take_profit",
  "strategy_id",
  "strategy_version",
]);

/** The trade as the correction form shows it. */
function formValues(trade: Trade): Record<Correctable, string> {
  const local = (iso: string | null) => (iso ? toLocalInput(new Date(iso)) : "");
  return {
    symbol: trade.symbol,
    direction: trade.direction,
    entry_price: trade.entry_price,
    entry_size: trade.entry_size,
    entry_time: local(trade.entry_time),
    entry_fee: trade.entry_fee,
    exit_price: trade.exit_price ?? "",
    exit_size: trade.exit_size ?? "",
    exit_time: local(trade.exit_time),
    exit_fee: trade.exit_fee,
    stop_loss: trade.stop_loss ?? "",
    take_profit: trade.take_profit ?? "",
    leverage: trade.leverage,
    strategy_id: trade.strategy_id ?? "",
    strategy_version: trade.strategy_version?.toString() ?? "",
  };
}

function apiValue(field: Correctable, value: string): unknown {
  if (value === "" && CLEARABLE.has(field)) return null;
  if (value && field.endsWith("_time")) return fromLocalInput(value);
  if (value && field === "strategy_version") return Number(value);
  return value;
}

export function CorrectTrade({
  trade,
  strategies,
}: {
  trade: Trade;
  strategies: Schemas["StrategyRead"][];
}) {
  const before = formValues(trade);
  const [unchanged, setUnchanged] = useState(false);
  const correct = useTradeChange((body: Schemas["TradeCorrection"]) =>
    unwrap(
      api.POST("/api/trades/{trade_id}/correct", {
        params: { path: { trade_id: trade.id } },
        body,
      }),
    ),
  );
  const errors = fieldErrors(correct.error);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = texts(event.currentTarget);
    // Only what was edited is sent: the API recomputes P&L and audits each change.
    const changes = Object.fromEntries(
      CORRECTABLE.filter((field) => text(field) !== before[field]).map((field) => [
        field,
        apiValue(field, text(field)),
      ]),
    );
    setUnchanged(Object.keys(changes).length === 0);
    if (Object.keys(changes).length > 0) {
      correct.mutate({ ...changes, reason: text("reason") } as Schemas["TradeCorrection"]);
    }
  }

  const field = (label: string, name: Correctable, type = "text") => (
    <Field
      label={label}
      name={name}
      type={type}
      inputMode={type === "text" && name !== "symbol" ? "decimal" : undefined}
      defaultValue={before[name]}
      error={errors[name]}
    />
  );

  return (
    <details>
      <summary role="button" className="secondary outline">
        Correct trade
      </summary>
      <form onSubmit={submit} noValidate>
        <div className="grid">
          {field("Symbol", "symbol")}
          <label>
            Direction
            <select name="direction" defaultValue={before.direction}>
              <option value="long">long</option>
              <option value="short">short</option>
            </select>
          </label>
          {field("Leverage", "leverage")}
        </div>
        <div className="grid">
          {field("Entry price", "entry_price")}
          {field("Entry size", "entry_size")}
          {field("Entry time", "entry_time", "datetime-local")}
          {field("Entry fee", "entry_fee")}
        </div>
        <div className="grid">
          {field("Exit price", "exit_price")}
          {field("Exit size", "exit_size")}
          {field("Exit time", "exit_time", "datetime-local")}
          {field("Exit fee", "exit_fee")}
        </div>
        <div className="grid">
          {field("Stop-loss", "stop_loss")}
          {field("Take-profit", "take_profit")}
          <label>
            Strategy
            <select name="strategy_id" defaultValue={before.strategy_id}>
              <option value="">None</option>
              {strategies.map((strategy) => (
                <option key={strategy.id} value={strategy.id}>
                  {strategy.name}
                </option>
              ))}
            </select>
          </label>
          {field("Strategy version", "strategy_version", "number")}
        </div>
        <Field
          label="Reason for the correction"
          name="reason"
          required
          maxLength={500}
          error={errors.reason}
        />
        {unchanged && <p role="alert">Nothing to correct: change at least one field.</p>}
        {correct.error && Object.keys(errors).length === 0 && (
          <p role="alert">{correct.error.message}</p>
        )}
        <button type="submit" aria-busy={correct.isPending} disabled={correct.isPending}>
          Save correction
        </button>
      </form>
    </details>
  );
}
