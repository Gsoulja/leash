import type { ReactNode } from "react";

export function PhoneFrame({ children }: { children: ReactNode }) {
  return (
    <div className="phone">
      <section className="screen" aria-label="Leash app">
        <div className="sbar" aria-hidden="true">
          <span>9:41</span>
          <span className="sig">●●● ⌁</span>
        </div>
        {children}
      </section>
    </div>
  );
}
