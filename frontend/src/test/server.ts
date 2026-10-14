import { setupServer } from "msw/node";

/** The mocked API: each test adds the handlers it needs with `server.use()`. */
export const server = setupServer();
