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
  getSchedule: (start: string) =>
    request<{ classes: import("./types").ClassInstance[] }>(`/api/schedule?start=${encodeURIComponent(start)}`),
  getSurfaced: (start: string, days = 7) =>
    request<{ by_day: Record<string, import("./types").SurfacedChip[]> }>(
      `/api/notes/surfaced?start=${encodeURIComponent(start)}&days=${days}`,
    ),
  flagTask: (id: string) =>
    request(`/api/tasks/${encodeURIComponent(id)}/flag`, { method: "POST" }),
  dismissMemory: (memory_id: string) =>
    request(`/api/capture/note/dismiss`, {
      method: "POST",
      body: JSON.stringify({ memory_id }),
    }),
  undoCreate: (id: string) =>
    request(`/api/tasks/${encodeURIComponent(id)}/undo-create`, { method: "POST" }),
  suggest: (duration: number, start_iso: string) =>
    request<import("./types").SuggestResponse>(
      `/api/suggest?duration=${duration}&start_iso=${encodeURIComponent(start_iso)}`,
    ),
  searchNotes: (q: string) =>
    request<{ results: import("./types").SurfacedChip[] }>(
      `/api/notes/search?q=${encodeURIComponent(q)}`,
    ),
  captureNote: (text: string) =>
    request<import("./types").CaptureResult>(`/api/capture/note`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
};
