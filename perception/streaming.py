"""
Streaming voice interaction module.

Continuously captures audio from microphone, detects speech segments via energy VAD,
splits into complete utterances, then: ASR transcription, SER emotion recognition,
emotion fusion, dialogue management generates reply, TTS playback.
Supports user speech interrupting TTS playback.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Optional

import numpy as np

from cognitive.dialogue_manager import DialogueManager
from fusion.emotion_fusion import EmotionFusion
from io_devices.audio_service import AudioService
from action.tts_engine import TTSEngine
from perception.asr import ASREngine
from perception.ser import SEREngine
from utils.http_reporter import HttpReporter


class StreamingVoiceInteraction(threading.Thread):
    """
    Streaming voice interaction thread: pull audio stream, detect utterance boundaries,
    run ASR/SER, update emotion, generate TTS reply.
    """

    def __init__(
        self,
        audio_service: AudioService,
        asr_engine: ASREngine,
        ser_engine: SEREngine,
        emotion_fusion: EmotionFusion,
        dialog_manager: DialogueManager,
        tts_engine: TTSEngine,
        reporter: HttpReporter | None = None,
        *,
        vad_threshold: int,
        pre_speech_ms: int = 200,
        start_speech_ms: int = 200,
        end_silence_ms: int = 600,
        min_speech_ms: int = 300,
        max_utterance_s: float = 8.0,
    ):
        super().__init__(daemon=True)
        self.audio_service = audio_service
        self.asr_engine = asr_engine
        self.ser_engine = ser_engine
        self.emotion_fusion = emotion_fusion
        self.dialog_manager = dialog_manager
        self.tts_engine = tts_engine
        self.reporter = reporter
        # VAD and utterance segmentation params
        self.vad_threshold = vad_threshold
        self.pre_speech_ms = pre_speech_ms      # Pre-speech buffer at utterance start (ms)
        self.start_speech_ms = start_speech_ms  # Continuous voice duration to start utterance
        self.end_silence_ms = end_silence_ms    # End silence duration to end utterance
        self.min_speech_ms = min_speech_ms      # Min valid utterance length
        self.max_utterance_s = max_utterance_s  # Max single utterance duration (s)

        self._running = threading.Event()
        self._running.set()
        self._buffer = deque()
        self._buffer_lock = threading.Lock()

    def _on_audio_chunk(self, data: bytes) -> None:
        """音频服务回调：将收到的音频块放入队列。"""
        with self._buffer_lock:
            self._buffer.append(data)

    def _pop_chunk(self) -> Optional[bytes]:
        """Pop one audio chunk from queue, return None if empty."""
        with self._buffer_lock:
            if self._buffer:
                return self._buffer.popleft()
        return None

    def stop(self) -> None:
        """Stop streaming interaction and audio stream."""
        self._running.clear()
        self.audio_service.stop_streaming()

    def run(self) -> None:
        """Main loop: consume audio chunks, VAD, utterance segmentation, call _process_utterance on end."""
        print("[Streaming] Voice interaction started.")
        self.audio_service.start_streaming(self._on_audio_chunk)

        rate = self.audio_service.rate
        channels = self.audio_service.channels
        bytes_per_sample = 2

        pre_speech_chunks: deque[bytes] = deque()
        pre_speech_max = max(1, int(self.pre_speech_ms / 10))

        speech_active = False
        speech_ms = 0.0
        voice_ms = 0.0
        silence_ms = 0.0
        utterance = bytearray()
        tts_interrupted = False
        last_activity = time.time()

        while self._running.is_set():
            chunk = self._pop_chunk()
            if chunk is None:
                time.sleep(0.005)
                continue

            # 根据采样率计算本块时长（毫秒）
            chunk_ms = (len(chunk) / (rate * channels * bytes_per_sample)) * 1000.0

            # Energy VAD: RMS above threshold = voice
            audio_array = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
            energy = float(np.sqrt(np.mean(audio_array ** 2))) if audio_array.size else 0.0
            is_voice = energy > self.vad_threshold

            # Pre-speech buffer: include leading chunk to avoid cutting start
            pre_speech_chunks.append(chunk)
            if len(pre_speech_chunks) > pre_speech_max:
                pre_speech_chunks.popleft()

            if is_voice:
                last_activity = time.time()
                silence_ms = 0.0
                speech_ms += chunk_ms
                voice_ms += chunk_ms

                # Interrupt TTS as soon as user speaks
                # Only try when TTS playing, higher threshold to avoid false trigger (0.3 -> 0.8)
                if not tts_interrupted and self.tts_engine.is_speaking() and voice_ms >= self.start_speech_ms * 0.8:
                    self.tts_engine.stop()
                    tts_interrupted = True
                    print(f"[VAD] TTS interrupted by voice detection ({voice_ms:.1f}ms)")

                if not speech_active and voice_ms >= self.start_speech_ms:
                    speech_active = True
                    if not tts_interrupted:
                        self.tts_engine.stop()
                        tts_interrupted = True
                    for c in pre_speech_chunks:
                        utterance.extend(c)
                    pre_speech_chunks.clear()
                    utterance.extend(chunk)
                elif speech_active:
                    utterance.extend(chunk)
            else:
                if tts_interrupted and silence_ms > 500:
                    tts_interrupted = False
                voice_ms = 0.0
                if speech_active:
                    silence_ms += chunk_ms
                    utterance.extend(chunk)

            # 语句结束：超长或句尾静音够久且语句够长
            if speech_active:
                if speech_ms >= self.max_utterance_s * 1000.0:
                    self._process_utterance(bytes(utterance))
                    utterance.clear()
                    speech_active = False
                    speech_ms = 0.0
                    silence_ms = 0.0
                    pre_speech_chunks.clear()
                    tts_interrupted = False  # Reset interrupt flag
                    continue

                if silence_ms >= self.end_silence_ms and speech_ms >= self.min_speech_ms:
                    self._process_utterance(bytes(utterance))
                    utterance.clear()
                    speech_active = False
                    speech_ms = 0.0
                    silence_ms = 0.0
                    pre_speech_chunks.clear()
                    tts_interrupted = False  # Reset interrupt flag
                    continue

            # Clear pre-buffer on long inactivity, allow next TTS interrupt
            if time.time() - last_activity > 2.0 and not speech_active:
                pre_speech_chunks.clear()
                tts_interrupted = False

        print("[Streaming] Voice interaction stopped.")

    def _process_utterance(self, audio_bytes: bytes) -> None:
        """
        Process full utterance: stop TTS, then ASR transcribe -> SER emotion -> update fusion ->
        report (optional) -> dialogue generates reply and prints.
        """
        if not audio_bytes:
            return

        self.tts_engine.stop()
        print("[Streaming] Processing utterance...")
        asr_msg = self.asr_engine.transcribe_bytes(audio_bytes)
        if not asr_msg.text:
            print("[Streaming] No speech detected.")
            return

        print(f"✓ You said: \"{asr_msg.text}\"")

        if self.reporter is not None:
            self.reporter.report_asr(asr_msg)

        ser_msg = self.ser_engine.recognize_bytes(audio_bytes)
        self.emotion_fusion.update_ser(ser_msg)
        if self.reporter is not None:
            self.reporter.report_ser(ser_msg)
            self.reporter.report_fusion(self.emotion_fusion.get_emotion_state())

        reply = self.dialog_manager.process_user_text(asr_msg.text)
        print(f"\n🤖 Robot: {reply}\n")
