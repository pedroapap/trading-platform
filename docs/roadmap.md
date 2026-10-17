# Roadmap

What the app can't do yet, and what could come next. Nothing here is promised: it is a list
to choose from.

## Limits today

### Backtests

- **One symbol, one position.** A backtest runs one strategy on one symbol, with at most one
  position open. Portfolios, pairs and several positions at once aren't modelled.
- **One entry and one exit per trade.** There is no scaling in or out.
- **Borrowing is free.** A position over 100% of equity borrows the rest without interest,
  and funding rates aren't charged.
- **Margin calls only at zero equity.** There is no maintenance margin.
- **One out-of-sample split.** There is no walk-forward testing, no Monte Carlo and no built-in
  parameter sweep, though a script can run a sweep ([use case 70](use-cases.md#70-run-a-sweep-of-backtests-from-the-shell)).
- **Sessions can't cross midnight,** as futures sessions do.
- **The rule language** has 13 indicators, and no `bars_since`, `value_when` or VWAP bands.
  Rules are written as JSON, with no formula syntax or visual builder.
- **Backtests run inside the API's process.** A restart marks a running backtest as failed.

### Prices

- **Files only.** Prices come from files you download and import. The app fetches nothing and
  has no live prices.
- **Two formats:** OHLCV with a header row, and Binance klines.
- **Stock prices are used as they are.** Columns such as Yahoo's `Adj Close` are ignored, so
  splits and dividends count only if the file's prices already include them.
- **Gaps don't show.** The stored bars list gives each symbol's first and last bar and its
  count, not where bars are missing.

### Trades and the journal

- **No broker connection.** Trades are logged by hand or by script.
- **One exit per trade.** Closing part of a position leaves the rest untracked.
- **Open trades are changed through the API.** The pages close, cancel and correct.
- **Journal entries are dated when written,** so a plan can't be backdated.
- **Nothing is deleted from the app,** on purpose. Old backtests can be deleted with SQL
  ([The data model](schema.md#what-cant-be-changed-or-deleted)).

### Running it

- **One person:** one account, with no roles.
- **Development servers.** `make dev` runs the API with auto-reload and the pages on Vite's
  development server. There is no production build, HTTPS, or service that starts with the
  computer.
- **Currencies are guessed offline,** from the symbol's name. Stocks and other names without a
  currency need theirs set by hand.

## What could come next

### Better verdicts

- **Parameter sweeps,** with the best result checked out-of-sample.
- **Walk-forward testing:** pick the parameters on one stretch of data, test them on the next,
  and move along.
- **Monte Carlo:** shuffle the trades to see how deep the drawdown could have been.

### Richer strategies

- **A text formula syntax,** such as `rsi(14) < 30 and close > sma(200)`, or a visual rule
  builder.
- **New operands:** `bars_since` and `value_when`.
- **Day trading:** VWAP bands, sessions that cross midnight, maintenance margin and borrowing
  costs.
- **Several symbols per test,** and scaling in and out of positions.

### Prices

- **More file formats,** each one class behind the app's file-format interface.
- **Downloads from inside the app,** such as Binance's monthly files, or exchanges through
  [ccxt](https://github.com/ccxt/ccxt).
- **A gaps report** for the stored bars.

### Trading

- **Paper trading:** a strategy's signals recorded as they happen.
- **Live trading** through a broker connection, after that.
- **An online currency lookup** when a symbol first appears, from ccxt for crypto or a stock
  data provider such as Finnhub, with the name-based guess as the offline fallback.

### Running it

- **A production setup:** the pages built once and served by the API, HTTPS, and a service
  that starts with the computer.
