# User guide

What each part of the app does, what every field means, and the rules behind them. For a
first walk through, see [Getting started](getting-started.md).

The menu leads to seven pages: **Trades**, **Journal**, **Strategies**, **Backtests**,
**Analytics**, **Market data** and **Instruments**. **Log out** is at its end.

The app shows times in your browser's time zone. Times you type into forms are read in that
time zone too, and stored in UTC.

## Your account

The app is for one person. The account is created on the command line:

```sh
make user email=you@example.com
```

The password must be 12 to 128 characters. Logging in keeps you signed in for 7 days on that
browser, until you log out. Each account sees only its own trades, journal, strategies and
backtests. Market data and instruments are shared, since prices are the same for everyone.

## Trades

**Trades** is your record of the trades you actually made. Prices are what you type, and
nothing is fetched from a broker.

### Logging a trade

Select **New trade** and fill in:

| Field | Rules |
|---|---|
| **Symbol** | 1 to 20 characters: letters, digits and `. _ : / -`, stored in capitals (`btc/usdt` becomes `BTC/USDT`) |
| **Direction** | `long` (bought first) or `short` (sold first) |
| **Entry price**, **Size** | Above 0, with up to 12 decimals |
| **Entry time** | When you entered |
| **Entry fee** | 0 or more, in the quote currency. Optional |
| **Stop-loss**, **Take-profit** | The levels you planned, above 0. Optional, for your record |
| **Leverage** | 1 or more, 1 by default |
| **Strategy** | One of your strategies, if the trade followed one |
| **Strategy version** | The version it followed. Left empty, it is the strategy's current version |

Select **Log trade**. A trade starts *open*. A new symbol is added to
[Instruments](#instruments-and-currencies), with its quote currency guessed from its name.

### Closing it

On an open trade's page, open **Close trade** and fill in:

- **Exit price** and **Exit time**. The exit can't be before the entry.
- **Exit size**: left empty, it is the whole position. It can be less, but not more.
- **Exit fee**: optional.

Then select **Save exit**. The trade becomes *closed*, with its P&L worked out as below.

### Cancelling an order that never filled

**Cancel trade** marks an open trade as *cancelled*, with an optional reason (*Why it never
happened*). Cancelled trades have no P&L and are left out of the analytics.

### Correcting a closed trade

A closed trade can be fixed with **Correct trade**.

- **What can change:** any of its fields, entry and exit alike.
- **A reason is required**, 3 to 500 characters.
- **Checks:** the exit is checked again, so it can't be before the entry or larger than the
  position, and the P&L is worked out again.
- **The record:** only the fields that changed are recorded, with your reason. A correction
  that changes nothing records nothing.

To change an open trade's details, use the API (`PATCH /api/trades/{id}`). The app's own pages
close, cancel and correct.

### A trade's history

Each trade's page ends with its **History**: every event (entered, updated, closed, cancelled,
corrected), when it happened, what changed from what to what, and the reason given. The
database refuses to change or delete this history.

### The trades list

**Trades** lists your trades, the most recently entered first, 50 to a page. Filter it by
**Symbol** and **Status** (open, closed or cancelled). Each row shows the P&L in the trade's
quote currency.

### How P&L is worked out

For a long, P&L is (exit price − entry price) × exit size, less both fees. A short is the other
way round: (entry price − exit price) × exit size, less both fees.

- **Return on margin** is that P&L as a percentage of the money committed: the entry price ×
  the size ÷ the leverage. At 5× leverage, a 1% move is about a 5% return.
- **Precision:** amounts are exact decimals, kept to 12 places.

## Journal

The journal is where you write about your trading: plans before a trade, reviews after it,
and notes about the market.

### Writing an entry

Select **New journal entry**, or **Write a journal entry about it** on a trade's page, which
links the trade and makes the entry a post-trade review.

| Field | What it holds |
|---|---|
| **Type** | Pre-trade (a plan), Post-trade (a review) or Note |
| **Trade** | One of your trades. Optional |
| **Emotion** | How you felt: calm, confident, excited, greedy, fomo (fear of missing out), fearful, frustrated, impatient or uncertain. Optional |
| **Title** | Required, up to 200 characters |
| **Thesis**, **Market context**, **Risk assessment**, **Lessons** | Free text, up to 10,000 characters each. Optional |
| **Tags, separated by commas** | Up to 20 tags. A tag is one word of letters, digits, `-` and `_`, up to 50 characters, stored in lowercase. Repeats are dropped |

### Drafts, publishing and versions

- **Save draft:** a new entry is a *draft*, which you can edit freely.
- **Publish:** the entry becomes version 1, a snapshot that can't be changed.
- **Editing it later:** a published entry can still be edited, but each edit needs a
  **reason** and is saved as the next version (**Save as version 2**). An edit that changes
  nothing is refused.
- **History:** the entry's page lists every version with the fields it changed and its reason.
  Open one to read what you wrote then.

### The journal list

**Journal** lists your entries, the newest first. Filter them by **Type**, **Status** (draft or
published), **Emotion** and **Tag**.

## Instruments and currencies

**Instruments** lists every symbol the app has seen, with its *quote currency*: the currency
its prices are in. Money is only ever added up within one currency, and never converted.
So 120 USDT and 0.01 BTC are shown side by side.

### The guess

When a symbol first appears, its currency is guessed from its name:

- **A separator:** `BTC/USDT`, `BTC-USD` and `ETH_BTC` use the part after it.
- **An exchange prefix:** `BINANCE:BTCUSDT` is read without its prefix.
- **A known currency at the end:** otherwise the name's longest known currency ending counts.
  `BTCFDUSD` is in FDUSD, `ETHBTC` in BTC and `EURUSD` in USD.
- **No guess:** a name like `AAPL` has no currency in it, so it is left unset and marked
  *currency not set*.

The known currencies are USDT, USDC, FDUSD, BUSD, TUSD, USD, EUR, GBP, JPY, AUD, CAD, CHF, TRY,
BRL, BTC, ETH and BNB.

### Setting or fixing one

Type a code (2 to 10 letters or digits, such as `USD`) in a symbol's row and select **Save**.
Every report uses the new currency at once.

Until a symbol has a currency, its money is totalled under *currency not set*, which may mix
currencies.

## Market data

**Market data** is where prices come in. Bars are stored once and shared by every backtest.

### Importing a price file

Under **Import a price file**:

| Field | Meaning |
|---|---|
| **CSV file** | The file, up to 200 MB |
| **Symbol** | The symbol to store the bars under, with the same rules as a trade's symbol |
| **Timeframe** | The bars' size: 1m, 5m, 15m, 30m, 1h, 4h or 1d. By default, *From the spacing of the bars*: the most common gap between them |
| **Format** | *Detect it* (the default), *OHLCV with a header row (Yahoo, TradingView…)* or *Binance klines* |

Select **Import**. The summary gives the bars added, the bars already stored, the rows rejected
and the time the file's bars cover.

### File formats

- **OHLCV with a header row.** It reads Yahoo Finance and TradingView exports, and most other
  vendors' files.
  - **Columns:** the header must name a time column (`time`, `timestamp`, `date`, `datetime`,
    `date_time` or `open_time`) and `open`, `high`, `low` and `close`. `volume` is optional.
    Short names (`o`, `h`, `l`, `c`, `v`, `vol`) work too, in any case and order.
  - **Separators:** commas, semicolons or tabs.
  - **Times:** ISO dates and times, plain dates, or Unix times in seconds, milliseconds or
    microseconds. Times without a time zone are read as UTC.
- **Binance klines.** These are Binance's own files, such as the monthly files on
  `data.binance.vision`: no header, 12 columns, times in milliseconds or microseconds.

### What is checked

Each row is checked, and a bad row is rejected with its line number and the reason, while the
rest still import. The summary lists the first 100 problems. A row is rejected when:

- a price isn't above 0, or the volume is negative;
- the low and high don't bracket the open and close;
- its time isn't the start of a bar of its timeframe, such as 10:07 in a 1h file;
- its time repeats an earlier row's.

Bars already stored, for the same symbol, timeframe and time, are kept as they were and
counted as *already stored*. So importing a file twice, or overlapping files, is safe.

### Stored bars, and bigger bars on demand

**Stored bars** lists each symbol and timeframe with its first and last bar and its count.

You don't need to import every size. A backtest or the API can ask for bigger bars, and the
app builds them from the biggest stored size that divides into them. For example, 4h bars are
built from stored 1h bars, and daily bars from 1m. Smaller bars than any stored can't be made
up.

### Big files

For files over 200 MB, or many files, use the command line:

```sh
make import-csv file=prices.csv symbol=BTCUSDT [timeframe=1m]
```
