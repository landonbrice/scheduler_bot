import { useState } from "react";
import { api } from "../api";

export interface QuickAddProps {
  currentFilter: string;
  onCreated(): void;
  onStatus?(flags: { classifierOffline?: boolean; membaseOffline?: boolean }): void;
}

export function QuickAdd({ onCreated, onStatus }: QuickAddProps) {
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const submit = async () => {
    const trimmed = text.trim();
    if (!trimmed || submitting) return;
    setSubmitting(true);
    setToast(null);
    try {
      const r = await api.captureNote(trimmed);
      onStatus?.({
        classifierOffline: r.classifier_offline,
        membaseOffline: !r.memory_stored,
      });
      setText("");
      if (r.classification === "ambiguous") {
        setToast("Needs a category — tap + to finish");
        window.setTimeout(() => setToast(null), 2500);
      } else if (r.classification === "thought") {
        setToast("Saved as thought");
        window.setTimeout(() => setToast(null), 1500);
      } else if (r.classification === "resurface") {
        setToast("Will resurface");
        window.setTimeout(() => setToast(null), 1500);
      }
      onCreated();
    } catch (e) {
      setToast(String(e));
      window.setTimeout(() => setToast(null), 2500);
    } finally {
      setSubmitting(false);
    }
  };

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void submit();
    }
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 6,
        marginBottom: 12,
      }}
    >
      <div style={{ display: "flex", gap: 8 }}>
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKey}
          placeholder="Quick add a note or task…"
          style={{
            flex: 1,
            padding: "10px 12px",
            borderRadius: "var(--radius-pill)",
            border: "1px solid var(--ink-hairline)",
            background: "var(--surface-card)",
            fontFamily: "var(--font-body)",
            fontSize: 14,
            color: "var(--ink-primary)",
            outline: "none",
          }}
        />
        <button
          type="button"
          onClick={submit}
          disabled={!text.trim() || submitting}
          style={{
            padding: "10px 16px",
            borderRadius: "var(--radius-pill)",
            border: "none",
            background: "var(--ink-primary)",
            color: "var(--surface-paper)",
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            letterSpacing: ".08em",
            textTransform: "uppercase",
            fontWeight: 600,
            cursor: !text.trim() || submitting ? "not-allowed" : "pointer",
            opacity: !text.trim() || submitting ? 0.5 : 1,
          }}
        >
          {submitting ? "…" : "Add"}
        </button>
      </div>
      {toast && (
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            letterSpacing: ".06em",
            color: "var(--ink-tertiary)",
          }}
        >
          {toast}
        </div>
      )}
    </div>
  );
}
