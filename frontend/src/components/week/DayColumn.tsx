import type { TaskWithPriority, SurfacedChip } from "../../types";
import { FixedBlockPill } from "./FixedBlockPill";
import { TaskPill } from "./TaskPill";
import { ThoughtChip } from "./ThoughtChip";
import { PX_PER_HOUR } from "./HourAxis";

export interface DayColumnProps {
  date: Date;
  isToday: boolean;
  fixedBlocks: Array<{
    kind: "class" | "event";
    title: string;
    category: string;
    start: string;
    end: string;
    location?: string;
  }>;
  tasks: TaskWithPriority[];
  chips: SurfacedChip[];
  onTaskToggle(id: string, done: boolean): void;
  onTaskFlag(id: string): void;
  onChipDismiss(memory_id: string): void;
  onChipCreateTask(chip: SurfacedChip): void;
  onEmptyBlockTap(startIso: string, duration: number): void;
  showScores?: boolean;
}

const START_HOUR = 7;
const END_HOUR = 23;

/**
 * A single day column: weekday header, hour-axis-aligned fixed-blocks strip,
 * surfaced-chip strip (3-thought cap, unbounded resurface), task pile sorted
 * by priority_score desc. Empty gaps between fixed blocks render a transparent
 * button that invokes onEmptyBlockTap — scaffold only, caller wires suggest.
 */
export function DayColumn({
  date,
  isToday,
  fixedBlocks,
  tasks,
  chips,
  onTaskToggle,
  onTaskFlag,
  onChipDismiss,
  onChipCreateTask,
  onEmptyBlockTap,
  showScores = false,
}: DayColumnProps) {
  const weekday = date.toLocaleDateString("en-US", { weekday: "short" });
  const dateNum = date.getDate();

  // Chip rule: first 3 thoughts + ALL resurface items, preserving original order.
  const thoughtSeen: SurfacedChip[] = [];
  const resurfaceAll: SurfacedChip[] = [];
  for (const c of chips) {
    if (c.kind === "resurface") resurfaceAll.push(c);
    else if (thoughtSeen.length < 3) thoughtSeen.push(c);
  }
  const visibleChips = [...resurfaceAll, ...thoughtSeen];

  const sortedTasks = [...tasks].sort(
    (a, b) => b.priority_score - a.priority_score,
  );

  // Parse fixed-block time into a minutes-from-midnight pair so we can compute
  // top/height relative to the axis. Sort by start; detect gaps for empty-block taps.
  type Positioned = {
    block: (typeof fixedBlocks)[number];
    startMin: number;
    endMin: number;
  };
  const positioned: Positioned[] = fixedBlocks
    .map((b) => ({
      block: b,
      startMin: parseMinutes(b.start),
      endMin: parseMinutes(b.end),
    }))
    .filter((p) => p.startMin != null && p.endMin != null)
    .sort((a, b) => a.startMin - b.startMin);

  const axisHeight = (END_HOUR - START_HOUR) * PX_PER_HOUR;

  // Empty gaps >= 60min between blocks, within the axis window, clickable.
  const gaps: Array<{ startMin: number; endMin: number }> = [];
  const windowStartMin = START_HOUR * 60;
  const windowEndMin = END_HOUR * 60;
  let cursor = windowStartMin;
  for (const p of positioned) {
    if (p.startMin - cursor >= 60) {
      gaps.push({ startMin: cursor, endMin: p.startMin });
    }
    cursor = Math.max(cursor, p.endMin);
  }
  if (windowEndMin - cursor >= 60) {
    gaps.push({ startMin: cursor, endMin: windowEndMin });
  }

  const dayIso = toISODate(date);

  return (
    <div
      className="flex-shrink-0 flex flex-col relative"
      data-today={isToday || undefined}
      style={{
        width: 260,
        background: "var(--surface-card)",
        borderRadius: "var(--radius-card)",
        padding: "var(--space-5) var(--space-4) var(--space-6)",
        minHeight: 520,
        boxShadow: "var(--shadow-card)",
        ...(isToday ? { background: "#FDFBF6" } : {}),
      }}
    >
      {isToday && (
        <div
          aria-hidden="true"
          style={{
            position: "absolute",
            left: 16,
            right: 16,
            top: 0,
            height: 2,
            background: "var(--ink-primary)",
            borderRadius: "0 0 2px 2px",
          }}
        />
      )}

      {/* Header */}
      <div
        className="flex items-baseline justify-between"
        style={{
          paddingBottom: 12,
          marginBottom: 2,
          borderBottom: "1px dashed var(--ink-hairline)",
        }}
      >
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-meta)",
            letterSpacing: ".12em",
            textTransform: "uppercase",
            color: isToday ? "var(--ink-primary)" : "var(--ink-secondary)",
            fontWeight: isToday ? 700 : 500,
          }}
        >
          {weekday}
        </div>
        <div
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "var(--text-date)",
            fontWeight: 500,
            letterSpacing: "-0.015em",
            lineHeight: 1,
            color: "var(--ink-primary)",
          }}
        >
          {dateNum}
        </div>
      </div>

      {/* Hour-anchored fixed-block strip */}
      {positioned.length > 0 && (
        <div
          className="relative"
          style={{
            height: axisHeight,
            marginTop: 10,
          }}
        >
          {positioned.map((p, i) => {
            const top = Math.max(
              0,
              ((p.startMin - windowStartMin) / 60) * PX_PER_HOUR,
            );
            const height = Math.max(
              24,
              ((p.endMin - p.startMin) / 60) * PX_PER_HOUR - 2,
            );
            return (
              <div
                key={`fb-${i}`}
                style={{
                  position: "absolute",
                  top,
                  left: 0,
                  right: 0,
                  height,
                }}
              >
                <FixedBlockPill
                  title={p.block.title}
                  category={p.block.category}
                  start={p.block.start}
                  end={p.block.end}
                  location={p.block.location}
                />
              </div>
            );
          })}
          {gaps.map((g, i) => {
            const top = ((g.startMin - windowStartMin) / 60) * PX_PER_HOUR;
            const height = ((g.endMin - g.startMin) / 60) * PX_PER_HOUR;
            const startIso = `${dayIso}T${minutesToHHMM(g.startMin)}:00`;
            const duration = g.endMin - g.startMin;
            return (
              <button
                key={`gap-${i}`}
                type="button"
                onClick={() => onEmptyBlockTap(startIso, duration)}
                aria-label={`Open ${duration}-minute block`}
                style={{
                  position: "absolute",
                  top: top + 2,
                  left: 0,
                  right: 0,
                  height: Math.max(16, height - 4),
                  background: "transparent",
                  border: "1px dashed transparent",
                  borderRadius: "var(--radius-pill)",
                  cursor: "pointer",
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.borderColor =
                    "var(--ink-hairline)";
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.borderColor =
                    "transparent";
                }}
              />
            );
          })}
        </div>
      )}

      {/* Chip strip */}
      {visibleChips.length > 0 && (
        <div className="flex flex-col gap-2 mt-3">
          {visibleChips.map((chip, i) => (
            <ThoughtChip
              key={chip.memory_id ?? `chip-${i}`}
              chip={chip}
              onDismiss={onChipDismiss}
              onCreateTask={onChipCreateTask}
            />
          ))}
        </div>
      )}

      {/* Task pile */}
      {sortedTasks.length > 0 ? (
        <div className="flex flex-col gap-2 mt-3">
          {sortedTasks.map((t) => (
            <TaskPill
              key={t.id}
              task={t}
              onToggle={onTaskToggle}
              onFlag={onTaskFlag}
              showScore={showScores}
            />
          ))}
        </div>
      ) : (
        positioned.length === 0 &&
        visibleChips.length === 0 && (
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-meta)",
              color: "var(--ink-tertiary)",
              marginTop: 16,
              letterSpacing: ".08em",
              textTransform: "uppercase",
            }}
          >
            nothing scheduled
          </div>
        )
      )}
    </div>
  );
}

// --- helpers ---

/** HH:MM or ISO "…T14:30…" → minutes from midnight; null if unparseable. */
function parseMinutes(s: string): number {
  const m1 = s.match(/^(\d{2}):(\d{2})/);
  if (m1) return parseInt(m1[1], 10) * 60 + parseInt(m1[2], 10);
  const m2 = s.match(/T(\d{2}):(\d{2})/);
  if (m2) return parseInt(m2[1], 10) * 60 + parseInt(m2[2], 10);
  return NaN;
}

function minutesToHHMM(m: number): string {
  const hh = Math.floor(m / 60)
    .toString()
    .padStart(2, "0");
  const mm = (m % 60).toString().padStart(2, "0");
  return `${hh}:${mm}`;
}

export function toISODate(d: Date): string {
  const y = d.getFullYear();
  const m = (d.getMonth() + 1).toString().padStart(2, "0");
  const day = d.getDate().toString().padStart(2, "0");
  return `${y}-${m}-${day}`;
}
