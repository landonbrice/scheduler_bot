import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { SurfacedChip } from "../types";

export interface SearchModalProps {
  open: boolean;
  onClose(): void;
  onCreateTaskFromMemory(mem: { text: string; tags?: string[] }): void;
}

export function SearchModal({
  open,
  onClose,
  onCreateTaskFromMemory,
}: SearchModalProps) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SurfacedChip[]>([]);
  const [loading, setLoading] = useState(false);
  const [offline, setOffline] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Reset + focus on open.
  useEffect(() => {
    if (!open) return;
    setQ("");
    setResults([]);
    setOffline(false);
    const t = setTimeout(() => inputRef.current?.focus(), 50);
    return () => clearTimeout(t);
  }, [open]);

  // Debounced search.
  useEffect(() => {
    if (!open) return;
    const trimmed = q.trim();
    if (!trimmed) {
      setResults([]);
      setLoading(false);
      setOffline(false);
      return;
    }
    setLoading(true);
    const handle = setTimeout(async () => {
      try {
        const r = await api.searchNotes(trimmed);
        setResults(r.results ?? []);
        setOffline(Boolean(r.offline));
      } catch {
        setResults([]);
        setOffline(true);
      } finally {
        setLoading(false);
      }
    }, 250);
    return () => clearTimeout(handle);
  }, [q, open]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Search notes"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 40,
        background: "var(--surface-paper)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "12px 14px",
          borderBottom: "1px solid var(--ink-hairline)",
          background: "var(--surface-card)",
        }}
      >
        <input
          ref={inputRef}
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search notes, thoughts, tasks…"
          style={{
            flex: 1,
            background: "transparent",
            border: "none",
            outline: "none",
            fontFamily: "var(--font-body)",
            fontSize: 16,
            color: "var(--ink-primary)",
            padding: "8px 4px",
          }}
        />
        <button
          type="button"
          onClick={onClose}
          aria-label="Close search"
          style={{
            border: "1px solid var(--ink-hairline)",
            background: "var(--surface-card)",
            borderRadius: 6,
            padding: "4px 10px",
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            letterSpacing: ".08em",
            textTransform: "uppercase",
            color: "var(--ink-primary)",
            cursor: "pointer",
          }}
        >
          Close
        </button>
      </div>

      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "12px 14px",
        }}
      >
        {loading && (
          <div
            style={{
              textAlign: "center",
              padding: "32px 0",
              color: "var(--ink-tertiary)",
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-meta)",
              letterSpacing: ".08em",
              textTransform: "uppercase",
            }}
          >
            Searching…
          </div>
        )}

        {!loading && q.trim() && offline && (
          <div
            style={{
              textAlign: "center",
              padding: "32px 0",
              color: "var(--ink-secondary)",
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-meta)",
              letterSpacing: ".08em",
              textTransform: "uppercase",
            }}
          >
            Search offline — memory service unavailable.
          </div>
        )}

        {!loading && q.trim() && !offline && results.length === 0 && (
          <div
            style={{
              textAlign: "center",
              padding: "32px 0",
              color: "var(--ink-tertiary)",
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-meta)",
              letterSpacing: ".08em",
              textTransform: "uppercase",
            }}
          >
            No results.
          </div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {results.map((r, i) => (
            <div
              key={r.memory_id ?? `res-${i}`}
              style={{
                background: "var(--surface-card)",
                border: "1px solid var(--ink-hairline)",
                borderRadius: "var(--radius-pill)",
                padding: "12px 14px",
                display: "flex",
                flexDirection: "column",
                gap: 6,
              }}
            >
              <div
                style={{
                  fontFamily: "var(--font-body)",
                  fontSize: 14,
                  color: "var(--ink-primary)",
                  lineHeight: 1.4,
                }}
              >
                {r.text}
              </div>
              {r.tags && r.tags.length > 0 && (
                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    gap: 4,
                    fontFamily: "var(--font-mono)",
                    fontSize: 10,
                    letterSpacing: ".05em",
                    color: "var(--ink-tertiary)",
                  }}
                >
                  {r.tags.map((t) => (
                    <span
                      key={t}
                      style={{
                        background: "var(--surface-sunken)",
                        padding: "2px 6px",
                        borderRadius: 4,
                      }}
                    >
                      #{t}
                    </span>
                  ))}
                </div>
              )}
              <div style={{ marginTop: 2 }}>
                <button
                  type="button"
                  onClick={() =>
                    onCreateTaskFromMemory({ text: r.text, tags: r.tags })
                  }
                  style={{
                    border: "none",
                    background: "transparent",
                    padding: 0,
                    color: "var(--cat-projects)",
                    fontFamily: "var(--font-mono)",
                    fontSize: 11,
                    letterSpacing: ".08em",
                    textTransform: "uppercase",
                    textDecoration: "underline",
                    textUnderlineOffset: 3,
                    cursor: "pointer",
                  }}
                >
                  Create task
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
