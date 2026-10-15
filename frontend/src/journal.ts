import type { components } from "./api/schema";

type Schemas = components["schemas"];

export const ENTRY_TYPES: Record<Schemas["EntryType"], string> = {
  pre_trade: "Pre-trade",
  post_trade: "Post-trade",
  note: "Note",
};

export const EMOTIONS: Schemas["Emotion"][] = [
  "calm",
  "confident",
  "excited",
  "greedy",
  "fomo",
  "fearful",
  "frustrated",
  "impatient",
  "uncertain",
];

/** "draft", or "published v3" once published. */
export function entryStatus(entry: Schemas["JournalEntryRead"]): string {
  return entry.status === "draft" ? "draft" : `published v${entry.current_version}`;
}
