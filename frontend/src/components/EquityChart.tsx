import {
  ColorType,
  CrosshairMode,
  LineSeries,
  LineStyle,
  createChart,
  type AutoscaleInfo,
  type MouseEventParams,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";

import { toPlotted, type ChartPoint, type PlottedPoint } from "../chartData";
import { formatDateTime } from "../format";

export type EquityChartProps = {
  points: ChartPoint[];
  /** What the values are, for the readout and the table: "Equity". */
  label: string;
  /** A value as the readout and the table show it, with its currency. */
  format: (value: number) => string;
  /** A level drawn as a hairline, such as the initial capital; the scale always shows it. */
  reference?: { value: number; title: string };
  /** The points are events, such as closed trades, drawn one after another rather than to
   * scale in time: the time axis is hidden, and the readout gives each point's time. */
  sequence?: boolean;
  /** A second series at the same times, such as buy and hold over the same bars: drawn in the
   * palette's second color, keyed, and read out and tabled beside the first. */
  compared?: { label: string; points: ChartPoint[] };
};

const compact = new Intl.NumberFormat(undefined, {
  notation: "compact",
  maximumFractionDigits: 1,
});
const small = new Intl.NumberFormat(undefined, { maximumSignificantDigits: 4 });

// Plotted times are local times written as UTC (see toPlotted), so they are read back as UTC.
const crosshairTime = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "UTC",
});

/** Axis ticks: compact from 1,000 up (9.5K), and 4 significant digits below. */
function tick(value: number): string {
  return Math.abs(value) >= 1_000 ? compact.format(value) : small.format(value);
}

/** The page's colors for the current color scheme: the series take the dataviz palette's
 * first two slots (see app.css), while text and gridlines take Pico's muted tokens. */
function themeOf(element: HTMLElement) {
  const style = getComputedStyle(element);
  const read = (name: string) => style.getPropertyValue(name).trim();
  return {
    series: [read("--chart-series"), read("--chart-series-2")],
    ink: read("--pico-muted-color"),
    grid: read("--pico-muted-border-color"),
    surface: read("--pico-background-color"),
    font: read("--pico-font-family"),
  };
}

type Theme = ReturnType<typeof themeOf>;

function chartOptions(theme: Theme, sequence: boolean) {
  return {
    layout: {
      background: { type: ColorType.Solid, color: "transparent" },
      textColor: theme.ink,
      fontFamily: theme.font || undefined,
    },
    // Recessive chrome: solid hairlines across, none down; no frame.
    grid: {
      vertLines: { visible: false },
      horzLines: { color: theme.grid, style: LineStyle.Solid },
    },
    rightPriceScale: { borderVisible: false },
    timeScale: {
      visible: !sequence,
      borderColor: theme.grid,
      timeVisible: true,
      secondsVisible: false,
    },
    // A vertical hairline that snaps to the nearest point.
    crosshair: {
      mode: CrosshairMode.Magnet,
      vertLine: {
        color: theme.ink,
        width: 1 as const,
        style: LineStyle.Solid,
        labelBackgroundColor: theme.ink,
      },
      horzLine: { visible: false, labelVisible: false },
    },
  };
}

/** A price format fine enough for the values: the library puts ticks on multiples of its
 * minimum move, 0.01 by default, so amounts in BTC and the like would get none. */
function priceFormatFor(values: number[]) {
  const span = Math.max(...values) - Math.min(...values) || Math.max(...values.map(Math.abs)) || 1;
  const exponent = Math.min(-2, Math.floor(Math.log10(span)) - 3);
  return { type: "price" as const, precision: -exponent, minMove: 10 ** exponent };
}

/** Near-black or white, whichever has the higher contrast on `background` (#rrggbb). */
function inkOn(background: string): string {
  const [r, g, b] = [1, 3, 5].map((at) => {
    const channel = parseInt(background.slice(at, at + 2), 16) / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  // The contrasts with black and white are equal at a luminance of about 0.18.
  return luminance > 0.18 ? "#0b0b0b" : "#ffffff";
}

/** A label on the scale at a series' last value, naming it: in the series' color, with text
 * that reads on it (the library's own last-value label picks white, too faint on these). */
function endLabelOptions(theme: Theme, slot: number) {
  return {
    color: theme.series[slot],
    lineVisible: false,
    axisLabelVisible: true,
    axisLabelColor: theme.series[slot],
    axisLabelTextColor: inkOn(theme.series[slot]),
  };
}

/** The `slot`th series (0 or 1), of `points` points. */
function seriesOptions(theme: Theme, points: number, slot: number) {
  return {
    color: theme.series[slot],
    lineWidth: 2 as const,
    // A few points, such as one per trade, are marked; a single one is only its marker.
    lineVisible: points > 1,
    pointMarkersVisible: points <= 50,
    pointMarkersRadius: 4,
    // An 8px marker with a 2px ring in the surface color.
    crosshairMarkerRadius: 4,
    crosshairMarkerBorderWidth: 2,
    crosshairMarkerBorderColor: theme.surface,
    crosshairMarkerBackgroundColor: theme.series[slot],
    lastValueVisible: false,
    priceLineVisible: false,
  };
}

/** A series' key: a short stroke of its color, as its line is drawn. */
function Key({ slot }: { slot: number }) {
  return <span className={`key key-${slot + 1}`} aria-hidden="true" />;
}

/** One series over time, or two to compare: lines with the values under the pointer read out
 * above them, and the same points as a table for anyone who can't use the chart. */
export default function EquityChart({
  points,
  label,
  format,
  reference,
  sequence = false,
  compared,
}: EquityChartProps) {
  const container = useRef<HTMLDivElement>(null);
  const plotted = useMemo(() => toPlotted(points), [points]);
  const comparedPoints = compared?.points;
  const comparedLabel = compared?.label;
  const plottedCompared = useMemo(
    () => (comparedPoints ? toPlotted(comparedPoints) : []),
    [comparedPoints],
  );
  const [hovered, setHovered] = useState<PlottedPoint | null>(null);
  const [tableOpen, setTableOpen] = useState(false);
  const referenceValue = reference?.value;
  const referenceTitle = reference?.title;
  const two = plottedCompared.length > 0;

  useEffect(() => {
    const element = container.current;
    if (!element || plotted.length === 0) return;
    let theme = themeOf(element);
    const chart = createChart(element, {
      ...chartOptions(theme, sequence),
      autoSize: true,
      localization: {
        priceFormatter: tick,
        timeFormatter: (time: Time) => crosshairTime.format(new Date((time as number) * 1000)),
      },
    });
    const priceFormat = priceFormatFor([
      ...plotted.map((point) => point.value),
      ...plottedCompared.map((point) => point.value),
      ...(referenceValue === undefined ? [] : [referenceValue]),
    ]);
    const series = chart.addSeries(LineSeries, {
      ...seriesOptions(theme, plotted.length, 0),
      priceFormat,
      // Keep the reference level in view, even when every point is above or below it.
      autoscaleInfoProvider: (base: () => AutoscaleInfo | null) => {
        const info = base();
        if (info?.priceRange && referenceValue !== undefined) {
          info.priceRange.minValue = Math.min(info.priceRange.minValue, referenceValue);
          info.priceRange.maxValue = Math.max(info.priceRange.maxValue, referenceValue);
        }
        return info;
      },
    });
    series.setData(plotted);
    const second = two
      ? chart.addSeries(LineSeries, {
          ...seriesOptions(theme, plottedCompared.length, 1),
          priceFormat,
        })
      : undefined;
    second?.setData(plottedCompared);
    // Two series are each named at their last value; one is named by the readout.
    const endLabels = second
      ? [
          series.createPriceLine({
            ...endLabelOptions(theme, 0),
            price: plotted.at(-1)!.value,
            title: label,
          }),
          second.createPriceLine({
            ...endLabelOptions(theme, 1),
            price: plottedCompared.at(-1)!.value,
            title: comparedLabel,
          }),
        ]
      : [];
    const line =
      referenceValue === undefined
        ? undefined
        : series.createPriceLine({
            price: referenceValue,
            title: referenceTitle,
            color: theme.ink,
            lineWidth: 1,
            lineStyle: LineStyle.Solid,
            axisLabelVisible: true,
            axisLabelColor: theme.ink,
            axisLabelTextColor: theme.surface,
          });
    // All the points, with a little room at both ends so the edge ticks aren't cut off.
    const room = Math.max(1, Math.round(plotted.length * 0.03));
    chart.timeScale().setVisibleLogicalRange({ from: -room, to: plotted.length - 1 + room });

    const byTime = new Map(plotted.map((point) => [point.time, point]));
    const follow = (param: MouseEventParams<Time>) =>
      setHovered(
        param.time === undefined ? null : (byTime.get(param.time as UTCTimestamp) ?? null),
      );
    chart.subscribeCrosshairMove(follow);

    // Recolor when the color scheme changes.
    const scheme = window.matchMedia?.("(prefers-color-scheme: dark)");
    const restyle = () => {
      theme = themeOf(element);
      chart.applyOptions(chartOptions(theme, sequence));
      series.applyOptions(seriesOptions(theme, plotted.length, 0));
      second?.applyOptions(seriesOptions(theme, plottedCompared.length, 1));
      endLabels.forEach((endLabel, slot) => endLabel.applyOptions(endLabelOptions(theme, slot)));
      line?.applyOptions({
        color: theme.ink,
        axisLabelColor: theme.ink,
        axisLabelTextColor: theme.surface,
      });
    };
    scheme?.addEventListener("change", restyle);
    return () => {
      scheme?.removeEventListener("change", restyle);
      chart.unsubscribeCrosshairMove(follow);
      chart.remove();
    };
  }, [
    plotted,
    plottedCompared,
    two,
    label,
    comparedLabel,
    referenceValue,
    referenceTitle,
    sequence,
  ]);

  const comparedAt = useMemo(
    () => new Map(plottedCompared.map((point) => [point.time, point.value])),
    [plottedCompared],
  );
  if (plotted.length === 0) return <p>Nothing to draw yet.</p>;
  // The point under the pointer, or else the last one.
  const shown = (hovered && plotted.includes(hovered) ? hovered : null) ?? plotted.at(-1)!;
  const comparedValue = (time: UTCTimestamp) => {
    const value = comparedAt.get(time);
    return value === undefined ? "—" : format(value);
  };

  return (
    <figure className="equity-chart">
      {two ? (
        // The spaces between the flex items keep the words apart when read aloud.
        <figcaption aria-live="polite" className="keyed">
          <span>
            <Key slot={0} /> <strong>{format(shown.value)}</strong> <small>{label}</small>
          </span>{" "}
          <span>
            <Key slot={1} /> <strong>{comparedValue(shown.time)}</strong>{" "}
            <small>{comparedLabel}</small>
          </span>{" "}
          <small>{formatDateTime(shown.at)}</small>
        </figcaption>
      ) : (
        <figcaption aria-live="polite">
          <strong>{format(shown.value)}</strong>{" "}
          <small>
            {label}, {formatDateTime(shown.at)}
          </small>
        </figcaption>
      )}
      <div ref={container} className="chart" />
      <details onToggle={(event) => setTableOpen(event.currentTarget.open)}>
        <summary>{label} as a table</summary>
        {tableOpen && (
          <div className="overflow-auto">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th className="number">{label}</th>
                  {two && <th className="number">{comparedLabel}</th>}
                </tr>
              </thead>
              <tbody>
                {plotted.map((point) => (
                  <tr key={point.time}>
                    <td>{formatDateTime(point.at)}</td>
                    <td className="number">{format(point.value)}</td>
                    {two && <td className="number">{comparedValue(point.time)}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </details>
    </figure>
  );
}
