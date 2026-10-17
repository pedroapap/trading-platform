# Stories

Six longer walk-throughs. The first five follow one trader through a year of the made-up
sample prices, DEMOUSDT, from [Getting started](getting-started.md). They were run start to
finish on a fresh database, and the numbers are the ones the app returned. The sixth is a
real test, on Bitcoin's history. The [use cases](use-cases.md) cover each step in short.

## 1. From a chart idea to a tested strategy

**The idea.** On a chart, you see a pattern you trust: after a dip, price makes a new low at
the same horizontal line twice, then turns up. You want to know whether buying it would have
made money.

**As rules.** In the app's [rule language](rules.md), the idea becomes the **Double bottom
after a dip** example: the 50-bar average crossed below 100 within the last 48 bars, and price
made two swing lows within 0.5% of each other. Buy with a limit 0.3% above the latest low.
The stop is 1% under that low, and the target twice the risk.

**First run,** on hourly bars with a 0.1% fee and 0.05% slippage:

- **14 trades and +14.48%,** against +2.06% for buying and holding.
- **A small drawdown:** the deepest fall was 3.74%, against 23.02% for buy and hold.
- **But a warning:** 14 trades are too few to judge. The average trade, 0.99%, has a 95%
  range from −0.03% to 2.01%, which spans zero.

**Then, the checks a skeptic would ask for:**

| Check | Result |
|---|---|
| Fills settled by 1-minute bars | The same 14 trades: no exit depended on what came first inside an hour |
| No costs at all | +18.03% |
| Double the costs (0.2% and 0.1%) | +11.04% |
| A target at 3× the risk (version 2) | 12 trades, +13.16%, drawdown 5.98%: no better |
| The same rule on 15-minute bars | 42 trades, +30.87%, drawdown 7.94% |
| The same rule on 4-hour bars | 4 trades, −2.28% |
| Held out: October to December | 2 trades, +0.81%, while buy and hold lost 1.60% |

**What it says.** On these prices, the rule holds up: it survives costs, doesn't depend on
intrabar luck, and kept working on the held-out quarter. That is no surprise, since the double
bottoms were planted in the sample to show how the app works. The 15-minute run is a reminder
that the same rule is a different strategy on other bars: its swings and its 48-bar window
shrink with them.

On a real market, the same steps give the verdict. Version 2 stays on record, and version 1's
backtests can be run again at any time with the same result.

## 2. One trade, from plan to review

**Before the trade.** On 10 January 2025, a double bottom forms near 95.4. Before buying, you
write a *Pre-trade* journal entry:

- **Thesis:** *The 50-hour average fell under 100 yesterday, and price made two lows near
  95.4. Buy at 95.50 if the second low holds.*
- **Risk assessment:** *Stop at 94.50: 100 USDT at risk on 100 units. Target 97.50, twice the
  risk.*
- **Emotion:** confident. **Tag:** `double-bottom`.

You save it as a draft.

**The trade.** The limit fills at 95.50 at 11:30. You log it with its stop and target, and
link it to version 1 of the strategy. Then you edit the plan, pick the trade under **Trade**,
and publish the plan: it can no longer be rewritten.

**The exit.** The target fills at 97.50 at 14:05. Closing the trade gives a P&L of
**180.70 USDT** after 19.30 of fees: 1.89% of the 9,550 USDT put in.

**The review.** From the trade's page, **Write a journal entry about it** starts a
*Post-trade* review of it. *Waited for the second low. The limit filled, and the target came
2.5 hours later.* Emotion: calm. Tags: `double-bottom`, `limit-entry`.

**In the analytics,** the trade now appears:

- under *Double bottom after a dip*, by strategy;
- under both *confident* and *calm*, by emotion, since its plan and its review each recorded
  one;
- under *confident* alone with **Journal entries** set to *Pre-trade*: the feeling before the
  result was known.

## 3. A monthly review

It is early July 2025. The month of June needs a look.

**Analytics,** closed from 1 June to 30 June:

| Group | Trades | Result |
|---|---|---|
| Double bottom after a dip | 1 | −144.67 USDT |
| No strategy | 2 | +1,046.37 USDT and +6,200 JPY |

**By emotion,** the one strategy trade is the *fomo* one: bought at 98.95 before the second
low formed, and stopped out. The other two trades have no journal entry at all.

**Realized P&L:** +901.70 USDT over 2 trades, with a deepest fall of 144.67, and +6,200 JPY.

**The review,** a *Note* tagged `monthly-review`: *The month's profit came from a 5x trade that
was in no plan. The one planned trade broke the rule: bought before the second low, out of
fomo, and lost 144.67.*

**What it says.** A profitable month can hide a bad one. The plan was broken, and the profit
came from an unplanned, leveraged trade. Next month's review starts from the tag
`monthly-review`, which lists every review so far.

## 4. Is my live trading matching the backtest?

By July, you have taken five trades on version 1 of the double bottom. The backtest of version
1 over 2025 has 14. Under **Backtest and live** on the backtest's page:

| | Backtest | Live |
|---|---|---|
| Trades | 14 | 5 |
| Win rate | 64.29% | 80.00% |
| Average return on notional | 0.99% | 1.48% |
| Total P&L | 1,448.42 USDT | 712.02 USDT |

Live looks better. Lining up each live trade with the backtest's trades tells more:

| Signal | Backtest | Live |
|---|---|---|
| 10 January | in at 95.49, +2.39% | in at 95.50, +1.89% |
| 28 February | in at 98.11, +2.39% | in at 98.20, +2.24% |
| 27 April | in at 95.21, +2.39% | in at 95.25, +2.37% |
| 31 May | in at 97.69, +2.39% | in at 97.70, +2.36% |
| 1 June | in at 98.96, −1.48% | in at 98.95, −1.46% |

- **On the same signals,** live did a little worse: 1.48% a trade against the backtest's
  1.62% on those five. Four of the five fills were slightly higher, and the 10 January target
  was set at 97.50, under the strategy's 97.96.
- **The real difference** is the 9 signals not taken. They were 5 winners and 4 losers, and
  the 80% live win rate comes from which signals were skipped, not from trading better.
- **Five trades** can't confirm anything. The backtest's own 14 are flagged as too few.

## 5. Three currencies, honest totals

Besides DEMOUSDT, you trade ETHBTC, Apple (AAPL) and Toyota in Tokyo (7203.T).

- **ETHBTC** is quoted in bitcoin: its P&L is 0.00126458 BTC, guessed from the name.
- **AAPL** says nothing about its currency. Until it is set, its 87 sits under *Currency not
  set*, in a curve that warns it may add up different currencies.
- **7203.T** was registered as JPY before its first trade, so its 6,200 has been yen from the
  start.

After setting AAPL to USD on **Instruments**, the strategies table shows, for the trades with
no strategy:

| Currency | Trades | P&L |
|---|---|---|
| BTC | 1 | 0.00126458 |
| JPY | 1 | 6,200 |
| USD | 1 | 87.00 |
| USDT | 2 | 1,215.09 |

Adding these up would give 7,502.09 of nothing in particular, most of it yen. The app never
does: money is totalled per currency, and only counts, win rates and percentages, which have
no currency, cover all trades at once. Here: 5 trades, 5 wins, an average return of 2.46%.

## 6. Day trading Bitcoin on real prices

**The question.** Do simple intraday rules make money on Bitcoin, after costs? This test ran
on 16 October 2026.

**The data.** Binance's 1-minute BTCUSDT bars from January 2022 to September 2026: 57 monthly
files from `data.binance.vision`, each checked against Binance's SHA-256 checksum. They gave
2,496,880 bars, with no row rejected. The only gap is Binance's own: 80 minutes on 24 March
2023, when spot trading was halted. The files aren't in this repository; use case 22 shows how
to download them.

**The rules, fixed before any test.** Four textbook long-only rules, on the UTC day, out by
23:55:

1. **Opening-range breakout:** a buy stop at the first hour's high, from 01:00 to 12:00. The
   stop is at the first hour's low, the target at twice the risk.
2. **VWAP pullback in an uptrend:** when yesterday's daily close is above its 20-day average
   and the close is above VWAP, a limit buy at VWAP. 0.5% stop, 1% target.
3. **Breakout of yesterday's high in an uptrend:** a buy stop at yesterday's high, with the
   same trend filter. The stop is at VWAP, the target at twice the risk.
4. **VWAP stretch:** a close more than 1% under VWAP buys at the next open, and a close back
   above VWAP sells. 1% stop.

**The test, also fixed in advance.**

- **Settings:** 5-minute bars with 1-minute fills, 10,000 USDT with all of it in each trade,
  a 0.1% fee (Binance's spot rate) and 0.02% slippage.
- **The split:** in-sample is 2022 and 2023; out-of-sample starts on 1 January 2024.
- **The pick:** the best in-sample Sharpe ratio with at least 100 trades.
- **Holding up** means a positive out-of-sample return and average trade, over at least 100
  trades.

**The results:**

| Rule | In-sample trades | In-sample return | In-sample Sharpe | Out-of-sample trades | Out-of-sample return |
|---|---|---|---|---|---|
| 1. Opening-range breakout | 650 | −81.72% | −4.04 | 1,000 | −84.25% |
| 2. VWAP pullback | 1,145 | −92.98% | −7.04 | 1,605 | −96.68% |
| 3. Yesterday's high | 485 | −70.70% | −3.67 | 738 | −82.77% |
| 4. VWAP stretch | 1,276 | −96.48% | −4.27 | 1,474 | −96.34% |
| Buy and hold | | −8.73% | | | +97.29% |

- **The pick** is rule 3, the least bad in-sample. Out-of-sample it lost 82.77% over 738
  trades. Its average trade was −0.24%, with a 95% range of ±0.05%, so the loss is no
  accident. It doesn't hold up.
- **At double the slippage,** it lost 85.41% out-of-sample.
- **Why:** run without any costs, the four rules' average trades fall between −0.02% and
  +0.05%. Costs take about 0.22–0.24% of every round trip. None of these rules has an edge
  anywhere near that size.
- **Checked by hand:** the pick's trade 489, on 8 January 2024, was worked out again from the
  raw file with plain pandas. Entry 44,489.49 (yesterday's high plus slippage), stop
  43,794.82, target 45,878.82, fees and P&L of 83.94 USDT all matched to the cent.
- **The same data:** all runs saw the same data fingerprint, `fc0c4c5a4faa`.

**What it says.** Not that day trading can't work, but that these four rules don't on these
years, once costs are paid. Out-of-sample, simply holding Bitcoin almost doubled. A test like
this takes an afternoon, and costs nothing next to finding out with real money.

**To repeat it:**

1. **Download and import** the months, as in use cases 22 and 26.
2. **Create the four rules.** Rule 2 is the editor's *VWAP pullback in a daily uptrend*
   example, and rule 3 is in use case 57. Rules 1 and 4:

   ```json strategy
   {
     "direction": "long",
     "entry": {"all": [
       {"time": ["01:00", "12:00"]},
       {"left": {"price": "close"}, "op": "<", "right": {"indicator": "opening_range", "minutes": 60, "output": "high"}}
     ]},
     "entry_order": {"type": "stop", "price": {"indicator": "opening_range", "minutes": 60, "output": "high"}, "expires_after": 1},
     "stop_loss_at": {"indicator": "opening_range", "minutes": 60, "output": "low"},
     "take_profit_r": 2,
     "flat_at": "23:55"
   }
   ```

   ```json strategy
   {
     "direction": "long",
     "entry": {"left": {"price": "close"}, "op": "<", "right": {"multiply": [{"indicator": "vwap"}, {"value": 0.99}]}},
     "exit": {"left": {"price": "close"}, "op": "crosses_above", "right": {"indicator": "vwap"}},
     "stop_loss_pct": 1,
     "flat_at": "23:55"
   }
   ```

3. **Backtest each** on BTCUSDT at 5m with the settings and split above. Each run took about
   half a minute.
