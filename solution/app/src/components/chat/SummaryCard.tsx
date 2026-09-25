// The consent moment's summary card (handoff V4, LEASH-191), built only from the platform draft that was posted:
// the hard stop, the uncertainty choice, questions left open, and a disclosure with every posted hard rule exactly as
// sent. There is no separate summary text that could drift from what Viseca received.
import type { HardRule, PlatformDraft } from "../../api/client";
import { LimitTile } from "../ui/LimitTile";
import { Chip } from "../ui/Chip";

const UNSURE = { ask: "ask me", decline: "decline", approve: "approve" } as const;

export function SummaryCard({ posted, limit, ruleLine }: {
  posted: PlatformDraft; limit: number | null; ruleLine: (r: HardRule) => string;
}) {
  const others = posted.hard_rules.length - (limit === null ? 0 : 1);
  return (
    <section className="summary-card" aria-label="What Viseca received" role="region">
      <div className="sum-row">
        <div className="k">What Viseca received</div>
        <Chip tone="neutral">{posted.platform_draft_id}</Chip>
      </div>
      <p className="small">This exact draft becomes your permission when you confirm. It isn't active yet.</p>
      <p className="message">{posted.instruction}</p>
      {/* Only an enforceable hard rule is a tile; guidance is never shown as enforced (DEC-044). */}
      {limit !== null && <div className="tiles"><LimitTile tone="stopped" amount={limit.toFixed(2)} /></div>}
      <p className="small">When unsure: {UNSURE[posted.uncertainty_policy]}.</p>
      {(posted.open_questions ?? []).length > 0 && (
        <>
          <p className="small">You left these optional questions open; they go to Viseca unanswered:</p>
          <ul className="notes" aria-label="Questions left open (sent as they are)">
            {posted.open_questions!.map((q) => <li key={q} className="small">{q}</li>)}
          </ul>
        </>
      )}
      {posted.guidance.length > 0 && (
        <ul className="notes" aria-label="Guidance (not enforced)">{posted.guidance.map((g) => <li key={g} className="small">{g}</li>)}</ul>
      )}
      <details className="exact-rules">
        <summary>{others > 0 ? `Exact rules (${posted.hard_rules.length}, ${others} besides the hard stop)` : `Exact rules (${posted.hard_rules.length})`}</summary>
        <ul className="rules exact" aria-label="Exact rules sent to Viseca">
          {posted.hard_rules.map((r) => <li key={ruleLine(r)}><code>{ruleLine(r)}</code></li>)}
        </ul>
      </details>
    </section>
  );
}
