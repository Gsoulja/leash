// The icon set of designPrototype/Visual System.dc.html: a 24px grid, 2px stroke, square caps, the bracket
// motif of the logo. Filled shapes only for the decision dots. Stroke stays 2px at every size.
import type { ReactNode } from "react";

const dot = (cx: number, cy: number, r: number) => <circle cx={cx} cy={cy} r={r} fill="currentColor" stroke="none" />;

const GLYPHS = {
  leash: <><rect x={3} y={6} width={18} height={12} rx={4} />{dot(12, 12, 2.2)}</>,
  card: <><rect x={2.5} y={5.5} width={19} height={13} rx={2.5} /><path d="M2.5 10h19" /></>,
  virtualCard: <><rect x={2.5} y={5.5} width={19} height={13} rx={2.5} /><path d="M2.5 10h19M7 14.5h4" /></>,
  shield: <path d="M12 3l7 3v5.5c0 4-3 7-7 9.5-4-2.5-7-5.5-7-9.5V6l7-3z" />,
  lock: <><rect x={4.5} y={10.5} width={15} height={10} rx={2} /><path d="M8 10.5V7.5a4 4 0 018 0v3" /></>,
  limit: <path d="M4 16h16M4 16l5-5 4 3 7-7M20 7v4" />,
  policy: <><rect x={4.5} y={3} width={15} height={18} rx={2} /><path d="M8 8h8M8 12h8M8 16h5" /></>,
  approve: <><circle cx={12} cy={12} r={8.5} /><path d="M8.5 12.2l2.6 2.6 4.6-5" /></>,
  decline: <><circle cx={12} cy={12} r={8.5} /><path d="M9 9l6 6M15 9l-6 6" /></>,
  ask: <><circle cx={12} cy={12} r={8.5} /><path d="M9.6 9.6a2.5 2.5 0 114.4 1.6c-.7.9-2 1.1-2 2.4M12 16.6v.3" /></>,
  freeze: <><rect x={4} y={4} width={16} height={16} rx={3} /><rect x={9} y={9} width={6} height={6} rx={1} /></>,
  revoke: <><circle cx={12} cy={12} r={8.5} /><path d="M6.5 6.5l11 11" /></>,
  log: <><rect x={4.5} y={3} width={15} height={18} rx={2} /><path d="M8 8h8M8 12h6" /><circle cx={15.5} cy={16} r={2} /></>,
  merchant: <><path d="M4 9l2-4h12l2 4M10 20v-6M14 20v-6" /><rect x={4} y={9} width={16} height={11} rx={1.5} /></>,
  flag: <path d="M6 3v18M6 4h11l-2.5 4L17 12H6" />,
  timer: <><circle cx={12} cy={12} r={8.5} /><path d="M12 7.5V12l3 2" /></>,
  report: <><path d="M4 20h16" /><rect x={6} y={12} width={3.5} height={8} rx={0.5} /><rect x={11.5} y={8} width={3.5} height={12} rx={0.5} /><rect x={17} y={14} width={3.5} height={6} rx={0.5} /></>,
  home: <path d="M4 10.5L12 4l8 6.5V20H4z" />,
  agent: <><rect x={5} y={7} width={14} height={11} rx={3} />{dot(9.5, 12, 1.2)}{dot(14.5, 12, 1.2)}<path d="M12 4v3" /></>,
  receipt: <path d="M6 3h12v18l-3-2-3 2-3-2-3 2zM9.5 8h5M9.5 12h5" />,
  biometric: <path d="M12 3.2c-4.3 0-7.2 3-7.2 7.3v4.2M19.2 14.7v-4.2c0-4.3-2.9-7.3-7.2-7.3M8.4 10.6a3.6 3.6 0 017.2 0v6.2M8.4 14.4v2.4M12 10.4v7.4" />,
  // Utility glyphs in the same geometry: navigation and sending, which the set has no mark for.
  back: <path d="M14.5 5.5L8 12l6.5 6.5" />,
  send: <path d="M12 19.5V5M6 11l6-6 6 6" />,
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof GLYPHS;

/** Decorative by default: every icon in the product sits beside a word that carries its meaning. */
export function Icon({ name, size = 24, className }: { name: IconName; size?: 16 | 20 | 24 | 32; className?: string }) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth={2} strokeLinecap="square" strokeLinejoin="miter" aria-hidden="true" focusable="false">
      {GLYPHS[name]}
    </svg>
  );
}

export type LogoState = "active" | "idle" | "frozen";

/** The mark: a closed bracket around one point. The dot is a status — green while a leash is active, grey when
 *  none is, red only when spending is frozen. `onDark` is the app-icon variant, white bracket on ink. */
export function LogoMark({ state = "active", size = 24, onDark = false }: { state?: LogoState; size?: number; onDark?: boolean }) {
  return (
    <svg className={`logo-mark ${state}${onDark ? " on-dark" : ""}`} width={size} height={size} viewBox="0 0 52 52"
         fill="none" aria-hidden="true" focusable="false">
      <path d="M2 14A12 12 0 0114 2h24a12 12 0 0112 12M2 38a12 12 0 0012 12h24a12 12 0 0012-12"
            stroke="currentColor" strokeWidth={4} />
      <circle className="logo-dot" cx={26} cy={26} r={7} />
    </svg>
  );
}

/** The lockup: mark plus the "Wallet Control" wordmark, with the tagline where there is room for it. */
export function Logo({ state = "active", tagline = false }: { state?: LogoState; tagline?: boolean }) {
  return (
    <span className="logo">
      <LogoMark state={state} size={tagline ? 36 : 24} />
      <span className="logo-words">
        <span className="logo-name">Wallet Control</span>
        {tagline && <span className="logo-tagline">Agent on the leash</span>}
      </span>
    </span>
  );
}
