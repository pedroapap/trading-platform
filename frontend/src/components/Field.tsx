import { useId, type InputHTMLAttributes } from "react";

type Props = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  name: string;
  // What the field is for, shown under it unless there is an error.
  hint?: string;
  // The server's complaint about this field, shown under it.
  error?: string;
};

/** A labelled input that shows its validation error, or else its hint. */
export default function Field({ label, hint, error, ...input }: Props) {
  const id = useId();
  const note = error ?? hint;
  return (
    <div>
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        {...input}
        aria-invalid={error ? true : undefined}
        aria-describedby={note ? `${id}-note` : undefined}
      />
      {note && <small id={`${id}-note`}>{note}</small>}
    </div>
  );
}
