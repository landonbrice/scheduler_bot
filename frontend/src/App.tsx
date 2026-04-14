import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { Task, View } from "./types";
import { daysUntil } from "./utils";
import { Header } from "./components/Header";
import { AlertBanner } from "./components/AlertBanner";
import { CourseStats } from "./components/CourseStats";
import { ViewToggle } from "./components/ViewToggle";
import { Milestones } from "./components/Milestones";
import { TaskList } from "./components/TaskList";
import { AddTaskForm } from "./components/AddTaskForm";
import { CrunchNotice } from "./components/CrunchNotice";

export default function App() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [filter, setFilter] = useState<string>("all");
  const [view, setView] = useState<View>("priority");
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const { tasks } = await api.listTasks();
      setTasks(tasks);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    reload();
    const id = setInterval(reload, 60_000);
    return () => clearInterval(id);
  }, [reload]);

  const toggle = useCallback(async (id: string, done: boolean) => {
    setTasks(prev => prev.map(t => t.id === id ? { ...t, done } : t));
    try {
      if (done) await api.markDone(id);
      else await api.markUndo(id);
    } catch (e) {
      setError(String(e));
      await reload();
    }
  }, [reload]);

  const add = useCallback(async (body: Omit<Task, "id" | "done">) => {
    const { task } = await api.addTask(body);
    setTasks(prev => [...prev, task]);
  }, []);

  const today = new Date();
  const active = tasks.filter(t => !t.done);
  const dueTodayOrSoon = active.filter(t => {
    const d = daysUntil(t.due, today);
    return d >= 0 && d <= 7;
  });

  return (
    <div className="min-h-screen bg-bg text-neutral-200 p-4 max-w-3xl mx-auto">
      <Header today={today} activeCount={active.length} weekCount={dueTodayOrSoon.length} />
      {error && <div className="mb-3 p-2 rounded bg-red-950 border border-red-800 text-xs text-red-300">{error}</div>}
      <AlertBanner thisWeek={dueTodayOrSoon} />
      <CourseStats tasks={tasks} filter={filter} onFilter={setFilter} />
      <ViewToggle view={view} onView={setView} filter={filter} onResetFilter={() => setFilter("all")} />
      <Milestones tasks={filter === "all" ? tasks : tasks.filter(t => t.course === filter)} />
      <TaskList tasks={tasks} filter={filter} view={view} onToggle={toggle} />
      <AddTaskForm onAdd={add} />
      <CrunchNotice tasks={tasks} />
      <div className="mt-8 p-3 rounded bg-card border border-border text-[11px] text-neutral-500">
        Tap any task to toggle done. Pulls update every 60s.
      </div>
    </div>
  );
}
