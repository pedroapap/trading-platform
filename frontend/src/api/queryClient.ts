import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "./client";

/** Retry network and server failures twice, but never a 4xx: asking again won't help. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  const clientError = error instanceof ApiError && error.status < 500;
  return !clientError && failureCount < 2;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: shouldRetry } } });
}
