export interface HourAxisProps {
  startHour?: number;
  endHour?: number;
}

export const PX_PER_HOUR = 40;

/**
 * Left-gutter hour axis. Renders mono-labeled ticks for each hour
 * between startHour and endHour. Used as a sibling column in WeekView.
 */
export function HourAxis({ startHour = 7, endHour = 23 }: HourAxisProps) {
  const hours: number[] = [];
  for (let h = startHour; h <= endHour; h++) hours.push(h);

  return (
    <div
      className="relative flex-shrink-0"
      style={{
        width: 44,
        paddingTop: 8,
        height: (endHour - startHour) * PX_PER_HOUR,
        fontFamily: "var(--font-mono)",
        fontSize: "var(--text-meta)",
        letterSpacing: ".08em",
        textTransform: "uppercase",
        color: "var(--ink-tertiary)",
      }}
      aria-hidden="true"
    >
      {hours.map((h, i) => (
        <div
          key={h}
          style={{
            position: "absolute",
            top: (h - startHour) * PX_PER_HOUR,
            left: 0,
            right: 6,
            textAlign: "right",
            lineHeight: 1,
            paddingRight: 4,
            borderTop: i === 0 ? "none" : "1px dashed var(--ink-hairline)",
            paddingTop: 2,
          }}
        >
          {formatHour(h)}
        </div>
      ))}
    </div>
  );
}

function formatHour(h: number): string {
  if (h === 0) return "12a";
  if (h === 12) return "12p";
  if (h < 12) return `${h}a`;
  return `${h - 12}p`;
}
