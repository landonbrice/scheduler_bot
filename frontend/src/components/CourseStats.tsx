import type { Task } from "../types";
import { COURSE_COLORS } from "../theme";
import { daysUntil } from "../utils";
import { haptic } from "../telegram";

type Props = {
  tasks: Task[];
  filter: string;
  onFilter: (course: string) => void;
};

export function CourseStats({ tasks, filter, onFilter }: Props) {
  return (
    <div className="flex gap-2 mb-5 overflow-x-auto -mx-4 px-4 pb-1 snap-x">
      {Object.entries(COURSE_COLORS).map(([course, colors]) => {
        const courseTasks = tasks.filter(t => t.course === course);
        const active = courseTasks.filter(t => !t.done && daysUntil(t.due) >= 0);
        const next = [...active].sort((a, b) => a.due.localeCompare(b.due))[0];
        const selected = filter === course;
        return (
          <button
            key={course}
            onClick={() => { haptic("light"); onFilter(selected ? "all" : course); }}
            className="snap-start flex-shrink-0 rounded-lg px-4 py-3 text-left min-w-[140px] transition-colors"
            style={{
              background: selected ? colors.light : "#171717",
              border: `1px solid ${selected ? colors.accent : "#262626"}`,
            }}
          >
            <div className="text-[10px] font-bold uppercase tracking-widest" style={{ color: colors.accent }}>{course}</div>
            <div className="text-2xl font-bold mt-0.5" style={{ color: colors.text }}>{active.length}</div>
            <div className="text-[10px] text-neutral-500 mt-0.5 truncate max-w-[140px]">
              {next ? `Next: ${next.name}` : "All done"}
            </div>
          </button>
        );
      })}
    </div>
  );
}
