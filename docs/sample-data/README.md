# Sample data: DEMOUSDT (synthetic)

`demousdt-1h.csv` is a year of **made-up** hourly prices for a made-up symbol, DEMOUSDT:
8,760 bars from 1 January 2025 00:00 UTC to 31 December 2025 23:00 UTC. It isn't a real
market's data. Use it to learn the app, and draw no trading conclusions from it.

## How it is made

`generate.py` builds it with nothing but Python's standard library, and writes the same
bytes on every machine:

```sh
python docs/sample-data/generate.py
```

- **The price** is a seeded random walk, the same every time. It is pulled toward a level
  that starts at 100 and drifts between 93 and 117, month by month. Its closes range from
  88.93 to 122.77.
- **The volume** is higher in the European and American afternoon and on big moves.
- **Patterns are planted in it**, so that the docs' example strategies have something to find.
  The script prints where:

| Pattern | Starts (UTC) |
|---|---|
| Double bottom | 2025-01-09 16:00 |
| Breakout | 2025-01-31 03:00 |
| Double bottom | 2025-02-27 05:00 |
| Double bottom | 2025-03-25 06:00 |
| Breakout | 2025-04-13 06:00 |
| Double bottom | 2025-04-26 13:00 |
| Double bottom | 2025-05-30 22:00 |
| Breakout | 2025-06-22 06:00 |
| Breakout | 2025-09-01 01:00 |

- **Double bottom:** each one starts just after the 50-hour average crosses below 100. It
  is a slide, a low, a bounce, a second low 0.2% above the first, then a rally. The editor's
  double-bottom example wins on these by construction. That shows how the app works, not
  that the rule works on a real market.
- **Breakout:** 22 quiet hours in a 0.7% range, then a 3% rise.

## The 1-minute file

```sh
python docs/sample-data/generate.py --minutes
```

This also writes `demousdt-1m.csv`: 525,600 one-minute bars. Together they make up the
hourly bars exactly, with each hour's open, high, low, close and volume. The file is about
29 MB, so it isn't kept in the repository. Import it with the command line:

```sh
make import-csv file=docs/sample-data/demousdt-1m.csv symbol=DEMOUSDT
```

With it you can settle fills inside the hourly bars, and run the day-trading examples on
5-minute bars.

## The format

A header row, then `timestamp,open,high,low,close,volume` on each line. Timestamps are ISO
8601 in UTC, prices are to the cent and volumes to 4 decimals. The app reads the file as
generic OHLCV.
