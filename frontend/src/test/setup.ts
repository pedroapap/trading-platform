import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "./server";

// A request without a handler fails the test instead of reaching the network.
beforeAll(() => server.listen({ onUnhandledFrame: "error" }));

afterEach(() => {
  // Without Vitest globals, Testing Library can't register its own cleanup.
  cleanup();
  server.resetHandlers();
  localStorage.clear();
});

afterAll(() => server.close());
