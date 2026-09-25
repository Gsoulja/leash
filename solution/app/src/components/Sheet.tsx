// Bottom sheet for a deliberate decision (handoff V7, DEC-044): a modal dialog over a dim that does NOT dismiss on
// tap, so the customer has to choose. Escape cancels. Focus starts on `initialFocus`, stays inside while open, and
// goes back to whatever opened the sheet when it closes (the same trap as PaymentDetail).
import { useEffect, useId, useRef, type ReactNode, type RefObject } from "react";

export function Sheet({ title, onCancel, initialFocus, children }: {
  title: string; onCancel: () => void; initialFocus?: RefObject<HTMLElement | null>; children: ReactNode;
}) {
  const dialog = useRef<HTMLDivElement>(null);
  const heading = useId();
  const cancel = useRef(onCancel);
  cancel.current = onCancel;

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    (initialFocus?.current ?? dialog.current)?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        cancel.current();
        return;
      }
      if (e.key !== "Tab" || !dialog.current) return;
      const focusable = [...dialog.current.querySelectorAll<HTMLElement>("button:not(:disabled), [href], [tabindex]:not([tabindex='-1'])")];
      if (!focusable.length) return;
      const first = focusable[0], last = focusable[focusable.length - 1];
      const inside = dialog.current.contains(document.activeElement) && document.activeElement !== dialog.current;
      if (e.shiftKey && (document.activeElement === first || !inside)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && (document.activeElement === last || !inside)) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      if (opener?.isConnected) opener.focus();  // back to the opener, if it is still on the page
    };
  }, []);  // once per opening

  return (
    <div className="scrim dim-45">  {/* no onClick: tapping the dim never dismisses */}
      <div className="sheet sheet-v7" role="dialog" aria-modal="true" aria-labelledby={heading} tabIndex={-1} ref={dialog}>
        <div className="grab" aria-hidden="true" />
        <h2 id={heading} className="sheet-title">{title}</h2>
        {children}
      </div>
    </div>
  );
}
