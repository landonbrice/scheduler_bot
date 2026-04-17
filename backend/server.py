from __future__ import annotations
import json as _json
import re
import uuid
from datetime import date, datetime, timedelta, timezone as _tz
from datetime import datetime as _dt2
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
from .memory import search_memory as _search_memory
from .schedule import load_schedule, week_instances
from .surfacing import surface_week, load_dismissed
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
        week_start = week_start - timedelta(days=week_start.weekday())
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


_dismissed_path = PROJECT_ROOT / "data" / "dismissed.jsonl"
_resurface_path = PROJECT_ROOT / "data" / "resurface.jsonl"


def _load_resurface_by_day(week_start, week_end) -> dict:
    out: dict = {}
    try:
        lines = _resurface_path.read_text().strip().splitlines()
    except FileNotFoundError:
        return {}
    from datetime import date as _d_local
    for line in lines:
        try:
            row = _json.loads(line)
            td = row.get("trigger_date")
            if not td:
                continue
            day = _d_local.fromisoformat(td)
            if week_start <= day <= week_end:
                out.setdefault(day, []).append(row)
        except (ValueError, KeyError):
            continue
    return out


@app.get("/api/notes/surfaced")
async def get_surfaced(start: str, days: int = 7, _: TelegramUser = Depends(current_user)):
    from datetime import date as _d_local, timedelta as _td_local
    try:
        week_start = _d_local.fromisoformat(start)
    except ValueError:
        raise HTTPException(400, "start must be ISO YYYY-MM-DD")
    dates = [week_start + _td_local(days=i) for i in range(days)]
    now = _dt2.now(tz=_tz.utc)
    tasks = store.list()
    tasks_by_day: dict = {}
    for t in tasks:
        try:
            td = _d_local.fromisoformat(t.due)
            if dates[0] <= td <= dates[-1]:
                tasks_by_day.setdefault(td, []).append(t.__dict__)
        except ValueError:
            continue
    events = fetch_events(week_start, days=days)
    events_by_day: dict = {}
    for e in events:
        try:
            ed_dict = e.as_dict() if hasattr(e, "as_dict") else (e if isinstance(e, dict) else e.__dict__)
            ed = _d_local.fromisoformat(str(ed_dict["start"])[:10])
            events_by_day.setdefault(ed, []).append(ed_dict)
        except (ValueError, KeyError, AttributeError):
            continue
    resurface_by_day = _load_resurface_by_day(dates[0], dates[-1])
    chips_by_day = await surface_week(
        dates=dates, tasks_by_day=tasks_by_day, events_by_day=events_by_day,
        resurface_by_day=resurface_by_day, dismissed_path=_dismissed_path,
        memory_search=_search_memory, now=now,
    )
    return {"surfaced": {d.isoformat(): chips for d, chips in chips_by_day.items()}}


@app.get("/api/notes/search")
async def search_notes(q: str, _: TelegramUser = Depends(current_user)):
    if not q.strip():
        return {"results": [], "offline": False}
    try:
        hits = await _search_memory(q, 20)
    except Exception:
        return {"results": [], "offline": True}
    return {"results": hits, "offline": False}


class DismissBody(BaseModel):
    memory_id: str


@app.post("/api/capture/note/dismiss")
def dismiss_memory(body: DismissBody, _: TelegramUser = Depends(current_user)):
    entry = {
        "memory_id": body.memory_id,
        "dismissed_at": _dt2.now(tz=_tz.utc).isoformat(),
    }
    _dismissed_path.parent.mkdir(parents=True, exist_ok=True)
    with _dismissed_path.open("a") as f:
        f.write(_json.dumps(entry) + "\n")
    return {"ok": True}


_static_dir = PROJECT_ROOT / "backend" / "static"
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
