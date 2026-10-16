# The strategy rule language

A strategy is a small JSON document: when to enter, in which direction, and how to get out.
The app checks it when you save it, and points to the exact place of any mistake. Each saved
change becomes a new version, and every backtest records which version it ran. There is no
code to run, so a strategy can't do anything but read prices and indicators, and it can't
look into the future: every block below has been tested for that.

This page is the reference, with a [cookbook](#cookbook) at the end. Every complete example
on it is checked by the docs' tests.

## A strategy at a glance

```json strategy
{
  "direction": "long",
  "entry": {"left": {"indicator": "rsi", "period": 14}, "op": "<", "right": {"value": 30}},
  "exit": {"left": {"indicator": "rsi", "period": 14}, "op": ">", "right": {"value": 70}},
  "stop_loss_pct": 2
}
```

*Buy when the 14-bar RSI is under 30, sell when it is over 70, with a 2% stop-loss.*

| Field | What it is |
|---|---|
| `direction` | `long` (buy, then sell) or `short` (sell, then buy back). Required |
| `entry` | A [rule](#rules): where it holds at a bar's close, the strategy enters. Required |
| `exit` | A rule: where it holds, an open position leaves at the next open. Optional |
| `entry_order` | How entries fill: at the next open (the default), or at a [limit or stop](#entry-orders) price |
| `stop_loss_pct` or `stop_loss_at` | A [stop-loss](#stop-loss-take-profit-and-trailing-stops), as a percentage below the entry or at a price level |
| `take_profit_pct`, `take_profit_at` or `take_profit_r` | A take-profit, as a percentage, a price level, or a multiple of the risk |
| `trailing_stop_pct` or `trailing_stop_at` | A stop that follows the trade and only tightens |
| `exit_after_bars` | Leave at the open that many bars after the entry, 1 to 100,000 |
| `session` | The market's [trading hours](#sessions-and-the-trading-day) and time zone. Without it, the trading day is the UTC day |
| `flat_at` | A time of day to be [out by](#flat-by-a-time-of-day), every day, such as `"15:55"` |

A strategy needs at least one way out: an exit rule, a stop-loss, a take-profit, a trailing
stop, `exit_after_bars` or `flat_at`. It has at most one stop-loss, one take-profit and one
trailing stop. A long's percentage stop-loss and trailing stop, and a short's percentage
take-profit, must be under 100%, since a price can't fall below zero.

## Operands

Rules compare *operands*, values that can change from bar to bar.

### Values and prices

- `{"value": 30}` is a number, the same on every bar.
- `{"price": "close"}` is the bar's `open`, `high`, `low`, `close` or `volume`.

### Indicators

`{"indicator": "sma", "period": 50}` and so on. Every indicator is computed once per backtest,
however many times a strategy uses it.

| Indicator | Parameters (default) | What it gives |
|---|---|---|
| `sma` | `period` 1–1000, `source` (`close`) | Simple moving average of the last `period` bars |
| `ema` | `period` 1–1000, `source` (`close`) | Exponential moving average, started from the SMA of its first `period` bars, as charting sites do |
| `rsi` | `period` 2–1000 (14), `source` (`close`) | Relative strength index, 0 to 100, with Wilder's smoothing. A flat price gives 50 |
| `macd` | `fast` (12), `slow` (26), `signal` (9), `output` (`line`), `source` (`close`) | MACD `line`, `signal` or `histogram`; `fast` must be shorter than `slow` |
| `bbands` | `period` 2–1000 (20), `std` above 0 to 10 (2), `output` (`middle`), `source` (`close`) | Bollinger Bands: the `upper`, `middle` or `lower` band |
| `atr` | `period` 1–1000 (14) | Average true range: how far price moves in a bar, on average |
| `lowest` | `period` 1–1000, `source` (`low`) | The lowest value of the last `period` bars, this one included |
| `highest` | `period` 1–1000, `source` (`high`) | The highest value of the last `period` bars, this one included |
| `swing_low` | `strength` 1–50, `occurrence` 0–9 (0), `output` (`price`), `source` (`low`) | A recent [swing low](#swing-lows-and-highs): its `price`, or the `bars_since` it |
| `swing_high` | as `swing_low`, `source` (`high`) | A recent swing high |
| `vwap` | — | The trading day's volume-weighted average price so far |
| `day` | `output`: `open`, `high`, `low` or `close`; `days_ago` 0–10 (0) | The trading day's levels: today's so far, or an earlier day's |
| `opening_range` | `minutes` 1–240, `output`: `high` or `low` | The high or low of the day's first `minutes` |

`period` is required for `sma`, `ema`, `lowest` and `highest`, as is `strength` for swings and
`output` for `day` and `opening_range`. A `source` can be any of the bar's prices or its
volume.

#### Swing lows and highs

A swing low is a bar lower than each of the `strength` bars before it and no higher than each
of the `strength` bars after it. So it is known only `strength` bars later, never sooner, as
on TradingView. `occurrence` 0 is the latest known swing, 1 the one before, and so on.

#### The trading day's indicators

`vwap`, `day` and `opening_range` belong to the [trading day](#sessions-and-the-trading-day):

- **`vwap`** averages each bar's (high + low + close) ÷ 3, weighted by its volume, from the
  day's first bar. It starts again each day, and is unknown before the day has any volume.
- **`day` with `days_ago` 0** is today so far: the open of its first bar, its high and low up
  to now, and this bar's close.
- **`day` with `days_ago` 1 or more** is that earlier day's whole open, high, low or close,
  known all day. Days with no bars in the session don't count.
- **`opening_range`** is the high or low of the bars that start in the session's first
  `minutes`. It is unknown until the last of them closes, then stays the same all day. With
  bars longer than the range, it is the day's first bar.

All three are unknown on bars outside the session.

### Looking back: `bars_ago`

Any price or indicator can take `bars_ago`, 0 to 1000: the value that many bars earlier.
`{"price": "low", "bars_ago": 1}` is the previous bar's low. It is unknown on the first bars.

### Arithmetic

`add`, `subtract`, `multiply` and `divide` combine exactly two operands:

```json
{"multiply": [{"indicator": "swing_low", "strength": 3}, {"value": 1.003}]}
```

That is 0.3% above the latest swing low. `subtract` takes the first minus the second, and
`divide` the first over the second, which is unknown where the second is 0. Arithmetic can be
nested up to 4 levels deep.

### A higher timeframe

`{"timeframe": "1d", "of": <operand>}` computes an operand on bigger bars:

```json
{"timeframe": "1d", "of": {"indicator": "sma", "period": 20}}
```

That is a daily 20-day average, used on hourly or 5-minute bars.

- **The bigger bars are built from the backtest's own**, in the app's sizes: `1m`, `5m`,
  `15m`, `30m`, `1h`, `4h` or `1d`. Days start at 00:00 UTC.
- **Only completed bars count.** On a 10:00 bar, a daily average is yesterday's, as with
  TradingView's `request.security` without look-ahead.
- **The backtest's bars must build it**, so they must divide the timeframe evenly: 1h bars
  can build 4h and 1d bars, but not 30m bars. A backtest that can't is refused.
- **What it can't hold:** another timeframe, or the trading day's indicators (`vwap`, `day`,
  `opening_range`).

## Rules

A rule holds or not at each bar's close.

### Conditions

```json
{"left": {"price": "close"}, "op": "crosses_above", "right": {"indicator": "sma", "period": 50}}
```

`op` is `<`, `<=`, `>`, `>=`, `crosses_above` or `crosses_below`.

- **A cross** happens on the bar where `left` goes from at or below `right` to above it, as
  TradingView's `crossover`. `crosses_below` is the mirror.
- **One side must move:** a condition must involve a price or an indicator, so two numbers
  can't be compared.

### Groups: `all`, `any` and `not`

- `{"all": [rule, rule, …]}` holds when every rule in it does.
- `{"any": [rule, rule, …]}` holds when at least one does.
- `{"not": rule}` holds when the rule doesn't, and only once every value it uses is known.

### `happened`: did it happen recently?

```json
{"happened": {"left": {"indicator": "sma", "period": 50}, "op": "crosses_below", "right": {"value": 100}}, "within": 48, "times": 1}
```

This holds when the rule held on at least `times` separate runs of bars within the last
`within` bars, this one included. `within` is 1 to 1000, and `times` is 1 to 10, 1 by default.
A run that began before the window counts once if it reaches into it.

### Patterns: equal lows and highs

```json
{"pattern": "equal_lows", "strength": 3, "times": 2, "within": 48, "tolerance_pct": 0.5}
```

A double bottom, or with `times` 3 a triple bottom. It holds on the bar where the latest of
`times` swing lows is confirmed, `strength` bars after it.

- **The earlier lows** began fewer than `within` bars before it, and are within
  `tolerance_pct` of it.
- **Price held the line** between them.
- **Ranges:** `strength` is 1 to 50, `times` 2 to 5, `within` 2 to 1000, and `tolerance_pct`
  above 0 to 10.

`equal_highs` finds swing highs the same way: a double or triple top.

### Time windows

```json
{"time": ["09:30", "11:00"]}
```

This holds on bars that start at or after the first time and before the second, in the
session's time zone (UTC without a session).

- **Times** are `HH:MM` on a 24-hour clock, and `24:00` is the end of the day.
- **Wrapping:** a first time later than the second wraps past midnight, as in
  `["22:00", "02:00"]`.
- **Fills:** as in TradingView, a signal on the 10:55 bar fills at 11:00.

### Limits

Rules can be nested 6 levels deep, and a strategy's entry or exit rule may hold at most 20
conditions, patterns and time windows.

## Warm-up: values not known yet

An indicator needs some bars before it has a value. Until then it is *unknown*, and so is
anything computed from it.

- **Comparisons:** one with an unknown value is false.
- **`not`:** it is false too, so a strategy never trades on missing data.
- **Levels:** if an order's price or a stop's level is unknown, the signal places no order.

## How orders fill

Signals are read at each bar's close.

### Entry orders

- **Market (the default):** the entry fills at the next bar's open, plus slippage.
- **Limit and stop orders** are set in `entry_order`:

```json
{"type": "limit", "price": {"multiply": [{"indicator": "swing_low", "strength": 3}, {"value": 1.003}]}, "expires_after": 6}
```

The price is read on the signal bar, and the order works from the next bar for
`expires_after` bars (1 to 1000, 1 by default). A newer signal replaces it.

- **A `limit` order buys at its price or lower** (a short sells at it or higher). It fills at
  that price, or at a better open, without slippage.
- **A `stop` order buys once price trades up through its price** (a short sells on the way
  down). It fills at that price, or at a worse open, with slippage. It suits breakouts.

Only one position is open at a time: entry signals are ignored while one is. After an exit, a
signal from that bar's close on can enter again.

### Stop-loss, take-profit and trailing stops

- **Stop-loss:** `stop_loss_pct` is a percentage from the entry fill. `stop_loss_at` is a
  price level read on the signal bar, such as a swing low.
  - It counts from the entry bar on, against each bar's low (or high for a short).
  - It fills at the stop, or at the open if the bar gaps past it, with slippage.
  - A level already passed when the entry fills exits at that bar's open.
- **Take-profit:** `take_profit_pct`, `take_profit_at` (a level), or `take_profit_r`, a
  multiple of the risk, the distance from the entry fill to the stop-loss. `take_profit_r`
  goes up to 100, and needs a stop-loss.
  - It is a limit order: it fills at the target, or at a better open, without slippage.
- **Trailing stop:** `trailing_stop_pct` stays that far behind the best price since the
  entry. `trailing_stop_at` is a level read at each close and used from the next bar, such as
  the highest high less three ATRs.
  - It only ever tightens. With a fixed stop-loss too, the tighter one counts.

### When a bar can't say what came first

A bar's high and low don't say which came first.

- **Both stop and target in one bar:** when a bar reaches both, the stop-loss counts.
- **The bar a limit or stop entry fills on:** a stop-loss reached in that bar counts, but a
  take-profit doesn't.
- **With finer bars:** a backtest given finer bars, such as 1-minute bars inside hourly ones,
  replays those bars through them to settle what really happened first.

### Other exits

- **The exit rule:** a signal exit fills at the next bar's open, before a stop on that bar.
- **`exit_after_bars`:** the position leaves at the open that many bars after the entry bar,
  unless something exits first.
- **The end of the data:** a position still open on the last bar closes at its close.
- **Margin call:** a position is closed where its losses would use up all of the equity. It
  works like a stop at that price, and a tighter stop-loss counts first. It can't happen to a
  long of 100% of equity or less; for a short of all of it, it happens when the price doubles.

Each trade records why it ended: `signal`, `stop_loss`, `take_profit`, `trailing_stop`,
`time_exit`, `end_of_day`, `margin_call` or `end_of_data`.

## Sessions and the trading day

```json
{"timezone": "America/New_York", "start": "09:30", "end": "16:00"}
```

`session` says when the market trades each day, in its own time zone.

- **Defaults:** without it, the trading day is the UTC day, 00:00 to 24:00, which suits
  crypto.
- **Fields:** `timezone` is an IANA name, and daylight saving follows it. `start` and `end`
  are `HH:MM`, with `24:00` allowed as the end. Each field has a default (`UTC`, `00:00`,
  `24:00`).
- **Bars:** a bar belongs to the trading day whose session it overlaps. A bar overlapping none
  is outside the session.
- **Inside the session only:** no entry fills outside it, and `vwap`, `day` and
  `opening_range` skip such bars.

### Flat by a time of day

`"flat_at": "15:55"` keeps day trades from being held overnight.

- **No new entries:** no entry fills from that time to the end of the trading day.
- **The exit:** a position still open leaves at the open of the day's first bar starting at
  or after it, with the reason `end_of_day`.
- **Shortened days:** if the day ends first, the position closes at its last bar's close. So
  `flat_at` equal to the session's end means "out at the close".
- **Range:** `flat_at` must be after the session starts and no later than it ends.

## When a strategy is refused

The app checks a strategy when you save it. It lists each problem with its place in the
definition, such as:

- `entry.left.period`: *Input should be greater than or equal to 1*
- `entry.all[0].time[0]`: *a time of day is HH:MM on a 24-hour clock, such as 09:30*

Problems with the whole strategy, such as having no way out, have no place.

## Cookbook

Each recipe is a complete strategy. Paste one into a new strategy's definition, or start from
the editor's **Examples** menu, which has the first four and the last two.

### Double bottom after a dip

The 50-bar average crossed below 100 within the last 48 bars, and price then made two swing
lows within 0.5% of each other. Buy 0.3% above the latest low with a limit order that works
for 6 bars. The stop is 1% under that low, and the target is twice the risk.

```json strategy
{
  "direction": "long",
  "entry": {"all": [
    {"happened": {"left": {"indicator": "sma", "period": 50}, "op": "crosses_below", "right": {"value": 100}}, "within": 48},
    {"pattern": "equal_lows", "strength": 3, "times": 2, "within": 48, "tolerance_pct": 0.5}
  ]},
  "entry_order": {"type": "limit", "price": {"multiply": [{"indicator": "swing_low", "strength": 3}, {"value": 1.003}]}, "expires_after": 6},
  "stop_loss_at": {"multiply": [{"indicator": "swing_low", "strength": 3}, {"value": 0.99}]},
  "take_profit_r": 2
}
```

### RSI dip

Buy when RSI(14) dips under 30, sell when it rises over 70, with a 2% stop.

```json strategy
{
  "direction": "long",
  "entry": {"left": {"indicator": "rsi", "period": 14}, "op": "<", "right": {"value": 30}},
  "exit": {"left": {"indicator": "rsi", "period": 14}, "op": ">", "right": {"value": 70}},
  "stop_loss_pct": 2
}
```

### Breakout with a stop entry

While the 20-bar EMA is above the 50-bar EMA, buy if price trades through the 20-bar high
within 5 bars. The stop is the 10-bar low, and the target twice the risk.

```json strategy
{
  "direction": "long",
  "entry": {"left": {"indicator": "ema", "period": 20}, "op": ">", "right": {"indicator": "ema", "period": 50}},
  "entry_order": {"type": "stop", "price": {"indicator": "highest", "period": 20}, "expires_after": 5},
  "stop_loss_at": {"indicator": "lowest", "period": 10},
  "take_profit_r": 2
}
```

### Trend with an ATR trailing stop

Buy when the close crosses above the 50-bar SMA with RSI over 50. Trail a stop three ATRs
under the 22-bar high, and leave after 240 bars at the latest.

```json strategy
{
  "direction": "long",
  "entry": {"all": [
    {"left": {"price": "close"}, "op": "crosses_above", "right": {"indicator": "sma", "period": 50}},
    {"left": {"indicator": "rsi"}, "op": ">", "right": {"value": 50}}
  ]},
  "trailing_stop_at": {"subtract": [
    {"indicator": "highest", "period": 22},
    {"multiply": [{"indicator": "atr", "period": 22}, {"value": 3}]}
  ]},
  "exit_after_bars": 240
}
```

### Dip to the moving average

After a close above the 20-bar average, buy at that average with a limit order for the next
bar. 20% stop-loss, 100% take-profit.

```json strategy
{
  "direction": "long",
  "entry": {"left": {"price": "close"}, "op": ">", "right": {"indicator": "sma", "period": 20}},
  "entry_order": {"type": "limit", "price": {"indicator": "sma", "period": 20}, "expires_after": 1},
  "stop_loss_pct": 20,
  "take_profit_pct": 100
}
```

### Golden cross

Buy when the 50-bar average crosses above the 200-bar average, and sell when it crosses back
below.

```json strategy
{
  "direction": "long",
  "entry": {"left": {"indicator": "sma", "period": 50}, "op": "crosses_above", "right": {"indicator": "sma", "period": 200}},
  "exit": {"left": {"indicator": "sma", "period": 50}, "op": "crosses_below", "right": {"indicator": "sma", "period": 200}}
}
```

### MACD with a trend filter

Buy when the MACD line crosses above its signal line while the close is above the 200-bar
EMA. Sell when it crosses back below, with a 3% stop.

```json strategy
{
  "direction": "long",
  "entry": {"all": [
    {"left": {"indicator": "macd", "output": "line"}, "op": "crosses_above", "right": {"indicator": "macd", "output": "signal"}},
    {"left": {"price": "close"}, "op": ">", "right": {"indicator": "ema", "period": 200}}
  ]},
  "exit": {"left": {"indicator": "macd", "output": "line"}, "op": "crosses_below", "right": {"indicator": "macd", "output": "signal"}},
  "stop_loss_pct": 3
}
```

### Bollinger dip in an uptrend

With the close above the 200-bar average and under the lower band, buy. Sell on a close above
the middle band.

```json strategy
{
  "direction": "long",
  "entry": {"all": [
    {"left": {"price": "close"}, "op": ">", "right": {"indicator": "sma", "period": 200}},
    {"left": {"price": "close"}, "op": "<", "right": {"indicator": "bbands", "period": 20, "std": 2, "output": "lower"}}
  ]},
  "exit": {"left": {"price": "close"}, "op": ">", "right": {"indicator": "bbands", "period": 20, "std": 2, "output": "middle"}}
}
```

### Double top, short

Two swing highs within 0.5% of each other within 48 bars: sell short 0.3% under the latest
high, with the stop 1% above it and the target at twice the risk. It mirrors the double
bottom.

```json strategy
{
  "direction": "short",
  "entry": {"pattern": "equal_highs", "strength": 3, "times": 2, "within": 48, "tolerance_pct": 0.5},
  "entry_order": {"type": "limit", "price": {"multiply": [{"indicator": "swing_high", "strength": 3}, {"value": 0.997}]}, "expires_after": 6},
  "stop_loss_at": {"multiply": [{"indicator": "swing_high", "strength": 3}, {"value": 1.01}]},
  "take_profit_r": 2
}
```

### Buy the first new low in a while

Buy when the low breaks under the previous 20-bar low, but only if it hasn't done so in the
last 100 bars, and hold for 24 bars.

```json strategy
{
  "direction": "long",
  "entry": {"all": [
    {"left": {"price": "low"}, "op": "<", "right": {"indicator": "lowest", "period": 20, "bars_ago": 1}},
    {"not": {"happened": {"left": {"price": "low"}, "op": "<", "right": {"indicator": "lowest", "period": 20, "bars_ago": 1}}, "within": 100, "times": 2}}
  ]},
  "exit_after_bars": 24,
  "stop_loss_pct": 5
}
```

### Opening-range breakout (New York)

In New York trading hours, from 10:00 to 12:00, while price is under the first 30 minutes'
high: buy if it trades through that high. The stop is at the range's low and the target twice
the risk, and the position is out by 15:55.

```json strategy
{
  "direction": "long",
  "session": {"timezone": "America/New_York", "start": "09:30", "end": "16:00"},
  "entry": {"all": [
    {"time": ["10:00", "12:00"]},
    {"left": {"price": "close"}, "op": "<", "right": {"indicator": "opening_range", "minutes": 30, "output": "high"}}
  ]},
  "entry_order": {"type": "stop", "price": {"indicator": "opening_range", "minutes": 30, "output": "high"}, "expires_after": 1},
  "stop_loss_at": {"indicator": "opening_range", "minutes": 30, "output": "low"},
  "take_profit_r": 2,
  "flat_at": "15:55"
}
```

### VWAP pullback in a daily uptrend

On the UTC day, as crypto trades: when yesterday's close was above its 20-day average and
price closes above VWAP, buy at VWAP with a limit order. 0.5% stop-loss, 1% take-profit, out
by 23:55.

```json strategy
{
  "direction": "long",
  "entry": {"all": [
    {"left": {"timeframe": "1d", "of": {"price": "close"}}, "op": ">", "right": {"timeframe": "1d", "of": {"indicator": "sma", "period": 20}}},
    {"left": {"price": "close"}, "op": ">", "right": {"indicator": "vwap"}}
  ]},
  "entry_order": {"type": "limit", "price": {"indicator": "vwap"}, "expires_after": 1},
  "stop_loss_pct": 0.5,
  "take_profit_pct": 1,
  "flat_at": "23:55"
}
```
