import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";

import { api, unwrap } from "../api/client";
import { fieldErrors } from "../api/errors";
import type { components } from "../api/schema";
import { useStrategies } from "../api/strategies";
import Field from "../components/Field";
import { fromLocalInput, toLocalInput } from "../format";

type TradeCreate = components["schemas"]["TradeCreate"];

/** The form's text, with optional fields left out when empty. Prices stay strings, so they
 * reach the API exactly as typed. */
function tradeFrom(form: FormData): TradeCreate {
  const text = (name: string) => String(form.get(name) ?? "").trim();
  const optional = (name: string) => text(name) || undefined;
  return {
    symbol: text("symbol"),
    direction: text("direction") as TradeCreate["direction"],
    entry_price: text("entry_price"),
    entry_size: text("entry_size"),
    // Left empty, it's sent as is, and the API says what's missing.
    entry_time: text("entry_time") && fromLocalInput(text("entry_time")),
    entry_fee: text("entry_fee") || "0",
    stop_loss: optional("stop_loss"),
    take_profit: optional("take_profit"),
    leverage: text("leverage") || "1",
    strategy_id: optional("strategy_id"),
    strategy_version: optional("strategy_version") ? Number(text("strategy_version")) : undefined,
  };
}

export default function NewTradePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const strategies = useStrategies();
  const create = useMutation({
    mutationFn: (trade: TradeCreate) => unwrap(api.POST("/api/trades", { body: trade })),
    onSuccess: async (trade) => {
      await queryClient.invalidateQueries({ queryKey: ["trades"] });
      navigate(`/trades/${trade.id}`);
    },
  });
  const errors = fieldErrors(create.error);
  // Entry time defaults to when the form was opened.
  const [openedAt] = useState(() => toLocalInput(new Date()));

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    create.mutate(tradeFrom(new FormData(event.currentTarget)));
  }

  return (
    <>
      <p>
        <Link to="/trades">← Trades</Link>
      </p>
      <h1>New trade</h1>
      <form onSubmit={submit} noValidate>
        <div className="grid">
          <Field label="Symbol" name="symbol" required error={errors.symbol} />
          <label>
            Direction
            <select name="direction" defaultValue="long">
              <option value="long">long</option>
              <option value="short">short</option>
            </select>
          </label>
        </div>
        <div className="grid">
          <Field
            label="Entry price"
            name="entry_price"
            inputMode="decimal"
            required
            error={errors.entry_price}
          />
          <Field
            label="Size"
            name="entry_size"
            inputMode="decimal"
            required
            error={errors.entry_size}
          />
          <Field
            label="Entry time"
            name="entry_time"
            type="datetime-local"
            defaultValue={openedAt}
            required
            error={errors.entry_time}
          />
        </div>
        <div className="grid">
          <Field
            label="Entry fee"
            name="entry_fee"
            inputMode="decimal"
            placeholder="0"
            error={errors.entry_fee}
          />
          <Field label="Stop-loss" name="stop_loss" inputMode="decimal" error={errors.stop_loss} />
          <Field
            label="Take-profit"
            name="take_profit"
            inputMode="decimal"
            error={errors.take_profit}
          />
          <Field
            label="Leverage"
            name="leverage"
            inputMode="decimal"
            placeholder="1"
            error={errors.leverage}
          />
        </div>
        <div className="grid">
          <label>
            Strategy
            <select name="strategy_id" defaultValue="">
              <option value="">None</option>
              {strategies.data?.map((strategy) => (
                <option key={strategy.id} value={strategy.id}>
                  {strategy.name} (v{strategy.current_version})
                </option>
              ))}
            </select>
          </label>
          <Field
            label="Strategy version"
            name="strategy_version"
            type="number"
            min={1}
            placeholder="Current"
            error={errors.strategy_version}
          />
        </div>
        {create.error && Object.keys(errors).length === 0 && (
          <p role="alert">{create.error.message}</p>
        )}
        <button type="submit" aria-busy={create.isPending} disabled={create.isPending}>
          Log trade
        </button>
      </form>
    </>
  );
}
