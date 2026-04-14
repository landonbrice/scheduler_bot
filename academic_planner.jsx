import { useState, useMemo } from "react";

const TASKS = [
  // === CORP FIN (BUSN 20410) ===
  { id: 1, course: "CorpFin", name: "Problem Set 1", due: "2026-04-03", type: "pset", weight: "part of 15%", done: true, notes: "Already past due" },
  { id: 2, course: "CorpFin", name: "Case 1", due: "2026-04-08", type: "case", weight: "part of 15%", done: true, notes: "Already past due" },
  { id: 3, course: "CorpFin", name: "Problem Set 2", due: "2026-04-10", type: "pset", weight: "part of 15%", done: true, notes: "Already past due" },
  { id: 4, course: "CorpFin", name: "Case 2", due: "2026-04-15", type: "case", weight: "part of 15%", notes: "From screenshot — dated 2025 but likely same schedule" },
  { id: 5, course: "CorpFin", name: "Problem Set 3", due: "2026-04-17", type: "pset", weight: "part of 15%" },
  { id: 6, course: "CorpFin", name: "Problem Set 4", due: "2026-04-24", type: "pset", weight: "part of 15%" },
  { id: 7, course: "CorpFin", name: "Midterm Exam", due: "2026-05-01", type: "exam", weight: "25% (or 0% if final higher)", notes: "In-class, closed book" },
  { id: 8, course: "CorpFin", name: "Problem Set 5", due: "2026-05-08", type: "pset", weight: "part of 15%" },
  { id: 9, course: "CorpFin", name: "Valuation Project", due: "2026-05-09", type: "project", weight: "15%", notes: "Group presentation, 15 min. Must use ChatGPT for some part. Topic due Wk 5." },
  { id: 10, course: "CorpFin", name: "Final Exam", due: "2026-05-22", type: "exam", weight: "35-60%", notes: "In-class, closed book. Higher weight if midterm dropped." },

  // === SCS III (Self, Culture, Society) ===
  { id: 11, course: "SCS III", name: "Canvas Posts (ongoing)", due: "2026-04-13", type: "recurring", weight: "5%", notes: "Due 11:59pm night before each class. Every M/W class." },
  { id: 12, course: "SCS III", name: "Self-Feedback Exercise", due: "2026-04-19", type: "essay", weight: "10%" },
  { id: 13, course: "SCS III", name: "Midterm Essay", due: "2026-04-28", type: "essay", weight: "35%", notes: "Major paper. Due 11:59 PM." },
  { id: 14, course: "SCS III", name: "Final Paper Presentation", due: "2026-05-13", type: "presentation", weight: "5%", notes: "In-class presentations" },
  { id: 15, course: "SCS III", name: "Final Paper", due: "2026-05-28", type: "essay", weight: "30%", notes: "Due 11:59 PM" },

  // === APES (ANTH 21428) ===
  { id: 16, course: "APES", name: "Read: 99% Primate Behavior + Diet articles", due: "2026-04-14", type: "reading", weight: "attendance", notes: "Before Tuesday lecture" },
  { id: 17, course: "APES", name: "Online Midterm Exam", due: "2026-04-21", type: "exam", weight: "50/280 pts (18%)", notes: "Online, 9am-8pm. Covers Weeks 1-4." },
  { id: 18, course: "APES", name: "Debate Presentation (group)", due: "2026-04-28", type: "presentation", weight: "50/280 pts (18%)", notes: "Must present on scheduled day. No exceptions." },
  { id: 19, course: "APES", name: "Zoo Report / Individual Poster", due: "2026-05-14", type: "project", weight: "50/280 pts (18%)", notes: "Choose poster or zoo report. Hard + electronic copy." },
  { id: 20, course: "APES", name: "Online Final Exam", due: "2026-05-21", type: "exam", weight: "50/280 pts (18%)", notes: "Online, 9am-8pm. Weeks 5-9 focus + key terms." },

  // === E4E (Economics for Everyone) ===
  { id: 21, course: "E4E", name: "AI Tutor Wk 3 (Discrimination)", due: "2026-04-13", type: "ai-tutor", weight: "part of discussion grade", notes: "Due Monday 11:59pm" },
  { id: 22, course: "E4E", name: "AI Tutor Wk 4 (Behavioral Econ)", due: "2026-04-20", type: "ai-tutor", weight: "part of discussion grade" },
  { id: 23, course: "E4E", name: "Midterm Exam", due: "2026-04-21", type: "exam", weight: "midterm", notes: "In-class Tuesday" },
  { id: 24, course: "E4E", name: "AI Tutor Wk 6 (Markets)", due: "2026-05-04", type: "ai-tutor", weight: "part of discussion grade" },
  { id: 25, course: "E4E", name: "AI Tutor Wk 7 (Uncertainty)", due: "2026-05-11", type: "ai-tutor", weight: "part of discussion grade" },
  { id: 26, course: "E4E", name: "AI Tutor Wk 8 (Risk/Labor)", due: "2026-05-18", type: "ai-tutor", weight: "part of discussion grade" },
  { id: 27, course: "E4E", name: "Midterm 2 / Final Exam", due: "2026-05-21", type: "exam", weight: "midterm", notes: "In-class Thursday" },
  { id: 28, course: "E4E", name: "AI Tutor Wk 9", due: "2026-05-25", type: "ai-tutor", weight: "part of discussion grade" },
  { id: 29, course: "E4E", name: "Final Project", due: "2026-05-29", type: "project", weight: "TBD", notes: "Details TBD. Due finals week." },

  // === From handwritten notes screenshot ===
  { id: 30, course: "APES", name: "APES Debate Presentation (Slideshow + Script + Sources)", due: "2026-04-28", type: "presentation", weight: "50/280 pts", notes: "Week 6. Slideshow + debate script + sources needed." },
];

const COURSE_COLORS = {
  "CorpFin": { bg: "#1a1a2e", text: "#e0d6ff", accent: "#a78bfa", light: "#2d2b55" },
  "SCS III": { bg: "#1c1917", text: "#fde68a", accent: "#f59e0b", light: "#292524" },
  "APES": { bg: "#052e16", text: "#bbf7d0", accent: "#34d399", light: "#14532d" },
  "E4E": { bg: "#1e1b4b", text: "#c7d2fe", accent: "#818cf8", light: "#312e81" },
};

const TYPE_ICONS = {
  exam: "◆",
  essay: "✎",
  pset: "≡",
  case: "◈",
  project: "★",
  presentation: "▶",
  reading: "◻",
  "ai-tutor": "⚡",
  recurring: "↻",
};

const TODAY = new Date("2026-04-13");

function daysUntil(dateStr) {
  const d = new Date(dateStr);
  const diff = Math.ceil((d - TODAY) / (1000 * 60 * 60 * 24));
  return diff;
}

function formatDate(dateStr) {
  const d = new Date(dateStr + "T12:00:00");
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

function urgencyColor(days) {
  if (days < 0) return "#6b7280";
  if (days <= 2) return "#ef4444";
  if (days <= 7) return "#f59e0b";
  if (days <= 14) return "#3b82f6";
  return "#6b7280";
}

function priorityScore(task) {
  const days = daysUntil(task.due);
  if (task.done) return 999;
  if (days < 0) return 998;
  let score = days;
  if (task.type === "exam") score -= 5;
  if (task.type === "essay" && task.weight?.includes("35")) score -= 4;
  if (task.type === "project") score -= 3;
  if (task.type === "presentation") score -= 2;
  return score;
}

export default function AcademicPlanner() {
  const [filter, setFilter] = useState("all");
  const [completedIds, setCompletedIds] = useState(new Set(TASKS.filter(t => t.done).map(t => t.id)));
  const [view, setView] = useState("priority"); // priority | timeline | course

  const toggleDone = (id) => {
    setCompletedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const filteredTasks = useMemo(() => {
    let tasks = TASKS.map(t => ({ ...t, done: completedIds.has(t.id) }));
    if (filter !== "all") tasks = tasks.filter(t => t.course === filter);
    if (view === "priority") {
      tasks.sort((a, b) => priorityScore(a) - priorityScore(b));
    } else if (view === "timeline") {
      tasks.sort((a, b) => new Date(a.due) - new Date(b.due));
    } else {
      tasks.sort((a, b) => {
        if (a.course !== b.course) return a.course.localeCompare(b.course);
        return new Date(a.due) - new Date(b.due);
      });
    }
    return tasks;
  }, [filter, completedIds, view]);

  const upcoming = filteredTasks.filter(t => !t.done && daysUntil(t.due) >= 0);
  const thisWeek = upcoming.filter(t => daysUntil(t.due) <= 7);
  const examsProjects = upcoming.filter(t => ["exam", "project", "essay", "presentation"].includes(t.type));

  // Crunch week detection
  const weekBuckets = {};
  upcoming.forEach(t => {
    const weekStart = new Date(t.due);
    weekStart.setDate(weekStart.getDate() - weekStart.getDay());
    const key = weekStart.toISOString().split("T")[0];
    weekBuckets[key] = (weekBuckets[key] || 0) + 1;
  });
  const crunchWeeks = Object.entries(weekBuckets).filter(([, count]) => count >= 3).map(([date]) => date);

  return (
    <div style={{
      minHeight: "100vh",
      background: "#0a0a0a",
      color: "#e5e5e5",
      fontFamily: "'JetBrains Mono', 'SF Mono', 'Fira Code', monospace",
      padding: "24px",
    }}>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <h1 style={{
          fontSize: 28,
          fontWeight: 700,
          color: "#fafafa",
          margin: 0,
          letterSpacing: "-0.5px",
        }}>
          SPRING 2026 — COMMAND CENTER
        </h1>
        <p style={{ color: "#737373", fontSize: 13, marginTop: 4 }}>
          Today is {formatDate("2026-04-13")} · {upcoming.length} active tasks · {thisWeek.length} due this week
        </p>
      </div>

      {/* Alert Banner */}
      {thisWeek.length > 0 && (
        <div style={{
          background: "linear-gradient(135deg, #7f1d1d 0%, #991b1b 100%)",
          border: "1px solid #dc2626",
          borderRadius: 8,
          padding: "14px 18px",
          marginBottom: 20,
          fontSize: 13,
        }}>
          <span style={{ fontWeight: 700, color: "#fca5a5" }}>⚠ THIS WEEK:</span>{" "}
          {thisWeek.map(t => `${t.name} (${t.course}, ${formatDate(t.due)})`).join(" · ")}
        </div>
      )}

      {/* Stats Row */}
      <div style={{ display: "flex", gap: 12, marginBottom: 24, flexWrap: "wrap" }}>
        {Object.entries(COURSE_COLORS).map(([course, colors]) => {
          const courseTasks = TASKS.filter(t => t.course === course);
          const remaining = courseTasks.filter(t => !completedIds.has(t.id) && daysUntil(t.due) >= 0).length;
          const nextTask = courseTasks
            .filter(t => !completedIds.has(t.id) && daysUntil(t.due) >= 0)
            .sort((a, b) => new Date(a.due) - new Date(b.due))[0];
          return (
            <div
              key={course}
              onClick={() => setFilter(filter === course ? "all" : course)}
              style={{
                background: filter === course ? colors.light : "#171717",
                border: `1px solid ${filter === course ? colors.accent : "#262626"}`,
                borderRadius: 8,
                padding: "12px 16px",
                flex: "1 1 140px",
                cursor: "pointer",
                transition: "all 0.15s",
              }}
            >
              <div style={{ fontSize: 11, color: colors.accent, fontWeight: 700, textTransform: "uppercase", letterSpacing: 1 }}>
                {course}
              </div>
              <div style={{ fontSize: 22, fontWeight: 700, color: colors.text, marginTop: 2 }}>
                {remaining}
              </div>
              <div style={{ fontSize: 11, color: "#737373", marginTop: 2 }}>
                {nextTask ? `Next: ${nextTask.name.substring(0, 20)}` : "All done"}
              </div>
            </div>
          );
        })}
      </div>

      {/* View Toggle */}
      <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
        {[
          { key: "priority", label: "By Priority" },
          { key: "timeline", label: "By Date" },
          { key: "course", label: "By Course" },
        ].map(v => (
          <button
            key={v.key}
            onClick={() => setView(v.key)}
            style={{
              background: view === v.key ? "#262626" : "transparent",
              border: `1px solid ${view === v.key ? "#525252" : "#262626"}`,
              color: view === v.key ? "#fafafa" : "#737373",
              borderRadius: 6,
              padding: "6px 14px",
              fontSize: 12,
              cursor: "pointer",
              fontFamily: "inherit",
            }}
          >
            {v.label}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <button
          onClick={() => setFilter("all")}
          style={{
            background: filter === "all" ? "#262626" : "transparent",
            border: `1px solid ${filter === "all" ? "#525252" : "#262626"}`,
            color: filter === "all" ? "#fafafa" : "#737373",
            borderRadius: 6,
            padding: "6px 14px",
            fontSize: 12,
            cursor: "pointer",
            fontFamily: "inherit",
          }}
        >
          All Courses
        </button>
      </div>

      {/* Big Milestones Section */}
      <div style={{ marginBottom: 28 }}>
        <h2 style={{ fontSize: 13, color: "#a3a3a3", fontWeight: 600, textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 10 }}>
          Major Milestones
        </h2>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          {examsProjects
            .filter(t => filter === "all" || t.course === filter)
            .sort((a, b) => new Date(a.due) - new Date(b.due))
            .slice(0, 8)
            .map(t => {
              const days = daysUntil(t.due);
              const colors = COURSE_COLORS[t.course];
              return (
                <div key={t.id} style={{
                  background: colors.light,
                  border: `1px solid ${colors.accent}40`,
                  borderRadius: 8,
                  padding: "10px 14px",
                  minWidth: 160,
                  flex: "0 1 auto",
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 11, color: colors.accent, fontWeight: 700 }}>{t.course}</span>
                    <span style={{ fontSize: 11, color: urgencyColor(days), fontWeight: 700 }}>
                      {days === 0 ? "TODAY" : days === 1 ? "TOMORROW" : `${days}d`}
                    </span>
                  </div>
                  <div style={{ fontSize: 13, color: colors.text, fontWeight: 600, marginTop: 4 }}>
                    {TYPE_ICONS[t.type]} {t.name}
                  </div>
                  <div style={{ fontSize: 11, color: "#737373", marginTop: 2 }}>{formatDate(t.due)}</div>
                </div>
              );
            })}
        </div>
      </div>

      {/* Task List */}
      <div>
        <h2 style={{ fontSize: 13, color: "#a3a3a3", fontWeight: 600, textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 10 }}>
          All Tasks {filter !== "all" && `— ${filter}`}
        </h2>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {filteredTasks.map(t => {
            const days = daysUntil(t.due);
            const colors = COURSE_COLORS[t.course];
            const isDone = completedIds.has(t.id);
            const isPast = days < 0 && !isDone;
            return (
              <div
                key={t.id}
                onClick={() => toggleDone(t.id)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  background: isDone ? "#0a0a0a" : isPast ? "#1a0a0a" : "#141414",
                  border: `1px solid ${isDone ? "#1a1a1a" : isPast ? "#3f1515" : "#222"}`,
                  borderLeft: `3px solid ${isDone ? "#333" : colors.accent}`,
                  borderRadius: 6,
                  padding: "10px 14px",
                  cursor: "pointer",
                  opacity: isDone ? 0.4 : 1,
                  transition: "all 0.15s",
                }}
              >
                {/* Checkbox */}
                <div style={{
                  width: 18,
                  height: 18,
                  borderRadius: 4,
                  border: `2px solid ${isDone ? "#525252" : colors.accent}`,
                  background: isDone ? colors.accent : "transparent",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 12,
                  color: "#0a0a0a",
                  fontWeight: 700,
                  flexShrink: 0,
                }}>
                  {isDone && "✓"}
                </div>

                {/* Type icon */}
                <span style={{ fontSize: 14, color: colors.accent, width: 18, textAlign: "center", flexShrink: 0 }}>
                  {TYPE_ICONS[t.type] || "·"}
                </span>

                {/* Course label */}
                <span style={{
                  fontSize: 10,
                  color: colors.accent,
                  background: `${colors.accent}15`,
                  padding: "2px 6px",
                  borderRadius: 3,
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: 0.5,
                  flexShrink: 0,
                  width: 60,
                  textAlign: "center",
                }}>
                  {t.course}
                </span>

                {/* Task name */}
                <span style={{
                  fontSize: 13,
                  color: isDone ? "#525252" : "#e5e5e5",
                  fontWeight: 500,
                  textDecoration: isDone ? "line-through" : "none",
                  flex: 1,
                  minWidth: 0,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}>
                  {t.name}
                </span>

                {/* Weight */}
                {t.weight && (
                  <span style={{ fontSize: 10, color: "#525252", flexShrink: 0 }}>
                    {t.weight}
                  </span>
                )}

                {/* Date + urgency */}
                <div style={{ textAlign: "right", flexShrink: 0, minWidth: 90 }}>
                  <div style={{ fontSize: 11, color: "#737373" }}>{formatDate(t.due)}</div>
                  <div style={{ fontSize: 10, color: urgencyColor(days), fontWeight: 700 }}>
                    {isDone ? "DONE" : days < 0 ? "PAST DUE" : days === 0 ? "TODAY" : days === 1 ? "TOMORROW" : `${days} days`}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Crunch Week Warnings */}
      {crunchWeeks.length > 0 && (
        <div style={{ marginTop: 28, padding: "14px 18px", background: "#1c1917", border: "1px solid #78350f", borderRadius: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "#fbbf24", marginBottom: 6 }}>⚡ CRUNCH WEEKS DETECTED</div>
          <div style={{ fontSize: 12, color: "#a3a3a3" }}>
            Weeks with 3+ overlapping deadlines:{" "}
            {crunchWeeks.map(w => {
              const d = new Date(w + "T12:00:00");
              return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
            }).join(", ")}
          </div>
        </div>
      )}

      {/* Notes */}
      <div style={{ marginTop: 28, padding: "14px 18px", background: "#141414", border: "1px solid #262626", borderRadius: 8, fontSize: 12, color: "#737373" }}>
        <div style={{ fontWeight: 700, color: "#a3a3a3", marginBottom: 6 }}>KEY NOTES</div>
        <div>• CorpFin Case 2 date (4/15) inferred from 2025 schedule — confirm with Canvas</div>
        <div>• SCS Canvas posts are recurring before each M/W class — not tracked individually here</div>
        <div>• APES debate presentation date (4/28) = Week 6 per syllabus — confirm your group's slot</div>
        <div>• CorpFin project topic must be sent to professor by Week 5 (~Apr 20)</div>
        <div>• E4E drops lowest 2 AI tutor discussion grades</div>
        <div>• Click any task to mark it complete</div>
      </div>
    </div>
  );
}
