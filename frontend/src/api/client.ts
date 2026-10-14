import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "./schema";
import { tokenStore } from "./token";

/** A response other than 2xx. `detail` is FastAPI's error detail: a message, or for a
 * validation error the list of problems, each with the location of its field. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, body: unknown) {
    const detail =
      typeof body === "object" && body !== null && "detail" in body ? body.detail : body;
    super(describe(status, detail));
    this.status = status;
    this.detail = detail;
  }
}

function describe(status: number, detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((problem: { msg?: string }) => problem.msg).join("; ");
  }
  return `Request failed with status ${status}`;
}

const auth: Middleware = {
  onRequest({ request }) {
    const token = tokenStore.get();
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    return request;
  },
  onResponse({ response }) {
    // The token expired or is no longer valid: log out.
    if (response.status === 401) tokenStore.clear();
    return response;
  },
};

// The API is served from the same origin: Vite forwards /api to it in development. `fetch` is
// looked up per request, so that a mock installed later (as in tests) still applies.
export const api = createClient<paths>({
  baseUrl: window.location.origin,
  fetch: (request) => globalThis.fetch(request),
});
api.use(auth);

type Result<T> =
  | { data: T; error?: never; response: Response }
  | { data?: never; error: unknown; response: Response };

/** The data of a successful response; any other response throws an ApiError. */
export async function unwrap<T>(request: Promise<Result<T>>): Promise<T> {
  const { data, error, response } = await request;
  if (!response.ok) throw new ApiError(response.status, error);
  return data as T;
}
