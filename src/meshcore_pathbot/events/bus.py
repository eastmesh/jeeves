"""Async event bus for decoupling bot core from web layer."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .types import AppEvent

log = logging.getLogger("pathbot.bus")


class EventBus:
    """Lightweight async event bus with queue-based fan-out for SSE streams."""

    def __init__(self) -> None:
        self._queues: list[tuple[set[AppEvent], asyncio.Queue]] = []
        self._lock = asyncio.Lock()

    async def publish(self, event_type: AppEvent, data: dict[str, Any] | None = None) -> None:
        """Publish an event to all subscribed queues."""
        payload = {
            "type": event_type.name.lower(),
            "payload": data or {},
        }
        async with self._lock:
            for subscribed_types, queue in self._queues:
                if event_type in subscribed_types:
                    try:
                        queue.put_nowait(payload)
                    except asyncio.QueueFull:
                        log.warning(f"Queue full, dropping {event_type.name} event")

    async def create_queue(self, *event_types: AppEvent, maxsize: int = 100) -> asyncio.Queue:
        """Create a queue subscribed to the given event types.

        Used by SSE streams: each connected client gets its own queue.
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        async with self._lock:
            self._queues.append((set(event_types), q))
        return q

    async def remove_queue(self, queue: asyncio.Queue) -> None:
        """Unsubscribe and clean up a queue."""
        async with self._lock:
            self._queues = [(types, q) for types, q in self._queues if q is not queue]
