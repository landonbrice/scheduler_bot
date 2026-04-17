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

export interface ClassInstance {
  title: string;
  category: string;
  date: string;
  start: string;
  end: string;
  location: string;
}

export interface SurfacedChip {
  kind: "thought" | "resurface";
  memory_id?: string;
  text: string;
  tags?: string[];
  trigger_date?: string;
  score?: number;
}

export interface TaskWithPriority extends Task {
  priority_score: number;
  tier: "red" | "amber" | "neutral";
  priority_boost?: number | null;
  impact_override?: string | null;
}

export interface SuggestResponse {
  picked: { task_id: string; reasoning: string } | null;
  alternatives: { task_id: string; reasoning: string }[];
  source: "llm" | "fallback";
  rate_limited?: boolean;
}

export interface CaptureResult {
  classification: "task" | "thought" | "resurface" | "ambiguous";
  confidence: number;
  created_task_id: string | null;
  undo_token: string | null;
  memory_stored: boolean;
  classifier_offline: boolean;
  suggested_category: string | null;
  suggested_due: string | null;
  raw_text: string;
  tags?: string[];
  defaulted_due?: boolean;
}
