import { Link } from "react-router";

/** An exact amount from the API, in its quote currency. */
export default function Money({
  amount,
  currency,
}: {
  amount: string | null | undefined;
  currency: string | null;
}) {
  if (amount == null) return <>—</>;
  return (
    <>
      {amount}{" "}
      {currency ?? (
        <small title="This symbol's quote currency isn't set, so its P&L can't be totalled with others">
          <Link to="/instruments">currency not set</Link>
        </small>
      )}
    </>
  );
}
