import type { components } from "../api/schema";

type Schemas = components["schemas"];

let ids = 0;

/** A fresh, valid UUID: tests that need a known id pass their own. */
export function nextId(): string {
  ids += 1;
  return `00000000-0000-4000-8000-${String(ids).padStart(12, "0")}`;
}

export const USER: Schemas["UserRead"] = {
  id: "0b4a6a4e-1c2d-4a1f-9e1b-2f6f1e0c9d11",
  email: "trader@example.com",
  is_active: true,
  created_at: "2026-01-05T14:30:00Z",
};

export const STRATEGY: Schemas["StrategyRead"] = {
  id: "5d2f8a3c-7e41-4b6a-9c0d-3e1f2a4b5c6d",
  name: "RSI dip",
  description: null,
  current_version: 2,
  definition: {
    direction: "long",
    entry: {
      left: { indicator: "rsi", period: 14, source: "close" },
      op: "<",
      right: { value: 30 },
    },
    exit: null,
    stop_loss_pct: 2,
    take_profit_pct: null,
  },
  created_at: "2026-01-01T09:00:00Z",
  updated_at: "2026-01-02T09:00:00Z",
};

/** A closed BTCUSDT long: 1 bought at 50000 and sold at 50120, a 120 USDT profit. */
export function trade(overrides: Partial<Schemas["TradeRead"]> = {}): Schemas["TradeRead"] {
  return {
    id: nextId(),
    strategy_id: null,
    strategy_version: null,
    symbol: "BTCUSDT",
    quote_currency: "USDT",
    direction: "long",
    status: "closed",
    entry_price: "50000",
    entry_time: "2026-01-05T14:30:00Z",
    entry_size: "1",
    entry_fee: "0",
    exit_price: "50120",
    exit_time: "2026-01-05T16:00:00Z",
    exit_size: "1",
    exit_fee: "0",
    stop_loss: null,
    take_profit: null,
    leverage: "1",
    pnl: "120",
    pnl_pct: "0.24",
    created_at: "2026-01-05T14:30:00Z",
    updated_at: "2026-01-05T16:00:00Z",
    ...overrides,
  };
}

/** An open trade has no exit and no P&L yet. */
export function openTrade(overrides: Partial<Schemas["TradeRead"]> = {}): Schemas["TradeRead"] {
  return trade({
    status: "open",
    exit_price: null,
    exit_time: null,
    exit_size: null,
    pnl: null,
    pnl_pct: null,
    ...overrides,
  });
}

/** An audit event of `trade_id`, recorded by USER. */
export function auditEvent(
  overrides: Partial<Schemas["AuditEventRead"]> & Pick<Schemas["AuditEventRead"], "event_type">,
): Schemas["AuditEventRead"] {
  ids += 1;
  return {
    id: ids,
    old_values: null,
    new_values: null,
    changed_by: USER.id,
    change_reason: null,
    created_at: "2026-01-05T14:30:00Z",
    ...overrides,
  };
}

/** A published post-trade review, at version 1. */
export function journalEntry(
  overrides: Partial<Schemas["JournalEntryRead"]> = {},
): Schemas["JournalEntryRead"] {
  return {
    id: nextId(),
    entry_type: "post_trade",
    trade_id: null,
    title: "Breakout review",
    thesis: "Range break with volume",
    market_context: null,
    risk_assessment: null,
    lessons: "Waited for the retest",
    emotion: "calm",
    tags: ["breakout"],
    status: "published",
    current_version: 1,
    published_at: "2026-01-05T18:00:00Z",
    created_at: "2026-01-05T17:00:00Z",
    updated_at: "2026-01-05T18:00:00Z",
    ...overrides,
  };
}
