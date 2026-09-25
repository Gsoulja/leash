// Chips in the handoff's three exclusive hues (green = within rules, violet = needs attention, red = stopped) plus the
// AGENT tag, and a neutral grey for outcomes that are none of those (no answer, not sent). The chip's words carry
// the meaning; the tone only repeats it.
import type { HTMLAttributes, ReactNode } from "react";

export type ChipTone = "allowed" | "attention" | "stopped" | "agent" | "neutral";

type Props = Omit<HTMLAttributes<HTMLSpanElement>, "className" | "children"> & { tone: ChipTone; children: ReactNode };

export function Chip({ tone, children, ...rest }: Props) {
  return <span className={`chip ${tone}`} {...rest}>{children}</span>;
}
