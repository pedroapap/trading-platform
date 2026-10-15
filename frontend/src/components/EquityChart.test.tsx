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
