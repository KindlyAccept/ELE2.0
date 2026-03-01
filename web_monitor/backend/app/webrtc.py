from __future__ import annotations

import asyncio
from typing import Optional

import numpy as np
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame

from app.state import LatestFrameStore


class LatestFrameTrack(VideoStreamTrack):
    def __init__(self, frame_store: LatestFrameStore, fps: int = 30) -> None:
        super().__init__()
        self.frame_store = frame_store
        self.fps = fps

    async def recv(self) -> VideoFrame:
        frame_interval = 1.0 / max(1, self.fps)
        await asyncio.sleep(frame_interval)
        frame = self.frame_store.get_frame()
        if frame is None:
            frame = np.zeros(
                (self.frame_store.height, self.frame_store.width, 3),
                dtype=np.uint8,
            )
        video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
        video_frame.pts, video_frame.time_base = await self.next_timestamp()
        return video_frame


async def handle_offer(
    offer: dict,
    frame_store: LatestFrameStore,
    pcs: set,
    fps: int = 30,
) -> dict:
    pc = RTCPeerConnection()
    pcs.add(pc)

    track = LatestFrameTrack(frame_store, fps=fps)
    pc.addTrack(track)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange() -> None:
        if pc.connectionState in ("failed", "closed", "disconnected"):
            await pc.close()
            pcs.discard(pc)

    await pc.setRemoteDescription(
        RTCSessionDescription(sdp=offer["sdp"], type=offer["type"])
    )
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
