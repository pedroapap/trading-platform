import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { useStrategy, useStrategyVersions } from "../api/strategies";
import { ErrorMessage, Loading } from "../components/Status";
import StrategyForm, { type StrategyFields } from "../components/StrategyForm";
import { formatDateTime } from "../format";

type Strategy = components["schemas"]["StrategyRead"];

function Json({ value }: { value: unknown }) {
  return (
    <pre>
      <code>{JSON.stringify(value, null, 2)}</code>
    </pre>
  );
}

/** Renaming and re-describing change the strategy in place; a changed definition is saved
 * as its next version. */
function EditStrategy({ strategy }: { strategy: Strategy }) {
  const queryClient = useQueryClient();
  const edit = useMutation({
    mutationFn: (fields: StrategyFields) =>
      unwrap(
        api.PATCH("/api/strategies/{strategy_id}", {
          params: { path: { strategy_id: strategy.id } },
          body: fields,
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["strategies"] }),
  });
  // A save that changes something remounts this form, which closes it.
  const unchanged = edit.data?.updated_at === strategy.updated_at;

  return (
    <details>
      <summary role="button" className="secondary outline">
        Edit strategy
      </summary>
      <StrategyForm
        initial={strategy}
        submitLabel="Save changes"
        pending={edit.isPending}
        error={edit.error}
        onSubmit={(fields) => edit.mutate(fields)}
      >
        <p>
          <small>
            A changed definition is saved as version {strategy.current_version + 1}; earlier
            versions stay as they were, with their backtests.
          </small>
        </p>
        {unchanged && <p role="alert">Nothing changed.</p>}
      </StrategyForm>
    </details>
  );
}

/** Every version of the definition, oldest first, each opening to the definition. */
function VersionHistory({ strategyId }: { strategyId: string }) {
  const versions = useStrategyVersions(strategyId);
  if (versions.isPending) return <Loading />;
  if (versions.error) return <ErrorMessage error={versions.error} />;
  return versions.data.map((version) => (
    <details key={version.version} className="version">
      <summary>
        v{version.version}, {formatDateTime(version.created_at)}:{" "}
        {version.changed_fields ? `changed ${version.changed_fields.join(", ")}` : "created"}
      </summary>
      <Json value={version.definition} />
    </details>
  ));
}

export default function StrategyPage() {
  const { strategyId = "" } = useParams();
  const strategy = useStrategy(strategyId);

  return (
    <>
      <p>
        <Link to="/strategies">← Strategies</Link>
      </p>
      {strategy.isPending && <Loading />}
      {strategy.error && <ErrorMessage error={strategy.error} />}
      {strategy.data && (
        <>
          <h1>{strategy.data.name}</h1>
          <p>
            v{strategy.data.current_version} · {strategy.data.definition.direction}
          </p>
          {strategy.data.description && <p className="prose">{strategy.data.description}</p>}
          <Json value={strategy.data.definition} />
          <EditStrategy key={strategy.data.updated_at} strategy={strategy.data} />
          <h2>History</h2>
          <VersionHistory strategyId={strategy.data.id} />
        </>
      )}
    </>
  );
}
