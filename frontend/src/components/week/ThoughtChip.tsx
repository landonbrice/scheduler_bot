import { useState } from "react";
import type { SurfacedChip } from "../../types";

export interface ThoughtChipProps {
  chip: SurfacedChip;
  onDismiss(memory_id: string): void;
  onCreateTask(chip: SurfacedChip): void;
}

/**
 * Tier-3 chip: ghost border, muted, icon-prefixed. Collapsed shows first
 * ~60 chars with ellipsis. Tap expands in-place to full text + actions.
 * Resurface chips (🔁) may lack memory_id; dismiss is hidden in that case.
 */
export function ThoughtChip({ chip, onDismiss, onCreateTask }: ThoughtChipProps) {
  const [expanded, setExpanded] = useState(false);
  const icon = chip.kind === "resurface" ? "🔁" : "💭";
  const canDismiss = Boolean(chip.memory_id);

  const collapsedText =
    chip.text.length > 60 ? `${chip.text.slice(0, 60).trimEnd()}…` : chip.text;

  const handleClick = (e: React.MouseEvent) => {
    // Ignore clicks that landed on action buttons.
    if ((e.target as HTMLElement).closest("[data-stop]")) return;
    setExpanded((v) => !v);
  };

  const handleDismiss = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (chip.memory_id) onDismiss(chip.memory_id);
  };

  const handlePromote = (e: React.MouseEvent) => {
    e.stopPropagation();
    onCreateTask(chip);
  };

  if (!expanded) {
    return (
      <button
        type="button"
        onClick={handleClick}
        className="inline-flex items-center gap-[6px] cursor-pointer text-left"
        style={{
          padding: "6px 10px",
          borderRadius: "var(--radius-chip)",
          background: "transparent",
          border: "1px dashed var(--ink-hairline)",
          color: "var(--ink-secondary)",
          fontFamily: "var(--font-body)",
          fontSize: "var(--text-chip)",
          maxWidth: "100%",
        }}
        aria-expanded="false"
      >
        <span
          style={{ fontSize: 11, color: "var(--ink-tertiary)" }}
          aria-hidden="true"
        >
          {icon}
        </span>
        <span
          style={{
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            maxWidth: 180,
          }}
        >
          {collapsedText}
        </span>
      </button>
    );
  }

  return (
    <div
      onClick={handleClick}
      className="flex flex-col gap-2 cursor-pointer"
      style={{
        padding: "10px 12px",
        borderRadius: "var(--radius-chip)",
        background: "var(--surface-card)",
        border: "1px solid var(--ink-hairline)",
        color: "var(--ink-primary)",
        fontFamily: "var(--font-body)",
        fontSize: "var(--text-chip)",
      }}
      role="group"
      aria-expanded="true"
    >
      <div className="flex items-start gap-2">
        <span style={{ fontSize: 12, marginTop: 1 }} aria-hidden="true">
          {icon}
        </span>
        <div style={{ whiteSpace: "normal", lineHeight: 1.4, flex: 1 }}>
          {chip.text}
        </div>
      </div>
      <div
        className="flex gap-[10px]"
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: 10,
          letterSpacing: ".08em",
          textTransform: "uppercase",
        }}
      >
        <button
          type="button"
          data-stop
          onClick={handlePromote}
          style={{
            border: "none",
            background: "transparent",
            color: "var(--cat-projects)",
            padding: 0,
            textDecoration: "underline",
            textUnderlineOffset: 3,
            cursor: "pointer",
          }}
        >
          Create task
        </button>
        {canDismiss && (
          <button
            type="button"
            data-stop
            onClick={handleDismiss}
            style={{
              border: "none",
              background: "transparent",
              color: "var(--ink-primary)",
              padding: 0,
              textDecoration: "underline",
              textUnderlineOffset: 3,
              cursor: "pointer",
            }}
          >
            Dismiss
          </button>
        )}
      </div>
    </div>
  );
}
