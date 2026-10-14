import { ApiError } from "./client";

type Problem = { loc?: (string | number)[]; msg?: string };

/** The problems of a validation error (422) by the body field they name, such as
 * `entry_price`; the first problem of each field. Empty for any other error. */
export function fieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError) || !Array.isArray(error.detail)) return {};
  const errors: Record<string, string> = {};
  for (const { loc, msg } of error.detail as Problem[]) {
    const field = loc?.[0] === "body" ? loc.slice(1).join(".") : undefined;
    if (field && msg && !(field in errors)) errors[field] = msg;
  }
  return errors;
}
