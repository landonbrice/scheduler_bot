import { useEffect, useMemo, useState } from "react";
import type {
  CalendarEvent,
  ClassInstance,
  SurfacedChip,
  TaskWithPriority,
} from "../../types";
import { DayColumn, toISODate } from "./DayColumn";
import { HourAxis } from "./HourAxis";
import { useSwipe } from "../../hooks/useSwipe";

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

const WEEKDAY_LETTERS = ["M", "T", "W", "T", "F", "S", "S"];
const WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/**
 * Container: prev/today/next header + overdue badge, a 7-pip day strip,
 * and a single full-width DayColumn for the selected day. Horizontal
 * swipe navigates day-by-day; swiping past the week boundary advances
 * to the adjacent week's edge day.
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

  const todayIndex = useMemo(() => {
    const i = days.findIndex((d) => toISODate(d) === todayIso);
    return i;
  }, [days, todayIso]);

  const [selectedDayIndex, setSelectedDayIndex] = useState<number>(() =>
    todayIndex >= 0 ? todayIndex : 0,
  );

  // When user taps "Today", App.tsx resets weekStart; snap selection to today.
  useEffect(() => {
    if (todayIndex >= 0) {
      setSelectedDayIndex(todayIndex);
    }
    // Intentionally only on weekStart change where today lands in-range;
    // when user nav'd to a week without today, keep whatever they had.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [weekStart]);

  const goToDay = (newIdx: number) => {
    if (newIdx > 6) {
      onNextWeek();
      setSelectedDayIndex(0);
    } else if (newIdx < 0) {
      onPrevWeek();
      setSelectedDayIndex(6);
    } else {
      setSelectedDayIndex(newIdx);
    }
  };

  const weekSwipe = useSwipe({
    onSwipeLeft: () => goToDay(selectedDayIndex + 1),
    onSwipeRight: () => goToDay(selectedDayIndex - 1),
    threshold: 50,
  });

  const rangeLabel = useMemo(() => {
    const last = new Date(weekStart);
    last.setDate(weekStart.getDate() + 6);
    const fmt = (d: Date) =>
      d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    return `${fmt(weekStart)} – ${fmt(last)}`;
  }, [weekStart]);

  const overdueCount = overdueTasks?.length ?? 0;

  // Per-day urgent flag: any task tier "red" or priority_boost 1.5 on that day.
  const pipHasUrgent = useMemo(() => {
    return days.map((d) => {
      const iso = toISODate(d);
      return tasks.some(
        (t) =>
          t.due === iso && (t.tier === "red" || t.priority_boost === 1.5),
      );
    });
  }, [days, tasks]);

  const selectedDay = days[selectedDayIndex] ?? days[0];
  const selectedIso = toISODate(selectedDay);
  const isSelectedToday = selectedIso === todayIso;

  const dayTasks = tasks.filter((t) => t.due === selectedIso);
  const daySchedule = schedule
    .filter((c) => c.date === selectedIso)
    .map((c) => ({
      kind: "class" as const,
      title: c.title,
      category: c.category,
      start: c.start,
      end: c.end,
      location: c.location,
    }));
  const dayEvents = events
    .filter((e) => typeof e.start === "string" && e.start.startsWith(selectedIso))
    .map((e) => ({
      kind: "event" as const,
      title: e.summary,
      category: "Life",
      start: e.start,
      end: e.end,
      location: undefined as string | undefined,
    }));
  const fixedBlocks = [...daySchedule, ...dayEvents];
  const chips = surfaced[selectedIso] ?? [];

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
        style={{ padding: "8px 4px 12px" }}
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

      {/* Day pip strip: 7 weekday letters; tap to jump, active is highlighted. */}
      <DayPipStrip
        days={days}
        selectedIndex={selectedDayIndex}
        todayIso={todayIso}
        pipHasUrgent={pipHasUrgent}
        onSelect={(i) => setSelectedDayIndex(i)}
      />

      {/* Single full-width day view + swipe handlers. */}
      <div
        {...weekSwipe}
        style={{
          padding: "4px 2px 12px",
          touchAction: "pan-y",
        }}
      >
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-meta)",
            letterSpacing: ".08em",
            textTransform: "uppercase",
            color: "var(--ink-tertiary)",
            padding: "4px 6px 10px",
          }}
        >
          {WEEKDAY_NAMES[selectedDayIndex]}{" "}
          {selectedDay.toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
          })}
        </div>
        <div className="flex gap-3" style={{ alignItems: "flex-start" }}>
          <HourAxis />
          <div style={{ flex: 1, minWidth: 0 }}>
            <DayColumn
              date={selectedDay}
              isToday={isSelectedToday}
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
        </div>
      </div>
    </div>
  );
}

interface DayPipStripProps {
  days: Date[];
  selectedIndex: number;
  todayIso: string;
  pipHasUrgent: boolean[];
  onSelect(i: number): void;
}

function DayPipStrip({
  days,
  selectedIndex,
  todayIso,
  pipHasUrgent,
  onSelect,
}: DayPipStripProps) {
  return (
    <div
      className="flex items-stretch"
      style={{
        padding: "4px 4px 10px",
        gap: 4,
        borderBottom: "1px dashed var(--ink-hairline)",
        marginBottom: 8,
      }}
    >
      {days.map((d, i) => {
        const iso = toISODate(d);
        const isActive = i === selectedIndex;
        const isToday = iso === todayIso;
        const hasUrgent = pipHasUrgent[i];
        return (
          <button
            key={iso}
            type="button"
            onClick={() => onSelect(i)}
            aria-label={`Select ${WEEKDAY_NAMES[i]} ${d.getDate()}`}
            aria-pressed={isActive}
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 2,
              padding: "6px 0 4px",
              background: isActive ? "var(--ink-primary)" : "transparent",
              color: isActive
                ? "var(--surface-paper)"
                : isToday
                  ? "var(--ink-primary)"
                  : "var(--ink-secondary)",
              border: "none",
              borderRadius: 6,
              cursor: "pointer",
              fontFamily: "var(--font-mono)",
              fontWeight: isActive || isToday ? 700 : 500,
              letterSpacing: ".08em",
              textTransform: "uppercase",
            }}
          >
            <span style={{ fontSize: 12, lineHeight: 1 }}>
              {WEEKDAY_LETTERS[i]}
            </span>
            <span
              style={{
                fontSize: 10,
                lineHeight: 1,
                opacity: 0.75,
              }}
            >
              {d.getDate()}
            </span>
            <span
              aria-hidden="true"
              style={{
                width: 4,
                height: 4,
                borderRadius: 99,
                marginTop: 2,
                background: hasUrgent ? "var(--tier-red)" : "transparent",
              }}
            />
          </button>
        );
      })}
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
