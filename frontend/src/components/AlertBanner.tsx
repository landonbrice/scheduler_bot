import type { Task } from "../types";
import { formatDate } from "../utils";

export function AlertBanner({ thisWeek }: { thisWeek: Task[] }) {
  if (thisWeek.length === 0) return null;
  return (
    <div className="rounded-lg border border-red-600 p-3 mb-4 text-xs"
         style={{ background: "linear-gradient(135deg, #7f1d1d 0%, #991b1b 100%)" }}>
      <span className="font-bold text-red-300">⚠ THIS WEEK:</span>{" "}
      <span className="text-red-100">
        {thisWeek.map(t => `${t.name} (${t.course}, ${formatDate(t.due)})`).join(" · ")}
      </span>
    </div>
  );
}
