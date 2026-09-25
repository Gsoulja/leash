// The handoff's logo (DEC-044, designPrototype/Visual System.dc.html): a bracket around a dot. The dot is a status
// light for the agent's permission; the accessible name says the status in words, so colour never carries it alone.
import { useId } from "react";

export type LogoStatus = "none" | "active" | "revoked";

const DOT: Record<LogoStatus, string> = { none: "var(--hf-muted)", active: "var(--hf-allowed)", revoked: "var(--hf-stopped)" };

export function LogoMark({ status, onDark = false, size = 28 }: { status: LogoStatus; onDark?: boolean; size?: number }) {
  const mask = `logo-${useId().replace(/[^\w-]/g, "")}`;  // useId's colons would break url(#…) in some browsers
  const fill = status === "active" && onDark ? "var(--hf-on-dark)" : DOT[status];
  // Drawn on the handoff's 52px construction: a 4px rounded square, opened at the middle of each side, and a 14px dot.
  return (
    <svg className="logo-mark" viewBox="0 0 52 52" width={size} height={size} role="img" aria-label={`Agent permission: ${status}`}
         focusable="false">
      <mask id={mask}>
        <rect width={52} height={52} fill="#fff" />
        <rect x={0} y={14} width={14} height={24} fill="#000" />
        <rect x={38} y={14} width={14} height={24} fill="#000" />
      </mask>
      <rect x={2} y={2} width={48} height={48} rx={12} fill="none" stroke="currentColor" strokeWidth={4} mask={`url(#${mask})`} />
      <circle cx={26} cy={26} r={7} style={{ fill }} />
    </svg>
  );
}
