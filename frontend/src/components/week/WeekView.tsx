import { useEffect, useMemo, useRef } from "react";
import type {
  CalendarEvent,
  ClassInstance,
  SurfacedChip,
  TaskWithPriority,
} from "../../types";
import { DayColumn, toISODate } from "./DayColumn";
import { HourAxis } from "./HourAxis";

export interface WeekViewProps {
  tasks: TaskWithPriority[];
  schedule: ClassInstance[];
  events: CalendarEvent[];
  surfaced: Record<string, SurfacedChip[]>;
  weekStart: Date;
  onPrevWeek(): void;
  onNextWeek(): void;
  onToday(): void;
  onTaskToggle(id: string, done: boolean): void;
  onTaskFlag(id: string): void;
  onChipDismiss(memory_id: string): void;
  onChipCreateTask(chip: SurfacedChip): void;
  onEmptyBlockTap(startIso: string, duration: number): void;
  showScores?: boolean;
  overdueTasks?: TaskWithPriority[];
  onOverdueOpen?(): void;
}

/**
 * Container: prev/today/next header + overdue badge, HourAxis left gutter,
 * 7 DayColumns horizontally scrolling, today column scrolled into view on mount.
 * OverdueDrawer mounting is deferred to App.tsx (Task 9).
 */
export function WeekView({
  tasks,
  schedule,
  events,
  surfaced,
  weekStart,
  onPrevWeek,
  onNextWeek,
  onToday,
  onTaskToggle,
  onTaskFlag,
  onChipDismiss,
  onChipCreateTask,
  onEmptyBlockTap,
  showScores = false,
  overdueTasks,
  onOverdueOpen,
}: WeekViewProps) {
  const todayRef = useRef<HTMLDivElement | null>(null);
  const todayIso = toISODate(new Date());

  // Build the 7 day-buckets Mon→Sun from weekStart.
  const days = useMemo(() => {
    const out: Date[] = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(weekStart);
      d.setDate(weekStart.getDate() + i);
      out.push(d);
    }
    return out;
  }, [weekStart]);

  useEffect(() => {
    if (todayRef.current) {
      todayRef.current.scrollIntoView({ inline: "center", behavior: "auto" });
    }
  }, []); // mount-only

  const rangeLabel = useMemo(() => {
    const last = new Date(weekStart);
    last.setDate(weekStart.getDate() + 6);
    const fmt = (d: Date) =>
      d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    return `${fmt(weekStart)} – ${fmt(last)}`;
  }, [weekStart]);

  const overdueCount = overdueTasks?.length ?? 0;

  return (
    <div
      className="flex flex-col"
      style={{
        background: "var(--surface-paper)",
        borderRadius: "var(--radius-card)",
      }}
    >
      {/* Header row */}
      <div
        className="flex items-center justify-between"
        style={{ padding: "8px 4px 20px" }}
      >
        <div className="flex items-center gap-3">
          <div
            style={{
              fontFamily: "var(--font-display)",
              fontSize: 20,
              fontWeight: 500,
              fontStyle: "italic",
              letterSpacing: "-0.005em",
              color: "var(--ink-primary)",
            }}
          >
            Week of{" "}
            <em>
              {weekStart.toLocaleDateString("en-US", {
                month: "long",
                day: "numeric",
              })}
            </em>
          </div>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-meta)",
              letterSpacing: ".08em",
              textTransform: "uppercase",
              color: "var(--ink-tertiary)",
            }}
          >
            {rangeLabel}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {overdueCount > 0 && onOverdueOpen && (
            <button
              type="button"
              onClick={onOverdueOpen}
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-meta)",
                letterSpacing: ".08em",
                textTransform: "uppercase",
                background: "var(--tier-red)",
                color: "#fff",
                padding: "4px 10px",
                borderRadius: 6,
                border: "none",
                cursor: "pointer",
              }}
            >
              {overdueCount} overdue
            </button>
          )}
          <NavButton label="Prev" onClick={onPrevWeek} />
          <NavButton label="Today" onClick={onToday} primary />
          <NavButton label="Next" onClick={onNextWeek} />
        </div>
      </div>

      {/* Scroller: hour axis + 7 day columns */}
      <div
        className="flex gap-3 overflow-x-auto"
        style={{
          padding: "4px 2px 12px",
          scrollSnapType: "x mandatory",
        }}
      >
        <HourAxis />
        {days.map((d) => {
          const dayIso = toISODate(d);
          const isToday = dayIso === todayIso;

          const dayTasks = tasks.filter((t) => t.due === dayIso);
          const daySchedule = schedule
            .filter((c) => c.date === dayIso)
            .map((c) => ({
              kind: "class" as const,
              title: c.title,
              category: c.category,
              start: c.start,
              end: c.end,
              location: c.location,
            }));
          const dayEvents = events
            .filter((e) => typeof e.start === "string" && e.start.startsWith(dayIso))
            .map((e) => ({
              kind: "event" as const,
              title: e.summary,
              category: "Life",
              start: e.start,
              end: e.end,
              location: undefined as string | undefined,
            }));
          const fixedBlocks = [...daySchedule, ...dayEvents];
          const chips = surfaced[dayIso] ?? [];

          return (
            <div
              key={dayIso}
              ref={isToday ? todayRef : undefined}
              style={{ scrollSnapAlign: "start" }}
            >
              <DayColumn
                date={d}
                isToday={isToday}
                fixedBlocks={fixedBlocks}
                tasks={dayTasks}
                chips={chips}
                onTaskToggle={onTaskToggle}
                onTaskFlag={onTaskFlag}
                onChipDismiss={onChipDismiss}
                onChipCreateTask={onChipCreateTask}
                onEmptyBlockTap={onEmptyBlockTap}
                showScores={showScores}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

interface NavButtonProps {
  label: string;
  onClick(): void;
  primary?: boolean;
}
function NavButton({ label, onClick, primary = false }: NavButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        fontFamily: "var(--font-mono)",
        fontSize: "var(--text-meta)",
        letterSpacing: ".08em",
        textTransform: "uppercase",
        background: primary ? "var(--ink-primary)" : "var(--surface-card)",
        color: primary ? "var(--surface-paper)" : "var(--ink-primary)",
        border: primary ? "none" : "1px solid var(--ink-hairline)",
        padding: "6px 12px",
        borderRadius: "var(--radius-chip)",
        cursor: "pointer",
      }}
    >
      {label}
    </button>
  );
}
