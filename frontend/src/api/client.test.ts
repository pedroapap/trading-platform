import { http, HttpResponse } from "msw/http";
import { expect, test, vi } from "vitest";

import { server } from "../test/server";
import { ApiError, api, unwrap } from "./client";
import type { components } from "./schema";
import { tokenStore } from "./token";

const USER: components["schemas"]["UserRead"] = {
  id: "0b4a6a4e-1c2d-4a1f-9e1b-2f6f1e0c9d11",
  email: "trader@example.com",
  is_active: true,
  created_at: "2026-01-05T14:30:00Z",
};

/** Answers /api/auth/me with `response`, keeping the Authorization header it was sent. */
function me(response = HttpResponse.json(USER)) {
  const sent: { authorization?: string | null } = {};
  server.use(
    http.get("/api/auth/me", ({ request }) => {
      sent.authorization = request.headers.get("Authorization");
      return response;
    }),
  );
  return sent;
}

test("a stored token is sent as a bearer token", async () => {
  tokenStore.set("abc");
  const sent = me();

  const user = await unwrap(api.GET("/api/auth/me"));

  expect(sent.authorization).toBe("Bearer abc");
  expect(user.email).toBe("trader@example.com");
});

test("without a token no authorization is sent", async () => {
  const sent = me();

  await api.GET("/api/auth/me");

  expect(sent.authorization).toBeNull();
});

test("a 401 clears the token and tells its subscribers", async () => {
  tokenStore.set("expired");
  me(HttpResponse.json({ detail: "Could not validate credentials" }, { status: 401 }));
  const listener = vi.fn<() => void>();
  const unsubscribe = tokenStore.subscribe(listener);

  await expect(unwrap(api.GET("/api/auth/me"))).rejects.toMatchObject({ status: 401 });

  expect(tokenStore.get()).toBeNull();
  expect(listener).toHaveBeenCalled();
  unsubscribe();
});

test("an error's message is FastAPI's detail", async () => {
  me(HttpResponse.json({ detail: "Trade not found" }, { status: 404 }));

  const error = await unwrap(api.GET("/api/auth/me")).catch((caught: unknown) => caught);

  expect(error).toBeInstanceOf(ApiError);
  expect(error).toMatchObject({ status: 404, message: "Trade not found" });
});

test("a validation error's message lists its problems", async () => {
  const detail = [
    { loc: ["body", "entry_price"], msg: "Input should be greater than 0", type: "greater_than" },
    { loc: ["body", "symbol"], msg: "Field required", type: "missing" },
  ];
  me(HttpResponse.json({ detail }, { status: 422 }));

  const error = await unwrap(api.GET("/api/auth/me")).catch((caught: unknown) => caught);

  expect(error).toMatchObject({
    status: 422,
    message: "Input should be greater than 0; Field required",
    detail,
  });
});
