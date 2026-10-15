import { useCoverage } from "../api/marketData";
import { ErrorMessage, Loading } from "../components/Status";
import { formatCount, formatDateTime } from "../format";

export default function MarketDataPage() {
  const coverage = useCoverage();

  return (
    <>
      <h1>Market data</h1>
      <h2>Stored bars</h2>
      {coverage.isPending && <Loading />}
      {coverage.error && <ErrorMessage error={coverage.error} />}
      {coverage.data?.length === 0 && <p>No bars stored yet.</p>}
      {coverage.data && coverage.data.length > 0 && (
        <div className="overflow-auto">
          <table className="striped">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Timeframe</th>
                <th>First bar</th>
                <th>Last bar</th>
                <th className="number">Bars</th>
              </tr>
            </thead>
            <tbody>
              {coverage.data.map((entry) => (
                <tr key={`${entry.symbol} ${entry.timeframe}`}>
                  <td>{entry.symbol}</td>
                  <td>{entry.timeframe}</td>
                  <td>{formatDateTime(entry.first_ts)}</td>
                  <td>{formatDateTime(entry.last_ts)}</td>
                  <td className="number">{formatCount(entry.bars)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
