// Handoff limit tile (DEC-044 ruling 4): the red "Hard stop at" tile is the enforceable per-order limit; a green
// budget tile is guidance only and says so. Amounts arrive as decimal strings from the API and are formatted as
// strings, so money never passes through a float.
export type LimitTone = "allowed" | "attention" | "stopped";

const TITLE: Record<LimitTone, string> = { allowed: "Budget · guidance", attention: "Stretch up to", stopped: "Hard stop at" };

/** "1234.5" → "1'234.50". Throws on anything that is not a plain non-negative decimal with at most two places. */
export function formatChf(amount: string): string {
  const m = /^(\d+)(?:\.(\d{1,2}))?$/.exec(amount);
  if (!m) throw new Error(`not a CHF amount: ${JSON.stringify(amount)}`);
  const whole = m[1].replace(/^0+(?=\d)/, "").replace(/\B(?=(\d{3})+$)/g, "'");
  return `${whole}.${(m[2] ?? "").padEnd(2, "0")}`;
}

export function LimitTile({ tone, amount, title = TITLE[tone] }: { tone: LimitTone; amount: string; title?: string }) {
  const value = `CHF ${formatChf(amount)}`;
  return (
    <div className={`tile tile-${tone}`} role="group" aria-label={`${title} ${value}`}>
      <div className="tile-over">{title}</div>
      <div className="tile-amt">{value}</div>
    </div>
  );
}
