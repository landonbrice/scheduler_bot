export interface CalendarPickerListProps {
  available: { id: string; summary: string }[];
  selected: string[];
  onChange(ids: string[]): void;
}

export function CalendarPickerList({
  available,
  selected,
  onChange,
}: CalendarPickerListProps) {
  const toggle = (id: string) => {
    onChange(
      selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id],
    );
  };

  if (available.length === 0) {
    return (
      <p style={{ opacity: 0.6, margin: 0 }}>
        No calendars available. Make sure Google Calendar is authenticated.
      </p>
    );
  }

  return (
    <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
      {available.map((c) => (
        <li key={c.id} style={{ padding: "4px 0" }}>
          <label
            style={{
              display: "flex",
              gap: 8,
              alignItems: "center",
              cursor: "pointer",
            }}
          >
            <input
              type="checkbox"
              checked={selected.includes(c.id)}
              onChange={() => toggle(c.id)}
            />
            <span>{c.summary}</span>
          </label>
        </li>
      ))}
    </ul>
  );
}
