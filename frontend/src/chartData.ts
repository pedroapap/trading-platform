import type { UTCTimestamp } from "lightweight-charts";

/** A value at a time from the API (ISO, in UTC). */
export type ChartPoint = { time: string; value: number };

/** A point as the chart draws it, keeping the API's time for readouts. */
export type PlottedPoint = { time: UTCTimestamp; value: number; at: string };

/** The chart draws every time as UTC, so each is shifted to read in the browser's time zone,
 * as the library's docs advise. Times must then strictly increase: of points at the same time
 * (trades closed together, or an hour repeated when clocks go back) the last is kept, as it
 * is the state after all of them; a point earlier than the one before is left out. */
export function toPlotted(points: ChartPoint[]): PlottedPoint[] {
  const plotted: PlottedPoint[] = [];
  for (const point of points) {
    const date = new Date(point.time);
    const local =
      Date.UTC(
        date.getFullYear(),
        date.getMonth(),
        date.getDate(),
        date.getHours(),
        date.getMinutes(),
        date.getSeconds(),
      ) / 1000;
    const previous = plotted.at(-1);
    if (previous && local < previous.time) continue;
    if (previous && local === previous.time) plotted.pop();
    plotted.push({ time: local as UTCTimestamp, value: point.value, at: point.time });
  }
  return plotted;
}
