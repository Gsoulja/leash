// The handoff's icon set (DEC-044): 24px grid, 2px stroke, square caps. Path data is lifted from
// designPrototype/Visual System.dc.html (the 20-icon set) and the v4 prototype's icon() method, never redrawn.
// The handoff draws back and chevrons as text glyphs (‹ ⌃ ⌄), so those two are new strokes on the same grid. It has
// no close icon either; close is the cross from the handoff's decline icon, lifted as is.
import type { ReactNode } from "react";

const dot = { fill: "currentColor", stroke: "none" };

export const ICONS = {
  home: <path d="M4 10.5L12 4l8 6.5V20H4z" />,
  chat: <path d="M4 5h16v11H9l-5 4z" />,
  shield: <path d="M12 3l7 3v5.5c0 4-3 7-7 9.5-4-2.5-7-5.5-7-9.5V6l7-3z" />,
  card: <><rect x={2.5} y={5.5} width={19} height={13} rx={2.5} /><line x1={2.5} y1={10} x2={21.5} y2={10} /></>,
  lock: <><rect x={4.5} y={10.5} width={15} height={10} rx={2} /><path d="M8 10.5V7.5a4 4 0 018 0v3" /></>,
  limit: <><line x1={4} y1={16} x2={20} y2={16} /><path d="M4 16l5-5 4 3 7-7" /><line x1={20} y1={7} x2={20} y2={11} /></>,
  policy: <><rect x={4.5} y={3} width={15} height={18} rx={2} /><line x1={8} y1={8} x2={16} y2={8} /><line x1={8} y1={12} x2={16} y2={12} /><line x1={8} y1={16} x2={13} y2={16} /></>,
  approve: <><circle cx={12} cy={12} r={8.5} /><path d="M8.5 12.2l2.6 2.6 4.6-5" /></>,
  decline: <><circle cx={12} cy={12} r={8.5} /><path d="M9 9l6 6M15 9l-6 6" /></>,
  ask: <><circle cx={12} cy={12} r={8.5} /><path d="M9.6 9.6a2.5 2.5 0 114.4 1.6c-.7.9-2 1.1-2 2.4" /><line x1={12} y1={16.6} x2={12} y2={16.9} /></>,
  freeze: <><rect x={4} y={4} width={16} height={16} rx={3} /><rect x={9} y={9} width={6} height={6} rx={1} /></>,
  revoke: <><circle cx={12} cy={12} r={8.5} /><line x1={6.5} y1={6.5} x2={17.5} y2={17.5} /></>,
  log: <><rect x={4.5} y={3} width={15} height={18} rx={2} /><line x1={8} y1={8} x2={16} y2={8} /><line x1={8} y1={12} x2={14} y2={12} /><circle cx={15.5} cy={16} r={2} /></>,
  store: <><path d="M4 9l2-4h12l2 4" /><rect x={4} y={9} width={16} height={11} rx={1.5} /><line x1={10} y1={20} x2={10} y2={14} /><line x1={14} y1={20} x2={14} y2={14} /></>,
  flag: <><line x1={6} y1={3} x2={6} y2={21} /><path d="M6 4h11l-2.5 4L17 12H6" /></>,
  timer: <><circle cx={12} cy={12} r={8.5} /><path d="M12 7.5V12l3 2" /></>,
  report: <><line x1={4} y1={20} x2={20} y2={20} /><rect x={6} y={12} width={3.5} height={8} rx={0.5} /><rect x={11.5} y={8} width={3.5} height={12} rx={0.5} /><rect x={17} y={14} width={3.5} height={6} rx={0.5} /></>,
  agent: <><rect x={5} y={7} width={14} height={11} rx={3} /><circle cx={9.5} cy={12} r={1.2} {...dot} /><circle cx={14.5} cy={12} r={1.2} {...dot} /><line x1={12} y1={4} x2={12} y2={7} /></>,
  receipt: <><path d="M6 3h12v18l-3-2-3 2-3-2-3 2z" /><line x1={9.5} y1={8} x2={14.5} y2={8} /><line x1={9.5} y1={12} x2={14.5} y2={12} /></>,
  fingerprint: <><path d="M12 3.2c-4.3 0-7.2 3-7.2 7.3v4.2" /><path d="M19.2 14.7v-4.2c0-4.3-2.9-7.3-7.2-7.3" /><path d="M8.4 10.6a3.6 3.6 0 017.2 0v6.2" /><path d="M8.4 14.4v2.4" /><path d="M12 10.4v7.4" /></>,
  leash: <><rect x={3} y={6} width={18} height={12} rx={4} /><circle cx={12} cy={12} r={2.2} {...dot} /></>,
  bell: <><path d="M6 16V11a6 6 0 0112 0v5l1.5 2h-15z" /><path d="M10 20.5h4" /></>,
  check: <path d="M6 12.5l4 4 8-9" />,
  send: <path d="M4 12l16-8-6 16-2.5-6.5z" />,
  mic: <><rect x={9} y={3} width={6} height={11} rx={3} /><path d="M5.5 11a6.5 6.5 0 0013 0" /><line x1={12} y1={17.5} x2={12} y2={21} /></>,
  back: <path d="M15 5l-7 7 7 7" />,
  chevron: <path d="M9 5l7 7-7 7" />,
  close: <path d="M9 9l6 6M15 9l-6 6" />,
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof ICONS;

/** Decorative by default; pass `label` when the icon alone carries meaning. */
export function Icon({ name, label }: { name: IconName; label?: string }) {
  const a11y = label ? { role: "img", "aria-label": label } : { "aria-hidden": true as const };
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="square" strokeLinejoin="miter"
         focusable="false" {...a11y}>
      {ICONS[name]}
    </svg>
  );
}
