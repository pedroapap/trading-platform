import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";

import { tokenStore } from "../api/token";
import { routes } from "../routes";

/** Renders the whole app at `path`, with a fresh query cache that never retries. */
export function renderApp(path = "/") {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { router, user };
}

/** Renders the app logged in, at `path`. */
export function renderPage(path: string) {
  tokenStore.set("token");
  return renderApp(path);
}
