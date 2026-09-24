import { Icon, type IconName } from "./icons";

export type Tab = "home" | "agent" | "rules";

export const TABS: { id: Tab; label: string; icon: IconName }[] = [
  { id: "home", label: "Cockpit", icon: "home" },
  { id: "agent", label: "Agent", icon: "chat" },
  { id: "rules", label: "Permission", icon: "shield" },
];

export function TabBar({ current, onSelect }: { current: Tab; onSelect: (tab: Tab) => void }) {
  return (
    <nav className="tabs" aria-label="App sections">
      {TABS.map((t) => (
        <button key={t.id} type="button" aria-current={current === t.id ? "page" : undefined}
                onClick={() => onSelect(t.id)}>
          <Icon name={t.icon} />
          {t.label}
        </button>
      ))}
    </nav>
  );
}
