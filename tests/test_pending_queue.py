from __future__ import annotations
import json
from pathlib import Path
import pytest
from backend.pending_queue import PendingQueue


def test_append_then_iter_returns_entries(tmp_path: Path):
    q = PendingQueue(tmp_path / "pending.jsonl")
    q.append({"content": "hello", "project": "apes"})
    q.append({"content": "world", "project": None})
    entries = list(q.iter_entries())
    assert entries == [
        {"content": "hello", "project": "apes"},
        {"content": "world", "project": None},
    ]


def test_iter_on_missing_file_returns_empty(tmp_path: Path):
    q = PendingQueue(tmp_path / "does-not-exist.jsonl")
    assert list(q.iter_entries()) == []


def test_clear_removes_file(tmp_path: Path):
    q = PendingQueue(tmp_path / "pending.jsonl")
    q.append({"content": "hi", "project": None})
    assert (tmp_path / "pending.jsonl").exists()
    q.clear()
    assert not (tmp_path / "pending.jsonl").exists()


def test_append_creates_parent_dir(tmp_path: Path):
    q = PendingQueue(tmp_path / "nested" / "pending.jsonl")
    q.append({"content": "x", "project": None})
    assert (tmp_path / "nested" / "pending.jsonl").exists()


def test_malformed_line_is_skipped(tmp_path: Path):
    p = tmp_path / "pending.jsonl"
    p.write_text('{"content": "ok", "project": null}\ngarbage\n{"content": "also ok", "project": "x"}\n')
    q = PendingQueue(p)
    entries = list(q.iter_entries())
    assert entries == [
        {"content": "ok", "project": None},
        {"content": "also ok", "project": "x"},
    ]
