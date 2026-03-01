from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator


async def event_stream(
    queue: asyncio.Queue, disconnect_checker
) -> AsyncGenerator[str, None]:
    try:
        while True:
            if await disconnect_checker():
                break
            try:
                data = await asyncio.wait_for(queue.get(), timeout=10.0)
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                yield "data: {}\n\n"
    finally:
        return
