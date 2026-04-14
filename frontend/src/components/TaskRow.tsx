import type { Task } from "../types";
import { COURSE_COLORS, TYPE_ICONS, DEFAULT_COURSE_COLOR } from "../theme";
import { daysUntil, formatDate, urgencyColor } from "../utils";
import { haptic } from "../telegram";

type Props = { task: Task; onToggle: (id: string, done: boolean) => void };

export function TaskRow({ task: t, onToggle }: Props) {
  const days = daysUntil(t.due);
  const colors = COURSE_COLORS[t.course] ?? DEFAULT_COURSE_COLOR;
  const isPast = days < 0 && !t.done;
  const handle = () => { haptic("light"); onToggle(t.id, !t.done); };
  return (
    <div onClick={handle}
         className={`flex items-center gap-3 rounded-md px-3 py-3 cursor-pointer transition-opacity ${t.done ? "opacity-40" : ""}`}
         style={{
           background: t.done ? "#0a0a0a" : isPast ? "#1a0a0a" : "#141414",
           border: `1px solid ${t.done ? "#1a1a1a" : isPast ? "#3f1515" : "#222"}`,
           borderLeft: `3px solid ${t.done ? "#333" : colors.accent}`,
         }}>
      <div className="w-5 h-5 rounded flex items-center justify-center flex-shrink-0 text-[11px] font-bold text-black"
           style={{
             border: `2px solid ${t.done ? "#525252" : colors.accent}`,
             background: t.done ? colors.accent : "transparent",
           }}>
        {t.done && "✓"}
      </div>
      <span className="text-sm w-4 text-center flex-shrink-0" style={{ color: colors.accent }}>
        {TYPE_ICONS[t.type] ?? "·"}
      </span>
      <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded flex-shrink-0 w-[56px] text-center"
            style={{ color: colors.accent, background: `${colors.accent}15` }}>
        {t.course}
      </span>
      <span className={`text-[13px] flex-1 min-w-0 truncate ${t.done ? "line-through text-neutral-600" : "text-neutral-200"}`}>
        {t.name}
      </span>
      <div className="text-right flex-shrink-0">
        <div className="text-[10px] text-neutral-500">{formatDate(t.due)}</div>
        <div className="text-[10px] font-bold" style={{ color: urgencyColor(days) }}>
          {t.done ? "DONE" : days < 0 ? "PAST" : days === 0 ? "TODAY" : days === 1 ? "TMRW" : `${days}d`}
        </div>
      </div>
    </div>
  );
}
