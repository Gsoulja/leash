// The permission bar under the chat header (handoff V4, LEASH-191): state tint, the draft's own rule count (never a
// fixed "of 7"), and the rules on demand.
import { useState } from "react";

export function MandateBar({ state, rules }: { state: "draft" | "active"; rules: string[] }) {
  const [open, setOpen] = useState(false);
  const count = `${rules.length} ${rules.length === 1 ? "rule" : "rules"}`;
  return (
    <div className={`mandate-bar ${state}`}>
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span>{state === "active" ? "Permission active" : "Permission draft"} · {count}</span>
        <span aria-hidden="true">{open ? "⌃" : "⌄"}</span>
      </button>
      {open && <ul aria-label="Rules in this permission">{rules.map((r) => <li key={r}>{r}</li>)}</ul>}
    </div>
  );
}
