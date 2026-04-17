export interface CategoryColorRowProps {
  slug: string;
  label: string;
  color: string;
  onChange(color: string): void;
}

export function CategoryColorRow({ label, color, onChange }: CategoryColorRowProps) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "8px 0",
      }}
    >
      <span>{label}</span>
      <input
        type="color"
        value={color}
        onChange={(e) => onChange(e.target.value)}
        style={{
          width: 40,
          height: 28,
          border: "none",
          background: "transparent",
          cursor: "pointer",
        }}
      />
    </div>
  );
}
