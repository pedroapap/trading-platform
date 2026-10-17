# Use cases

Short recipes for what you can do with the app, grouped by theme. Each says what you want,
how to do it in the app, the API call where it helps, and what you get.

The examples use the sample prices from [Getting started](getting-started.md): a made-up
symbol, DEMOUSDT, with a strategy made from the **Double bottom after a dip** example. A few
use other markets. Each was run on a fresh database, and the numbers are the ones the app
returned. For the `curl` lines, set `$API` and `$AUTH` as in
[Logging in](api.md#logging-in).

**Themes:** [Recording trades](#recording-trades) · [Journaling](#journaling) ·
[Currencies](#currencies) · [Market data](#market-data) · [Strategies](#strategies) ·
[Backtesting](#backtesting) · [Day trading](#day-trading) · [Analytics](#analytics) ·
[Automation](#automation) · [Owning your data](#owning-your-data)

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

## Market data

### 22. Import Binance's own files

Binance publishes the history of every pair at `data.binance.vision`, one zip file per month.
For Bitcoin's 1-minute bars of January 2024:

```sh
curl -O https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip
curl -O https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip.CHECKSUM
sha256sum -c BTCUSDT-1m-2024-01.zip.CHECKSUM
unzip BTCUSDT-1m-2024-01.zip
```

- **In the app:** on **Market data**, choose `BTCUSDT-1m-2024-01.csv`, type the symbol
  `BTCUSDT` and select **Import**.
- **You get:** *BTCUSDT 1m (binance_klines): 44,640 bars added, 0 already stored, 0
  rejected*, from 1 January 00:00 to 31 January 23:59 UTC. The format and the timeframe are
  worked out from the file.
- **Times:** Binance's files give times in milliseconds up to 2024, and in microseconds from
  January 2025. The app reads both: June 2025 adds 43,200 bars.

### 23. Import a Yahoo Finance or TradingView export

Both are CSV files with a header row, which the app reads as *OHLCV with a header row*. Here
are three days in Yahoo Finance's layout, with made-up prices for a made-up symbol, ACME:

```text
Date,Open,High,Low,Close,Adj Close,Volume
2025-03-03,101.20,102.85,100.90,102.40,101.95,1250300
2025-03-04,102.40,103.10,101.75,102.05,101.60,1102800
2025-03-05,102.05,104.30,101.95,104.10,103.64,1530200
```

Imported as `ACME`, it adds 3 daily bars: the timeframe comes from their spacing. Extra
columns such as `Adj Close` are ignored, so the bars hold the Open, High, Low and Close as
they are.

TradingView's chart export can give times as Unix seconds:

```text
time,open,high,low,close,Volume
1741010400,102.10,102.60,101.90,102.45,84120
1741014000,102.45,102.80,102.20,102.30,61900
1741017600,102.30,102.55,101.80,101.95,70350
```

It adds 3 hourly bars, from 14:00 to 16:00 UTC on 3 March 2025. ACME's name holds no currency,
so set it on **Instruments** ([use case 20](#20-fix-a-missing-or-wrong-currency)).

### 24. Import the same file twice, or files that overlap

Importing the sample file a second time gives *0 bars added, 8,760 already stored, 0
rejected*. Bars already stored, for the same symbol, timeframe and time, are kept as they were.
So you can import overlapping downloads, such as a month's file again once it is complete.

### 25. Find the bad rows in a file

A made-up file with four problems in it:

```text
timestamp,open,high,low,close,volume
2025-03-10T00:00:00Z,100.0,101.0,99.0,100.5,10
2025-03-10T01:00:00Z,100.5,100.2,99.8,100.1,12
2025-03-10T02:07:00Z,100.1,100.6,99.9,100.4,9
2025-03-10T03:00:00Z,100.4,100.9,100.2,100.8,15
2025-03-10T03:00:00Z,100.8,101.0,100.5,100.9,8
2025-03-10T04:00:00Z,100.9,101.4,100.7,101.2,-3
2025-03-10T05:00:00Z,101.2,101.5,100.9,101.1,11
```

**You get:** 3 bars added and 4 rows rejected, each with its line in the file and the reason:

| Line | Reason |
|---|---|
| 3 | low/high do not bracket open and close |
| 4 | 2025-03-10T02:07:00+00:00 is not the start of a 1h bar |
| 6 | duplicate of the bar on line 5 |
| 7 | volume cannot be negative |

The good rows are stored. Fix the others and import the file again: the rows already stored
count as such.

### 26. Import a big file from the command line

The web form takes files up to 200 MB. The command line takes any size, and suits many
files. The sample's 1-minute file comes from its generator:

```sh
python docs/sample-data/generate.py --minutes
make import-csv file=docs/sample-data/demousdt-1m.csv symbol=DEMOUSDT
```

**You get:** *Imported 525600 1m bars for DEMOUSDT (generic_ohlcv): 0 already stored, 0 rows
rejected*, in about 25 seconds here. The 1-minute bars make up the hourly ones exactly. With
them, the backtests below run on 5-minute bars, and settle fills inside hourly bars.

For many files, such as Binance's months, import them one after another:

```sh
for file in BTCUSDT-1m-*.csv; do make import-csv file=$file symbol=BTCUSDT; done
```

### 27. Use bigger bars without importing them

A backtest or the API can ask for any timeframe the stored bars divide into:

```sh
curl -s -H "$AUTH" "$API/market-data/DEMOUSDT/bars?timeframe=1d&limit=1" | jq -c '{aggregated_from, bars}'
```

```json
{"aggregated_from":"1h","bars":[{"ts":"2025-01-01T00:00:00Z","open":"100","high":"100.78","low":"95.63","close":"95.65","volume":"14124.4068"}]}
```

The daily bar is built from the stored hourly bars, the biggest stored size that divides a
day. With the 1-minute file stored too, 5-minute bars are built from it
(`"aggregated_from":"1m"`).

### 28. Symbols with a slash

Exchanges often write pairs as `BTC/USDT`. Imported as `demo/usdt`, the sample is stored as
`DEMO/USDT`, and its currency, USDT, is guessed from the name. In API paths, write the slash
as `%2F`:

```sh
curl -s -H "$AUTH" "$API/market-data/DEMO%2FUSDT/bars?timeframe=1d&limit=1" | jq .symbol
```

This prints `"DEMO/USDT"`.

### 29. See what is stored

- **In the app:** **Market data** lists the **Stored bars**: each symbol and timeframe with
  its first and last bar and its count.
- **API:** `GET /api/market-data/symbols`.
- **You get,** after the imports above (times in UTC):

| Symbol | Timeframe | First bar | Last bar | Bars |
|---|---|---|---|---|
| ACME | 1h | 2025-03-03 14:00 | 2025-03-10 05:00 | 6 |
| ACME | 1d | 2025-03-03 | 2025-03-05 | 3 |
| BTCUSDT | 1m | 2024-01-01 00:00 | 2025-06-30 23:59 | 87,840 |
| DEMO/USDT | 1h | 2025-01-01 00:00 | 2025-12-31 23:00 | 8,760 |
| DEMOUSDT | 1m | 2025-01-01 00:00 | 2025-12-31 23:59 | 525,600 |
| DEMOUSDT | 1h | 2025-01-01 00:00 | 2025-12-31 23:00 | 8,760 |

Gaps don't show here: BTCUSDT's two months are counted as one stretch.

## Strategies

### 30. Start from an example

- **In the app:** **Strategies** → **New strategy** → **Start from an example**. Six examples
  each say what they do in words: *Double bottom after a dip*, *Breakout with a stop entry*,
  *Trend with an ATR trailing stop*, *RSI dip*, *Opening-range breakout (New York)* and *VWAP
  pullback in a daily uptrend*. Choosing one fills in the definition. Name it and select
  **Create strategy**.
- **You get:** a working strategy to backtest at once, and to change.

### 31. Try the cookbook on the sample prices

[The rule language](rules.md#cookbook) ends with 12 recipes. Each was saved as a strategy and
backtested on DEMOUSDT with the tour's settings: 10,000 USDT, a 0.1% fee and 0.05% slippage,
on 1h bars, or on 5-minute bars with 1-minute fills for the two day-trading recipes. Buying and
holding made 2.06%.

| Recipe | Trades | Return | Max drawdown | Win rate |
|---|---|---|---|---|
| Double bottom after a dip | 14 | +14.48% | 3.74% | 64.29% |
| RSI dip | 73 | +35.69% | 22.48% | 38.36% |
| Breakout with a stop entry | 70 | −48.54% | 51.42% | 25.71% |
| Trend with an ATR trailing stop | 243 | −49.80% | 54.04% | 24.28% |
| Dip to the moving average | 1 | +6.05% | 23.02% | 100.00% |
| Golden cross | 33 | −47.31% | 53.51% | 27.27% |
| MACD with a trend filter | 181 | −60.06% | 60.84% | 24.86% |
| Bollinger dip in an uptrend | 56 | −9.41% | 21.61% | 66.07% |
| Double top, short | 117 | −15.44% | 29.15% | 35.90% |
| Buy the first new low in a while | 2 | −4.61% | 5.03% | 50.00% |
| Opening-range breakout (New York) | 300 | −54.93% | 55.35% | 33.33% |
| VWAP pullback in a daily uptrend | 780 | −93.42% | 93.43% | 25.90% |

The prices are made up, so this says nothing about the recipes on a real market. It does
show why you test:

- **Most rules lose after costs.** 9 of the 12 lost money.
- **The winners have reasons.** The double bottoms were planted. The made-up price keeps
  being pulled back toward a level, which suits a dip buyer such as the RSI dip, and is hard
  on trend followers.
- **One trade proves nothing.** The dip to the moving average bought once and held to the
  end.

### 32. Get told exactly what's wrong

When you save a definition, the app checks it and lists each problem at its place:

- **An RSI with a period of 0:** `entry.left.period` *Input should be greater than or equal
  to 2*.
- **A word where arithmetic needs a number:** `entry.right.multiply[1].value` *Input should
  be a valid number, unable to parse string as a number*.
- **No way out at all:** a problem with the whole strategy, so it has no place: *a strategy
  needs a way out: an exit rule, a stop-loss, a take-profit, a trailing stop, exit_after_bars
  or flat_at*.

Nothing is saved until the definition is valid.

### 33. Buy at a price, with the stop at a level

The double-bottom example doesn't buy at the market. It places a limit order 0.3% above the
latest swing low, which works for 6 bars. Its stop is 1% under that low, and its target is at
twice the risk (`"take_profit_r": 2`). On the sample, 9 of its 14 trades reached the target
and 5 the stop. See [Entry orders](rules.md#entry-orders).

### 34. Let a winner run with a trailing stop

*Trend with an ATR trailing stop* trails its stop 3 ATRs under the 22-bar high, so the stop
rises with the price and never falls. On the sample, 242 of its 243 trades ended at the
trailing stop, and the last was still open at the end of the data. It lost 49.80%: the
made-up price keeps turning back, which is hard on trend followers.

### 35. Get out after a set time

`"exit_after_bars": 24` leaves at the open 24 bars after the entry, unless something exits
first. *Buy the first new low in a while* holds for 24 bars, with a 5% stop as a backstop.
Both its trades on the sample ended on time (`time_exit`).

### 36. Exit only by a stop or a target

A strategy needs no exit rule if a stop or a target can close its trades. *Breakout with a
stop entry* has a stop under the 10-bar low and a target at twice the risk. On the sample, 52
trades ended at the stop and 17 at the target, and one was still open at the end of the data.

### 37. Trade the short side

`"direction": "short"` sells first and buys back later. *Double top, short* mirrors the
double bottom: 117 trades on the sample, of which 74 were stopped out and 42 reached the
target, for −15.44%.

### 38. Combine conditions

`all`, `any` and `not` nest. This buys on an RSI dip or a close under the lower Bollinger
band, but not while the 50-bar average is under the 200-bar one:

```json strategy
{
  "direction": "long",
  "entry": {"all": [
    {"any": [
      {"left": {"indicator": "rsi", "period": 14}, "op": "<", "right": {"value": 30}},
      {"left": {"price": "close"}, "op": "<", "right": {"indicator": "bbands", "period": 20, "std": 2, "output": "lower"}}
    ]},
    {"not": {"left": {"indicator": "sma", "period": 50}, "op": "<", "right": {"indicator": "sma", "period": 200}}}
  ]},
  "exit": {"left": {"indicator": "rsi", "period": 14}, "op": ">", "right": {"value": 60}},
  "stop_loss_pct": 3
}
```

On the sample: 83 trades and −16.99%. 52 left on the exit rule and 31 at the stop.

### 39. React to something that happened recently

`happened` asks whether a rule held within the last bars. The double bottom's first condition
is one: the 50-bar average crossed below 100 within the last 48 bars. With `times`, it counts
separate occasions, such as a low at or under a line twice. See
[`happened`](rules.md#happened-did-it-happen-recently).

### 40. Change a strategy without losing old results

- **In the app:** on the strategy's page, select **Edit strategy**, change
  `"take_profit_r": 2` to `3`, and select **Save changes**.
- **You get:** version 2, recorded as *changed take_profit_r*. Version 1 can't change, so its
  backtests stay as they were. Run version 1 again at any time: it gives the same 14 trades
  and +14.48%, from the same data fingerprint.

## Backtesting

These use the tour's settings unless said otherwise: DEMOUSDT's 1h bars, 10,000 USDT with all
of it in each trade, a 0.1% fee and 0.05% slippage.

### 41. Compare two versions on the same bars

| | Version 1, target at 2R | Version 2, target at 3R |
|---|---|---|
| Trades | 14 | 12 |
| Return | +14.48% | +13.16% |
| Max drawdown | 3.74% | 5.98% |
| Win rate | 64.29% | 50.00% |
| Exits | 9 at the target, 5 at the stop | 6 at the target, 6 at the stop |

The **Backtests** page lists both runs with their versions. The bigger target won more per
win, but less often.

### 42. Stress-test the costs

Version 1 at four levels of costs:

| Fee | Slippage | Return | Profit factor | Buy and hold |
|---|---|---|---|---|
| 0% | 0% | +18.03% | 3.47 | +2.37% |
| 0.1% | 0.05% | +14.48% | 2.69 | +2.06% |
| 0.2% | 0.1% | +11.04% | 2.13 | +1.76% |
| 0.5% | 0.25% | +1.33% | 1.10 | +0.85% |

Buy and hold pays the same costs, once in and once out. A rule that trades often needs an
edge well above its costs.

### 43. Size positions, and borrow

| Position size | Return | Max drawdown |
|---|---|---|
| 50% | +7.08% | 1.88% |
| 100% | +14.48% | 3.74% |
| 300% | +47.36% | 10.96% |

Over 100% borrows the rest, with no interest charged: returns and drawdowns grow together.
[Use case 58](#58-leverage-and-margin-calls) shows where that ends.

### 44. Hold out the latest months

Set **Out-of-sample from** to 1 October 2025, and the run reports both sides apart:

| | In-sample, to September | Out-of-sample, from October |
|---|---|---|
| Trades | 12 | 2 |
| Return | +13.57% | +0.81% |
| Buy and hold | +3.41% | −1.60% |
| Max drawdown | 3.00% | 2.32% |

Both sides are marked as too few trades to judge.

### 45. Beat buy and hold, or not

Each results page shows buy and hold under the return, CAGR and drawdown, and as a second line
on the chart. The double bottom made +14.48% against +2.06%, with a deepest fall of 3.74%
against 23.02%. The RSI dip on 5-minute bars lost 83.64% against the same +2.06%.

### 46. Settle fills inside hourly bars with 1-minute bars

An hourly bar doesn't say whether it reached its high or its low first. When a bar reaches
both a trade's stop and its target, the stop counts, unless finer bars settle it.

- **Example:** an RSI dip with a 0.5% stop, a 0.5% target and no exit rule. With **Finer
  bars for fills** set to 1m, one of its 204 trades ended differently. Its last bar, at 22:00
  on 28 April 2025, reached both levels. The worst case counted the stop (−57.77 USDT); the
  1-minute bars show that the target came first (+23.09 USDT). The return went from −36.30%
  to −35.63%. Later trades changed only because they started from a different equity.
- **The cookbook's rules** didn't change on the sample: their stops and targets lie further
  apart than an hour's range.

### 47. Run one rule at 5m to 1d

The RSI dip on bars built from the same stored prices:

| Bars | Trades | Return | Max drawdown |
|---|---|---|---|
| 5m | 648 | −83.64% | 84.44% |
| 15m | 138 | +23.61% | 23.14% |
| 1h | 73 | +35.69% | 22.48% |
| 4h | 15 | +16.03% | 16.14% |
| 1d | 0 | 0.00% | 0.00% |

The same rule is a different strategy on each timeframe. At 5 minutes it trades 648 times,
each round trip paying about 0.3% of costs. On daily bars, RSI never fell under 30.

### 48. Know when there are too few trades

- **Under 30 trades,** the results page warns: *Too few trades to judge. With 14 trades,
  under 30, results like these can come from luck alone.* Each side of a split is marked the
  same way: *⚠ 12, too few to judge*.
- **The average trade** comes with its 95% range: the double bottom's 0.99% ranges from
  −0.03% to 2.01%.
- **A range that spans zero** means the run can't tell an edge from luck. Even the RSI dip's
  73 trades average 0.48%, with a range from −0.34% to 1.30%.

### 49. Test a short period

From 1 March to 1 April 2025 (744 bars), the double bottom made 2 trades and +4.83%. A month
says little about a year, so CAGR, Sharpe and Sortino show *—*, with the note *Not
annualized: under 90 days of data*.

### 50. Stocks or crypto: periods per year

**Periods per year** scales the Sharpe and Sortino ratios: 365 for markets that trade every
day, 252 for stock exchanges. The RSI dip's Sharpe ratio is 1.27 at 365 and 1.05 at 252.
Only those two ratios change.

### 51. Read every simulated trade

The results page lists every trade: its entry and exit time and price, size, fees, slippage,
P&L, and why it ended. `GET /api/backtests/{id}/trades` gives the same, and
[the API page](api.md#from-python) loads them into pandas.

### 52. Check that two runs saw the same data

Each run records a fingerprint of the bars it read, and its settings show the first 12
characters.

- **The same data:** running version 1 again gave the same fingerprint, `26cc79108572`, and
  the same results.
- **Other data:** with 1-minute fills it is `3ac0a18b572b`, since the finer bars count too.
  Each timeframe has its own.

The same fingerprint, version and settings give the same results.

## Day trading

These run on the sample's 5-minute bars, built from the 1-minute file
([use case 26](#26-import-a-big-file-from-the-command-line)), with 1-minute fills and the
tour's costs. DEMOUSDT trades around the clock, like crypto, so a New York session uses only
part of each day.

### 53. Trade only during New York hours

- **A session** gives the market's hours in its own time zone, daylight saving included:
  `"session": {"timezone": "America/New_York", "start": "09:30", "end": "16:00"}`. Outside
  it, no entry fills.
- **A time window** narrows entries to part of the day: `{"time": ["10:00", "12:00"]}`.

The opening-range example has both. See [Sessions](rules.md#sessions-and-the-trading-day).

### 54. Be out by 15:55 every day

`"flat_at": "15:55"`: no entry fills from 15:55 to the end of the day, and a position still
open leaves at the open of the 15:55 bar, with the reason `end_of_day`. In the opening-range
breakout below, 44 of 300 trades ended that way.

### 55. An opening-range breakout

*Opening-range breakout (New York)*: from 10:00 to 12:00, a buy stop at the high of the first
30 minutes, with the stop at their low and the target at twice the risk. On the sample: 300
trades and −54.93%. 185 were stopped out, 71 reached the target and 44 left at 15:55.

### 56. A VWAP pullback with a daily trend filter

*VWAP pullback in a daily uptrend*: when yesterday's daily close is above its 20-day average,
read with `{"timeframe": "1d", "of": …}`, and the close is above VWAP, it places a limit buy at
VWAP. It has a 0.5% stop and a 1% target, and is out by 23:55 UTC. On the sample: 780 trades
and −93.42%. 563 were stopped out, 192 reached the target and 25 left at 23:55.

### 57. A breakout of yesterday's high

`{"indicator": "day", "output": "high", "days_ago": 1}` is yesterday's high. This places a buy
stop there in a daily uptrend, with the stop at VWAP and the target at twice the risk:

```json strategy
{
  "direction": "long",
  "entry": {"all": [
    {"left": {"timeframe": "1d", "of": {"price": "close"}}, "op": ">", "right": {"timeframe": "1d", "of": {"indicator": "sma", "period": 20}}},
    {"left": {"price": "close"}, "op": "<", "right": {"indicator": "day", "output": "high", "days_ago": 1}}
  ]},
  "entry_order": {"type": "stop", "price": {"indicator": "day", "output": "high", "days_ago": 1}, "expires_after": 1},
  "stop_loss_at": {"indicator": "vwap"},
  "take_profit_r": 2,
  "flat_at": "23:55"
}
```

On the sample: 262 trades and −62.01%. 198 were stopped out, 41 reached the target and 23 left
at 23:55.

### 58. Leverage, and margin calls

The RSI dip without its stop, at three position sizes, on 1h bars:

| Position size | Trades | Return | Max drawdown |
|---|---|---|---|
| 100% | 32 | +63.57% | 16.87% |
| 400% | 32 | +401.03% | 63.04% |
| 1,000% | 6 | −103.78% | 101.09% |

At 10×, a 10% fall uses up the equity. The sixth trade bought at 110.55 on 22 February and
was closed by a margin call at 99.54 on 25 February, losing 28,401.37 USDT of the 28,023.18
the account held. Like a stop, the call filled with slippage and paid the exit fee, so the
account ended 378.19 USDT below zero, and no trade followed. Borrowing costs aren't modelled.

### 59. Day trade Bitcoin on real prices

1. **Download** Binance's monthly BTCUSDT files as in
   [use case 22](#22-import-binances-own-files). From January 2022 to September 2026, that is
   57 files.
2. **Import** them with the loop in [use case 26](#26-import-a-big-file-from-the-command-line):
   about 2.5 million bars, in about 4 minutes.
3. **Test** a day-trading rule on 5-minute bars, with **Finer bars for fills** set to 1m and
   an out-of-sample start, such as 1 January 2024.

## Analytics

These use the trades and journal entries of use cases 1–21. **Analytics** counts closed trades
only, and ranks groups by their average return, best first.

### 60. See which strategy pays

- **In the app:** **Analytics**, grouped by **Strategy**.
- **API:** `GET /api/analytics/performance?by=strategy`.
- **You get:**

| Strategy | Trades | Wins | Losses | Win rate | Average return | P&L |
|---|---|---|---|---|---|---|
| No strategy | 5 | 5 | 0 | 100.00% | 2.46% | 0.00126458 BTC, 6,200 JPY, 87 USD, 1,215.09 USDT |
| Double bottom after a dip | 5 | 4 | 1 | 80.00% | 1.48% | 712.02 USDT |

### 61. See which symbol pays

Grouped by **Symbol**: 7203.T made 2.34% on its one trade, AAPL 2.05% and ETHBTC 1.64%.
DEMOUSDT's 7 trades won 6 times, for 1,927.11 USDT and an average return of 1.96%.

### 62. See how your feelings pay

Grouped by **Emotion**, each trade counts once for each emotion its journal entries record:

| Emotion | Trades | P&L |
|---|---|---|
| calm | 1 | 180.70 USDT |
| confident | 1 | 180.70 USDT |
| fomo | 1 | −144.67 USDT |
| No emotion | 8 | the other trades |

The 10 January trade counts twice: its plan said *confident*, and its review *calm*. The trade
taken out of fear of missing out is the one loser.

### 63. Only the feelings you had before the trade

How you felt afterwards is colored by the result. To see only the feelings you wrote down
beforehand, set **Journal entries** to *Pre-trade*: only *confident* is left, with its one
trade. *Post-trade* keeps *calm* and *fomo*.

### 64. See which setup pays

Grouped by **Tag**: `limit-entry` has 1 trade and +180.70 USDT, `early-entry` 1 trade and
−144.67 USDT, and `double-bottom` both of them, for +36.03 USDT. The tags came from the plan
and the reviews of use cases 11 to 15.

### 65. Review a month or a quarter

Set **Closed from** to 1 April 2025 and **Closed to (inclusive)** to 30 June:

- **Double bottom after a dip:** 3 trades, 2 wins, +311.24 USDT.
- **No strategy:** 3 trades, all wins: 87 USD from AAPL, 6,200 JPY from 7203.T and
  1,046.37 USDT from the 5× trade.
- **Realized P&L:** 1,357.61 USDT over 4 trades with a deepest fall of 144.67, then 87 USD and
  6,200 JPY.

Both dates are kept in the page's address, so a bookmark brings the same quarter back.

### 66. Follow realized P&L and drawdown per currency

**Realized P&L** draws one curve per currency: each trade's P&L added up in the order the
trades closed.

- **All trades:** 1,927.11 USDT over 7 trades, with a deepest fall of 144.67 (the 1 June
  loss), plus 0.00126458 BTC, 87 USD and 6,200 JPY.
- **Filtered** by the symbol DEMOUSDT and the double-bottom strategy: 712.02 USDT over 5
  trades.
- **The points** are evenly spaced, one per trade, not to scale in time. Point at one, or open
  the table, for its date.

### 67. Is live trading matching its backtest?

Open a completed backtest. Under **Backtest and live**, the live trades of the same strategy
version and symbol, entered within the backtest's bars, sit beside the backtest's own:

| | Backtest | Live |
|---|---|---|
| Trades | 14 | 5 |
| Win rate | 64.29% | 80.00% |
| Average return on notional | 0.99% | 1.48% |
| Total P&L | 1,448.42 USDT | 712.02 USDT |

The cancelled trade doesn't count. A backtest of version 2 shows no live trades, since they
all followed version 1. API: `GET /api/analytics/backtests/{id}/comparison`.

### 68. Why returns are on the position's value

The 5× trade made 16.74% on its margin, but 3.35% on the position's value. The analytics
average the return on the position's value (its *notional*): under *No strategy*, 2.46%.
Averaging the returns on margin would give 5.14%, so one leveraged trade would count five
times over. The money totals are the real P&L either way.

## Automation

### 69. Explore the API in your browser

<http://localhost:8000/api/docs> lists every endpoint with its fields. Select **Authorize**
and log in with your email and password, then select an endpoint and **Try it out**. The
schema itself is at `/api/openapi.json`. [Automating with the API](api.md) has curl and
Python examples.

### 70. Run a sweep of backtests from the shell

The app runs one backtest at a time, but a script can run many. This one saves the RSI dip
at four levels as four strategies, and backtests each:

```sh
DEFINITION=$(curl -s -H "$AUTH" $API/strategies | jq '.[] | select(.name == "RSI dip") | .definition')
for level in 20 25 30 35; do
  STRATEGY=$(curl -s -H "$AUTH" -H 'Content-Type: application/json' $API/strategies -d '{
    "name": "RSI under '$level'",
    "definition": '"$(echo "$DEFINITION" | jq --argjson level $level '.entry.right.value = $level')"'
  }' | jq -r .id)
  RUN=$(curl -s -H "$AUTH" -H 'Content-Type: application/json' $API/backtests -d '{
    "strategy_id": "'$STRATEGY'", "symbol": "DEMOUSDT", "timeframe": "1h",
    "fee_pct": "0.1", "slippage_pct": "0.05"
  }' | jq -r .id)
  until curl -s -H "$AUTH" $API/backtests/$RUN | jq -e '.status | test("completed|failed")' >/dev/null; do sleep 1; done
  curl -s -H "$AUTH" $API/backtests/$RUN | jq -r --arg level $level \
    '"RSI under \($level): \(.metrics.num_trades) trades, \(.metrics.total_return_pct * 100 | round / 100)%"'
done
```

```text
RSI under 20: 5 trades, 1.63%
RSI under 25: 32 trades, 25.23%
RSI under 30: 73 trades, 35.69%
RSI under 35: 113 trades, 52.81%
```

The best of a sweep on the same bars flatters itself: it was picked because it did well there.
Check the pick on bars it wasn't picked on, with an out-of-sample start
([use case 44](#44-hold-out-the-latest-months)).

### 71. Analyse your trades in pandas

How long do you hold winners and losers? With [pandas](https://pandas.pydata.org/) and
requests:

```python
import pandas as pd
import requests

API = "http://localhost:8000/api"
token = requests.post(
    f"{API}/auth/login", data={"username": "you@example.com", "password": "your password"}
).json()["access_token"]
response = requests.get(
    f"{API}/trades", params={"status": "closed", "limit": 500},
    headers={"Authorization": f"Bearer {token}"},
)
trades = pd.DataFrame(response.json()["items"])
trades["held"] = pd.to_datetime(trades["exit_time"]) - pd.to_datetime(trades["entry_time"])
trades["result"] = trades["pnl"].astype(float).gt(0).map({True: "win", False: "loss"})
print(trades.groupby("result")["held"].agg(["count", "median", "max"]))
```

```text
        count          median             max
result
loss        1 0 days 04:55:00 0 days 04:55:00
win         9 0 days 04:40:00 2 days 06:00:00
```

### 72. Ask the database with SQL

`make db-shell` opens `psql` on the app's database. The tables are described in
[The data model](schema.md). P&L per month and currency:

```sql
SELECT to_char(t.exit_time, 'YYYY-MM') AS month, i.quote_currency, count(*) AS trades, sum(t.pnl) AS pnl
FROM trades t JOIN instruments i USING (symbol)
WHERE t.status = 'closed'
GROUP BY 1, 2 ORDER BY 1, 2;
```

```text
  month  | quote_currency | trades |        pnl
---------+----------------+--------+-------------------
 2025-01 | USDT           |      1 |  180.700000000000
 2025-02 | USDT           |      1 |  220.080000000000
 2025-03 | BTC            |      1 |    0.001264580000
 2025-04 | USDT           |      1 |  225.700000000000
 2025-05 | USD            |      1 |   87.000000000000
 2025-05 | USDT           |      1 |  230.210000000000
 2025-06 | JPY            |      1 | 6200.000000000000
 2025-06 | USDT           |      2 |  901.700000000000
 2025-07 | USDT           |      1 |  168.720000000000
```

Reading is safe. The database refuses to rewrite history (see
[What can't be changed or deleted](schema.md#what-cant-be-changed-or-deleted)), but other
changes made here skip the app's checks.

## Owning your data

### 73. Keep everything on your own machine

- **What runs:** three containers, started by `make dev`: the database (TimescaleDB, port
  5432), the API (8000) and the app's pages (5173).
- **Where the data is:** in a Docker volume named after the app's folder, such as
  `trading-platform_pgdata`.
- **What leaves:** nothing. The app calls no outside service, and prices come only from the
  files you import.
- **Stopping:** `make down` stops the containers and keeps the data. `docker compose down -v`
  deletes the volume, and everything in it.

### 74. Back up, and restore

```sh
make backup
```

It prints *Saved backups/backup-20261017-100755.dump*: here 10 MB in under 3 seconds, for a
database holding 630,969 bars and 53 backtests. `pg_dump` warns about circular foreign keys in
TimescaleDB's own tables; that is expected.

```sh
make restore file=backups/backup-20261017-100755.dump
```

- **What it does:** it stops the API and replaces the database with the backup, wrapping the
  restore in the steps TimescaleDB needs. Start the app again with `make dev`.
- **Checked:** restored into a new database, every table came back with the same rows. That
  includes the bars in 15 compressed chunks, their compression settings and schedule, and the
  triggers that keep history from being rewritten. The app on it showed the same analytics,
  and a new backtest found the same data fingerprint.
- **Keep copies elsewhere:** the backups are in the `backups` folder, on the same disk as the
  database. Restore with the same version of the app.

### 75. Use it from your phone

The pages fit a phone's screen. While `make dev` runs, they answer on every network address of
your computer. On the same Wi-Fi, open `http://` followed by your computer's IP address and
`:5173`, such as `http://192.168.1.20:5173`, on the phone. Use the address: the development
server refuses the computer's name.

Anyone on that network can reach the login page, so use a strong password. Away from home,
use a VPN to your network rather than opening the port to the internet.
