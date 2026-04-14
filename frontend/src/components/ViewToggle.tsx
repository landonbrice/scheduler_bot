import type { View } from "../types";

type Props = {
  view: View;
  onView: (v: View) => void;
  filter: string;
  onResetFilter: () => void;
};

const VIEWS: { key: View; label: string }[] = [
  { key: "priority", label: "Priority" },
  { key: "timeline", label: "Date" },
  { key: "course", label: "Course" },
];

export function ViewToggle({ view, onView, filter, onResetFilter }: Props) {
  return (
    <div className="flex gap-2 mb-4 items-center flex-wrap">
      {VIEWS.map(v => {
        const active = view === v.key;
        return (
          <button
            key={v.key}
            onClick={() => onView(v.key)}
            className={`rounded-md px-3 py-1.5 text-xs transition-colors ${
              active ? "bg-neutral-800 border-neutral-600 text-neutral-50" : "border-neutral-800 text-neutral-500"
            } border`}
          >
            {v.label}
          </button>
        );
      })}
      <div className="flex-1" />
      {filter !== "all" && (
        <button onClick={onResetFilter}
                className="rounded-md px-3 py-1.5 text-xs border border-neutral-800 text-neutral-400">
          All Courses
        </button>
      )}
    </div>
  );
}
