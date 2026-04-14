export type Task = {
  id: string;
  course: "CorpFin" | "SCS III" | "APES" | "E4E" | string;
  name: string;
  due: string; // YYYY-MM-DD
  type: "exam" | "pset" | "essay" | "case" | "project" | "presentation" | "reading" | "ai-tutor" | "recurring" | "admin";
  weight: string;
  done: boolean;
  notes?: string | null;
};

export type View = "priority" | "timeline" | "course";

export type CalendarEvent = {
  summary: string;
  start: string;  // ISO string with timezone
  end: string;
  all_day: boolean;
};
