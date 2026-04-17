import { categorySlug } from "./category";

export interface FixedBlockPillProps {
  title: string;
  category: string;
  start: string;
  end: string;
  location?: string;
}

/**
 * Tier-1 pill: solid category-colored background. Pure presentational —
 * class blocks and calendar events. 12px radius per canonical pill spec.
 */
export function FixedBlockPill({
  title,
  category,
  start,
  end,
  location,
}: FixedBlockPillProps) {
  const slug = categorySlug(category);

  return (
    <div
      className="flex flex-col gap-[2px] text-white cursor-pointer select-none"
      style={{
        padding: "var(--space-3) var(--space-4)",
        borderRadius: "var(--radius-pill)",
        backgroundColor: `var(--cat-${slug})`,
        boxShadow: "var(--shadow-pill)",
        fontFamily: "var(--font-body)",
      }}
    >
      <div
        style={{
          fontSize: "var(--text-pill)",
          fontWeight: 600,
          letterSpacing: "-0.005em",
          lineHeight: 1.2,
        }}
      >
        {title}
      </div>
      <div
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: "var(--text-meta)",
          letterSpacing: ".06em",
          textTransform: "uppercase",
          opacity: 0.82,
        }}
      >
        {formatRange(start, end)}
        {location ? ` · ${location}` : ""}
      </div>
    </div>
  );
}

function formatRange(start: string, end: string): string {
  // Schedule uses HH:MM strings; events can be ISO. Strip to HH:MM best-effort.
  return `${shortTime(start)}–${shortTime(end)}`;
}

function shortTime(s: string): string {
  // Accept "HH:MM" or ISO "...T14:30:00..." — fall back to raw.
  if (/^\d{2}:\d{2}/.test(s)) return s.slice(0, 5);
  const m = s.match(/T(\d{2}):(\d{2})/);
  if (m) return `${m[1]}:${m[2]}`;
  return s;
}
