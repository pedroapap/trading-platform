import { useSyncExternalStore } from "react";

import { api, unwrap } from "./api/client";
import { tokenStore } from "./api/token";

/** The stored login token. Components re-render when it changes, so logging out anywhere,
 * including through a 401, takes effect everywhere. */
export function useToken(): string | null {
  return useSyncExternalStore(tokenStore.subscribe, tokenStore.get);
}

export async function logIn(email: string, password: string): Promise<void> {
  // OAuth2's password flow: form fields, with the email as the username.
  const { access_token } = await unwrap(
    api.POST("/api/auth/login", {
      body: { username: email, password, scope: "" },
      bodySerializer: (fields) => new URLSearchParams(fields as Record<string, string>),
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    }),
  );
  tokenStore.set(access_token);
}
