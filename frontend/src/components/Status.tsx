export function Loading() {
  return <p aria-busy="true">Loading…</p>;
}

export function ErrorMessage({ error }: { error: Error }) {
  return <p role="alert">{error.message}</p>;
}
