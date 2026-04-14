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
