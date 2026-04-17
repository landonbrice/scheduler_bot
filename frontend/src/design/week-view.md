# Week View — Visual System

_LANDO OS v2 · R2 · design source of truth for Tasks 8–11_

Aesthetic direction: **refined editorial academic**. Warm paper-white ground, deep ink text, a display serif (Fraunces) paired with a humanist sans (Inter Tight) and a structural mono (JetBrains Mono). Eight grounded category hues used as index-card tabs. Three tiers differentiated by *weight* (fill vs. bordered vs. ghost), not by gradients or glow. No AI-assistant aesthetics — no purple gradients, no pastel washes, no glassmorphism.

Open `preview.html` in a browser for the full mockup.

---

## 1. Tokens (see `tokens.css`)

### Categories — 8 canonical hues, one per bucket

| Slug | CSS var | Hex | Used on |
|---|---|---|---|
| CorpFin | `--cat-corpfin` | `#1F4E6B` | pill bg, task left-border, chip border, filter dot, badge |
| SCS III | `--cat-scsiii` | `#6B1F3A` | same |
| APES | `--cat-apes` | `#3B6B2A` | same |
| E4E | `--cat-e4e` | `#C2571B` | same |
| Baseball | `--cat-baseball` | `#8B4513` | same |
| Recruiting | `--cat-recruiting` | `#4A3A7C` | same |
| Projects | `--cat-projects` | `#0F6B6B` | same |
| Life | `--cat-life` | `#7A6B3A` | same |

Each hue has a `--cat-[slug]-soft` pair (e.g. `--cat-corpfin-soft: #EAF0F5`) reserved for optional task-pill backgrounds in dense layouts. Default task pills use `--surface-card` white; softs are held in reserve.

### Tier — urgency-semantic, category-agnostic

| Role | CSS var | Hex | Trigger |
|---|---|---|---|
| Urgent / overdue | `--tier-red` | `#B3261E` | task is overdue, or in Overdue Drawer |
| Due today / soon | `--tier-amber` | `#B87A14` | task due within ~24h |
| Default accent | `--tier-neutral` | `#3A3834` | task with no urgency signal |

Soft pairings `--tier-red-soft` / `--tier-amber-soft` are used for urgent pill backgrounds and drawer header tints.

### Neutrals

`--surface-paper` (app bg, `#FAF8F3`) · `--surface-card` (day column, `#FFFFFF`) · `--surface-sunken` (drawer, filter hover, `#F1EEE6`) · `--ink-primary` (`#1C1B1A`) · `--ink-secondary` (`#5A564F`) · `--ink-tertiary` (`#8C877D`) · `--ink-hairline` (`#E7E2D5`, the only "grid line" used anywhere).

### Radius

- `--radius-chip: 10px` — ThoughtChip, filter chip
- `--radius-pill: 12px` — **canonical** — FixedBlockPill, TaskPill
- `--radius-card: 14px` — DayColumn, OverdueDrawer
- `--radius-fab: 999px` — CaptureFAB

### Spacing

4 / 8 / 12 / 16 / 20 / 24 / 32 px scale. Pill vertical padding = 12. Pill horizontal padding = 16 (18 on the left edge of a TaskPill to accommodate the 4px accent). Day-column breathing = 24 bottom, 20 top.

### Typography

- Display: **Fraunces** (italic 500 for headlines, roman 500 for DayColumn dates)
- Body: **Inter Tight** (500 for pill labels, 400 for body)
- Meta: **JetBrains Mono** (11px, `.08em` tracking, UPPERCASE) for weekday labels, timestamps, section headers

Font sizes: `--text-chip 12` · `--text-pill 14` · `--text-meta 11` · `--text-day 13` · `--text-date 28`.

### Elevation (restrained)

One-pixel shadow on pills. Two-pixel card shadow on DayColumn. A proper drop shadow only on the FAB. No glows.

---

## 2. Component → token map

### `WeekView` (container)
- bg: `--surface-paper`
- title: Fraunces italic 500, 20px, `--ink-primary`
- week range: mono 11px uppercase, `--ink-tertiary`
- children: filter rail → day grid → overdue drawer

### `DayColumn`
- bg: `--surface-card`
- radius: `--radius-card` (14px)
- shadow: `--shadow-card`
- weekday label: mono 11px uppercase, `--ink-secondary`
- date numeral: Fraunces 28px, `--ink-primary`
- divider under header: 1px **dashed** `--ink-hairline` (not solid — dashed keeps the "breathe" feel)
- today marker: 2px `--ink-primary` bar flush to the top edge, inset 16px left/right
- `tod` (time-of-day labels: "morning", "afternoon", "evening"): mono 10px uppercase, `--ink-tertiary`

### `FixedBlockPill` (Tier 1 — solid)
- radius: `--radius-pill` (12px)
- bg: `var(--cat-[slug])` — category canonical hue
- label: Inter Tight 600 14px, `#fff`
- meta (time · location): mono 11px uppercase, `#fff` at 82% opacity
- hover: `translateY(-1px)` + slightly deeper shadow
- tap: opens event detail sheet (later)

### `TaskPill` (Tier 2 — bordered)
- radius: `--radius-pill` (12px)
- bg: `--surface-card` (default) / `--tier-red-soft` (urgent)
- border: 1px solid `--ink-hairline` + 4px solid **left** `var(--cat-[slug])`
  - `data-due="today"` overrides left border with `--tier-amber`
  - `data-urgent="true"` replaces the whole border with 1.5px solid `--tier-red` (no more left-accent treatment — the whole pill is the warning)
- check: 16px rounded square, 1.5px `--ink-tertiary` border
- label: Inter Tight 500 14px, `--ink-primary` (urgent: 600 `--tier-red`)
- meta: `--cat-badge` (mono 11px, bg `--surface-sunken`) + timestamp
- tap: toggles `data-expanded="true"` → inline action row (Open note · +1 day · Reassign). Task 10 layers swipe gestures on top.

### `ThoughtChip` (Tier 3 — ghost)
- radius: `--radius-chip` (10px)
- bg: transparent (collapsed) / `--surface-card` (hover, expanded)
- border: 1px **dashed** `--ink-hairline` (or 1px **dotted** `var(--cat-[slug])` when categorized)
- icon: 12px inline SVG, `--ink-tertiary`
- label: Inter Tight 400 12px, `--ink-secondary` (hover/expanded → `--ink-primary`)
- truncation: single line, ellipsis, `max-width: 180px` collapsed
- expanded: width fills parent, text wraps, action row underneath with mono 10px uppercase links. Primary "promote to task" action is `--cat-projects` by convention (or whichever category the chip was classified as).

### `CaptureFAB`
- 56×56, `--radius-fab` (999px), bg `--ink-primary`, glyph `--surface-paper`
- shadow: `--shadow-fab` (only component with a real drop shadow)
- hover: `scale(1.04)` + bg `#000`; press: `scale(0.98)`
- focus: `--shadow-focus` (ink ring, not blue)
- sticky 20px from right, 24px from bottom (above safe-area inset)

### `OverdueDrawer`
- sticky under WeekView, bg `--surface-sunken`
- top border: 1px `--tier-red`
- radius: 14px top corners only
- header label: Fraunces italic 18px `--tier-red` + count badge (mono 11px, bg `--tier-red`, fg `#fff`)
- handle: 36×4 `--ink-hairline` rounded, 14px margin-bottom (signals pull-to-expand)
- body: stacked TaskPills, all forced `data-urgent="true"`
- empty state: collapses to just the header row (or hides entirely — TBD during Task 9)

### Filter chip rail
- horizontal scroll on mobile, hidden scrollbar
- inactive: `--surface-card` bg, 1px `--ink-hairline` border, 8px dot in `var(--cat-[slug])`
- active ("All" or a single category): bg `--ink-primary`, text `--surface-paper`, dot stays category-colored
- tap: toggles visibility of that category across all day columns

---

## 3. Interaction affordances

| State | Effect |
|---|---|
| **Hover (pointer)** | FixedBlockPill lifts 1px. TaskPill shifts 1px right + slight paper tint. ThoughtChip border goes from dashed to solid, bg fills. |
| **Tap (touch)** | TaskPill expands in-place (inline action row). ThoughtChip expands in-place (full text + promote/open/dismiss). FixedBlockPill opens event detail sheet (Task 9+). |
| **Swipe right on TaskPill** | Mark complete (Task 10). |
| **Swipe left on TaskPill** | Snooze +1 day (Task 10). |
| **Long-press** | Reserved — not used in R2. |
| **Focus (keyboard)** | `--shadow-focus` double-ring (paper then ink), never blue. |
| **Empty day** | DayColumn still renders with header + faint "nothing scheduled" hint in mono 11px `--ink-tertiary` (add during Task 9 if desired). |
| **Reduced motion** | `@media (prefers-reduced-motion: reduce)` disables all transitions and the stagger entrance. |

### Entrance (page load)

DayColumns stagger in with 40ms offsets (`animation-delay`), `translateY(8px) → 0`, `opacity 0 → 1`, 320ms `cubic-bezier(.2,0,0,1)`. One well-orchestrated load beats scattered micro-interactions.

---

## 4. How consumers (Task 8) should pull tokens

`tokens.css` is imported from `src/index.css` at the top of the cascade. React components should reference CSS variables via either:

**Tailwind arbitrary values:**
```tsx
<div className="bg-[color:var(--cat-corpfin)] rounded-[12px] px-4 py-3" />
```

**Inline style (cleaner for dynamic category):**
```tsx
<div
  className="rounded-[12px] px-4 py-3 text-white"
  style={{ backgroundColor: `var(--cat-${slug})` }}
/>
```

Keep the category slug in sync with the CSS var names — lowercase, no spaces: `corpfin`, `scsiii`, `apes`, `e4e`, `baseball`, `recruiting`, `projects`, `life`. The backend taxonomy lives in `backend/priority.py` and `data/tasks.json`; keep one canonical slug table on both sides.

---

## 5. What's intentionally _not_ here

- No dark mode — the briefing cron runs at 7am and the Mini App is read mostly in daylight / in Telegram's light chat bg. Dark mode is a Task 11+ consideration, not R2.
- No gradients, no glass, no frosted blur, no neon accents — all would betray the editorial-academic direction.
- No React code — that's Task 8. This directory is design artifacts only.
- No per-component storybook — the single `preview.html` _is_ the storybook.
