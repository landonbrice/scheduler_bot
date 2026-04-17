import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type {
  CalendarEvent,
  ClassInstance,
  SurfacedChip,
  TaskWithPriority,
} from "./types";
import { TabBar, type Tab } from "./components/TabBar";
import { WeekView } from "./components/week/WeekView";
import { OverdueDrawer } from "./components/week/OverdueDrawer";
import { TaskList } from "./components/TaskList";
import { QuickAdd } from "./components/QuickAdd";
import { CaptureFAB } from "./components/CaptureFAB";
import { CaptureModal } from "./components/CaptureModal";
import { SuggestModal } from "./components/SuggestModal";
import { SearchModal } from "./components/SearchModal";
import { DegradedBanner } from "./components/DegradedBanner";
import { SettingsTab } from "./components/SettingsTab";

function mondayOf(d: Date): Date {
  const out = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const offset = (out.getDay() + 6) % 7; // Monday = 0
  out.setDate(out.getDate() - offset);
  return out;
}

function toISODate(d: Date): string {
  const y = d.getFullYear();
  const m = (d.getMonth() + 1).toString().padStart(2, "0");
  const day = d.getDate().toString().padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export default function App() {
  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;
    try { tg.expand?.(); } catch { /* no-op on older clients */ }
    try { tg.disableVerticalSwipes?.(); } catch { /* no-op on older clients */ }
  }, []);

  const [tab, setTab] = useState<Tab>("week");
  const [tasks, setTasks] = useState<TaskWithPriority[]>([]);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [schedule, setSchedule] = useState<ClassInstance[]>([]);
  const [surfaced, setSurfaced] = useState<Record<string, SurfacedChip[]>>({});
  const [weekStart, setWeekStart] = useState<Date>(() => mondayOf(new Date()));

  const [searchOpen, setSearchOpen] = useState(false);
  const [captureOpen, setCaptureOpen] = useState(false);
  const [overdueOpen, setOverdueOpen] = useState(false);
  const [suggest, setSuggest] = useState<{ duration: number; iso: string } | null>(null);

  const [showScores, setShowScores] = useState(false);
  const [banner, setBanner] = useState({
    classifierOffline: false,
    membaseOffline: false,
  });

  const [error, setError] = useState<string | null>(null);
  const [authExpired, setAuthExpired] = useState(false);

  const updateStatus = useCallback(
    (flags: { classifierOffline?: boolean; membaseOffline?: boolean }) => {
      setBanner((b) => ({
        classifierOffline:
          flags.classifierOffline !== undefined
            ? flags.classifierOffline
            : b.classifierOffline,
        membaseOffline:
          flags.membaseOffline !== undefined
            ? flags.membaseOffline
            : b.membaseOffline,
      }));
    },
    [],
  );

  const reload = useCallback(async () => {
    const ws = toISODate(weekStart);
    try {
      const [tasksRes, calRes, schedRes, surfRes] = await Promise.all([
        api.listTasks(),
        api.calendar().catch(() => {
          setBanner((b) => ({ ...b, membaseOffline: b.membaseOffline }));
          return { events: [] as CalendarEvent[] };
        }),
        api.getSchedule(ws).catch(() => ({
          term_start: null,
          term_end: null,
          week_start: ws,
          instances: [] as ClassInstance[],
        })),
        api.getSurfaced(ws, 7).catch(() => ({
          surfaced: {} as Record<string, SurfacedChip[]>,
        })),
      ]);
      setTasks(tasksRes.tasks);
      setEvents(calRes.events);
      setSchedule(schedRes.instances);
      setSurfaced(surfRes.surfaced);
      setError(null);
      setAuthExpired(false);
    } catch (e) {
      const msg = String(e);
      if (msg.includes("401")) {
        setAuthExpired(true);
      } else {
        setError(msg);
      }
    }
  }, [weekStart]);

  useEffect(() => {
    reload();
    const id = window.setInterval(reload, 60_000);
    return () => window.clearInterval(id);
  }, [reload]);

  // --- Handlers ---

  const onTaskToggle = useCallback(
    async (id: string, done: boolean) => {
      setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, done } : t)));
      try {
        if (done) await api.markDone(id);
        else await api.markUndo(id);
      } catch (e) {
        setError(String(e));
        reload();
      }
    },
    [reload],
  );

  const onTaskFlag = useCallback(
    async (id: string) => {
      try {
        await api.flagTask(id);
        reload();
      } catch (e) {
        setError(String(e));
      }
    },
    [reload],
  );

  const onChipDismiss = useCallback(
    async (memory_id: string) => {
      try {
        await api.dismissMemory(memory_id);
        reload();
      } catch (e) {
        setError(String(e));
        setBanner((b) => ({ ...b, membaseOffline: true }));
      }
    },
    [reload],
  );

  const onChipCreateTask = useCallback((_chip: SurfacedChip) => {
    setCaptureOpen(true);
  }, []);

  const onEmptyBlockTap = useCallback((startIso: string, duration: number) => {
    setSuggest({ duration, iso: startIso });
  }, []);

  const goPrevWeek = useCallback(() => {
    setWeekStart((d) => {
      const n = new Date(d);
      n.setDate(n.getDate() - 7);
      return n;
    });
  }, []);

  const goNextWeek = useCallback(() => {
    setWeekStart((d) => {
      const n = new Date(d);
      n.setDate(n.getDate() + 7);
      return n;
    });
  }, []);

  const goToday = useCallback(() => {
    setWeekStart(mondayOf(new Date()));
  }, []);

  // Overdue: active tasks whose due < today.
  const overdueTasks = useMemo(() => {
    const startOfToday = new Date();
    startOfToday.setHours(0, 0, 0, 0);
    return tasks.filter((t) => {
      if (t.done) return false;
      const d = new Date(t.due + "T00:00:00");
      return d.getTime() < startOfToday.getTime();
    });
  }, [tasks]);

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--surface-paper)",
        color: "var(--ink-primary)",
        fontFamily: "var(--font-body)",
        paddingBottom: 72,
      }}
    >
      <DegradedBanner {...banner} />

      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "flex-end",
          padding: "8px 12px 0",
        }}
      >
        <button
          type="button"
          onClick={() => setSearchOpen(true)}
          aria-label="Search notes"
          style={{
            border: "1px solid var(--ink-hairline)",
            background: "var(--surface-card)",
            borderRadius: 999,
            padding: "6px 14px",
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            letterSpacing: ".08em",
            textTransform: "uppercase",
            color: "var(--ink-secondary)",
            cursor: "pointer",
          }}
        >
          Search
        </button>
      </div>

      {authExpired && (
        <div
          style={{
            margin: "10px 12px",
            padding: "8px 10px",
            borderRadius: 6,
            background: "var(--tier-amber-soft)",
            color: "var(--tier-amber)",
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            textAlign: "center",
          }}
        >
          Session expired — please close and reopen from Telegram.
        </div>
      )}
      {error && (
        <div
          style={{
            margin: "10px 12px",
            padding: "8px 10px",
            borderRadius: 6,
            background: "var(--tier-red-soft)",
            color: "var(--tier-red)",
            fontFamily: "var(--font-mono)",
            fontSize: 11,
          }}
        >
          {error}
        </div>
      )}

      {tab === "week" && (
        <div style={{ padding: "10px 8px 16px" }}>
          <WeekView
            tasks={tasks}
            schedule={schedule}
            events={events}
            surfaced={surfaced}
            weekStart={weekStart}
            onPrevWeek={goPrevWeek}
            onNextWeek={goNextWeek}
            onToday={goToday}
            onTaskToggle={onTaskToggle}
            onTaskFlag={onTaskFlag}
            onChipDismiss={onChipDismiss}
            onChipCreateTask={onChipCreateTask}
            onEmptyBlockTap={onEmptyBlockTap}
            showScores={showScores}
            overdueTasks={overdueTasks}
            onOverdueOpen={() => setOverdueOpen(true)}
          />
        </div>
      )}

      {tab === "tasks" && (
        <div
          style={{
            padding: "14px 14px 24px",
            maxWidth: 720,
            margin: "0 auto",
          }}
        >
          <QuickAdd
            currentFilter="all"
            onCreated={reload}
            onStatus={updateStatus}
          />
          <TaskList
            tasks={tasks}
            filter="all"
            view="priority"
            onToggle={onTaskToggle}
          />
        </div>
      )}

      {tab === "settings" && (
        <SettingsTab showScores={showScores} onToggleScores={setShowScores} />
      )}

      {/* Floating action button + tab bar */}
      <CaptureFAB onClick={() => setCaptureOpen(true)} />
      <TabBar current={tab} onChange={setTab} />

      {/* Modals */}
      <CaptureModal
        open={captureOpen}
        onClose={() => setCaptureOpen(false)}
        onTaskCreated={() => {
          /* reload handled via onReload */
        }}
        classifierOffline={banner.classifierOffline}
        onReload={reload}
        onStatus={updateStatus}
      />
      <SuggestModal
        open={suggest !== null}
        onClose={() => setSuggest(null)}
        duration={suggest?.duration ?? 60}
        startIso={suggest?.iso ?? ""}
        tasks={tasks}
        onPickTask={() => setSuggest(null)}
      />
      <SearchModal
        open={searchOpen}
        onClose={() => setSearchOpen(false)}
        onCreateTaskFromMemory={() => {
          setSearchOpen(false);
          setCaptureOpen(true);
        }}
      />
      <OverdueDrawer
        open={overdueOpen}
        tasks={overdueTasks}
        onClose={() => setOverdueOpen(false)}
        onToggle={onTaskToggle}
      />
    </div>
  );
}
