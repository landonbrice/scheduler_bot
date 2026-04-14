import type { Task } from "./types";

export function daysUntil(dateStr: string, today = new Date()): number {
  const d = new Date(dateStr + "T00:00:00");
  const t = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.ceil((d.getTime() - t.getTime()) / 86400000);
}

export function formatDate(dateStr: string): string {
  const d = new Date(dateStr + "T12:00:00");
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

export function urgencyColor(days: number): string {
  if (days < 0) return "#6b7280";
  if (days <= 2) return "#ef4444";
  if (days <= 7) return "#f59e0b";
  if (days <= 14) return "#3b82f6";
  return "#6b7280";
}

export function priorityScore(t: Task): number {
  if (t.done) return 999;
  const days = daysUntil(t.due);
  if (days < 0) return 998;
  let score = days;
  if (t.type === "exam") score -= 5;
  if (t.type === "essay" && t.weight?.includes("35")) score -= 4;
  if (t.type === "project") score -= 3;
  if (t.type === "presentation") score -= 2;
  return score;
}
