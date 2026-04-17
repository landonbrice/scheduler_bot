import { initData } from "./telegram";
import type {
  Task,
  TaskWithPriority,
  CalendarEvent,
  ClassInstance,
  SurfacedChip,
  SuggestResponse,
  CaptureResult,
} from "./types";

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

export type AddTaskBody = Omit<Task, "id" | "done"> & {
  priority_boost?: number | null;
};

export const api = {
  listTasks: () => request<{ tasks: TaskWithPriority[] }>("/api/tasks"),
  markDone: (id: string) =>
    request(`/api/tasks/${encodeURIComponent(id)}/done`, { method: "POST" }),
  markUndo: (id: string) =>
    request(`/api/tasks/${encodeURIComponent(id)}/undo`, { method: "POST" }),
  addTask: (body: AddTaskBody) =>
    request<{ task: Task }>("/api/tasks", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  briefing: () => request<{ text: string }>("/api/briefing"),
  calendar: () => request<{ events: CalendarEvent[] }>("/api/calendar"),
  getSchedule: (start: string) =>
    request<{
      term_start: string | null;
      term_end: string | null;
      week_start: string;
      instances: ClassInstance[];
    }>(`/api/schedule?start=${encodeURIComponent(start)}`),
  getSurfaced: (start: string, days = 7) =>
    request<{ surfaced: Record<string, SurfacedChip[]> }>(
      `/api/notes/surfaced?start=${encodeURIComponent(start)}&days=${days}`,
    ),
  flagTask: (id: string) =>
    request<{ task_id: string; priority_boost: number | null }>(
      `/api/tasks/${encodeURIComponent(id)}/flag`,
      { method: "POST" },
    ),
  dismissMemory: (memory_id: string) =>
    request(`/api/capture/note/dismiss`, {
      method: "POST",
      body: JSON.stringify({ memory_id }),
    }),
  undoCreate: (id: string) =>
    request(`/api/tasks/${encodeURIComponent(id)}/undo-create`, {
      method: "POST",
    }),
  suggest: (duration: number, start_iso: string) =>
    request<SuggestResponse>(
      `/api/suggest?duration=${duration}&start_iso=${encodeURIComponent(start_iso)}`,
    ),
  searchNotes: (q: string) =>
    request<{ results: SurfacedChip[]; offline: boolean }>(
      `/api/notes/search?q=${encodeURIComponent(q)}`,
    ),
  captureNote: (text: string) =>
    request<CaptureResult>(`/api/capture/note`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
};
