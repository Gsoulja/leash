// Handoff mandate status badge (DEC-044): the word carries the status; the tone only repeats it.
export type MandateStatus = "draft" | "active" | "revoked";

export function StatusBadge({ status }: { status: MandateStatus }) {
  return <span className={`badge badge-${status}`}>{status.toUpperCase()}</span>;
}
