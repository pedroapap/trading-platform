import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { MouseEventParams, Time } from "lightweight-charts";
import { beforeEach, expect, test, vi } from "vitest";

import EquityChart from "./EquityChart";

// jsdom has no canvas: the library is replaced by a recording stand-in.
const { chart, series } = vi.hoisted(() => {
  type Options = Record<string, unknown>;
  const series = {
    setData: vi.fn<(data: unknown[]) => void>(),
    applyOptions: vi.fn<(options: Options) => void>(),
    createPriceLine: vi.fn<(options: Options) => { applyOptions: (options: Options) => void }>(
      () => ({ applyOptions: vi.fn<(options: Options) => void>() }),
    ),
  };
  const chart = {
    addSeries: vi.fn<(definition: unknown, options: Options) => typeof series>(() => series),
    timeScale: vi.fn<() => { setVisibleLogicalRange: (range: object) => void }>(() => ({
      setVisibleLogicalRange: vi.fn<(range: object) => void>(),
    })),
    subscribeCrosshairMove: vi.fn<(handler: (param: MouseEventParams<Time>) => void) => void>(),
    unsubscribeCrosshairMove: vi.fn<(handler: unknown) => void>(),
    applyOptions: vi.fn<(options: Options) => void>(),
    remove: vi.fn<() => void>(),
  };
  return { chart, series };
});

vi.mock("lightweight-charts", async (importOriginal) => ({
  ...(await importOriginal<typeof import("lightweight-charts")>()),
  createChart: vi.fn<() => typeof chart>(() => chart),
}));

const POINTS = [
  { time: "2025-01-01T00:00:00Z", value: 10_000 },
  { time: "2025-01-01T01:00:00Z", value: 10_000 },
  { time: "2025-01-02T00:00:00Z", value: 10_500.25 },
];

const seconds = (iso: string) => Date.parse(iso) / 1000;

function renderChart() {
  return render(
    <EquityChart
      points={POINTS}
      label="Equity"
      format={(value) => `${value} USDT`}
      reference={{ value: 10_000, title: "Initial capital" }}
    />,
  );
}

beforeEach(() => vi.clearAllMocks());

test("the points are drawn with the reference line, and the last one is read out", () => {
  renderChart();

  expect(series.setData).toHaveBeenCalledWith(
    POINTS.map((point) => ({
      time: seconds(point.time),
      value: point.value,
      at: point.time,
    })),
  );
  expect(series.createPriceLine).toHaveBeenCalledWith(
    expect.objectContaining({ price: 10_000, title: "Initial capital" }),
  );
  expect(screen.getByRole("figure")).toHaveTextContent(
    "10500.25 USDT Equity, Jan 2, 2025, 12:00 AM",
  );
});

test("the readout follows the crosshair, and returns to the last point", () => {
  renderChart();
  const [[follow]] = chart.subscribeCrosshairMove.mock.calls;
  const caption = () => screen.getByRole("figure").querySelector("figcaption");

  act(() => follow({ time: seconds(POINTS[1].time) as Time } as MouseEventParams<Time>));
  expect(caption()).toHaveTextContent("10000 USDT Equity, Jan 1, 2025, 1:00 AM");

  act(() => follow({} as MouseEventParams<Time>));
  expect(caption()).toHaveTextContent("10500.25 USDT Equity, Jan 2, 2025, 12:00 AM");
});

test("the points are also a table", async () => {
  renderChart();

  await userEvent.click(screen.getByText("Equity as a table"));

  const rows = screen.getAllByRole("row").slice(1);
  expect(rows.map((row) => row.textContent)).toEqual([
    "Jan 1, 2025, 12:00 AM10000 USDT",
    "Jan 1, 2025, 1:00 AM10000 USDT",
    "Jan 2, 2025, 12:00 AM10500.25 USDT",
  ]);
});

// Buy and hold at the times of POINTS, but for the first.
const HELD = [
  { time: "2025-01-01T01:00:00Z", value: 9_950 },
  { time: "2025-01-02T00:00:00Z", value: 10_100 },
];

function renderTwo() {
  return render(
    <EquityChart
      points={POINTS}
      label="Equity"
      format={(value) => `${value} USDT`}
      compared={{ label: "Buy and hold", points: HELD }}
    />,
  );
}

test("a second series is drawn too, each named on the scale at its last value", () => {
  renderTwo();

  expect(chart.addSeries).toHaveBeenCalledTimes(2);
  expect(series.setData).toHaveBeenLastCalledWith(
    HELD.map((point) => ({ time: seconds(point.time), value: point.value, at: point.time })),
  );
  expect(series.createPriceLine.mock.calls.map(([options]) => options)).toEqual([
    expect.objectContaining({ price: 10_500.25, title: "Equity", lineVisible: false }),
    expect.objectContaining({ price: 10_100, title: "Buy and hold", lineVisible: false }),
  ]);
});

test("one series alone is not named on the scale: the readout names it", () => {
  renderChart();

  expect(chart.addSeries).toHaveBeenCalledTimes(1);
  // The initial capital's line only.
  expect(series.createPriceLine).toHaveBeenCalledTimes(1);
});

test("both values are read out, keyed, at the time under the pointer", () => {
  renderTwo();
  const [[follow]] = chart.subscribeCrosshairMove.mock.calls;
  const caption = () => screen.getByRole("figure").querySelector("figcaption")!;

  expect(caption()).toHaveTextContent(
    "10500.25 USDT Equity 10100 USDT Buy and hold Jan 2, 2025, 12:00 AM",
  );
  expect(caption().querySelectorAll(".key")).toHaveLength(2);

  act(() => follow({ time: seconds(POINTS[0].time) as Time } as MouseEventParams<Time>));
  expect(caption()).toHaveTextContent("10000 USDT Equity — Buy and hold Jan 1, 2025, 12:00 AM");
});

test("the table has a column for the second series", async () => {
  renderTwo();

  await userEvent.click(screen.getByText("Equity as a table"));

  const [header, ...rows] = screen.getAllByRole("row");
  expect(header).toHaveTextContent("TimeEquityBuy and hold");
  expect(rows.map((row) => row.textContent)).toEqual([
    "Jan 1, 2025, 12:00 AM10000 USDT—",
    "Jan 1, 2025, 1:00 AM10000 USDT9950 USDT",
    "Jan 2, 2025, 12:00 AM10500.25 USDT10100 USDT",
  ]);
});

test("the chart goes away with the component", () => {
  const { unmount } = renderChart();

  unmount();

  expect(chart.unsubscribeCrosshairMove).toHaveBeenCalled();
  expect(chart.remove).toHaveBeenCalled();
});

test("without points there is nothing to draw", () => {
  render(<EquityChart points={[]} label="Equity" format={String} />);

  expect(screen.getByText("Nothing to draw yet.")).toBeInTheDocument();
  expect(chart.addSeries).not.toHaveBeenCalled();
});

test("the scale keeps the reference level in view", () => {
  renderChart();
  const [[, options]] = chart.addSeries.mock.calls;
  const provider = options.autoscaleInfoProvider as (
    base: () => { priceRange: { minValue: number; maxValue: number } },
  ) => { priceRange: { minValue: number; maxValue: number } };

  // Every point above the initial capital of 10,000: the scale still reaches down to it.
  expect(provider(() => ({ priceRange: { minValue: 10_200, maxValue: 10_800 } }))).toEqual({
    priceRange: { minValue: 10_000, maxValue: 10_800 },
  });
});

test("points that are events have no time axis", async () => {
  const { createChart } = await import("lightweight-charts");
  render(<EquityChart points={POINTS} label="Realized P&L" format={String} sequence />);

  expect(vi.mocked(createChart).mock.lastCall?.[1]).toMatchObject({
    timeScale: { visible: false },
  });
});

test("small amounts get ticks, and a single point is only its marker", () => {
  render(
    <EquityChart
      points={[{ time: "2025-01-01T00:00:00Z", value: 0.0045 }]}
      label="Realized P&L"
      format={String}
      reference={{ value: 0, title: "Break-even" }}
    />,
  );

  expect(chart.addSeries.mock.lastCall?.[1]).toMatchObject({
    priceFormat: { type: "price", precision: 6, minMove: 1e-6 },
    lineVisible: false,
    pointMarkersVisible: true,
  });
});

test("large amounts keep cent ticks", () => {
  renderChart();

  expect(chart.addSeries.mock.lastCall?.[1]).toMatchObject({
    priceFormat: { precision: 2, minMove: 0.01 },
    lineVisible: true,
  });
});
