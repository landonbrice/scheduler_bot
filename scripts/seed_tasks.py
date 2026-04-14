"""Seed data/tasks.json with the Spring 2026 defaults from CLAUDE_CODE_DIRECTIONS.md."""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.config import load_settings  # noqa: E402

DEFAULT_TASKS = [
    {"id": "cf-case2", "course": "CorpFin", "name": "Case 2", "due": "2026-04-15", "type": "case", "weight": "part of 15%", "done": False},
    {"id": "cf-ps3", "course": "CorpFin", "name": "Problem Set 3", "due": "2026-04-17", "type": "pset", "weight": "part of 15%", "done": False},
    {"id": "cf-topic", "course": "CorpFin", "name": "Send project topic to professor", "due": "2026-04-20", "type": "admin", "weight": "", "done": False},
    {"id": "cf-ps4", "course": "CorpFin", "name": "Problem Set 4", "due": "2026-04-24", "type": "pset", "weight": "part of 15%", "done": False},
    {"id": "cf-mid", "course": "CorpFin", "name": "Midterm Exam (in-class, closed book)", "due": "2026-05-01", "type": "exam", "weight": "25%", "done": False},
    {"id": "cf-ps5", "course": "CorpFin", "name": "Problem Set 5", "due": "2026-05-08", "type": "pset", "weight": "part of 15%", "done": False},
    {"id": "cf-proj", "course": "CorpFin", "name": "Valuation Project Presentation (15 min, must use ChatGPT)", "due": "2026-05-09", "type": "project", "weight": "15%", "done": False},
    {"id": "cf-final", "course": "CorpFin", "name": "Final Exam (in-class, closed book)", "due": "2026-05-22", "type": "exam", "weight": "35-60%", "done": False},
    {"id": "scs-fb", "course": "SCS III", "name": "Self-Feedback Exercise", "due": "2026-04-19", "type": "essay", "weight": "10%", "done": False},
    {"id": "scs-mid", "course": "SCS III", "name": "Midterm Essay (major paper)", "due": "2026-04-28", "type": "essay", "weight": "35%", "done": False},
    {"id": "scs-pres", "course": "SCS III", "name": "Final Paper Presentation", "due": "2026-05-13", "type": "presentation", "weight": "5%", "done": False},
    {"id": "scs-final", "course": "SCS III", "name": "Final Paper", "due": "2026-05-28", "type": "essay", "weight": "30%", "done": False},
    {"id": "apes-mid", "course": "APES", "name": "Online Midterm (9am-8pm, Weeks 1-4)", "due": "2026-04-21", "type": "exam", "weight": "50/280 pts", "done": False},
    {"id": "apes-debate", "course": "APES", "name": "Debate Presentation (group, slideshow+script+sources)", "due": "2026-04-28", "type": "presentation", "weight": "50/280 pts", "done": False},
    {"id": "apes-zoo", "course": "APES", "name": "Zoo Report or Individual Poster (hard+electronic copy)", "due": "2026-05-14", "type": "project", "weight": "50/280 pts", "done": False},
    {"id": "apes-final", "course": "APES", "name": "Online Final Exam (9am-8pm, Weeks 5-9)", "due": "2026-05-21", "type": "exam", "weight": "50/280 pts", "done": False},
    {"id": "e4e-ai4", "course": "E4E", "name": "AI Tutor Wk 4 (Behavioral Econ)", "due": "2026-04-20", "type": "ai-tutor", "weight": "discussion grade", "done": False},
    {"id": "e4e-mid", "course": "E4E", "name": "Midterm (in-class Tuesday)", "due": "2026-04-21", "type": "exam", "weight": "midterm", "done": False},
    {"id": "e4e-ai6", "course": "E4E", "name": "AI Tutor Wk 6 (Markets)", "due": "2026-05-04", "type": "ai-tutor", "weight": "discussion grade", "done": False},
    {"id": "e4e-ai7", "course": "E4E", "name": "AI Tutor Wk 7 (Uncertainty)", "due": "2026-05-11", "type": "ai-tutor", "weight": "discussion grade", "done": False},
    {"id": "e4e-ai8", "course": "E4E", "name": "AI Tutor Wk 8 (Risk/Labor)", "due": "2026-05-18", "type": "ai-tutor", "weight": "discussion grade", "done": False},
    {"id": "e4e-final", "course": "E4E", "name": "Final Exam (in-class Thursday)", "due": "2026-05-21", "type": "exam", "weight": "midterm", "done": False},
    {"id": "e4e-ai9", "course": "E4E", "name": "AI Tutor Wk 9", "due": "2026-05-25", "type": "ai-tutor", "weight": "discussion grade", "done": False},
    {"id": "e4e-proj", "course": "E4E", "name": "Final Project", "due": "2026-05-29", "type": "project", "weight": "TBD", "done": False},
]


def main() -> None:
    settings = load_settings()
    path = settings.tasks_path
    path.parent.mkdir(parents=True, exist_ok=True)
    force = "--force" in sys.argv
    if path.exists() and not force:
        existing = json.loads(path.read_text() or "[]")
        if existing:
            print(f"{path} already has {len(existing)} tasks. Pass --force to overwrite.")
            return
    path.write_text(json.dumps(DEFAULT_TASKS, indent=2))
    print(f"Seeded {len(DEFAULT_TASKS)} tasks → {path}")


if __name__ == "__main__":
    main()
