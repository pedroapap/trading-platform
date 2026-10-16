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

## Strategies

A strategy is a set of rules for when to enter and how to get out, written in the
[rule language](rules.md). The **Strategies** page lists yours.

### Creating one

Select **New strategy** and give it:

- **Name:** up to 100 characters, and different from your other strategies' names.
- **Description (optional):** up to 2,000 characters.
- **Definition:** the rules, as JSON.

The definition box starts with a simple RSI strategy. **Start from an example** offers six
more, each with what it does in words. The help under the box sums up the language.

When you select **Create strategy**, the definition is checked. Each problem is listed with
its place in the definition, such as `entry.left.period`. A definition that isn't valid JSON
is caught before it is sent.

### Versions

A strategy's page shows its current definition, **Backtest it**, **Edit strategy** and its
**History**.

- **Changing the definition** makes a new version, recording which parts changed, such as
  *changed take_profit_r*. Earlier versions can't be changed, so their backtests stay
  reproducible. Open a version in the history to read it.
- **Changing the name or description** changes the strategy in place, without a version.
- **Saving an identical definition** changes nothing (*Nothing changed.*).

Trades and backtests record the version they followed.

## Backtests

A backtest runs one version of a strategy over one symbol's stored bars, and reports what it
would have done.

### Running one

Select **Backtest it** on a strategy, or **New backtest**:

| Field | Meaning and rules |
|---|---|
| **Strategy**, **Version** | The strategy, and its version: the current one if left empty |
| **Symbol** | A symbol with stored bars; the stored ones are suggested |
| **Timeframe** | The bar size to test on: stored, or [built from smaller stored bars](#stored-bars-and-bigger-bars-on-demand) |
| **From**, **To** (optional) | The first bar to use, and the bar to stop before. Empty means from the first or to the last stored bar |
| **Out-of-sample from** (optional) | Bars from this time on are reported apart: see [out-of-sample](#in-sample-and-out-of-sample). It must fall inside the range, with bars on both sides |
| **Finer bars for fills** | Smaller stored bars that settle what happened first inside a bar. Only stored sizes that divide the timeframe are offered, and the finest is picked. *None: assume the worst case* turns it off |
| **Initial capital** | The money to start with, in the symbol's quote currency, 10,000 by default |
| **Position size %** | The share of current equity put into each trade, the entry fee included: up to 1,000%. Over 100% borrows the rest, at no cost |
| **Fee %** | Charged on each fill's value, 0 to 10% |
| **Slippage %** | How far each market or stop fill lands against you, 0 to 10% |
| **Periods per year** | 365 for markets that trade every day (crypto), 252 for stock exchanges: it scales the Sharpe and Sortino ratios |

Select **Run backtest**. Most runs take a few seconds, and the results page shows *Pending*
and *Running* until it is done. A backtest is refused, with the reason, when:

- **there are no bars** for the symbol and timeframe in the range;
- **the version doesn't exist**;
- **the bars can't build** a timeframe the strategy uses;
- **the finer bars aren't finer** than the timeframe, or don't divide into it.

If a run fails, its page says why; if the app restarts mid-run, the run is marked failed
(*Interrupted*).

### How it fills orders

The simulation reads signals at each bar's close and fills them as described in
[the rule language](rules.md#how-orders-fill).

- **Prices:** orders fill at the next bar's open or at their price.
- **Costs:** every fill pays the fee, and market and stop fills pay slippage.
- **In doubt:** inside a bar, the worst case counts, unless finer bars settle it.
- **Positions:** one is open at a time, and one still open at the end closes at the last close.

### The results page

From the top:

- **The settings it ran with**:
  - the strategy version, market and range asked for;
  - the **bars used** (count, first and last);
  - capital, position size, costs and periods per year;
  - finer bars, the out-of-sample start;
  - the **data fingerprint**, a SHA-256 of every bar it read, finer bars included. Two runs
    with the same fingerprint saw exactly the same data.
- **Too few trades to judge**, a warning when a run has under 30 trades.
- **Results:** the [headline numbers](#what-the-numbers-mean), with buy and hold's return,
  CAGR and drawdown under the strategy's.
- **In-sample and out-of-sample**, when the run has a split: each side's numbers next to each
  other.
- **Backtest and live**: your logged trades of the same strategy version on the same symbol,
  entered while the backtest's bars ran, next to the backtest's. It shows trades, win rate,
  average return on notional and total P&L.
- **Equity**: the account's value at each bar's close next to buy and hold's, from the initial
  capital. Long runs are thinned to 1,000 points, keeping each stretch's highest and lowest
  values so no drawdown is hidden. Point at the chart for a value, or open **Equity as a
  table**.
- **Trades**, every simulated trade, 50 to a page:
  - entry and exit time and price, and size;
  - **Costs**, the fees plus slippage;
  - **P&L**, net of costs, and **P&L %** on the entry's value;
  - **Exit by**, why it ended.

### Buy and hold

Buy and hold is what a strategy has to beat. It buys at the first bar's open with all of the
initial capital, whatever the position size, and sells at the last bar's close. It pays the
same fee and slippage, and its return, CAGR and drawdown count from the initial capital.

### In-sample and out-of-sample

A rule shaped by looking at some bars will look good on them. Holding out the latest bars, the
*out-of-sample* ones, shows how it does on bars it wasn't shaped on.

- **Trades:** each counts on the side it was entered.
- **Equity:** the out-of-sample side's counts from its value on the last bar before the split.
- **Buy and hold:** each side has its own.

## Analytics

**Analytics** looks at your closed trades only, since open and cancelled trades have no P&L.
**Closed from** and **Closed to (inclusive)** limit it to trades closed in that time.

### Performance

**Group by** strategy, symbol, emotion or tag:

- **Trades**, **Wins** (P&L above 0) and **Losses** (below 0). A breakeven trade is neither.
- **Win rate**: wins as a share of the trades.
- **Average return**: the mean return per trade on the trade's full value, its *notional*. It
  is the return on margin divided by the leverage, so leverage doesn't make a trade look better
  or worse.
- **P&L**: the total in each quote currency, with the number of trades and the average.

Groups come best average return first. Trades without a strategy, emotion or tag are grouped
as *No strategy*, *No emotion recorded* or *No tag*.

By emotion or tag, a trade counts once in each emotion or tag that its journal entries
record, and **Journal entries** can keep, for example, only pre-trade feelings.

### Realized P&L

One chart per quote currency adds up the P&L of closed trades in the order they closed, one
point per trade, with the total and the deepest drawdown in money. The points are evenly
spaced rather than to scale in time. Point at one to see its date, or open the table.

**Symbol** and **Strategy** narrow it down. Trades of symbols without a set currency get a
chart of their own, flagged because it may mix currencies.

## What the numbers mean

| Number | How it is worked out |
|---|---|
| **Total return** | The change from the first to the last value of the equity curve |
| **CAGR** | The steady yearly growth that would turn the first value into the last over the run's length: (last ÷ first)^(1 ÷ years) − 1, with years of 365.25 days. −100% once the money is gone |
| **Max drawdown** | The largest fall from a high point of the equity curve, as a percentage of that high point |
| **Sharpe ratio** | The average daily return divided by how much daily returns vary (their standard deviation), times the square root of the periods per year. Days are UTC days, and the risk-free rate is taken as zero. Higher is steadier |
| **Sortino ratio** | Like Sharpe, but it only counts losing days as risk: the average daily return over the root mean square of the losing days' returns, counted over all days |
| **Trades** | Trades entered, including one closed at the end of the data |
| **Win rate** | The share of trades with a P&L above zero |
| **Profit factor** | The money made by winners divided by the money lost by losers. Above 1 makes money. Blank without a losing trade |
| **Expectancy** | The average P&L per trade, in money |
| **Average trade** | The average return per trade on its value, with its 95% range: ±1.96 standard errors, from 2 trades. A range that spans zero means the run can't tell a gain from luck |
| **Average win**, **Average loss** | The average P&L of winning and losing trades. The average loss is negative |
| **Exposure** | The share of bars on which a position was open at some point, its entry and exit bars included |

A run whose equity curve spans under 90 days shows CAGR, Sharpe and Sortino as "—", with
*Not annualized: under 90 days of data*. Scaled to a year, a few days' result says nothing:
a 2.4% gain in four days would show as a 630% CAGR. Buy and hold's CAGR is left out too, and
each side of a split follows the same rule.
