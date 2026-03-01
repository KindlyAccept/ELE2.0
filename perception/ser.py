# perception/ser.py
"""
SER (Speech Emotion Recognition) module - ONNX-based speech emotion recognition.
Recognizes speaker emotion state from speech.
"""
from __future__ import annotations

import numpy as np
import soundfile as sf
from typing import Dict
from pathlib import Path

try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False
    print("[SER] Warning: onnxruntime not installed")

from utils.message_types import SERMsg, EmotionScores, EmotionLabel, now_ts


class SEREngine:
    """
    Speech emotion recognition engine (ONNX).
    
    Features:
    1. Recognize 7 emotion classes (aligned with EmotionLabel)
    2. Output emotion probability distribution
    3. Provide recognition confidence
    """
    
    # Model output index to EmotionLabel mapping
    EMOTION_MAP = {
        0: EmotionLabel.NEUTRAL,
        1: EmotionLabel.HAPPY,
        2: EmotionLabel.SAD,
        3: EmotionLabel.ANGRY,
        4: EmotionLabel.FEAR,
        5: EmotionLabel.DISGUST,
        6: EmotionLabel.SURPRISE,
    }
    
    def __init__(
        self,
        model_path: str = None,
        sample_rate: int = 16000,
    ):
        """
        Initialize SER engine.
        
        Args:
            model_path: ONNX model path (directory or file)
            sample_rate: Audio sample rate
        """
        self.sample_rate = sample_rate
        self.emotion_map = self.EMOTION_MAP
        
        # 默认模型路径
        if model_path is None:
            base_dir = Path(__file__).parent.parent
            model_path = str(base_dir / "Data" / "Models" / "hubert-emotion")
        
        # If directory, look for model.onnx
        model_path = Path(model_path)
        if model_path.is_dir():
            model_file = model_path / "model.onnx"
        else:
            model_file = model_path
        
        self.model_path = str(model_file)
        
        if ONNX_AVAILABLE and model_file.exists():
            self._init_onnx(str(model_file))
        else:
            self._init_fallback()
    
    def _init_onnx(self, model_path: str):
        """初始化 ONNX 模型"""
        print(f"[SER] 正在加载 ONNX 模型: {model_path}")
        
        try:
            self.session = ort.InferenceSession(
                model_path,
                providers=['CPUExecutionProvider']
            )
            
            # Get input/output info
            inp = self.session.get_inputs()[0]
            self.input_name = inp.name
            self.output_names = [o.name for o in self.session.get_outputs()]
            out = self.session.get_outputs()[0]
            n_labels = out.shape[-1] if len(out.shape) >= 2 and isinstance(out.shape[-1], int) else 7

            self.backend = "onnx"
            print(f"[SER] Model loaded successfully")
            print(f"  - Input: {self.input_name}, shape: {inp.shape}")
            print(f"  - Emotion classes: {n_labels}")
            
        except Exception as e:
            print(f"[SER] Model load failed: {e}")
            self._init_fallback()
    
    def _init_fallback(self):
        """初始化备用方案"""
        self.backend = "fallback"
        print("[SER] 使用备用方案（返回中性情感）")
    
    def _preprocess(self, waveform: np.ndarray) -> np.ndarray:
        """
        Preprocess audio waveform.
        
        Args:
            waveform: Raw audio waveform (samples,) or (1, samples)
        
        Returns:
            Processed input data
        """
        # Ensure 1D
        if waveform.ndim > 1:
            waveform = waveform.flatten()
        
        # Normalize to [-1, 1]
        if waveform.max() > 1.0 or waveform.min() < -1.0:
            waveform = waveform / 32768.0
        
        # 添加 batch 维度
        waveform = np.expand_dims(waveform, axis=0).astype(np.float32)
        
        return waveform
    
    def _postprocess(self, outputs: list) -> Dict[EmotionLabel, float]:
        """Postprocess model output."""
        logits = outputs[0].flatten()
        
        # Softmax
        exp_logits = np.exp(logits - np.max(logits))
        probs = exp_logits / np.sum(exp_logits)
        
        # Build emotion score dict
        emotion_scores = {}
        for idx in range(min(len(probs), len(self.emotion_map))):
            if idx in self.emotion_map:
                emotion_scores[self.emotion_map[idx]] = float(probs[idx])
        
        return emotion_scores, float(np.max(probs))
    
    def _recognize_waveform(
        self,
        waveform: np.ndarray,
        utterance_id: str | None = None,
    ) -> SERMsg:
        """
        Internal entry: run emotion recognition on float32 waveform, return SERMsg.
        waveform: 1D or 2D array, normalized to [-1,1] or int16 range (handled by _preprocess).
        """
        if self.backend != "onnx":
            return self._get_default_result(utterance_id)
        try:
            input_data = self._preprocess(waveform)
            outputs = self.session.run(
                self.output_names,
                {self.input_name: input_data},
            )
            emotion_scores, confidence = self._postprocess(outputs)
            predicted_emotion = max(emotion_scores.items(), key=lambda x: x[1])[0]
            print(f"[SER] 识别完成: {predicted_emotion.value} ({confidence:.2%})")
            return SERMsg(
                timestamp=now_ts(),
                emotion=EmotionScores(
                    scores=emotion_scores,
                    confidence=confidence,
                ),
                utterance_id=utterance_id,
            )
        except Exception as e:
            print(f"[SER] Recognition failed: {e}")
            return self._get_default_result(utterance_id)

    def recognize_file(self, audio_path: str, utterance_id: str = None) -> SERMsg:
        """
        Recognize emotion from audio file.
        
        Args:
            audio_path: WAV audio file path
            utterance_id: Utterance ID (for alignment with ASR)
        """
        print(f"[SER] Analyzing emotion: {audio_path}")
        if self.backend != "onnx":
            return self._get_default_result(utterance_id)
        try:
            audio_data, sample_rate = sf.read(audio_path)
            if audio_data.ndim > 1:
                audio_data = np.mean(audio_data, axis=1)
            if sample_rate != self.sample_rate:
                new_length = int(len(audio_data) * self.sample_rate / sample_rate)
                audio_data = np.interp(
                    np.linspace(0, len(audio_data), new_length),
                    np.arange(len(audio_data)),
                    audio_data,
                )
            return self._recognize_waveform(audio_data, utterance_id)
        except Exception as e:
            print(f"[SER] Recognition failed: {e}")
            return self._get_default_result(utterance_id)

    def recognize_bytes(
        self,
        audio_data: bytes,
        utterance_id: str | None = None,
    ) -> SERMsg:
        """
        Recognize emotion from raw audio bytes.
        Requires: 16kHz, mono, 16-bit PCM (matches AudioService output).
        
        Args:
            audio_data: Raw PCM audio bytes (16-bit signed integer)
            utterance_id: Utterance ID
        """
        if self.backend != "onnx" or not audio_data:
            return self._get_default_result(utterance_id)
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
        audio_array = audio_array / 32768.0
        return self._recognize_waveform(audio_array, utterance_id)
    
    def _get_default_result(self, utterance_id: str = None) -> SERMsg:
        """Return default result."""
        return SERMsg(
            timestamp=now_ts(),
            emotion=EmotionScores(
                scores={EmotionLabel.NEUTRAL: 1.0},
                confidence=0.0
            ),
            utterance_id=utterance_id,
        )
