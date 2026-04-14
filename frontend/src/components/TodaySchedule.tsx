import type { CalendarEvent } from "../types";

type Props = { events: CalendarEvent[] };

function isToday(iso: string): boolean {
  const d = new Date(iso);
  const now = new Date();
  return d.getFullYear() === now.getFullYear()
    && d.getMonth() === now.getMonth()
    && d.getDate() === now.getDate();
}

function timeLabel(e: CalendarEvent): string {
  if (e.all_day) return "all-day";
  const d = new Date(e.start);
  return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

export function TodaySchedule({ events }: Props) {
  const today = events.filter(e => isToday(e.start)).sort((a, b) => a.start.localeCompare(b.start));
  if (today.length === 0) return null;
  return (
    <div className="mb-4">
      <h2 className="text-[11px] text-neutral-400 font-semibold uppercase tracking-widest mb-2">📅 Today's Schedule</h2>
      <div className="flex gap-2 overflow-x-auto -mx-4 px-4 pb-1 snap-x">
        {today.map((e, i) => (
          <div key={i} className="snap-start flex-shrink-0 rounded-lg px-3 py-2.5 min-w-[160px] bg-card border border-border">
            <div className="text-[10px] font-bold text-neutral-400">{timeLabel(e)}</div>
            <div className="text-[13px] font-semibold text-neutral-200 mt-1 truncate">{e.summary}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
