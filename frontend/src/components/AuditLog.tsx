import type { components } from "../api/schema";
import { formatDateTime } from "../format";

type AuditEvent = components["schemas"]["AuditEventRead"];

const EVENTS: Record<AuditEvent["event_type"], string> = {
  entry: "Entered",
  update: "Edited",
  exit: "Closed",
  cancel: "Cancelled",
  correction: "Corrected",
};

function show(field: string, value: unknown): string {
  if (value == null) return "—";
  return field.endsWith("_time") ? formatDateTime(String(value)) : String(value);
}

/** Each field an event set, with its previous value when it had one. */
function Changes({ event }: { event: AuditEvent }) {
  const old = event.old_values ?? {};
  const fields = Object.entries(event.new_values ?? {}).filter(
    ([field, value]) => value != null || old[field] != null,
  );
  return (
    <ul>
      {fields.map(([field, value]) => (
        <li key={field}>
          {field.replaceAll("_", " ")}:{" "}
          {event.old_values
            ? `${show(field, old[field])} → ${show(field, value)}`
            : show(field, value)}
        </li>
      ))}
    </ul>
  );
}

/** A trade's audit trail, oldest first. */
export default function AuditLog({ events }: { events: AuditEvent[] }) {
  return (
    <div className="overflow-auto">
      <table>
        <thead>
          <tr>
            <th>When</th>
            <th>Event</th>
            <th>Changes</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {events.map((event) => (
            <tr key={event.id}>
              <td>{formatDateTime(event.created_at)}</td>
              <td>{EVENTS[event.event_type]}</td>
              <td className="wrap">
                <Changes event={event} />
              </td>
              <td className="wrap">{event.change_reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
