export interface DegradedBannerProps {
  classifierOffline: boolean;
  membaseOffline: boolean;
}

export function DegradedBanner({
  classifierOffline,
  membaseOffline,
}: DegradedBannerProps) {
  if (!classifierOffline && !membaseOffline) return null;

  const messages: string[] = [];
  if (classifierOffline) {
    messages.push("Classifier offline — notes saved without auto-classification.");
  }
  if (membaseOffline) {
    messages.push("Memory sync delayed.");
  }

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        background: "var(--tier-amber-soft)",
        borderBottom: "1px solid var(--tier-amber)",
        color: "var(--tier-amber)",
        padding: "8px 14px",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--text-meta)",
        letterSpacing: ".05em",
        textAlign: "center",
      }}
    >
      {messages.join(" ")}
    </div>
  );
}
