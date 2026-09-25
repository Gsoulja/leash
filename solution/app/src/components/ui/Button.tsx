// Handoff button (DEC-044, designPrototype/Sticker Sheet.dc.html): ink primary, outlined secondary, red destructive,
// green approve, violet attention. The label is always text, so the tone never carries meaning alone.
import type { ButtonHTMLAttributes, ReactNode, Ref } from "react";

export type ButtonVariant = "primary" | "secondary" | "destructive" | "destructive-fill" | "approve" | "attention";

type Props = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className" | "children"> & {
  variant: ButtonVariant;
  /** A decision (approve, decline, confirm, revoke): at least 48px tall instead of 44px. */
  decision?: boolean;
  ref?: Ref<HTMLButtonElement>;
  children: ReactNode;
};

export function Button({ variant, decision = false, type = "button", children, ...rest }: Props) {
  return (
    <button type={type} className={`btn btn-${variant}${decision ? " btn-decision" : ""}`} {...rest}>
      {children}
    </button>
  );
}
