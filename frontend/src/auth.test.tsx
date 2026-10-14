import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw/http";
import { expect, test } from "vitest";

import { tokenStore } from "./api/token";
import { USER } from "./test/fixtures";
import { renderApp } from "./test/render";
import { server } from "./test/server";

/** The API's login: the right password gets a token; returns the fields it was sent. */
function loginEndpoint() {
  const sent: { fields?: URLSearchParams } = {};
  server.use(
    http.post("/api/auth/login", async ({ request }) => {
      sent.fields = new URLSearchParams(await request.text());
      if (sent.fields.get("password") !== "a-long-enough-password") {
        return HttpResponse.json({ detail: "Incorrect email or password" }, { status: 401 });
      }
      return HttpResponse.json({ access_token: "abc", token_type: "bearer" });
    }),
    http.get("/api/auth/me", () => HttpResponse.json(USER)),
  );
  return sent;
}

async function logIn(user: ReturnType<typeof renderApp>["user"], password: string) {
  await user.type(screen.getByLabelText("Email"), "trader@example.com");
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Log in" }));
}

test("a protected page without a token asks to log in", () => {
  const { router } = renderApp("/");

  expect(screen.getByRole("heading", { name: "Log in" })).toBeInTheDocument();
  expect(router.state.location.pathname).toBe("/login");
});

test("logging in posts the form and enters the app", async () => {
  const sent = loginEndpoint();
  const { user } = renderApp("/");

  await logIn(user, "a-long-enough-password");

  expect(await screen.findByText("Signed in as trader@example.com.")).toBeInTheDocument();
  expect(Object.fromEntries(sent.fields!)).toMatchObject({
    username: "trader@example.com",
    password: "a-long-enough-password",
  });
  expect(tokenStore.get()).toBe("abc");
});

test("after logging in the user returns to the page asked for", async () => {
  loginEndpoint();
  const { router, user } = renderApp("/nowhere");

  await logIn(user, "a-long-enough-password");

  expect(await screen.findByText("Page not found.")).toBeInTheDocument();
  expect(router.state.location.pathname).toBe("/nowhere");
});

test("a wrong password is refused", async () => {
  loginEndpoint();
  const { user } = renderApp("/login");

  await logIn(user, "not-the-password");

  expect(await screen.findByRole("alert")).toHaveTextContent("Wrong email or password.");
  expect(tokenStore.get()).toBeNull();
});

test("logging out returns to the login page", async () => {
  loginEndpoint();
  tokenStore.set("abc");
  const { user } = renderApp("/");
  await screen.findByText("Signed in as trader@example.com.");

  await user.click(screen.getByRole("button", { name: "Log out" }));

  expect(screen.getByRole("heading", { name: "Log in" })).toBeInTheDocument();
  expect(tokenStore.get()).toBeNull();
});

test("an expired token returns to the login page", async () => {
  tokenStore.set("expired");
  server.use(
    http.get("/api/auth/me", () =>
      HttpResponse.json({ detail: "Could not validate credentials" }, { status: 401 }),
    ),
  );

  renderApp("/");

  expect(await screen.findByRole("heading", { name: "Log in" })).toBeInTheDocument();
});
