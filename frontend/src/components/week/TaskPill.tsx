import type { TaskWithPriority } from "../../types";
import { categorySlug } from "./category";

export interface TaskPillProps {
  task: TaskWithPriority;
  onToggle(id: string, done: boolean): void;
  onFlag(id: string): void;
  onEdit?(task: TaskWithPriority): void;
  showScore?: boolean;
}

/**
 * Tier-2 pill: bordered, category left-accent, tier-driven urgency.
 * Checkbox on the left, body label + meta row, optional score badge,
 * category badge on the right. Swipe gestures deferred to Task 10.
 */
export function TaskPill({
  task,
  onToggle,
  onFlag,
  onEdit,
  showScore = false,
}: TaskPillProps) {
  const slug = categorySlug(task.course);
  const boosted = task.priority_boost === 1.5;
  const tier = boosted ? "red" : task.tier;
  const urgent = tier === "red";

  // Background: soft-red for urgent, paper card otherwise.
  const bg = urgent ? "var(--tier-red-soft)" : "var(--surface-card)";

  // Border: urgent = full red border (no left accent treatment).
  // Otherwise = hairline border + 4px category left accent (amber override if due today).
  const borderTop = urgent ? "1.5px solid var(--tier-red)" : "1px solid var(--ink-hairline)";
  const borderRight = borderTop;
  const borderBottom = borderTop;
  const leftAccent = urgent
    ? "1.5px solid var(--tier-red)"
    : tier === "amber"
      ? "4px solid var(--tier-amber)"
      : `4px solid var(--cat-${slug})`;

  const handlePillClick = (e: React.MouseEvent) => {
    // Avoid firing when the check or flag button was tapped.
    if ((e.target as HTMLElement).closest("[data-stop]")) return;
    onEdit?.(task);
  };

  const handleFlag = (e: React.MouseEvent) => {
    e.stopPropagation();
    onFlag(task.id);
  };

  const handleCheck = (e: React.MouseEvent) => {
    e.stopPropagation();
    onToggle(task.id, !task.done);
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={handlePillClick}
      data-urgent={urgent || undefined}
      data-due={tier === "amber" ? "today" : undefined}
      data-task-id={task.id}
      className="relative flex items-start gap-[10px] cursor-pointer select-none"
      style={{
        padding: "var(--space-3) var(--space-4) var(--space-3) 18px",
        background: bg,
        borderTop,
        borderRight,
        borderBottom,
        borderLeft: leftAccent,
        borderRadius: "var(--radius-pill)",
        color: "var(--ink-primary)",
        fontFamily: "var(--font-body)",
        boxShadow: "var(--shadow-pill)",
      }}
    >
      {/* Checkbox */}
      <button
        type="button"
        data-stop
        onClick={handleCheck}
        aria-label={task.done ? "Mark incomplete" : "Mark complete"}
        aria-pressed={task.done}
        className="flex-shrink-0 mt-[2px]"
        style={{
          width: 16,
          height: 16,
          borderRadius: 5,
          border: "1.5px solid var(--ink-tertiary)",
          background: task.done ? "var(--ink-primary)" : "transparent",
          padding: 0,
          cursor: "pointer",
        }}
      />

      {/* Body */}
      <div className="flex flex-col gap-[3px] min-w-0 flex-1">
        <div
          style={{
            fontSize: "var(--text-pill)",
            fontWeight: urgent ? 600 : 500,
            lineHeight: 1.25,
            color: urgent ? "var(--tier-red)" : "var(--ink-primary)",
            textDecoration: task.done ? "line-through" : undefined,
            opacity: task.done ? 0.6 : 1,
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {task.name}
        </div>
        <div
          className="flex items-center gap-2"
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-meta)",
            letterSpacing: ".06em",
            textTransform: "uppercase",
            color: "var(--ink-tertiary)",
          }}
        >
          <span
            style={{
              padding: "2px 6px",
              borderRadius: 4,
              background: urgent ? "#fff" : "var(--surface-sunken)",
              color: urgent ? "var(--tier-red)" : "var(--ink-secondary)",
              fontWeight: 600,
            }}
          >
            {task.course}
          </span>
          {task.weight && <span>{task.weight}</span>}
          {showScore && (
            <span
              style={{
                marginLeft: "auto",
                fontWeight: 600,
                color: "var(--ink-secondary)",
              }}
            >
              {Math.round(task.priority_score)}
            </span>
          )}
        </div>
      </div>

      {/* Flag button (right-edge, unobtrusive) */}
      <button
        type="button"
        data-stop
        onClick={handleFlag}
        aria-label="Flag task"
        className="flex-shrink-0 mt-[2px]"
        style={{
          border: "none",
          background: "transparent",
          color: "var(--ink-tertiary)",
          cursor: "pointer",
          fontSize: 14,
          padding: 0,
          lineHeight: 1,
        }}
      >
        ⚑
      </button>
    </div>
  );
}
