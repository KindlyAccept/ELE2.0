from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import Optional, Set

import cv2
import numpy as np


class LatestFrameStore:
    def __init__(self, width: int = 1280, height: int = 720) -> None:
        self._lock = threading.Lock()
        self._frame: Optional[np.ndarray] = None
        self._timestamp: float = 0.0
        self.width = width
        self.height = height

    def update_from_jpeg(
        self,
        jpeg_bytes: bytes,
        timestamp: float,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> bool:
        np_buf = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        frame = cv2.imdecode(np_buf, cv2.IMREAD_COLOR)
        if frame is None:
            return False
        with self._lock:
            self._frame = frame
            self._timestamp = timestamp
            self.width = width or frame.shape[1]
            self.height = height or frame.shape[0]
        return True

    def get_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            if self._frame is None:
                return None
            return self._frame.copy()

    def get_timestamp(self) -> float:
        with self._lock:
            return self._timestamp


class EventBus:
    def __init__(self) -> None:
        self._queues: Set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._queues.discard(queue)

    async def publish(self, data: dict) -> None:
        for queue in list(self._queues):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(data)
            except asyncio.QueueFull:
                continue


@dataclass
class AppState:
    frame_store: LatestFrameStore
    event_bus: EventBus
    db: "DialogueDB"
    session_id: str
    pcs: set
    latest_status: dict
    audio_volume: int = 50  # 默认音量 50%