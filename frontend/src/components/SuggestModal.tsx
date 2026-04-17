import { useEffect, useState } from "react";
import { api } from "../api";
import type { SuggestResponse, TaskWithPriority } from "../types";

export interface SuggestModalProps {
  open: boolean;
  onClose(): void;
  duration: number;
  startIso: string;
  tasks: TaskWithPriority[];
  onPickTask(task_id: string): void;
}

export function SuggestModal({
  open,
  onClose,
  duration,
  startIso,
  tasks,
  onPickTask,
}: SuggestModalProps) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SuggestResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !startIso) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setResult(null);
    api
      .suggest(duration, startIso)
      .then((r) => {
        if (!cancelled) setResult(r);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, duration, startIso]);

  if (!open) return null;

  const taskById = new Map(tasks.map((t) => [t.id, t]));
  const fallback = result?.source === "fallback";
  const rateLimited = Boolean(result?.rate_limited);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Suggested tasks for this block"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 44,
        display: "flex",
        alignItems: "flex-end",
        justifyContent: "center",
      }}
    >
      <button
        type="button"
        aria-label="Close"
        onClick={onClose}
        style={{
          position: "absolute",
          inset: 0,
          background: "rgba(28, 27, 26, 0.35)",
          border: "none",
          cursor: "default",
          padding: 0,
        }}
      />
      <div
        style={{
          position: "relative",
          width: "100%",
          maxWidth: 560,
          maxHeight: "80vh",
          overflowY: "auto",
          background: "var(--surface-paper)",
          borderTopLeftRadius: "var(--radius-card)",
          borderTopRightRadius: "var(--radius-card)",
          padding: "16px 18px 24px",
          boxShadow: "0 -6px 24px rgba(28, 27, 26, 0.18)",
          fontFamily: "var(--font-body)",
        }}
      >
        <div
          aria-hidden="true"
          style={{
            width: 36,
            height: 4,
            background: "var(--ink-hairline)",
            borderRadius: 999,
            margin: "0 auto 12px",
          }}
        />

        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 14,
          }}
        >
          <div
            style={{
              fontFamily: "var(--font-display)",
              fontStyle: "italic",
              fontSize: 20,
              fontWeight: 500,
              color: "var(--ink-primary)",
            }}
          >
            What should I do for {duration} min?
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
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

        {loading && (
          <div
            style={{
              textAlign: "center",
              padding: "24px 0",
              color: "var(--ink-tertiary)",
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-meta)",
              letterSpacing: ".08em",
              textTransform: "uppercase",
            }}
          >
            Thinking…
          </div>
        )}

        {!loading && error && (
          <div
            style={{
              padding: "10px 12px",
              borderRadius: 6,
              background: "var(--tier-red-soft)",
              color: "var(--tier-red)",
              fontFamily: "var(--font-mono)",
              fontSize: 11,
            }}
          >
            {error}
          </div>
        )}

        {!loading && result && (
          <>
            {(fallback || rateLimited) && (
              <div
                style={{
                  marginBottom: 12,
                  fontFamily: "var(--font-mono)",
                  fontSize: 10,
                  letterSpacing: ".08em",
                  textTransform: "uppercase",
                  color: "var(--ink-tertiary)",
                }}
              >
                {rateLimited
                  ? "Rate limit — fallback pick"
                  : "Offline fallback"}
              </div>
            )}

            {result.picked ? (
              <SuggestCard
                primary
                name={taskById.get(result.picked.task_id)?.name ?? result.picked.task_id}
                reasoning={fallback ? "" : result.picked.reasoning}
                onPick={() => onPickTask(result.picked!.task_id)}
              />
            ) : (
              <div
                style={{
                  padding: "16px 12px",
                  color: "var(--ink-tertiary)",
                  fontFamily: "var(--font-mono)",
                  fontSize: "var(--text-meta)",
                  letterSpacing: ".08em",
                  textTransform: "uppercase",
                  textAlign: "center",
                }}
              >
                No matching task.
              </div>
            )}

            {result.alternatives.length > 0 && (
              <>
                <div
                  style={{
                    marginTop: 14,
                    marginBottom: 6,
                    fontFamily: "var(--font-mono)",
                    fontSize: 10,
                    letterSpacing: ".1em",
                    textTransform: "uppercase",
                    color: "var(--ink-tertiary)",
                  }}
                >
                  Alternatives
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {result.alternatives.slice(0, 3).map((alt) => (
                    <SuggestCard
                      key={alt.task_id}
                      name={taskById.get(alt.task_id)?.name ?? alt.task_id}
                      reasoning={fallback ? "" : alt.reasoning}
                      onPick={() => onPickTask(alt.task_id)}
                    />
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

interface SuggestCardProps {
  name: string;
  reasoning: string;
  primary?: boolean;
  onPick(): void;
}
function SuggestCard({ name, reasoning, primary, onPick }: SuggestCardProps) {
  return (
    <button
      type="button"
      onClick={onPick}
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-start",
        gap: 6,
        width: "100%",
        padding: "12px 14px",
        borderRadius: "var(--radius-pill)",
        background: primary ? "var(--surface-card)" : "var(--surface-card)",
        border: primary
          ? "1.5px solid var(--ink-primary)"
          : "1px solid var(--ink-hairline)",
        color: "var(--ink-primary)",
        cursor: "pointer",
        textAlign: "left",
        fontFamily: "var(--font-body)",
      }}
    >
      <div
        style={{
          fontSize: 15,
          fontWeight: primary ? 600 : 500,
          color: "var(--ink-primary)",
          lineHeight: 1.3,
        }}
      >
        {name}
      </div>
      {reasoning && (
        <div
          style={{
            fontSize: 12,
            color: "var(--ink-secondary)",
            lineHeight: 1.4,
          }}
        >
          {reasoning}
        </div>
      )}
    </button>
  );
}
