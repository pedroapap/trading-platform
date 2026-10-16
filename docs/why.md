# Why this exists

## The story

I had trading ideas and no honest way to check them.

One idea came from staring at charts. When a moving average falls below a level, price
sometimes makes a new low at the same horizontal line twice within a few bars. Then buy just
above that line, with the stop-loss just under it. Another idea was simpler: when a stock dips
to its moving average, buy it, with a 20% stop-loss and a 100% take-profit. And I wanted to
know whether any of this would work for day trading.

A chart makes every idea look good, because you remember the times it worked. To know, you
have to count every signal, the losers included, and pay the fees you would really pay. I
wanted a tool where I could do that with my own price files:

- **Load real prices** from an exchange's or a data site's price files, in bars from one
  minute to one day.
- **Write the rule down once**, in a form that can't quietly look into the future.
- **See whether it would have made money**, after costs, next to simply buying and holding.

This app is that tool. It also keeps the journal and the record of the trades I actually make.
So I can check, later on, whether my live trading matches what the backtest promised.

The first test on real prices was humbling. I ran four common day-trading rules, fixed before
any test, on Bitcoin's 1-minute history from 2022 to 2026. All four lost money once fees and
slippage were paid, while buying and holding nearly doubled from 2024 on. That's the kind of
answer this app is for: better to learn it from a backtest than with real money.

## The problems it fixes

- **Ideas judged by eye.** A backtest counts every signal a rule gives, not the ones you
  remember.
- **Looking into the future by accident.** In a hand-written script, one wrong index uses
  tomorrow's price today. Here, rules can only see what was known when the bar closed, and
  tests check this for every block of the rule language.
- **Costs left out.** Every fill pays the fee you set, and market and stop orders pay slippage,
  the gap between the price you wanted and the price you'd get.
- **Bars that hide the order of events.** When one bar touches both the stop-loss and the
  target, the stop counts, because nothing says which came first. If you have finer bars, such
  as 1-minute bars inside hourly ones, they settle it.
- **No yardstick.** Each backtest shows buying and holding over the same bars, with the same
  capital and costs.
- **Rules tuned to the past.** You can hold out the latest stretch of data as out-of-sample.
  A rule shaped on the earlier bars has to hold up on bars it never saw.
- **Too few trades to judge.** The average trade comes with its 95% range, and fewer than 30
  trades get a warning.
- **A trading record that drifts.** Trades, journal entries and strategies keep their history.
  A correction needs a reason, and the old values stay on record.
- **Money in several currencies.** Profits in USDT, BTC and USD are totalled apart and never
  converted.

## Principles

- **An honest record.** Every change to a trade goes into its audit log. Strategy versions
  and published journal entries can only be added to, never changed, and the database
  enforces it. Drafts are yours to edit until you publish them.
- **Reproducible.** A backtest stores the strategy version it ran, its settings, and a
  fingerprint of the exact bars it used. Run it again on the same data and you get the same
  result.
- **Realistic fills.** Signals are read when a bar closes and fill at the next bar's open, or at
  your order's price. Fees and slippage apply to every fill, and when in doubt the worst case
  counts.
- **Currencies kept apart.** Each symbol has one quote currency, and money is only ever added
  up within it.
- **Your data on your machine.** It runs on your own computer, for one person: no cloud
  account, no tracking, and your prices and trades in your own database.
- **Simple to trust.** Strategies are written in a small, readable rule language, checked when
  you save them, with no code to run. Each change to a rule makes a new version.

## What it isn't

- **Not financial advice.** It tells you what a rule would have done on the prices you give
  it. It recommends nothing.
- **Not a broker.** It places no orders and has no live prices; you record your trades
  yourself.
- **Not a promise.** A backtest describes the past, and markets change. A rule that lost in a
  backtest is worth a lot to know about. A rule that won still has to prove itself.
- **Not a charting platform.** Its charts show results, not live markets.
- **Not for teams.** It is built for one person: nothing is shared between accounts, and
  there are no roles or permissions.
