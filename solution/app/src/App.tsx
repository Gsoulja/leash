import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { useAsks } from "./api/useAsks";
import { Inspector } from "./inspector/Inspector";
import { PhoneFrame } from "./components/PhoneFrame";
import { TABS, TabBar, type Tab } from "./components/TabBar";
import { Agent } from "./screens/Agent";
import { Cockpit } from "./screens/Cockpit";
import { Permission } from "./screens/Permission";
import { StepUp } from "./screens/StepUp";

function Asks() {
  const { asks } = useAsks();  // loaded from /api/asks, kept current from the event stream
  return <StepUp asks={asks} />;
}

export default function App() {
  const [client] = useState(() => new QueryClient());
  const [tab, setTab] = useState<Tab>("home");
  const label = TABS.find((t) => t.id === tab)!.label;
  return (
    <QueryClientProvider client={client}>
      <div className="stage">
        <PhoneFrame>
          <main className="view">
            <h1>{label}</h1>
            {tab === "home" ? <Cockpit /> : tab === "rules" ? <Permission /> : <Agent />}
          </main>
          <TabBar current={tab} onSelect={setTab} />
          <Asks />
        </PhoneFrame>
        <Inspector />
      </div>
    </QueryClientProvider>
  );
}
