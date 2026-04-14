import type { Task, View } from "../types";
import { priorityScore } from "../utils";
import { TaskRow } from "./TaskRow";
import { useMemo } from "react";

type Props = {
  tasks: Task[];
  filter: string;
  view: View;
  onToggle: (id: string, done: boolean) => void;
};

export function TaskList({ tasks, filter, view, onToggle }: Props) {
  const visible = useMemo(() => {
    let ts = filter === "all" ? [...tasks] : tasks.filter(t => t.course === filter);
    if (view === "priority") ts.sort((a, b) => priorityScore(a) - priorityScore(b));
    else if (view === "timeline") ts.sort((a, b) => a.due.localeCompare(b.due));
    else ts.sort((a, b) => a.course === b.course ? a.due.localeCompare(b.due) : a.course.localeCompare(b.course));
    return ts;
  }, [tasks, filter, view]);

  return (
    <div>
      <h2 className="text-[11px] text-neutral-400 font-semibold uppercase tracking-widest mb-2">
        All Tasks {filter !== "all" && `— ${filter}`}
      </h2>
      <div className="flex flex-col gap-1">
        {visible.map(t => <TaskRow key={t.id} task={t} onToggle={onToggle} />)}
        {visible.length === 0 && <div className="text-sm text-neutral-500 py-8 text-center">No tasks.</div>}
      </div>
    </div>
  );
}
