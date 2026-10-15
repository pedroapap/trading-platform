import { Link } from "react-router";

import { useStrategies } from "../api/strategies";
import { ErrorMessage, Loading } from "../components/Status";
import { formatDateTime } from "../format";

export default function StrategiesPage() {
  const strategies = useStrategies();

  return (
    <>
      <h1>Strategies</h1>
      <p>
        <Link to="/strategies/new" role="button">
          New strategy
        </Link>
      </p>
      {strategies.isPending && <Loading />}
      {strategies.error && <ErrorMessage error={strategies.error} />}
      {strategies.data?.length === 0 && <p>No strategies yet.</p>}
      {strategies.data && strategies.data.length > 0 && (
        <div className="overflow-auto">
          <table className="striped">
            <thead>
              <tr>
                <th>Name</th>
                <th>Direction</th>
                <th>Version</th>
                <th>Changed</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              {strategies.data.map((strategy) => (
                <tr key={strategy.id}>
                  <td>{strategy.name}</td>
                  <td>{strategy.definition.direction}</td>
                  <td>v{strategy.current_version}</td>
                  <td>{formatDateTime(strategy.updated_at)}</td>
                  <td className="wrap">{strategy.description ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
