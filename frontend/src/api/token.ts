// The login token, kept in localStorage. Subscribers hear every change, so a 401 that clears
// the token logs the whole app out.

const KEY = "trading-platform.token";
const listeners = new Set<() => void>();

function changed(): void {
  for (const listener of listeners) listener();
}

export const tokenStore = {
  get(): string | null {
    return localStorage.getItem(KEY);
  },
  set(token: string): void {
    localStorage.setItem(KEY, token);
    changed();
  },
  clear(): void {
    localStorage.removeItem(KEY);
    changed();
  },
  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },
};
