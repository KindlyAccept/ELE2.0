from __future__ import annotations

import queue
import threading
import time
from typing import Dict, Optional

import requests

from utils.message_types import EmotionScores, EmotionState, SERMsg, VisionFERMsg, ASRMsg


def _serialize_scores(scores: EmotionScores) -> Dict[str, float]:
    return {label.value: float(prob) for label, prob in scores.scores.items()}


def _top_label(scores: EmotionScores) -> str:
    if not scores.scores:
        return "unknown"
    label = max(scores.scores, key=scores.scores.get)
    return label.value


class HttpReporter:
    def __init__(
        self,
        base_url: str,
        timeout: float = 0.8,
        frame_fps: int = 30,
        jpeg_quality: int = 80,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.frame_fps = frame_fps
        self.frame_interval = 1.0 / max(1, frame_fps)
        self.jpeg_quality = jpeg_quality
        self._session = requests.Session()
        self._event_queue: queue.Queue = queue.Queue(maxsize=200)
        self._running = threading.Event()
        self._running.set()
        self._frame_lock = threading.Lock()
        self._frame_payload: Optional[tuple] = None

        self._event_thread = threading.Thread(
            target=self._event_worker, daemon=True
        )
        self._frame_thread = threading.Thread(
            target=self._frame_worker, daemon=True
        )
        self._event_thread.start()
        self._frame_thread.start()

    def stop(self) -> None:
        self._running.clear()

    def _event_worker(self) -> None:
        while self._running.is_set():
            try:
                path, payload = self._event_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._session.post(
                    f"{self.base_url}{path}",
                    json=payload,
                    timeout=self.timeout,
                )
            except requests.RequestException:
                continue

    def _frame_worker(self) -> None:
        last_send = 0.0
        while self._running.is_set():
            now = time.time()
            wait = self.frame_interval - (now - last_send)
            if wait > 0:
                time.sleep(wait)
            with self._frame_lock:
                payload = self._frame_payload
            if payload is None:
                time.sleep(0.05)
                continue
            jpeg_bytes, timestamp, width, height = payload
            try:
                self._session.post(
                    f"{self.base_url}/api/vision/frame",
                    params={
                        "timestamp": timestamp,
                        "width": width,
                        "height": height,
                    },
                    data=jpeg_bytes,
                    headers={"Content-Type": "image/jpeg"},
                    timeout=self.timeout,
                )
                last_send = time.time()
            except requests.RequestException:
                continue

    def post_event(self, path: str, payload: dict) -> None:
        try:
            self._event_queue.put_nowait((path, payload))
        except queue.Full:
            return

    def submit_frame(
        self, jpeg_bytes: bytes, timestamp: float, width: int, height: int
    ) -> None:
        with self._frame_lock:
            self._frame_payload = (jpeg_bytes, timestamp, width, height)

    def report_ser(self, ser_msg: SERMsg) -> None:
        payload = {
            "timestamp": ser_msg.timestamp,
            "label": _top_label(ser_msg.emotion),
            "confidence": ser_msg.emotion.confidence,
            "scores": _serialize_scores(ser_msg.emotion),
        }
        self.post_event("/api/events/ser", payload)

    def report_fer(self, fer_msg: VisionFERMsg) -> None:
        payload = {
            "timestamp": fer_msg.timestamp,
            "label": _top_label(fer_msg.emotion),
            "confidence": fer_msg.emotion.confidence,
            "scores": _serialize_scores(fer_msg.emotion),
        }
        self.post_event("/api/events/fer", payload)

    def report_fusion(self, state: EmotionState, label: str | None = None) -> None:
        payload = {
            "timestamp": state.timestamp,
            "valence": state.valence,
            "arousal": state.arousal,
            "dominance": state.dominance,
            "confidence": state.overall_confidence,
            "label": label,
        }
        self.post_event("/api/events/fusion", payload)

    def report_asr(self, asr_msg: ASRMsg) -> None:
        payload = {
            "timestamp": asr_msg.timestamp,
            "text": asr_msg.text,
            "confidence": asr_msg.confidence,
        }
        self.post_event("/api/events/asr", payload)

    def report_dialogue(
        self, role: str, content: str, emotion_state: EmotionState
    ) -> None:
        payload = {
            "timestamp": time.time(),
            "role": role,
            "content": content,
            "emotion_label": None,
            "valence": emotion_state.valence,
            "arousal": emotion_state.arousal,
            "dominance": emotion_state.dominance,
        }
        self.post_event("/api/events/dialogue", payload)

    def report_status(self, payload: dict) -> None:
        self.post_event("/api/status", payload)
