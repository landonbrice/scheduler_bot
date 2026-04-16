from __future__ import annotations
import time
from backend.undo_buffer import UndoBuffer, UndoEntry


def test_register_then_pop_returns_entry():
    buf = UndoBuffer(ttl_seconds=60)
    buf.register(chat_id=1, message_id=100, task_id="corpfin-pset4")
    entry = buf.pop_latest(chat_id=1)
    assert entry is not None
    assert entry.task_id == "corpfin-pset4"
    assert entry.message_id == 100


def test_pop_consumes_entry():
    buf = UndoBuffer(ttl_seconds=60)
    buf.register(1, 100, "t1")
    assert buf.pop_latest(1) is not None
    assert buf.pop_latest(1) is None


def test_latest_of_many_is_returned_first():
    buf = UndoBuffer(ttl_seconds=60)
    buf.register(1, 100, "t1")
    buf.register(1, 200, "t2")
    buf.register(1, 300, "t3")
    entry = buf.pop_latest(1)
    assert entry is not None and entry.task_id == "t3"
    entry = buf.pop_latest(1)
    assert entry is not None and entry.task_id == "t2"


def test_expired_entries_are_not_returned(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("backend.undo_buffer.time.monotonic", lambda: now[0])
    buf = UndoBuffer(ttl_seconds=60)
    buf.register(1, 100, "t1")
    now[0] += 61
    assert buf.pop_latest(1) is None


def test_entries_are_scoped_per_chat():
    buf = UndoBuffer(ttl_seconds=60)
    buf.register(1, 100, "t_one")
    buf.register(2, 200, "t_two")
    assert buf.pop_latest(1).task_id == "t_one"
    assert buf.pop_latest(2).task_id == "t_two"
    assert buf.pop_latest(1) is None
    assert buf.pop_latest(2) is None


def test_entry_has_all_fields():
    entry = UndoEntry(message_id=10, task_id="x", created_at=0.0)
    assert entry.message_id == 10
    assert entry.task_id == "x"
