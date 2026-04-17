import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { CaptureResult } from "../types";
import { KNOWN_CATEGORIES } from "./week/category";

export interface CaptureModalProps {
  open: boolean;
  onClose(): void;
  onTaskCreated(id: string): void;
  classifierOffline: boolean;
  onReload(): void;
  onStatus?(flags: { classifierOffline?: boolean; membaseOffline?: boolean }): void;
}

type Mode = "note" | "task";

type Toast =
  | { kind: "thought" }
  | { kind: "resurface" }
  | { kind: "task-created"; taskId: string; undoUntil: number };

const TYPES = [
  "exam",
  "essay",
  "pset",
  "case",
  "project",
  "presentation",
  "reading",
  "ai-tutor",
  "admin",
] as const;

type TaskType = (typeof TYPES)[number];

function todayPlus(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export function CaptureModal({
  open,
  onClose,
  onTaskCreated,
  classifierOffline,
  onReload,
  onStatus,
}: CaptureModalProps) {
  const [mode, setMode] = useState<Mode>("note");
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [ambiguous, setAmbiguous] = useState<CaptureResult | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Task mode form state.
  const [course, setCourse] = useState<string>("CorpFin");
  const [name, setName] = useState("");
  const [due, setDue] = useState("");
  const [taskType, setTaskType] = useState<TaskType>("admin");
  const [weight, setWeight] = useState("");
  const [notes, setNotes] = useState("");
  const [urgent, setUrgent] = useState(false);

  const closeTimerRef = useRef<number | null>(null);
  const undoTimerRef = useRef<number | null>(null);

  const reset = () => {
    setMode("note");
    setText("");
    setAmbiguous(null);
    setToast(null);
    setError(null);
    setCourse("CorpFin");
    setName("");
    setDue("");
    setTaskType("admin");
    setWeight("");
    setNotes("");
    setUrgent(false);
    setSubmitting(false);
  };

  useEffect(() => {
    if (!open) {
      reset();
    }
  }, [open]);

  useEffect(() => {
    return () => {
      if (closeTimerRef.current !== null) window.clearTimeout(closeTimerRef.current);
      if (undoTimerRef.current !== null) window.clearTimeout(undoTimerRef.current);
    };
  }, []);

  const scheduleClose = (delay: number) => {
    if (closeTimerRef.current !== null) window.clearTimeout(closeTimerRef.current);
    closeTimerRef.current = window.setTimeout(() => {
      closeTimerRef.current = null;
      onClose();
    }, delay);
  };

  const handleNoteSubmit = async () => {
    if (!text.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const r = await api.captureNote(text);
      onStatus?.({
        classifierOffline: r.classifier_offline,
        membaseOffline: !r.memory_stored,
      });
      if (r.classification === "task" && r.created_task_id) {
        onTaskCreated(r.created_task_id);
        onReload();
        const undoUntil = Date.now() + 60_000;
        setToast({
          kind: "task-created",
          taskId: r.created_task_id,
          undoUntil,
        });
        if (undoTimerRef.current !== null) window.clearTimeout(undoTimerRef.current);
        undoTimerRef.current = window.setTimeout(() => {
          undoTimerRef.current = null;
          onClose();
        }, 60_000);
      } else if (r.classification === "thought") {
        setToast({ kind: "thought" });
        onReload();
        scheduleClose(1500);
      } else if (r.classification === "resurface") {
        setToast({ kind: "resurface" });
        onReload();
        scheduleClose(1500);
      } else {
        // ambiguous
        setAmbiguous(r);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  };

  const handleUndoCreate = async () => {
    if (toast?.kind !== "task-created") return;
    const id = toast.taskId;
    try {
      await api.undoCreate(id);
    } catch {
      // Ignore — 60s may have elapsed server-side.
    }
    if (undoTimerRef.current !== null) {
      window.clearTimeout(undoTimerRef.current);
      undoTimerRef.current = null;
    }
    setToast(null);
    onReload();
    onClose();
  };

  const handleTaskSubmit = async () => {
    if (!name.trim() || !due || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const { task } = await api.addTask({
        course,
        name,
        due,
        type: taskType,
        weight,
        notes: notes || null,
        priority_boost: urgent ? 1.5 : null,
      });
      // Backend doesn't honor priority_boost in the create body yet, so flag
      // explicitly for urgent tasks (no-op if already 1.5).
      if (urgent) {
        try {
          await api.flagTask(task.id);
        } catch {
          /* non-fatal */
        }
      }
      onTaskCreated(task.id);
      onReload();
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  };

  const handleAmbiguousPickTask = () => {
    if (!ambiguous) return;
    // Pre-fill task form with suggested values, drop into Task mode.
    const suggested_due =
      ambiguous.suggested_due && ambiguous.suggested_due.length >= 10
        ? ambiguous.suggested_due.slice(0, 10)
        : todayPlus(3);
    const suggestedCategory =
      ambiguous.suggested_category &&
      KNOWN_CATEGORIES.includes(
        ambiguous.suggested_category as (typeof KNOWN_CATEGORIES)[number],
      )
        ? ambiguous.suggested_category
        : course;
    setCourse(suggestedCategory);
    setName(ambiguous.raw_text.slice(0, 80));
    setDue(suggested_due);
    setTaskType("admin");
    setAmbiguous(null);
    setMode("task");
  };

  const handleAmbiguousPickThought = () => {
    setToast({ kind: "thought" });
    onReload();
    scheduleClose(1200);
  };

  const handleAmbiguousPickResurface = () => {
    setToast({ kind: "resurface" });
    onReload();
    scheduleClose(1200);
  };

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Capture"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 45,
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
          maxHeight: "92vh",
          overflowY: "auto",
          background: "var(--surface-paper)",
          borderTopLeftRadius: "var(--radius-card)",
          borderTopRightRadius: "var(--radius-card)",
          padding: "16px 18px 24px",
          boxShadow: "0 -6px 24px rgba(28, 27, 26, 0.18)",
          fontFamily: "var(--font-body)",
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
            margin: "0 auto 12px",
          }}
        />

        {/* Header: segmented control + close */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 10,
            marginBottom: 14,
          }}
        >
          <div
            role="tablist"
            style={{
              display: "inline-flex",
              background: "var(--surface-sunken)",
              padding: 3,
              borderRadius: 999,
            }}
          >
            {(["note", "task"] as const).map((m) => {
              const active = mode === m;
              return (
                <button
                  key={m}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => {
                    setMode(m);
                    setAmbiguous(null);
                    setError(null);
                  }}
                  style={{
                    padding: "6px 18px",
                    borderRadius: 999,
                    border: "none",
                    background: active ? "var(--ink-primary)" : "transparent",
                    color: active ? "var(--surface-paper)" : "var(--ink-secondary)",
                    fontFamily: "var(--font-mono)",
                    fontSize: "var(--text-meta)",
                    letterSpacing: ".1em",
                    textTransform: "uppercase",
                    fontWeight: active ? 700 : 500,
                    cursor: "pointer",
                  }}
                >
                  {m}
                </button>
              );
            })}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close capture"
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

        {classifierOffline && mode === "note" && (
          <div
            style={{
              marginBottom: 10,
              padding: "6px 10px",
              borderRadius: 6,
              background: "var(--tier-amber-soft)",
              color: "var(--tier-amber)",
              fontFamily: "var(--font-mono)",
              fontSize: 11,
              letterSpacing: ".06em",
            }}
          >
            Classifier offline — note will be saved without auto-categorization.
          </div>
        )}

        {/* Content */}
        {mode === "note" && !ambiguous && !toast && (
          <>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="What's on your mind?"
              rows={5}
              style={{
                width: "100%",
                background: "var(--surface-card)",
                border: "1px solid var(--ink-hairline)",
                borderRadius: "var(--radius-pill)",
                padding: "10px 12px",
                fontFamily: "var(--font-body)",
                fontSize: 15,
                color: "var(--ink-primary)",
                resize: "vertical",
              }}
            />
            <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
              <button
                type="button"
                onClick={handleNoteSubmit}
                disabled={!text.trim() || submitting}
                style={{
                  flex: 1,
                  padding: "10px 16px",
                  borderRadius: "var(--radius-pill)",
                  border: "none",
                  background: "var(--ink-primary)",
                  color: "var(--surface-paper)",
                  fontFamily: "var(--font-mono)",
                  fontSize: 13,
                  letterSpacing: ".08em",
                  textTransform: "uppercase",
                  fontWeight: 600,
                  cursor:
                    !text.trim() || submitting ? "not-allowed" : "pointer",
                  opacity: !text.trim() || submitting ? 0.5 : 1,
                }}
              >
                {submitting ? "Saving…" : "Save"}
              </button>
            </div>
          </>
        )}

        {mode === "note" && ambiguous && !toast && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div
              style={{
                fontFamily: "var(--font-body)",
                fontSize: 14,
                color: "var(--ink-primary)",
                padding: "10px 12px",
                background: "var(--surface-card)",
                border: "1px solid var(--ink-hairline)",
                borderRadius: "var(--radius-pill)",
              }}
            >
              {ambiguous.raw_text}
            </div>
            <div
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 11,
                letterSpacing: ".08em",
                textTransform: "uppercase",
                color: "var(--ink-tertiary)",
              }}
            >
              How should we file this?
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <PickerButton label="Task" onClick={handleAmbiguousPickTask} />
              <PickerButton label="Thought" onClick={handleAmbiguousPickThought} />
              <PickerButton label="Resurface" onClick={handleAmbiguousPickResurface} />
            </div>
          </div>
        )}

        {mode === "task" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", gap: 8 }}>
              <select
                value={course}
                onChange={(e) => setCourse(e.target.value)}
                style={{
                  flex: 1,
                  padding: "8px 10px",
                  borderRadius: 8,
                  border: "1px solid var(--ink-hairline)",
                  background: "var(--surface-card)",
                  fontFamily: "var(--font-body)",
                  fontSize: 14,
                  color: "var(--ink-primary)",
                }}
              >
                {KNOWN_CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              <select
                value={taskType}
                onChange={(e) => setTaskType(e.target.value as TaskType)}
                style={{
                  padding: "8px 10px",
                  borderRadius: 8,
                  border: "1px solid var(--ink-hairline)",
                  background: "var(--surface-card)",
                  fontFamily: "var(--font-body)",
                  fontSize: 14,
                  color: "var(--ink-primary)",
                }}
              >
                {TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
            <input
              type="text"
              placeholder="Task name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              style={{
                padding: "8px 10px",
                borderRadius: 8,
                border: "1px solid var(--ink-hairline)",
                background: "var(--surface-card)",
                fontFamily: "var(--font-body)",
                fontSize: 14,
                color: "var(--ink-primary)",
              }}
            />
            <div style={{ display: "flex", gap: 8 }}>
              <input
                type="date"
                value={due}
                onChange={(e) => setDue(e.target.value)}
                style={{
                  flex: 1,
                  padding: "8px 10px",
                  borderRadius: 8,
                  border: "1px solid var(--ink-hairline)",
                  background: "var(--surface-card)",
                  fontFamily: "var(--font-body)",
                  fontSize: 14,
                  color: "var(--ink-primary)",
                }}
              />
              <input
                type="text"
                placeholder="Weight"
                value={weight}
                onChange={(e) => setWeight(e.target.value)}
                style={{
                  flex: 1,
                  padding: "8px 10px",
                  borderRadius: 8,
                  border: "1px solid var(--ink-hairline)",
                  background: "var(--surface-card)",
                  fontFamily: "var(--font-body)",
                  fontSize: 14,
                  color: "var(--ink-primary)",
                }}
              />
            </div>
            <textarea
              placeholder="Notes (optional)"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              style={{
                padding: "8px 10px",
                borderRadius: 8,
                border: "1px solid var(--ink-hairline)",
                background: "var(--surface-card)",
                fontFamily: "var(--font-body)",
                fontSize: 14,
                color: "var(--ink-primary)",
                resize: "vertical",
              }}
            />
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                fontFamily: "var(--font-mono)",
                fontSize: 12,
                letterSpacing: ".08em",
                textTransform: "uppercase",
                color: urgent ? "var(--tier-red)" : "var(--ink-secondary)",
                cursor: "pointer",
              }}
            >
              <input
                type="checkbox"
                checked={urgent}
                onChange={(e) => setUrgent(e.target.checked)}
                style={{ accentColor: "var(--tier-red)" }}
              />
              Urgent (boost priority)
            </label>
            <button
              type="button"
              onClick={handleTaskSubmit}
              disabled={!name.trim() || !due || submitting}
              style={{
                padding: "10px 16px",
                borderRadius: "var(--radius-pill)",
                border: "none",
                background: "var(--ink-primary)",
                color: "var(--surface-paper)",
                fontFamily: "var(--font-mono)",
                fontSize: 13,
                letterSpacing: ".08em",
                textTransform: "uppercase",
                fontWeight: 600,
                cursor:
                  !name.trim() || !due || submitting ? "not-allowed" : "pointer",
                opacity: !name.trim() || !due || submitting ? 0.5 : 1,
              }}
            >
              {submitting ? "Adding…" : "Add task"}
            </button>
          </div>
        )}

        {error && (
          <div
            style={{
              marginTop: 10,
              padding: "6px 10px",
              borderRadius: 6,
              background: "var(--tier-red-soft)",
              color: "var(--tier-red)",
              fontFamily: "var(--font-mono)",
              fontSize: 11,
              letterSpacing: ".05em",
            }}
          >
            {error}
          </div>
        )}

        {toast && toast.kind === "thought" && (
          <InlineToast icon="💭" label="Saved" />
        )}
        {toast && toast.kind === "resurface" && (
          <InlineToast icon="🔁" label="Will resurface" />
        )}
        {toast && toast.kind === "task-created" && (
          <div
            style={{
              marginTop: 12,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 10,
              padding: "10px 12px",
              borderRadius: "var(--radius-pill)",
              background: "var(--surface-card)",
              border: "1px solid var(--ink-hairline)",
            }}
          >
            <div
              style={{
                fontFamily: "var(--font-body)",
                fontSize: 13,
                color: "var(--ink-primary)",
              }}
            >
              Task created: <strong>{toast.taskId}</strong>
            </div>
            <button
              type="button"
              onClick={handleUndoCreate}
              style={{
                border: "1px solid var(--tier-red)",
                background: "var(--tier-red-soft)",
                color: "var(--tier-red)",
                padding: "4px 10px",
                borderRadius: 6,
                fontFamily: "var(--font-mono)",
                fontSize: 11,
                letterSpacing: ".08em",
                textTransform: "uppercase",
                cursor: "pointer",
                fontWeight: 600,
              }}
            >
              Undo
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

interface PickerButtonProps {
  label: string;
  onClick(): void;
}
function PickerButton({ label, onClick }: PickerButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        flex: 1,
        padding: "10px 14px",
        borderRadius: "var(--radius-pill)",
        border: "1px solid var(--ink-hairline)",
        background: "var(--surface-card)",
        color: "var(--ink-primary)",
        fontFamily: "var(--font-mono)",
        fontSize: 12,
        letterSpacing: ".08em",
        textTransform: "uppercase",
        fontWeight: 600,
        cursor: "pointer",
      }}
    >
      {label}
    </button>
  );
}

interface InlineToastProps {
  icon: string;
  label: string;
}
function InlineToast({ icon, label }: InlineToastProps) {
  return (
    <div
      style={{
        marginTop: 12,
        padding: "10px 14px",
        borderRadius: "var(--radius-pill)",
        background: "var(--surface-card)",
        border: "1px solid var(--ink-hairline)",
        display: "flex",
        alignItems: "center",
        gap: 8,
        fontFamily: "var(--font-body)",
        fontSize: 14,
        color: "var(--ink-primary)",
      }}
    >
      <span aria-hidden="true">{icon}</span>
      <span>{label}</span>
    </div>
  );
}
