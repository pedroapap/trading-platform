# Use cases

Short recipes for what you can do with the app, grouped by theme. Each says what you want,
how to do it in the app, the API call where it helps, and what you get.

The examples use the sample prices from [Getting started](getting-started.md): a made-up
symbol, DEMOUSDT, with a strategy made from the **Double bottom after a dip** example. A few
use other markets. Each was run on a fresh database, and the numbers are the ones the app
returned. For the `curl` lines, set `$API` and `$AUTH` as in
[Logging in](api.md#logging-in).

**Themes:** [Recording trades](#recording-trades) · [Journaling](#journaling) ·
[Currencies](#currencies)

## Recording trades

### 1. Log a trade as you take it

You bought 100 DEMOUSDT at 95.50 on a double bottom, with a stop at 94.50 and a target at
97.50.

- **In the app:** **Trades** → **New trade**. Fill in the symbol `DEMOUSDT`, entry price
  `95.50`, size `100`, the entry time and an entry fee of `9.55`. Add the stop-loss `94.50`,
  the take-profit `97.50`, and the strategy you followed. Select **Log trade**.
- **API:** `POST /api/trades`.
- **You get:** an open trade in USDT, the currency guessed from the symbol. It is linked to
  the strategy's current version, and its history starts with an *entry* event. The stop and
  target are for your record: the app doesn't watch prices.

### 2. Close it, with the P&L net of fees

The target filled at 97.50, with a fee of 9.75.

- **In the app:** on the trade's page, open **Close trade**. Enter the exit price `97.50`, the
  exit time and the exit fee `9.75`, then select **Save exit**.
- **API:** `POST /api/trades/{id}/close`.
- **You get:** a P&L of **180.70 USDT**: (97.50 − 95.50) × 100 = 200.00, less 19.30 of fees.
  That is **1.89%** of the 9,550 USDT put in. See
  [How P&L is worked out](guide.md#how-pl-is-worked-out).

### 3. Cancel an order that never filled

You logged a limit buy at 97.60, and it expired without filling.

- **In the app:** on the trade's page, select **Cancel trade**, with the reason *The limit at
  97.60 never filled*.
- **API:** `POST /api/trades/{id}/cancel`, with an optional `reason`.
- **You get:** a *cancelled* trade with no P&L, left out of the analytics. Its history keeps
  the reason. A cancelled trade can't be closed later.

### 4. Fix a typo in an open trade

You logged a size of 10 instead of 100. The pages close, cancel and correct trades; an open
trade's details are changed through the API:

```sh
curl -s -X PATCH -H "$AUTH" -H 'Content-Type: application/json' \
  $API/trades/$TRADE -d '{"entry_size": "100"}' | jq .entry_size
```

You get `"100"`, and an *update* event in the history: entry size 10 → 100. A closed trade
can't be changed this way (409, *Cannot edit a closed trade*): correct it instead.

### 5. Correct a closed trade, with a reason

The broker's statement shows an exit fee of 10.10, not the 10.06 you logged.

- **In the app:** on the trade's page, open **Correct trade**. Enter the exit fee `10.10` and
  the reason *Fee from the broker statement*.
- **API:** `POST /api/trades/{id}/correct`, with the changed fields and a `reason`.
- **You get:** the P&L worked out again, from 220.12 to **220.08 USDT**. The reason is
  required. A correction that changes nothing records nothing.

### 6. Read a trade's history

- **In the app:** a trade's page ends with its **History**.
- **API:** `GET /api/trades/{id}/audit-log`.
- **You get:** every event, oldest first, with what it changed and why. For the trade in use
  cases 4 and 5:

| Event | What changed | Reason |
|---|---|---|
| entry | Logged at 98.20, size 10, fee 9.82 | |
| update | Entry size 10 → 100 | |
| exit | Closed at 100.60, fee 10.06, P&L 220.12 | |
| correction | Exit fee 10.06 → 10.10, P&L 220.12 → 220.08 | Fee from the broker statement |

The database refuses to change or delete these events.

### 7. Backfill trades from a broker's export

You have months of past trades in your broker's export. Put them in a CSV file with these
columns, one row per round trip, such as `fills.csv`:

```text
symbol,direction,size,entry_time,entry_price,entry_fee,exit_time,exit_price,exit_fee,strategy
DEMOUSDT,long,100,2025-04-27T08:20:00Z,95.25,9.53,2025-04-27T11:15:00Z,97.70,9.77,Double bottom after a dip
DEMOUSDT,long,100,2025-05-31T17:40:00Z,97.70,9.77,2025-05-31T20:30:00Z,100.20,10.02,Double bottom after a dip
DEMOUSDT,long,100,2025-06-01T12:10:00Z,98.95,9.90,2025-06-01T17:05:00Z,97.70,9.77,Double bottom after a dip
```

This script, with [requests](https://requests.readthedocs.io/), logs and closes each row at
its own times:

```python
import csv

import requests

API = "http://localhost:8000/api"
token = requests.post(
    f"{API}/auth/login", data={"username": "you@example.com", "password": "your password"}
).json()["access_token"]
session = requests.Session()
session.headers["Authorization"] = f"Bearer {token}"
strategies = {s["name"]: s["id"] for s in session.get(f"{API}/strategies").json()}

with open("fills.csv", newline="") as file:
    for row in csv.DictReader(file):
        trade = session.post(f"{API}/trades", json={
            "symbol": row["symbol"], "direction": row["direction"], "entry_size": row["size"],
            "entry_price": row["entry_price"], "entry_time": row["entry_time"],
            "entry_fee": row["entry_fee"], "strategy_id": strategies.get(row["strategy"]),
        })
        trade.raise_for_status()
        closed = session.post(f"{API}/trades/{trade.json()['id']}/close", json={
            "exit_price": row["exit_price"], "exit_time": row["exit_time"],
            "exit_fee": row["exit_fee"],
        })
        closed.raise_for_status()
        print(row["entry_time"], closed.json()["pnl"])
```

It prints each trade's P&L:

```text
2025-04-27T08:20:00Z 225.7
2025-05-31T17:40:00Z 230.21
2025-06-01T12:10:00Z -144.67
```

- **The columns:** `strategy` names one of your strategies, or is left empty. Times need a
  time zone: `Z` is UTC.
- **If the API refuses a row,** the script stops there with an HTTP error. A trade logged
  but not closed stays open, to close or cancel by hand.

### 8. A short

You sold 50 DEMOUSDT at 114.50 and bought them back at 110.90.

- **In the app:** a new trade with the direction `short`, entry price `114.50`, size `50`
  and fee `5.73`. Close it at `110.90`, with a fee of `5.55`.
- **You get:** **168.72 USDT**: (114.50 − 110.90) × 50 = 180.00, less 11.28 of fees. That is
  2.95% of the 5,725 USDT the position was worth at the entry.

### 9. A leveraged trade

You bought 300 DEMOUSDT at 104.20 at 5× leverage: a position of 31,260 USDT on 6,252 of your
own money.

- **In the app:** a new trade with the leverage `5`, entry fee `31.26`. Close it at `107.90`,
  with a fee of `32.37`.
- **You get:** **1,046.37 USDT**, and a return of **16.74%** on the 6,252 USDT of margin. On
  the whole position it is 3.35%. The analytics average that unleveraged return, so a
  leveraged trade doesn't outweigh the others. Leverage can't be under 1.

### 10. Find trades

- **In the app:** **Trades** filters by **Symbol** and **Status**, latest entry first.
- **API:** `GET /api/trades` also filters by strategy and entry time. Here, the strategy's
  trades entered from April to June:

```sh
curl -s -H "$AUTH" "$API/trades?strategy_id=$STRATEGY&entry_from=2025-04-01T00:00:00Z&entry_to=2025-07-01T00:00:00Z" \
  | jq -c '.items[] | {entry_time, pnl}'
```

```json
{"entry_time":"2025-06-01T12:10:00Z","pnl":"-144.67"}
{"entry_time":"2025-05-31T17:40:00Z","pnl":"230.21"}
{"entry_time":"2025-04-27T08:20:00Z","pnl":"225.7"}
```

## Journaling

### 11. Plan a trade before you take it

- **In the app:** **Journal** → **New journal entry**, type *Pre-trade*. Write your thesis,
  and under **Risk assessment** what you risk: *Stop at 94.50: 100 USDT at risk on 100 units.
  Target 97.50, twice the risk.* Pick the emotion *confident*, add the tag `double-bottom`,
  and select **Save draft**.
- **Then:** once you have logged the trade, edit the draft and pick it under **Trade**,
  which lists your 50 latest trades. A draft changes in place. Select **Publish** when it's
  complete.
- **You get:** a plan you can't quietly rewrite later, linked to the trade it led to. The
  journal list links each entry to its trade, and `GET /api/journal?trade_id=…` lists the
  entries about one trade.

### 12. Review a trade straight from its page

- **In the app:** on a closed trade's page, select **Write a journal entry about it**. The
  entry is already a *Post-trade* review of that trade. Write the lessons, such as *Waited for
  the second low. The limit filled, and the target came 2.5 hours later.*, pick the emotion,
  then **Save draft** and **Publish**.
- **You get:** the review beside the plan from use case 11, both linked to the same trade.

### 13. Keep market notes

- **In the app:** a new entry of type *Note*, with no trade. Use **Market context**: *DEMOUSDT
  stuck between 99 and 101 all week, on half of last month's volume.*
- **You get:** a dated note in the journal. Notes without a trade don't count in the
  analytics, which look at the journal entries of closed trades.

### 14. Record how you felt

Each entry has an optional **Emotion**: calm, confident, excited, greedy, fomo (fear of missing
out), fearful, frustrated, impatient or uncertain.

- **In the app:** the review of the losing 1 June trade says *Bought at 98.95 before the
  second low formed, afraid to miss the move*, with the emotion *fomo*.
- **Then:** filter the journal by **Emotion** to read every *fomo* entry. Analytics grouped
  by emotion shows how the trades behind each feeling did.
- **You get:** a record of feelings next to results, not just memories of them.

### 15. Tag your setups

- **In the app:** give entries tags such as `double-bottom`, `limit-entry` or `early-entry`,
  separated by commas.
- **The rules:** a tag is one word of letters, digits, `-` and `_`. Tags are stored in
  lowercase, and repeats are dropped: `Breakout, breakout, Watch_List` becomes `breakout,
  watch_list`.
- **You get:** a **Tag** filter on the journal list. Here, `double-bottom` finds the plan and
  both reviews. Analytics grouped by tag shows how each setup paid.

### 16. Draft, then publish

- **A draft** changes in place as often as you like, and has no versions.
- **Publish** makes it version 1. Publishing it again is refused (*The entry is already
  published*).
- **API:** `POST /api/journal`, `PATCH /api/journal/{id}`, then
  `POST /api/journal/{id}/publish`.

### 17. Read what you originally wrote

You add a plan for next time to a published review.

- **In the app:** edit the published entry. It asks for a **reason**, here *Added a plan for
  next time*, and saves the edit as version 2. Without a reason, the edit is refused.
- **You get:** the entry's history with both versions. Version 2 says it changed `lessons`,
  and why. Version 1 still reads *Waited for the second low. The limit filled, and the target
  came 2.5 hours later.*
- **API:** `GET /api/journal/{id}/versions`.

### 18. A weekly review

1. **Analytics:** set **Closed from** to 26 May 2025 and **Closed to (inclusive)** to 1 June.
   *Double bottom after a dip* shows 2 trades, 1 win and 1 loss, for **85.54 USDT**.
2. **Journal:** write a *Note* about the week, such as *one rule followed, one broken*, and tag
   it `weekly-review`.
3. **Later:** the tag filter `weekly-review` lists every week's review, newest first.

## Currencies

### 19. Trade in USDT, BTC and USD without mixing them

Besides the DEMOUSDT trades, you log two more:

- **ETHBTC:** bought 2 at 0.03850, sold at 0.03921. Its quote currency, BTC, is guessed from
  the name. P&L: **0.00126458 BTC**, after fees of 0.000077 and 0.00007842.
- **AAPL:** bought 20 at 212.40, sold at 216.85, with a fee of 1 each way. P&L: **87**, but in
  what? `AAPL` has no currency in its name, so it shows *currency not set*.

**You get:** money totalled per currency and never converted. Analytics shows one realized P&L
chart for BTC, one for USDT (1,927.11 over 7 trades, with a deepest fall of 144.67), and one
titled *Currency not set*, which warns that it may add up different currencies. Trade counts,
win rates and average returns in percent don't depend on a currency, so they cover every
trade at once.

### 20. Fix a missing or wrong currency

- **In the app:** **Instruments** lists every symbol and its currency. Type `USD` in AAPL's
  row and select **Save**.
- **API:** `PUT /api/instruments/{symbol}` with `{"quote_currency": "usd"}`. The code is
  stored in capitals, and must be 2 to 10 letters or digits.
- **You get:** every report updated at once. The AAPL trade is now in USD, and its 87 shows
  in a USD chart. A wrong guess is fixed the same way.

### 21. Set a currency before the first trade

You are about to trade Toyota's Tokyo listing, `7203.T`. Nothing in that name says yen, and
the Instruments page lists only symbols already in use. So register it first:

```sh
curl -s -X PUT -H "$AUTH" -H 'Content-Type: application/json' \
  $API/instruments/7203.T -d '{"quote_currency": "JPY"}'
```

**You get:** trades in JPY from the first one. Bought 100 at 2,650 and sold at 2,712: a P&L
of **6,200 JPY** (2.34%). Under *No strategy*, the analytics now show four totals side by
side: 0.00126458 BTC, 6,200 JPY, 87 USD and 1,215.09 USDT, from 5 trades with an average
return of 2.46%.
