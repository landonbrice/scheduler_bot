"""In-memory TTL buffer for task-creation undos.

Single-process only (the bot runs in a single process). Lost on restart —
acceptable because the TTL is 60 seconds. Thread-safe is not required
because all handlers run on the telegram asyncio event loop.
"""
from __future__ import annotations
import time
from dataclasses import dataclass
from collections import defaultdict


@dataclass(frozen=True)
class UndoEntry:
    message_id: int
    task_id: str
    created_at: float  # monotonic seconds


class UndoBuffer:
    def __init__(self, ttl_seconds: int = 60):
        self.ttl = ttl_seconds
        self._entries: dict[int, list[UndoEntry]] = defaultdict(list)

    def register(self, chat_id: int, message_id: int, task_id: str) -> None:
        entry = UndoEntry(
            message_id=message_id,
            task_id=task_id,
            created_at=time.monotonic(),
        )
        self._entries[chat_id].append(entry)

    def pop_latest(self, chat_id: int) -> UndoEntry | None:
        """Return the most-recently-registered non-expired entry for this chat,
        removing it from the buffer. Returns None if none exist."""
        now = time.monotonic()
        entries = self._entries.get(chat_id, [])
        while entries:
            entry = entries.pop()
            if now - entry.created_at <= self.ttl:
                return entry
        return None
