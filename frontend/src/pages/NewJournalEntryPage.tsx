import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router";

import { api, unwrap } from "../api/client";
import JournalEntryForm, { type JournalContent } from "../components/JournalEntryForm";

export default function NewJournalEntryPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  // Writing about a trade: its page links here with ?trade=<id>.
  const [params] = useSearchParams();
  const create = useMutation({
    mutationFn: (content: JournalContent) => unwrap(api.POST("/api/journal", { body: content })),
    onSuccess: async (entry) => {
      await queryClient.invalidateQueries({ queryKey: ["journal"] });
      navigate(`/journal/${entry.id}`);
    },
  });

  return (
    <>
      <p>
        <Link to="/journal">← Journal</Link>
      </p>
      <h1>New journal entry</h1>
      <JournalEntryForm
        initial={{
          trade_id: params.get("trade"),
          entry_type: params.get("trade") ? "post_trade" : undefined,
        }}
        submitLabel="Save draft"
        pending={create.isPending}
        error={create.error}
        onSubmit={(content) => create.mutate(content)}
      />
    </>
  );
}
