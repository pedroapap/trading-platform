/** "51–100 of 120" with previous and next buttons, for a page of `limit` items from `offset`. */
export default function Pagination({
  offset,
  limit,
  total,
  onPage,
}: {
  offset: number;
  limit: number;
  total: number;
  onPage: (offset: number) => void;
}) {
  const last = Math.min(offset + limit, total);
  return (
    <nav aria-label="Pages">
      <ul>
        <li>{total === 0 ? "None" : `${offset + 1}–${last} of ${total}`}</li>
      </ul>
      <ul>
        <li>
          <button
            type="button"
            className="secondary outline"
            disabled={offset === 0}
            onClick={() => onPage(Math.max(0, offset - limit))}
          >
            Previous
          </button>
        </li>
        <li>
          <button
            type="button"
            className="secondary outline"
            disabled={last >= total}
            onClick={() => onPage(offset + limit)}
          >
            Next
          </button>
        </li>
      </ul>
    </nav>
  );
}
