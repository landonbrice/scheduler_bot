type Props = { today: Date; activeCount: number; weekCount: number };

export function Header({ today, activeCount, weekCount }: Props) {
  const dateStr = today.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
  return (
    <div className="mb-6">
      <h1 className="text-xl font-bold text-neutral-50 tracking-tight">SPRING 2026 — COMMAND CENTER</h1>
      <p className="text-[11px] text-neutral-500 mt-1">
        {dateStr} · {activeCount} active · {weekCount} due this week
      </p>
    </div>
  );
}
