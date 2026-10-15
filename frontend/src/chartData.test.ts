import { afterEach, expect, test, vi } from "vitest";

import { toPlotted } from "./chartData";

const seconds = (iso: string) => Date.parse(iso) / 1000;

afterEach(() => {
  vi.unstubAllEnvs();
});

test("times are shifted to read in the browser's time zone", () => {
  vi.stubEnv("TZ", "Europe/Lisbon"); // UTC+1 in summer

  const [point] = toPlotted([{ time: "2025-07-01T09:00:00Z", value: 1 }]);

  expect(point).toEqual({
    time: seconds("2025-07-01T10:00:00Z"),
    value: 1,
    at: "2025-07-01T09:00:00Z",
  });
});

test("of points at the same time, the last is kept", () => {
  vi.stubEnv("TZ", "America/New_York"); // clocks go back at 2:00 EDT on 2 Nov 2025

  const plotted = toPlotted([
    { time: "2025-11-02T04:00:00Z", value: 1 }, // 0:00 EDT
    { time: "2025-11-02T04:00:00Z", value: 2 }, // closed at the same time
    { time: "2025-11-02T05:00:00Z", value: 3 }, // 1:00 EDT
    { time: "2025-11-02T06:00:00Z", value: 4 }, // 1:00 EST again
    { time: "2025-11-02T07:00:00Z", value: 5 }, // 2:00 EST
  ]);

  expect(plotted.map((point) => point.value)).toEqual([2, 4, 5]);
});

test("a point earlier than the one before is left out", () => {
  vi.stubEnv("TZ", "America/New_York");

  const plotted = toPlotted([
    { time: "2025-11-02T05:30:00Z", value: 1 }, // 1:30 EDT
    { time: "2025-11-02T06:00:00Z", value: 2 }, // 1:00 EST, earlier on the clock
    { time: "2025-11-02T07:00:00Z", value: 3 }, // 2:00 EST
  ]);

  expect(plotted.map((point) => point.value)).toEqual([1, 3]);
});
