import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { CategoryColorRow } from "./settings/CategoryColorRow";
import { CalendarPickerList } from "./settings/CalendarPickerList";

interface Category {
  label: string;
  color: string;
}

export interface SettingsTabProps {
  showScores: boolean;
  onToggleScores(v: boolean): void;
}

export function SettingsTab({ showScores, onToggleScores }: SettingsTabProps) {
  const [categories, setCategories] = useState<Record<string, Category>>({});
  const [includedCalendarIds, setIncludedCalendarIds] = useState<string[]>([]);
  const [available, setAvailable] = useState<
    { id: string; summary: string }[]
  >([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const [s, cals] = await Promise.all([
        api.getSettings(),
        api
          .listAvailableCalendars()
          .catch(() => ({ calendars: [] as { id: string; summary: string }[] })),
      ]);
      setCategories(s.categories || {});
      setIncludedCalendarIds(s.settings?.included_calendar_ids || []);
      setAvailable(cals.calendars || []);
      if (s.settings?.show_priority_score !== undefined) {
        onToggleScores(!!s.settings.show_priority_score);
      }
      setLoading(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const persistSettings = useCallback(
    async (ids: string[], score: boolean) => {
      await api.putSettings({
        included_calendar_ids: ids,
        show_priority_score: score,
      });
    },
    [],
  );

  const persistCategories = useCallback(
    async (cs: Record<string, Category>) => {
      await api.putCategories(cs);
    },
    [],
  );

  if (loading) {
    return (
      <div
        style={{
          padding: "16px 14px",
          fontFamily: "var(--font-body)",
          color: "var(--ink-primary)",
        }}
      >
        Loading settings…
      </div>
    );
  }

  return (
    <div
      style={{
        padding: "16px 14px",
        fontFamily: "var(--font-body)",
        color: "var(--ink-primary)",
      }}
    >
      <h2
        style={{
          fontFamily: "var(--font-display)",
          fontStyle: "italic",
          fontSize: 22,
          fontWeight: 500,
          marginBottom: 14,
          letterSpacing: "-0.005em",
        }}
      >
        Settings
      </h2>

      <section
        style={{
          padding: "14px 16px",
          background: "var(--surface-card)",
          border: "1px solid var(--ink-hairline)",
          borderRadius: "var(--radius-pill)",
          marginBottom: 14,
        }}
      >
        <h3
          style={{
            fontFamily: "var(--font-display)",
            fontSize: 16,
            fontWeight: 500,
            marginTop: 0,
            marginBottom: 8,
          }}
        >
          Category colors
        </h3>
        {Object.entries(categories).map(([slug, cat]) => (
          <CategoryColorRow
            key={slug}
            slug={slug}
            label={cat.label}
            color={cat.color}
            onChange={(color) => {
              const next = { ...categories, [slug]: { ...cat, color } };
              setCategories(next);
              persistCategories(next);
            }}
          />
        ))}
      </section>

      <section
        style={{
          padding: "14px 16px",
          background: "var(--surface-card)",
          border: "1px solid var(--ink-hairline)",
          borderRadius: "var(--radius-pill)",
          marginBottom: 14,
        }}
      >
        <h3
          style={{
            fontFamily: "var(--font-display)",
            fontSize: 16,
            fontWeight: 500,
            marginTop: 0,
            marginBottom: 8,
          }}
        >
          Calendars to include
        </h3>
        <CalendarPickerList
          available={available}
          selected={includedCalendarIds}
          onChange={(ids) => {
            setIncludedCalendarIds(ids);
            persistSettings(ids, showScores);
          }}
        />
      </section>

      <section
        style={{
          padding: "14px 16px",
          background: "var(--surface-card)",
          border: "1px solid var(--ink-hairline)",
          borderRadius: "var(--radius-pill)",
        }}
      >
        <h3
          style={{
            fontFamily: "var(--font-display)",
            fontSize: 16,
            fontWeight: 500,
            marginTop: 0,
            marginBottom: 8,
          }}
        >
          Debug
        </h3>
        <label
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            cursor: "pointer",
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <div
              style={{
                fontSize: 14,
                fontWeight: 500,
                color: "var(--ink-primary)",
              }}
            >
              Show priority scores on task pills
            </div>
            <div
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 11,
                letterSpacing: ".04em",
                color: "var(--ink-tertiary)",
              }}
            >
              Overlay numeric priority on each TaskPill.
            </div>
          </div>
          <input
            type="checkbox"
            checked={showScores}
            onChange={(e) => {
              onToggleScores(e.target.checked);
              persistSettings(includedCalendarIds, e.target.checked);
            }}
            style={{
              width: 20,
              height: 20,
              accentColor: "var(--ink-primary)",
              cursor: "pointer",
            }}
          />
        </label>
      </section>
    </div>
  );
}
