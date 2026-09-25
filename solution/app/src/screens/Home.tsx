// Home (LEASH-198, DEC-045/046): the handoff's V1 top — greeting, the customer's credit card and four quick actions,
// then, until a permission is active, the invitation to set up the agent — above the Cockpit's run and payments.
import { useQuery } from "@tanstack/react-query";
import { useRef } from "react";
import { api } from "../api/client";
import type { RunSelection } from "../api/useSelectedRun";
import { Icon, type IconName } from "../components/icons";
import { formatChf } from "../components/ui/LimitTile";
import { Cockpit } from "./Cockpit";

type Destination = "agent" | "rules" | "revoke";

// Demo values for the card, as in the handoff (DEC-046). No API or pack field supplies a card number or balance;
// nothing reads these except the card's own markup, and they never reach a decision.
export const DEMO_CARD = { last4: "2291", available: "4312.60", expiry: "09/29" } as const;

function CreditCard() {
  return (
    <div className="card-row">
      <section className="card-hero" aria-label="Your credit card">
        <div className="hero-top"><span className="hero-k">Credit card</span><span className="hero-chip" aria-hidden="true" /></div>
        <div className="hero-number">•••• •••• •••• {DEMO_CARD.last4}</div>
        <div className="hero-foot">
          <div><div className="hero-k">Available</div><div className="hero-v">CHF {formatChf(DEMO_CARD.available)}</div></div>
          <div className="hero-k">{DEMO_CARD.expiry}</div>
        </div>
      </section>
      <div className="card-peek" aria-hidden="true" />
    </div>
  );
}

// The handoff's agent banner in its "never started" state (DEC-046): it names the external shopping agent, whose
// rules the chat sets; Leash itself never claims to search or shop (DEC-033).
function AgentBanner({ onOpen }: { onOpen: () => void }) {
  return (
    <button type="button" className="agent-banner" onClick={onOpen}>
      <span className="banner-ico"><Icon name="agent" /></span>
      <span className="banner-text">
        <span className="banner-title">Try your new AI shopping agent</span>
        <span className="banner-sub">Set rules together in a chat</span>
      </span>
      <span className="banner-go" aria-hidden="true">›</span>
    </button>
  );
}

export function Home({ selection, onNavigate }: { selection: RunSelection; onNavigate: (to: Destination) => void }) {
  const payments = useRef<HTMLDivElement>(null);
  const mandates = useQuery({ queryKey: ["mandates"], queryFn: () => api().mandates() });
  const active = (mandates.data?.mandates ?? []).some((m) => m.mandate_id === mandates.data?.current_mandate_id && m.status === "active");
  const noPermission = mandates.isSuccess && !active;  // wait for the answer: never flash the banner at an active customer
  const tiles: { label: string; icon: IconName; dark?: boolean; go: () => void }[] = [
    { label: "Limits", icon: "limit", go: () => onNavigate("rules") },
    { label: "AI agent", icon: "agent", dark: true, go: () => onNavigate("agent") },
    { label: "Payments", icon: "report", go: () => payments.current?.scrollIntoView({ block: "start" }) },
    ...(active ? [{ label: "Revoke", icon: "freeze" as IconName, go: () => onNavigate("revoke") }] : []),
  ];
  return (
    <>
      <h1 className="greeting">Hello</h1>
      <CreditCard />
      <nav className="tiles-row" aria-label="Quick actions">
        {tiles.map((t) => (
          <button key={t.label} type="button" className={`tile-btn${t.dark ? " dark" : ""}`} onClick={t.go}>
            <span className="tile-ico"><Icon name={t.icon} /></span>
            {t.label}
          </button>
        ))}
      </nav>
      {noPermission && <AgentBanner onOpen={() => onNavigate("agent")} />}
      <div className="home-payments" ref={payments}><Cockpit selection={selection} showSpending={false} /></div>
    </>
  );
}
