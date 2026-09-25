// "Added to permission" chip: the handoff's main trust device (DEC-044; "permission", not "mandate", per ruling 6).
// Label and value are always words; the tint and icon only repeat them.
import { Icon, type IconName } from "../icons";

export type RuleTone = "allowed" | "attention" | "stopped" | "neutral";

const ICON: Record<RuleTone, IconName> = { allowed: "approve", attention: "ask", stopped: "limit", neutral: "policy" };

/** `decision` names the decision-log entry a team reading comes from (e.g. DEC-013). */
export function RuleChip({ label, value, tone, decision }: { label: string; value: string; tone: RuleTone; decision?: string | null }) {
  return (
    <div className={`rule-chip ${tone}`}>
      <Icon name={ICON[tone]} />
      <div className="rule-text">
        <div className="rule-over">ADDED TO PERMISSION · {label.toUpperCase()}</div>
        <div className="rule-value">{value}{decision && <> <span className="rule-decision">{decision}</span></>}</div>
      </div>
    </div>
  );
}
