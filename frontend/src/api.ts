import { initData } from "./telegram";
import type { Task, CalendarEvent } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": initData(),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

export const api = {
  listTasks: () => request<{ tasks: Task[] }>("/api/tasks"),
  markDone: (id: string) => request(`/api/tasks/${encodeURIComponent(id)}/done`, { method: "POST" }),
  markUndo: (id: string) => request(`/api/tasks/${encodeURIComponent(id)}/undo`, { method: "POST" }),
  addTask: (body: Omit<Task, "id" | "done">) =>
    request<{ task: Task }>("/api/tasks", { method: "POST", body: JSON.stringify(body) }),
  briefing: () => request<{ text: string }>("/api/briefing"),
  calendar: () => request<{ events: CalendarEvent[] }>("/api/calendar"),
};
