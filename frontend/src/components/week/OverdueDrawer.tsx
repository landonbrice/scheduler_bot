import type { TaskWithPriority } from "../../types";
import { TaskPill } from "./TaskPill";

export interface OverdueDrawerProps {
  tasks: TaskWithPriority[];
  open: boolean;
  onClose(): void;
  onToggle(id: string, done: boolean): void;
}

/**
 * Slide-down drawer. Red-tinted header with count. Body reuses TaskPill
 * (tasks passed in here are already forced urgent by being in this drawer).
 * Backdrop click + close button both dismiss. Not rendered when closed.
 */
export function OverdueDrawer({
  tasks,
  open,
  onClose,
  onToggle,
}: OverdueDrawerProps) {
  if (!open) return null;

  const forced: TaskWithPriority[] = tasks.map((t) => ({ ...t, tier: "red" }));

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Overdue tasks"
      className="fixed inset-0 z-40 flex items-end justify-center"
    >
      {/* Backdrop */}
      <button
        type="button"
        aria-label="Close overdue drawer"
        onClick={onClose}
        className="absolute inset-0 w-full h-full cursor-default"
        style={{ background: "rgba(28, 27, 26, 0.25)", border: "none" }}
      />
      {/* Sheet */}
      <div
        className="relative w-full max-w-[720px]"
        style={{
          background: "var(--surface-sunken)",
          borderTop: "1px solid var(--tier-red)",
          borderRadius: "var(--radius-card) var(--radius-card) 0 0",
          padding: "16px 20px 20px",
          boxShadow: "0 -4px 16px rgba(28, 27, 26, 0.1)",
          maxHeight: "70vh",
          overflowY: "auto",
        }}
      >
        {/* Handle */}
        <div
          aria-hidden="true"
          style={{
            width: 36,
            height: 4,
            background: "var(--ink-hairline)",
            borderRadius: 999,
            margin: "0 auto 14px",
          }}
        />
        <div className="flex items-center justify-between mb-3">
          <div
            className="inline-flex items-center gap-2"
            style={{
              fontFamily: "var(--font-display)",
              fontStyle: "italic",
              fontSize: 18,
              fontWeight: 500,
              color: "var(--tier-red)",
            }}
          >
            <span aria-hidden="true">⚠</span>
            {tasks.length} overdue
          </div>
          <div className="flex items-center gap-2">
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-meta)",
                letterSpacing: ".08em",
                textTransform: "uppercase",
                background: "var(--tier-red)",
                color: "#fff",
                padding: "3px 8px",
                borderRadius: 6,
              }}
            >
              {tasks.length}
            </span>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              style={{
                border: "1px solid var(--ink-hairline)",
                background: "var(--surface-card)",
                borderRadius: 6,
                padding: "3px 10px",
                fontFamily: "var(--font-mono)",
                fontSize: 11,
                letterSpacing: ".08em",
                textTransform: "uppercase",
                cursor: "pointer",
                color: "var(--ink-primary)",
              }}
            >
              Close
            </button>
          </div>
        </div>
        <div className="flex flex-col gap-2">
          {forced.length === 0 ? (
            <div
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-meta)",
                color: "var(--ink-tertiary)",
                textAlign: "center",
                padding: "16px 0",
              }}
            >
              Nothing overdue.
            </div>
          ) : (
            forced.map((t) => (
              <TaskPill
                key={t.id}
                task={t}
                onToggle={onToggle}
                onFlag={() => {
                  /* no-op in drawer; flag stays on week view */
                }}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
