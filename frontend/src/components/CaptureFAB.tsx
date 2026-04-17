export interface CaptureFABProps {
  onClick(): void;
}

export function CaptureFAB({ onClick }: CaptureFABProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Capture note or task"
      style={{
        position: "fixed",
        right: 20,
        bottom: 80,
        zIndex: 29,
        width: 56,
        height: 56,
        borderRadius: "var(--radius-fab)",
        border: "none",
        background: "var(--ink-primary)",
        color: "var(--surface-paper)",
        fontSize: 28,
        lineHeight: 1,
        cursor: "pointer",
        boxShadow: "var(--shadow-fab)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "var(--font-display)",
      }}
    >
      +
    </button>
  );
}
