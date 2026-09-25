import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { useAsks } from "./api/useAsks";
import { useSelectedRun } from "./api/useSelectedRun";
import { Logo } from "./components/icons";
import { PhoneFrame } from "./components/PhoneFrame";
import { TABS, TabBar, type Tab } from "./components/TabBar";
import { Inspector } from "./inspector/Inspector";
import { Agent } from "./screens/Agent";
import { Cockpit, CockpitMark } from "./screens/Cockpit";
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
  const selection = useSelectedRun();
  const label = TABS.find((t) => t.id === tab)!.label;
  return (
    <>
    <header className="brand"><Logo tagline /></header>
    <div className="shell">
      <PhoneFrame>
        <main className={`view${tab === "agent" ? " chat-view" : ""}`}>
          {tab === "home" ? <h1 className="with-mark"><CockpitMark selection={selection} />{label}</h1> : tab !== "agent" && <h1>{label}</h1>}
          {tab === "home" ? <Cockpit selection={selection} onPermission={() => setTab("rules")} onChat={() => setTab("agent")} /> : tab === "rules" ? <Permission selectedRun={selection.run} onChat={() => setTab("agent")} /> : <Agent onBack={() => setTab("home")} onRunStarted={(id) => { selection.select(id); setTab("home"); }} />}
        </main>
        {tab !== "agent" && <TabBar current={tab} onSelect={setTab} />}
        <Asks />
      </PhoneFrame>
      <Inspector runId={selection.runId} />
    </div>
    </>
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
