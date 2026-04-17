export type Tab = "week" | "tasks" | "settings";

export interface TabBarProps {
  current: Tab;
  onChange(tab: Tab): void;
}

const LABELS: Record<Tab, string> = {
  week: "Week",
  tasks: "Tasks",
  settings: "Settings",
};

const ORDER: Tab[] = ["week", "tasks", "settings"];

export function TabBar({ current, onChange }: TabBarProps) {
  return (
    <nav
      role="tablist"
      aria-label="Primary"
      style={{
        position: "fixed",
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: 30,
        background: "var(--surface-card)",
        borderTop: "1px solid var(--ink-hairline)",
        display: "flex",
        justifyContent: "space-around",
        alignItems: "stretch",
        paddingBottom: "env(safe-area-inset-bottom, 0px)",
      }}
    >
      {ORDER.map((t) => {
        const active = current === t;
        return (
          <button
            key={t}
            role="tab"
            type="button"
            aria-selected={active}
            onClick={() => onChange(t)}
            style={{
              flex: 1,
              minHeight: 48,
              padding: "10px 8px",
              border: "none",
              background: "transparent",
              cursor: "pointer",
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-meta)",
              letterSpacing: ".1em",
              textTransform: "uppercase",
              fontWeight: active ? 700 : 500,
              color: active ? "var(--ink-primary)" : "var(--ink-tertiary)",
              borderTop: active
                ? "2px solid var(--ink-primary)"
                : "2px solid transparent",
              transition: "color var(--dur-fast) var(--ease-standard)",
            }}
          >
            {LABELS[t]}
          </button>
        );
      })}
    </nav>
  );
}
