export const COURSE_COLORS: Record<string, { bg: string; text: string; accent: string; light: string }> = {
  "CorpFin": { bg: "#1a1a2e", text: "#e0d6ff", accent: "#a78bfa", light: "#2d2b55" },
  "SCS III": { bg: "#1c1917", text: "#fde68a", accent: "#f59e0b", light: "#292524" },
  "APES":    { bg: "#052e16", text: "#bbf7d0", accent: "#34d399", light: "#14532d" },
  "E4E":     { bg: "#1e1b4b", text: "#c7d2fe", accent: "#818cf8", light: "#312e81" },
};

export const TYPE_ICONS: Record<string, string> = {
  exam: "◆", essay: "✎", pset: "≡", case: "◈",
  project: "★", presentation: "▶", reading: "◻",
  "ai-tutor": "⚡", recurring: "↻", admin: "·",
};

export const DEFAULT_COURSE_COLOR = { bg: "#111", text: "#ddd", accent: "#999", light: "#222" };
