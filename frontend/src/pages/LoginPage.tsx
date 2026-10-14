import { useMutation } from "@tanstack/react-query";
import type { FormEvent } from "react";
import { Navigate, useLocation, type Location } from "react-router";

import { ApiError } from "../api/client";
import { logIn, useToken } from "../auth";

type Credentials = { email: string; password: string };

export default function LoginPage() {
  const token = useToken();
  const location = useLocation();
  const login = useMutation({
    mutationFn: ({ email, password }: Credentials) => logIn(email, password),
  });

  // Logged in: go where the user was going before being asked to log in.
  if (token) {
    const from = (location.state as { from?: Location } | null)?.from;
    return <Navigate to={from ?? "/"} replace />;
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    login.mutate({ email: String(fields.get("email")), password: String(fields.get("password")) });
  }

  return (
    <main className="container login">
      <article>
        <h1>Log in</h1>
        <form onSubmit={submit}>
          <label>
            Email
            <input type="email" name="email" autoComplete="username" required />
          </label>
          <label>
            Password
            <input type="password" name="password" autoComplete="current-password" required />
          </label>
          {login.error && (
            <p role="alert">
              {login.error instanceof ApiError && login.error.status === 401
                ? "Wrong email or password."
                : login.error.message}
            </p>
          )}
          <button type="submit" aria-busy={login.isPending} disabled={login.isPending}>
            Log in
          </button>
        </form>
      </article>
    </main>
  );
}
