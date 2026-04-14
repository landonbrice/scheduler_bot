import type { Task } from "../types";
import { daysUntil } from "../utils";

export function CrunchNotice({ tasks }: { tasks: Task[] }) {
  const buckets: Record<string, number> = {};
  tasks.filter(t => !t.done && daysUntil(t.due) >= 0).forEach(t => {
    const d = new Date(t.due + "T00:00:00");
    d.setDate(d.getDate() - d.getDay());
    const key = d.toISOString().slice(0, 10);
    buckets[key] = (buckets[key] ?? 0) + 1;
  });
  const crunch = Object.entries(buckets).filter(([, n]) => n >= 3).map(([k]) => k);
  if (crunch.length === 0) return null;
  return (
    <div className="mt-6 p-4 rounded-lg border" style={{ background: "#1c1917", borderColor: "#78350f" }}>
      <div className="text-xs font-bold text-amber-400 mb-1">⚡ CRUNCH WEEKS DETECTED</div>
      <div className="text-xs text-neutral-400">
        Weeks with 3+ deadlines: {crunch.map(w => new Date(w + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })).join(", ")}
      </div>
    </div>
  );
}
