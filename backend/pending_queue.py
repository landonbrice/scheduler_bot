"""Append-only retry queue for Membase writes that failed.

The queue lives at an absolute path (typically data/membase_pending.jsonl).
One JSON object per line. Consumers read all entries, attempt to re-send
each, and clear() the queue once every entry has been processed.
"""
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Iterator

log = logging.getLogger(__name__)


class PendingQueue:
    def __init__(self, path: Path):
        self.path = Path(path)

    def append(self, entry: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    def iter_entries(self) -> Iterator[dict]:
        if not self.path.exists():
            return
        with self.path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    log.warning("skipping malformed pending-queue line: %r", line[:80])

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
