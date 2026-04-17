from __future__ import annotations
import re
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import priority
from .auth import verify_init_data, InitDataInvalid, TelegramUser
from .briefing import generate_briefing
from .config import load_settings, PROJECT_ROOT
from .gcal import fetch_events
from .schedule import load_schedule, week_instances
from .tasks_store import Task, TasksStore, TaskNotFoundError


settings = load_settings()
store = TasksStore(settings.tasks_path)
_schedule_path = PROJECT_ROOT / "data" / "schedule.json"
app = FastAPI(title="Academic Scheduler API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def current_user(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> TelegramUser:
    if not settings.telegram_bot_token:
        raise HTTPException(500, "TELEGRAM_BOT_TOKEN not configured")
    if not x_telegram_init_data:
        raise HTTPException(401, "missing X-Telegram-Init-Data header")
    try:
        return verify_init_data(x_telegram_init_data, settings.telegram_bot_token)
    except InitDataInvalid as e:
        raise HTTPException(401, f"invalid initData: {e}")


class AddTaskBody(BaseModel):
    course: str
    name: str
    due: str
    type: str
    weight: str = ""
    notes: str | None = None


@app.get("/api/tasks")
def get_tasks(_: TelegramUser = Depends(current_user)):
    now = datetime.now()
    enriched = []
    for t in store.list():
        score = priority.compute(t, now)
        tier_ = priority.tier(score, urgent_flag=(t.priority_boost == 1.5))
        enriched.append({**t.__dict__, "priority_score": round(score, 2), "tier": tier_})
    return {"tasks": enriched}


@app.post("/api/tasks/{task_id}/done")
def mark_done(task_id: str, _: TelegramUser = Depends(current_user)):
    try:
        store.set_done(task_id, True)
    except TaskNotFoundError:
        raise HTTPException(404, f"no task {task_id!r}")
    return {"ok": True}


@app.post("/api/tasks/{task_id}/undo")
def mark_undo(task_id: str, _: TelegramUser = Depends(current_user)):
    try:
        store.set_done(task_id, False)
    except TaskNotFoundError:
        raise HTTPException(404, f"no task {task_id!r}")
    return {"ok": True}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


@app.post("/api/tasks", status_code=201)
def add_task(body: AddTaskBody, _: TelegramUser = Depends(current_user)):
    course_slug = _slug(body.course)[:8] or "task"
    name_slug = _slug(body.name)[:16] or uuid.uuid4().hex[:6]
    base = f"{course_slug}-{name_slug}"
    existing = {t.id for t in store.list()}
    task_id = base
    i = 2
    while task_id in existing:
        task_id = f"{base}-{i}"
        i += 1
    task = Task(
        id=task_id, course=body.course, name=body.name, due=body.due,
        type=body.type, weight=body.weight, done=False, notes=body.notes,
    )
    store.add(task)
    return {"task": task.__dict__}


@app.get("/api/calendar")
def get_calendar(_: TelegramUser = Depends(current_user)):
    events = fetch_events(date.today(), days=7)
    return {"events": [e.as_dict() for e in events]}


@app.get("/api/schedule")
def get_schedule(
    start: str | None = None,
    _: TelegramUser = Depends(current_user),
):
    sched = load_schedule(_schedule_path)
    if start:
        try:
            week_start = date.fromisoformat(start)
        except ValueError:
            raise HTTPException(400, "start must be ISO YYYY-MM-DD")
    else:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())  # Monday
    instances = week_instances(sched, week_start=week_start)
    return {
        "term_start": sched.term_start.isoformat() if sched.term_start else None,
        "term_end": sched.term_end.isoformat() if sched.term_end else None,
        "week_start": week_start.isoformat(),
        "instances": [
            {"title": i.title, "category": i.category,
             "date": i.instance_date.isoformat(),
             "start": i.start, "end": i.end, "location": i.location}
            for i in instances
        ],
    }


@app.get("/api/briefing")
def get_briefing(_: TelegramUser = Depends(current_user)):
    events = fetch_events(date.today(), days=1)
    text = generate_briefing(store.list(), today=date.today(), events=events)
    return {"text": text}


_static_dir = PROJECT_ROOT / "backend" / "static"
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
