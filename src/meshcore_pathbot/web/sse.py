"""SSE stream generator bridging the EventBus to HTTP responses."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

from starlette.requests import Request

from ..events.bus import EventBus
from ..events.types import AppEvent


async def sse_stream(
    request: Request,
    bus: EventBus,
    *event_types: AppEvent,
) -> AsyncGenerator[dict, None]:
    """Async generator yielding SSE events from the bus.

    Each connected client gets its own queue. Events are yielded as dicts
    compatible with sse-starlette's EventSourceResponse.
    """
    queue = await bus.create_queue(*event_types)
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                event_data = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield {
                    "event": event_data["type"],
                    "data": json.dumps(event_data["payload"]),
                }
            except asyncio.TimeoutError:
                # Send keepalive comment to prevent connection timeout
                yield {"comment": "keepalive"}
    finally:
        await bus.remove_queue(queue)
