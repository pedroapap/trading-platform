import { expect, test } from "vitest";

import { ApiError } from "./client";
import { shouldRetry } from "./queryClient";

test("a 4xx is never retried", () => {
  expect(shouldRetry(0, new ApiError(404, { detail: "Not found" }))).toBe(false);
  expect(shouldRetry(0, new ApiError(422, { detail: [] }))).toBe(false);
});

test("server and network failures are retried twice", () => {
  const unavailable = new ApiError(503, null);
  const offline = new TypeError("Failed to fetch");

  expect([0, 1, 2].map((count) => shouldRetry(count, unavailable))).toEqual([true, true, false]);
  expect(shouldRetry(0, offline)).toBe(true);
});
