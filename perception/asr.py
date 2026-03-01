# perception/asr.py
"""
ASR (Automatic Speech Recognition) module - Whisper-based speech recognition.
Uses faster-whisper for high-performance offline speech-to-text.
"""
from __future__ import annotations

import numpy as np
from faster_whisper import WhisperModel
from pathlib import Path

from utils.message_types import ASRMsg, now_ts


class ASREngine:
    """
    Whisper speech recognition engine.
    
    Features: speech-to-text, multilingual, VAD filtering.
    """
    
    def __init__(
        self,
        model_path: str = None,
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "en",
        beam_size: int = 5,
        vad_filter: bool = True,
    ):
        """
        初始化Whisper ASR引擎
        
        参数：
            model_path: 本地模型路径
            device: 计算设备 (cpu/cuda)
            compute_type: 计算精度 (int8/float16/float32)
            language: 识别语言 (en/zh/None自动检测)
            beam_size: 束搜索宽度
            vad_filter: 是否启用VAD过滤
        """
        self.device = device
        self.language = language
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        
        # Default model path
        if model_path is None:
            base_dir = Path(__file__).parent.parent
            model_path = str(base_dir / "Data" / "Models" / "whisper-base")
        
        self.model_path = model_path
        
        print(f"[ASR] Loading Whisper model: {model_path}")
        print(f"  - Device: {device}, precision: {compute_type}")
        
        if not Path(model_path).exists():
            raise FileNotFoundError(f"[ASR] Model file not found: {model_path}")
        
        try:
            self.model = WhisperModel(model_path, device=device, compute_type=compute_type)
            print(f"[ASR] 模型加载完成")
        except Exception as e:
            print(f"[ASR] Model load failed: {e}")
            raise
    
    def _segments_to_asr_msg(
        self,
        segment_list: list,
        info,
        utterance_id: str | None,
    ) -> ASRMsg:
        """Convert Whisper segment list and info to ASRMsg (shared logic)."""
        if not segment_list:
            print(f"[ASR] No speech detected")
            return ASRMsg(
                timestamp=now_ts(),
                text="",
                lang=self.language or "en",
                confidence=0.0,
                utterance_id=utterance_id,
            )
        full_text = " ".join([s.text.strip() for s in segment_list])
        log_probs = [s.avg_logprob for s in segment_list]
        confidence = float(np.exp(np.mean(log_probs)))
        detected_lang = info.language if self.language is None else self.language
        print(f"[ASR] 识别完成: '{full_text}' (置信度: {confidence:.2f})")
        return ASRMsg(
            timestamp=now_ts(),
            text=full_text.strip(),
            lang=detected_lang,
            confidence=confidence,
            utterance_id=utterance_id,
        )

    def _transcribe_input(self, audio_input, utterance_id: str | None) -> ASRMsg:
        """
        Internal entry: transcribe audio input (file path or float32 waveform).
        audio_input: file path (str) or numpy waveform (np.ndarray, shape (n,) or (1,n), range [-1,1])
        """
        try:
            segments, info = self.model.transcribe(
                audio_input,
                language=self.language,
                beam_size=self.beam_size,
                vad_filter=self.vad_filter,
                vad_parameters=dict(min_silence_duration_ms=500, threshold=0.5),
            )
            segment_list = list(segments)
            return self._segments_to_asr_msg(segment_list, info, utterance_id)
        except Exception as e:
            print(f"[ASR] Recognition failed: {e}")
            return ASRMsg(
                timestamp=now_ts(),
                text="",
                lang=self.language or "en",
                confidence=0.0,
                utterance_id=utterance_id,
            )

    def transcribe_file(self, audio_path: str, utterance_id: str = None) -> ASRMsg:
        """
        Transcribe text from audio file.
        
        Args:
            audio_path: WAV audio file path
            utterance_id: Utterance ID (for alignment with SER)
        """
        print(f"[ASR] Transcribing: {audio_path}")
        return self._transcribe_input(audio_path, utterance_id)

    def transcribe_bytes(
        self,
        audio_data: bytes,
        utterance_id: str = None,
    ) -> ASRMsg:
        """
        Transcribe text from raw audio bytes.
        Requires: 16kHz, mono, 16-bit PCM (matches AudioService output).
        
        Args:
            audio_data: Raw PCM audio bytes (16-bit signed integer)
            utterance_id: Utterance ID
        """
        if not audio_data:
            return ASRMsg(
                timestamp=now_ts(),
                text="",
                lang=self.language or "en",
                confidence=0.0,
                utterance_id=utterance_id,
            )
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
        audio_array = audio_array / 32768.0
        return self._transcribe_input(audio_array, utterance_id)
