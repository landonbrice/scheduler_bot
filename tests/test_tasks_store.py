import json
from pathlib import Path
import pytest
from backend.tasks_store import TasksStore, Task, TaskNotFoundError


def _seed(path: Path, tasks: list[dict]) -> None:
    path.write_text(json.dumps(tasks))


def test_list_returns_empty_for_empty_file(tmp_tasks_path: Path):
    store = TasksStore(tmp_tasks_path)
    assert store.list() == []


def test_list_returns_tasks_preserving_order(tmp_tasks_path: Path):
    _seed(tmp_tasks_path, [
        {"id": "a", "course": "CorpFin", "name": "A", "due": "2026-05-01", "type": "pset", "weight": "", "done": False},
        {"id": "b", "course": "APES", "name": "B", "due": "2026-05-02", "type": "exam", "weight": "", "done": False},
    ])
    store = TasksStore(tmp_tasks_path)
    tasks = store.list()
    assert [t.id for t in tasks] == ["a", "b"]


def test_add_appends_task_and_persists(tmp_tasks_path: Path):
    store = TasksStore(tmp_tasks_path)
    store.add(Task(id="x", course="E4E", name="Quiz", due="2026-05-10", type="exam", weight="10%", done=False))
    assert json.loads(tmp_tasks_path.read_text())[0]["id"] == "x"


def test_add_rejects_duplicate_id(tmp_tasks_path: Path):
    store = TasksStore(tmp_tasks_path)
    t = Task(id="x", course="E4E", name="Quiz", due="2026-05-10", type="exam", weight="", done=False)
    store.add(t)
    with pytest.raises(ValueError):
        store.add(t)


def test_mark_done_flips_flag(tmp_tasks_path: Path):
    _seed(tmp_tasks_path, [
        {"id": "a", "course": "CorpFin", "name": "A", "due": "2026-05-01", "type": "pset", "weight": "", "done": False},
    ])
    store = TasksStore(tmp_tasks_path)
    store.set_done("a", True)
    assert json.loads(tmp_tasks_path.read_text())[0]["done"] is True
    store.set_done("a", False)
    assert json.loads(tmp_tasks_path.read_text())[0]["done"] is False


def test_set_done_on_missing_raises(tmp_tasks_path: Path):
    store = TasksStore(tmp_tasks_path)
    with pytest.raises(TaskNotFoundError):
        store.set_done("nope", True)


def test_auto_creates_parent_dir_and_empty_file(tmp_path: Path):
    path = tmp_path / "sub" / "tasks.json"
    store = TasksStore(path)
    assert store.list() == []
    assert path.exists()


def test_write_is_atomic_on_corruption(tmp_tasks_path: Path, monkeypatch):
    _seed(tmp_tasks_path, [{"id": "a", "course": "X", "name": "A", "due": "2026-01-01", "type": "pset", "weight": "", "done": False}])
    store = TasksStore(tmp_tasks_path)
    original = json.loads(tmp_tasks_path.read_text())
    import os
    def boom(*a, **kw): raise RuntimeError("disk full")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(RuntimeError):
        store.add(Task(id="b", course="X", name="B", due="2026-01-02", type="pset", weight="", done=False))
    assert json.loads(tmp_tasks_path.read_text()) == original
