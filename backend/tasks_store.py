from __future__ import annotations
import json
import os
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from threading import Lock
from typing import Optional


class TaskNotFoundError(LookupError):
    pass


@dataclass
class Task:
    id: str
    course: str
    name: str
    due: str           # ISO date YYYY-MM-DD
    type: str          # exam | pset | essay | case | project | presentation | reading | ai-tutor | recurring | admin
    weight: str
    done: bool
    notes: Optional[str] = None
    impact_override: Optional[str] = None  # "critical" | "high" | "medium" | "low" | None
    priority_boost: Optional[float] = None  # None ≡ 1.0


class TasksStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]")

    def list(self) -> list[Task]:
        with self._lock:
            raw = json.loads(self.path.read_text() or "[]")
        return [Task(**t) for t in raw]

    def add(self, task: Task) -> None:
        with self._lock:
            tasks = self._read()
            if any(t["id"] == task.id for t in tasks):
                raise ValueError(f"task id {task.id!r} already exists")
            tasks.append(asdict(task))
            self._write(tasks)

    def set_done(self, task_id: str, done: bool) -> None:
        with self._lock:
            tasks = self._read()
            for t in tasks:
                if t["id"] == task_id:
                    t["done"] = done
                    self._write(tasks)
                    return
            raise TaskNotFoundError(task_id)

    def replace_all(self, tasks: list[Task]) -> None:
        with self._lock:
            self._write([asdict(t) for t in tasks])

    def _read(self) -> list[dict]:
        return json.loads(self.path.read_text() or "[]")

    def _write(self, tasks: list[dict]) -> None:
        fd, tmp = tempfile.mkstemp(prefix=".tasks-", suffix=".json", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(tasks, f, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
