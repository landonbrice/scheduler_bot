import { useState } from "react";
import type { Task } from "../types";
import { COURSE_COLORS } from "../theme";

type Props = { onAdd: (body: Omit<Task, "id" | "done">) => Promise<void> };

const TYPES = ["exam", "essay", "pset", "case", "project", "presentation", "reading", "ai-tutor", "admin"] as const;

export function AddTaskForm({ onAdd }: Props) {
  const [open, setOpen] = useState(false);
  const [course, setCourse] = useState("CorpFin");
  const [name, setName] = useState("");
  const [due, setDue] = useState("");
  const [type, setType] = useState<typeof TYPES[number]>("pset");
  const [weight, setWeight] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!name || !due) return;
    setSubmitting(true);
    try {
      await onAdd({ course, name, due, type, weight });
      setName(""); setDue(""); setWeight("");
      setOpen(false);
    } finally { setSubmitting(false); }
  };

  if (!open) {
    return (
      <button onClick={() => setOpen(true)}
              className="w-full mt-4 py-3 rounded-md border border-dashed border-neutral-700 text-sm text-neutral-400">
        + Add Task
      </button>
    );
  }

  return (
    <div className="mt-4 p-4 rounded-lg bg-card border border-border space-y-2">
      <div className="flex gap-2">
        <select value={course} onChange={e => setCourse(e.target.value)}
                className="flex-1 bg-neutral-900 border border-border rounded px-2 py-2 text-sm">
          {Object.keys(COURSE_COLORS).map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={type} onChange={e => setType(e.target.value as typeof TYPES[number])}
                className="bg-neutral-900 border border-border rounded px-2 py-2 text-sm">
          {TYPES.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
      <input placeholder="Task name" value={name} onChange={e => setName(e.target.value)}
             className="w-full bg-neutral-900 border border-border rounded px-2 py-2 text-sm" />
      <div className="flex gap-2">
        <input type="date" value={due} onChange={e => setDue(e.target.value)}
               className="flex-1 bg-neutral-900 border border-border rounded px-2 py-2 text-sm" />
        <input placeholder="Weight (opt)" value={weight} onChange={e => setWeight(e.target.value)}
               className="flex-1 bg-neutral-900 border border-border rounded px-2 py-2 text-sm" />
      </div>
      <div className="flex gap-2">
        <button onClick={submit} disabled={submitting || !name || !due}
                className="flex-1 py-2 rounded bg-neutral-100 text-neutral-900 text-sm font-semibold disabled:opacity-50">
          {submitting ? "Adding…" : "Add"}
        </button>
        <button onClick={() => setOpen(false)}
                className="px-4 py-2 rounded border border-border text-sm text-neutral-400">Cancel</button>
      </div>
    </div>
  );
}
