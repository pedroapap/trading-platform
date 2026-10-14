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
