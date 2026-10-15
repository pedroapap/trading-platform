import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";

import { api, unwrap } from "../api/client";
import StrategyForm, { type StrategyFields } from "../components/StrategyForm";
import { EXAMPLES, STARTER_DEFINITION } from "../strategies";

export default function NewStrategyPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const create = useMutation({
    mutationFn: (fields: StrategyFields) => unwrap(api.POST("/api/strategies", { body: fields })),
    onSuccess: async (strategy) => {
      await queryClient.invalidateQueries({ queryKey: ["strategies"] });
      navigate(`/strategies/${strategy.id}`);
    },
  });

  return (
    <>
      <p>
        <Link to="/strategies">← Strategies</Link>
      </p>
      <h1>New strategy</h1>
      <StrategyForm
        initial={{ name: "", description: null, definition: STARTER_DEFINITION }}
        examples={EXAMPLES}
        submitLabel="Create strategy"
        pending={create.isPending}
        error={create.error}
        onSubmit={(fields) => create.mutate(fields)}
      />
    </>
  );
}
