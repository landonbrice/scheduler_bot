import type { Task } from "../types";
import { COURSE_COLORS, TYPE_ICONS, DEFAULT_COURSE_COLOR } from "../theme";
import { daysUntil, formatDate, urgencyColor } from "../utils";

export function Milestones({ tasks }: { tasks: Task[] }) {
  const items = tasks
    .filter(t => !t.done && daysUntil(t.due) >= 0 && ["exam", "project", "essay", "presentation"].includes(t.type))
    .sort((a, b) => a.due.localeCompare(b.due))
    .slice(0, 8);
  if (items.length === 0) return null;
  return (
    <div className="mb-6">
      <h2 className="text-[11px] text-neutral-400 font-semibold uppercase tracking-widest mb-2">Major Milestones</h2>
      <div className="flex gap-2 overflow-x-auto -mx-4 px-4 pb-1 snap-x">
        {items.map(t => {
          const days = daysUntil(t.due);
          const colors = COURSE_COLORS[t.course] ?? DEFAULT_COURSE_COLOR;
          return (
            <div key={t.id} className="snap-start flex-shrink-0 rounded-lg px-3 py-2.5 min-w-[160px]"
                 style={{ background: colors.light, border: `1px solid ${colors.accent}40` }}>
              <div className="flex justify-between items-center">
                <span className="text-[10px] font-bold" style={{ color: colors.accent }}>{t.course}</span>
                <span className="text-[10px] font-bold" style={{ color: urgencyColor(days) }}>
                  {days === 0 ? "TODAY" : days === 1 ? "TOMORROW" : `${days}d`}
                </span>
              </div>
              <div className="text-[13px] font-semibold mt-1" style={{ color: colors.text }}>
                {TYPE_ICONS[t.type] ?? "·"} {t.name}
              </div>
              <div className="text-[10px] text-neutral-500 mt-0.5">{formatDate(t.due)}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
