import { useId, type InputHTMLAttributes } from "react";

type Props = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  name: string;
  // The server's complaint about this field, shown under it.
  error?: string;
};

/** A labelled input that shows its validation error. */
export default function Field({ label, error, ...input }: Props) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        {...input}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
      />
      {error && <small id={`${id}-error`}>{error}</small>}
    </div>
  );
}
