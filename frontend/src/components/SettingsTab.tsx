export interface SettingsTabProps {
  showScores: boolean;
  onToggleScores(v: boolean): void;
}

export function SettingsTab({ showScores, onToggleScores }: SettingsTabProps) {
  return (
    <div
      style={{
        padding: "16px 14px",
        fontFamily: "var(--font-body)",
        color: "var(--ink-primary)",
      }}
    >
      <h2
        style={{
          fontFamily: "var(--font-display)",
          fontStyle: "italic",
          fontSize: 22,
          fontWeight: 500,
          marginBottom: 14,
          letterSpacing: "-0.005em",
        }}
      >
        Settings
      </h2>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 10,
          padding: "14px 16px",
          background: "var(--surface-card)",
          border: "1px solid var(--ink-hairline)",
          borderRadius: "var(--radius-pill)",
        }}
      >
        <label
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            cursor: "pointer",
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <div
              style={{
                fontSize: 14,
                fontWeight: 500,
                color: "var(--ink-primary)",
              }}
            >
              Debug: show priority scores
            </div>
            <div
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 11,
                letterSpacing: ".04em",
                color: "var(--ink-tertiary)",
              }}
            >
              Overlay numeric priority on each TaskPill.
            </div>
          </div>
          <input
            type="checkbox"
            checked={showScores}
            onChange={(e) => onToggleScores(e.target.checked)}
            style={{
              width: 20,
              height: 20,
              accentColor: "var(--ink-primary)",
              cursor: "pointer",
            }}
          />
        </label>
      </div>

      <div
        style={{
          marginTop: 14,
          padding: "14px 16px",
          background: "var(--surface-sunken)",
          border: "1px dashed var(--ink-hairline)",
          borderRadius: "var(--radius-pill)",
          fontFamily: "var(--font-mono)",
          fontSize: 12,
          letterSpacing: ".04em",
          color: "var(--ink-secondary)",
        }}
      >
        Category colors + calendar picker — coming in Task 11.
      </div>
    </div>
  );
}
