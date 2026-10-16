# Automating with the API and the command line

Everything the app's pages do goes through a REST API, so you can script it: import prices
every night, run a batch of backtests, or load your trades into pandas.

- **Interactive docs:** <http://localhost:8000/api/docs> lists every endpoint with its
  fields, and lets you try them.
- **The schema:** it is at <http://localhost:8000/api/openapi.json>.

## Logging in

The API uses a bearer token. Get one by posting your email and password as a form; it lasts
7 days:

```sh
API=http://localhost:8000/api
TOKEN=$(curl -s -X POST $API/auth/login \
  -d username=you@example.com -d password='your password' | jq -r .access_token)
AUTH="Authorization: Bearer $TOKEN"
curl -s -H "$AUTH" $API/auth/me
```

```json
{"id": "113bdf33-0706-4d61-8b82-6d8678a4006c", "email": "you@example.com", "is_active": true, "created_at": "2026-10-16T22:51:40.808623Z"}
```

The examples below use `curl` and `jq` with these three variables.

## Endpoints

Every endpoint but the health check and logging in needs the token. Each account sees only
its own trades, journal, strategies and backtests.

| Area | Endpoints |
|---|---|
| Health | `GET /api/health`: is the API up, and can it reach the database? |
| Account | `POST /api/auth/login`, `GET /api/auth/me`. `POST /api/auth/register` creates the account, and works only while there is none |
| Trades | `POST /api/trades`, `GET /api/trades` (filters `symbol`, `status`, `strategy_id`, `entry_from`, `entry_to`; `limit`, `offset`), `GET /api/trades/{id}`, `PATCH /api/trades/{id}` (an open trade), `POST /api/trades/{id}/close`, `POST /api/trades/{id}/cancel`, `POST /api/trades/{id}/correct` (a closed trade), `GET /api/trades/{id}/audit-log` |
| Market data | `POST /api/market-data/import`, `GET /api/market-data/symbols`, `GET /api/market-data/{symbol}/bars` |
| Instruments | `GET /api/instruments`, `PUT /api/instruments/{symbol}` |
| Strategies | `POST /api/strategies`, `GET /api/strategies`, `GET /api/strategies/{id}`, `PATCH /api/strategies/{id}`, `GET /api/strategies/{id}/versions`, `GET /api/strategies/{id}/versions/{number}` |
| Backtests | `POST /api/backtests`, `GET /api/backtests` (filter `strategy_id`), `GET /api/backtests/{id}`, `GET /api/backtests/{id}/trades`, `GET /api/backtests/{id}/equity` |
| Journal | `POST /api/journal`, `GET /api/journal` (filters `entry_type`, `trade_id`, `status`, `emotion`, `tag`, `created_from`, `created_to`), `GET /api/journal/{id}`, `PATCH /api/journal/{id}`, `POST /api/journal/{id}/publish`, `GET /api/journal/{id}/versions` |
| Analytics | `GET /api/analytics/performance`, `GET /api/analytics/equity`, `GET /api/analytics/backtests/{id}/comparison` |

### Conventions

- **Times** are ISO 8601 with a time zone, such as `2025-03-26T01:00:00Z`. Ranges include
  their start and leave out their end.
- **Money** is sent and returned as decimal strings, such as `"230.17"`, so nothing is lost
  to rounding. Backtest metrics are plain numbers.
- **Lists** come as `{"items": [...], "total": n, "limit": …, "offset": …}`. Page through them
  with `limit` and `offset`.
- **Errors** come with a status and a `detail`:
  - 401: not logged in.
  - 404: not found, or not yours.
  - 409: a conflict, such as a duplicate name or closing a closed trade.
  - 413: a file too large.
  - 422: invalid input. Its `detail` is a list of problems, each with a `loc` (where) and a
    `msg` (what).

## Common tasks

### Import prices, and read them back

```sh
curl -s -H "$AUTH" -F symbol=DEMOUSDT -F file=@docs/sample-data/demousdt-1h.csv \
  $API/market-data/import | jq '{inserted, duplicates, rejected, timeframe}'
```

```json
{"inserted": 8760, "duplicates": 0, "rejected": 0, "timeframe": "1h"}
```

Add `-F timeframe=1h` or `-F format=binance_klines` to say what the app would otherwise
work out. Then list what is stored, and ask for bars, stored or built from smaller ones:

```sh
curl -s -H "$AUTH" $API/market-data/symbols
curl -s -H "$AUTH" "$API/market-data/DEMOUSDT/bars?timeframe=4h&start=2025-03-26T00:00:00Z&limit=2" | jq
```

```json
{
  "symbol": "DEMOUSDT",
  "timeframe": "4h",
  "aggregated_from": "1h",
  "bars": [
    {"ts": "2025-03-26T00:00:00Z", "open": "99.26", "high": "99.59", "low": "97.82", "close": "99.48", "volume": "1717.4237"},
    {"ts": "2025-03-26T04:00:00Z", "open": "99.48", "high": "100.59", "low": "99.37", "close": "100.22", "volume": "1155.7651"}
  ]
}
```

`limit` is 1,000 bars by default and 10,000 at most. For more, ask again from the last bar's
time plus one bar.

### Create a strategy and backtest it

```sh
STRATEGY=$(curl -s -H "$AUTH" -H 'Content-Type: application/json' $API/strategies -d '{
  "name": "RSI dip",
  "definition": {
    "direction": "long",
    "entry": {"left": {"indicator": "rsi"}, "op": "<", "right": {"value": 30}},
    "exit": {"left": {"indicator": "rsi"}, "op": ">", "right": {"value": 70}},
    "stop_loss_pct": 2
  }
}' | jq -r .id)

BACKTEST=$(curl -s -H "$AUTH" -H 'Content-Type: application/json' $API/backtests -d '{
  "strategy_id": "'$STRATEGY'", "symbol": "DEMOUSDT", "timeframe": "1h",
  "fee_pct": "0.1", "slippage_pct": "0.05", "out_of_sample_from": "2025-10-01T00:00:00Z"
}' | jq -r .id)
```

The backtest runs in the background: its `status` goes from `pending` to `running`, then
`completed` or `failed` (with an `error_message`). Poll it:

```sh
until curl -s -H "$AUTH" $API/backtests/$BACKTEST | jq -e '.status | test("completed|failed")' >/dev/null; do sleep 1; done
curl -s -H "$AUTH" $API/backtests/$BACKTEST | jq '.metrics | {total_return_pct, buy_and_hold_return_pct, num_trades, win_rate_pct, sharpe_ratio}'
```

```json
{"total_return_pct": 35.69307806090245, "buy_and_hold_return_pct": 2.063350128132746, "num_trades": 73, "win_rate_pct": 38.35616438356164, "sharpe_ratio": 1.2668445598160059}
```

The run's `split_metrics` holds each side of the out-of-sample split.
`GET /api/backtests/{id}/trades` lists its trades, and `GET /api/backtests/{id}/equity` its
equity curve beside buy and hold's.

A strategy is changed with `PATCH /api/strategies/{id}`: a new `definition` makes the next
version, while `name` and `description` change in place.

### Record a trade, close it, and read its history

```sh
TRADE=$(curl -s -H "$AUTH" -H 'Content-Type: application/json' $API/trades -d '{
  "symbol": "DEMOUSDT", "direction": "long", "entry_price": "98.50", "entry_size": "50",
  "entry_time": "2025-06-02T09:00:00Z", "entry_fee": "4.93"
}' | jq -r .id)

curl -s -H "$AUTH" -H 'Content-Type: application/json' $API/trades/$TRADE/close \
  -d '{"exit_price": "101.20", "exit_time": "2025-06-03T15:00:00Z", "exit_fee": "5.06"}' \
  | jq '{status, pnl, pnl_pct, quote_currency}'
```

```json
{"status": "closed", "pnl": "125.01", "pnl_pct": "2.5383", "quote_currency": "USDT"}
```

Fix it later with a reason, and read what happened to it:

```sh
curl -s -H "$AUTH" -H 'Content-Type: application/json' $API/trades/$TRADE/correct \
  -d '{"exit_fee": "5.10", "reason": "Fee from the broker statement"}' | jq .pnl
curl -s -H "$AUTH" $API/trades/$TRADE/audit-log | jq -c '.[] | {event_type, change_reason}'
```

The P&L is worked out again (`"124.97"`), and the history has three events:

```json
{"event_type": "entry", "change_reason": null}
{"event_type": "exit", "change_reason": null}
{"event_type": "correction", "change_reason": "Fee from the broker statement"}
```

An open trade is changed with `PATCH /api/trades/{id}`, and dropped with
`POST /api/trades/{id}/cancel`.

### Write a journal entry and publish it

```sh
ENTRY=$(curl -s -H "$AUTH" -H 'Content-Type: application/json' $API/journal -d '{
  "entry_type": "post_trade", "trade_id": "'$TRADE'", "title": "June bounce",
  "lessons": "Patient entry paid off.", "emotion": "calm", "tags": ["bounce"]
}' | jq -r .id)
curl -s -X POST -H "$AUTH" $API/journal/$ENTRY/publish | jq '{status, current_version}'
curl -s -X PATCH -H "$AUTH" -H 'Content-Type: application/json' $API/journal/$ENTRY \
  -d '{"lessons": "Patient entry paid off; size up next time.", "edit_reason": "Added a plan"}' \
  | jq .current_version
```

### Set a symbol's currency

```sh
curl -s -X PUT -H "$AUTH" -H 'Content-Type: application/json' \
  $API/instruments/AAPL -d '{"quote_currency": "USD"}'
```

Symbols with a slash are written with it encoded: `$API/instruments/BTC%2FUSDT`.

### Analytics

```sh
curl -s -H "$AUTH" "$API/analytics/performance?by=symbol" | jq '.groups[] | {label, num_trades, average_return_pct, by_currency}'
curl -s -H "$AUTH" "$API/analytics/equity?closed_from=2025-01-01T00:00:00Z" | jq '.curves[] | {currency, total_pnl, max_drawdown}'
curl -s -H "$AUTH" $API/analytics/backtests/$BACKTEST/comparison | jq '{backtest, live}'
```

`by` is `strategy`, `symbol`, `emotion` or `tag`. For emotions and tags, `entry_type` keeps
only one type of journal entry, such as `pre_trade`.

## From Python

The same in Python, with [requests](https://requests.readthedocs.io/) and pandas: run a
backtest, then look at its trades in a DataFrame.

```python
import time

import pandas as pd
import requests

API = "http://localhost:8000/api"
token = requests.post(
    f"{API}/auth/login", data={"username": "you@example.com", "password": "your password"}
).json()["access_token"]
session = requests.Session()
session.headers["Authorization"] = f"Bearer {token}"

strategy = next(s for s in session.get(f"{API}/strategies").json() if s["name"] == "RSI dip")
backtest = session.post(f"{API}/backtests", json={
    "strategy_id": strategy["id"], "symbol": "DEMOUSDT", "timeframe": "4h",
    "fee_pct": "0.1", "slippage_pct": "0.05",
}).json()
while backtest["status"] in ("pending", "running"):
    time.sleep(1)
    backtest = session.get(f"{API}/backtests/{backtest['id']}").json()

trades = pd.DataFrame(
    session.get(f"{API}/backtests/{backtest['id']}/trades", params={"limit": 500}).json()["items"]
)
trades["pnl"] = trades["pnl"].astype(float)
print(backtest["metrics"]["total_return_pct"], len(trades))
print(trades.groupby("exit_reason")["pnl"].agg(["count", "sum"]))
```

On the sample data it prints:

```text
16.0333683950737 15
             count          sum
exit_reason
signal           4  4238.876858
stop_loss       11 -2635.540018
```

## The command line

The backend has a small command-line tool. `make` runs it for you:

| Command | What it does |
|---|---|
| `make user email=you@example.com` | Creates the account (`python -m app.cli create-user`); it asks for the password, or reads it from stdin with `--password-stdin` |
| `make import-csv file=prices.csv symbol=BTCUSDT [timeframe=1m]` | Imports a price file of any size (`python -m app.cli import-csv`); add `--format` to name the format |
| `make openapi` | Writes the API's schema for the app's generated types |

Run `cd backend && uv run python -m app.cli --help` for every option.
