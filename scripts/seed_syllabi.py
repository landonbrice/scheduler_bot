"""Seed tasks extracted from ANTH 21428 (APES) and SCS III syllabi.

Safe to run multiple times — skips any task IDs already in the store.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.config import load_settings  # noqa: E402
from backend.tasks_store import Task, TasksStore  # noqa: E402


# SCS III section 13 meets MW 3:00-4:20pm. Canvas post is due 11:59pm the
# night before each class. Week 1.1 (3/23) and 8.2 (5/13, class presentations
# day) are the only class dates with no Canvas post per the syllabus.
# Each tuple: (id_suffix, due_date, class_theme_for_the_next_class)
SCS_POSTS = [
    ("apr14", "2026-04-14", "Biopower and Beyond (Foucault Pt 5)"),
    ("apr19", "2026-04-19", "The Performative Turn (West & Zimmerman)"),
    ("apr21", "2026-04-21", "Making a Discipline (Said)"),
    ("apr26", "2026-04-26", "Agency & Resistance (Mahmood)"),
    ("apr28", "2026-04-28", "Inventing Race (Arendt)"),
    ("may03", "2026-05-03", "Politics, Power & News (Herman/Chomsky)"),
    ("may05", "2026-05-05", "The Culture Industry (Horkheimer/Adorno)"),
    ("may10", "2026-05-10", "Hyperreality (Eco)"),
    ("may17", "2026-05-17", "Messages and Un-messages (Zizek)"),
    ("may19", "2026-05-19", "Final Reading (TBD)"),
]

# APES readings are due before Tuesday's 9:30am lecture. Week 5 (4/20-4/24)
# and Week 9 (5/18-5/22) have no readings (exam weeks). Week 4's reading was
# due before today, so it's omitted. We place remaining readings on the
# Monday before each Tuesday lecture.
APES_READINGS = [
    ("wk6", "2026-04-27", "Read: Oldest Primate"),
    ("wk7", "2026-05-04", "Read: Hunting vs Gathering"),
    ("wk8", "2026-05-11", "Read: What Makes Us Human"),
]


def main() -> None:
    settings = load_settings()
    store = TasksStore(settings.tasks_path)
    existing = {t.id for t in store.list()}
    added = 0

    for suffix, due, theme in SCS_POSTS:
        tid = f"scs-post-{suffix}"
        if tid in existing:
            continue
        store.add(Task(
            id=tid, course="SCS III", name=f"Canvas Post: {theme}",
            due=due, type="recurring", weight="part of 5%", done=False,
        ))
        added += 1

    for suffix, due, name in APES_READINGS:
        tid = f"apes-read-{suffix}"
        if tid in existing:
            continue
        store.add(Task(
            id=tid, course="APES", name=name,
            due=due, type="reading", weight="attendance", done=False,
        ))
        added += 1

    print(f"Added {added} new tasks. Total tasks: {len(store.list())}")


if __name__ == "__main__":
    main()
