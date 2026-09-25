import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { useAsks } from "./api/useAsks";
import { useSelectedRun } from "./api/useSelectedRun";
import { PhoneFrame } from "./components/PhoneFrame";
import { TABS, TabBar, type Tab } from "./components/TabBar";
import { Inspector } from "./inspector/Inspector";
import { Agent } from "./screens/Agent";
import { Home } from "./screens/Home";
import { Permission } from "./screens/Permission";
import { StepUp } from "./screens/StepUp";

function Asks() {
  const { asks } = useAsks();  // loaded from /api/asks, kept current from the event stream
  return <StepUp asks={asks} />;
}

// The phone, and — on a wide screen only — the engine inspector beside it (LEASH-097). The run selection
// lives here so both describe the same run: switching it on the phone switches the panel too.
function Shell() {
  const [tab, setTab] = useState<Tab>("home");
  const [revoke, setRevoke] = useState(false);  // Home's Revoke tile opens Permission with the sheet showing
  const go = (to: Tab | "revoke") => {
    setRevoke(to === "revoke");
    setTab(to === "revoke" ? "rules" : to);
  };
  const selection = useSelectedRun();
  const label = TABS.find((t) => t.id === tab)!.label;
  return (
    <div className="shell">
      <PhoneFrame>
        <main className="view">
          {tab !== "home" && <h1>{label}</h1>}  {/* Home's greeting is its heading */}
          {tab === "home" ? <Home selection={selection} onNavigate={go} />
            : tab === "rules" ? <Permission startRevoke={revoke} /> : <Agent />}
        </main>
        <TabBar current={tab} onSelect={go} />
        <Asks />
      </PhoneFrame>
      <Inspector runId={selection.runId} />
    </div>
  );
}

export default function App() {
  const [client] = useState(() => new QueryClient());
  return (
    <QueryClientProvider client={client}>
      <Shell />
    </QueryClientProvider>
  );
}
