# perception/fer.py
"""
FER (Facial Expression Recognition) module - EfficientNet-based facial expression recognition.

Model: enet_b0_8_va_mtl.onnx
- Input: (batch_size, 3, 224, 224) RGB image
- Output: (batch_size, 10)
  - [0:8] - 8 expression logits (Neutral, Happy, Sad, Surprise, Fear, Disgust, Anger, Contempt)
  - [8] - Valence, [9] - Arousal
"""
from __future__ import annotations

import cv2
import numpy as np
import time
from pathlib import Path
from typing import Tuple, List, Dict, NamedTuple

try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False
    print("[FER] Warning: onnxruntime not installed")

from utils.message_types import EmotionLabel, EmotionScores, VisionFERMsg, now_ts


class FERResult(NamedTuple):
    """FER recognition result."""
    emotion: EmotionLabel
    emotion_scores: EmotionScores
    valence: float
    arousal: float
    confidence: float
    expression_name: str


class FEREngine:
    """
    Facial expression recognition engine.
    
    Output: 8 discrete expressions + Valence/Arousal continuous values
    Expression classes: Neutral, Happy, Sad, Surprise, Fear, Disgust, Anger, Contempt
    """
    
    # 8 expression classes mapped to EmotionLabel (Contempt -> Neutral)
    EXPRESSION_LABELS = [
        EmotionLabel.NEUTRAL,   # 0 - Neutral
        EmotionLabel.HAPPY,     # 1 - Happy
        EmotionLabel.SAD,       # 2 - Sad
        EmotionLabel.SURPRISE,  # 3 - Surprise
        EmotionLabel.FEAR,      # 4 - Fear
        EmotionLabel.DISGUST,   # 5 - Disgust
        EmotionLabel.ANGRY,     # 6 - Anger
        EmotionLabel.NEUTRAL,   # 7 - Contempt -> Neutral
    ]
    
    EXPRESSION_NAMES = [
        "Neutral", "Happy", "Sad", "Surprise",
        "Fear", "Disgust", "Anger", "Contempt"
    ]
    
    def __init__(
        self,
        model_path: str = None,
        input_size: Tuple[int, int] = (224, 224),
    ):
        """
        Initialize FER engine.
        
        Args:
            model_path: ONNX model path
            input_size: Model input size (H, W)
        """
        self.input_size = input_size
        self.input_format = "NCHW"
        
        if model_path is None:
            base_dir = Path(__file__).parent.parent
            model_path = str(base_dir / "Data" / "Models" / "enet" / "enet_b0_8_va_mtl.onnx")
        
        self.model_path = model_path
        
        if ONNX_AVAILABLE and Path(model_path).exists():
            self._init_onnx(model_path)
        else:
            self._init_fallback()
    
    def _init_onnx(self, model_path: str):
        """初始化 ONNX 模型"""
        print(f"[FER] 正在加载模型: {model_path}")
        
        try:
            self.session = ort.InferenceSession(
                model_path,
                providers=['CPUExecutionProvider']
            )
            
            self.input_name = self.session.get_inputs()[0].name
            input_shape = self.session.get_inputs()[0].shape
            
            if len(input_shape) == 4:
                h_idx, w_idx = (2, 3) if input_shape[1] == 3 else (1, 2)
                if isinstance(input_shape[h_idx], int) and isinstance(input_shape[w_idx], int):
                    self.input_size = (input_shape[h_idx], input_shape[w_idx])
                self.input_format = "NCHW" if input_shape[1] == 3 else "NHWC"
            
            self.output_names = [o.name for o in self.session.get_outputs()]
            self.backend = "onnx"
            print(f"[FER] Model loaded, input size: {self.input_size}")
            
        except Exception as e:
            print(f"[FER] Model load failed: {e}")
            self._init_fallback()
    
    def _init_fallback(self):
        """Initialize fallback."""
        self.backend = "fallback"
        print("[FER] Using fallback (returns neutral emotion)")
    
    def _preprocess(self, face_image: np.ndarray) -> np.ndarray:
        """预处理人脸图像"""
        resized = cv2.resize(face_image, (self.input_size[1], self.input_size[0]))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        normalized = rgb.astype(np.float32) / 255.0
        
        # ImageNet normalization
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        normalized = (normalized - mean) / std
        
        if self.input_format == "NCHW":
            transposed = np.transpose(normalized, (2, 0, 1))
        else:
            transposed = normalized
        
        return np.expand_dims(transposed, axis=0).astype(np.float32)
    
    def recognize(self, face_image: np.ndarray) -> FERResult:
        """Recognize face expression."""
        if face_image is None or face_image.size == 0:
            return self._get_default_result()
        
        if face_image.shape[0] < 10 or face_image.shape[1] < 10:
            return self._get_default_result()
        
        if self.backend == "onnx":
            return self._recognize_onnx(face_image)
        return self._get_default_result()
    
    def _recognize_onnx(self, face_image: np.ndarray) -> FERResult:
        """使用 ONNX 进行表情识别"""
        try:
            input_data = self._preprocess(face_image)
            outputs = self.session.run(self.output_names, {self.input_name: input_data})
            return self._postprocess(outputs)
        except Exception as e:
            print(f"[FER] Inference error: {e}")
            return self._get_default_result()
    
    def _postprocess(self, outputs: List[np.ndarray]) -> FERResult:
        """后处理模型输出"""
        output = outputs[0].flatten()
        
        if len(output) >= 10:
            expression_logits = output[:8]
            valence = float(output[8])
            arousal = float(output[9])
        elif len(output) == 8:
            expression_logits = output
            valence, arousal = 0.0, 0.5
        else:
            return self._get_default_result()
        
        # Softmax
        exp_logits = np.exp(expression_logits - np.max(expression_logits))
        probs = exp_logits / np.sum(exp_logits)
        
        # Build emotion scores
        scores: Dict[EmotionLabel, float] = {}
        for i, label in enumerate(self.EXPRESSION_LABELS):
            if i < len(probs):
                if label in scores:
                    scores[label] = max(scores[label], float(probs[i]))
                else:
                    scores[label] = float(probs[i])
        
        predicted_idx = int(np.argmax(probs))
        
        return FERResult(
            emotion=self.EXPRESSION_LABELS[predicted_idx],
            emotion_scores=EmotionScores(scores=scores, confidence=float(probs[predicted_idx])),
            valence=float(np.clip(valence, -1.0, 1.0)),
            arousal=float(np.clip(arousal, 0.0, 1.0)),
            confidence=float(probs[predicted_idx]),
            expression_name=self.EXPRESSION_NAMES[predicted_idx]
        )
    
    def _get_default_result(self) -> FERResult:
        """Return default result."""
        scores = {label: 0.0 for label in EmotionLabel}
        scores[EmotionLabel.NEUTRAL] = 1.0
        
        return FERResult(
            emotion=EmotionLabel.NEUTRAL,
            emotion_scores=EmotionScores(scores=scores, confidence=0.5),
            valence=0.0,
            arousal=0.3,
            confidence=0.5,
            expression_name="Neutral"
        )
    
    def create_fer_msg(
        self,
        result: FERResult,
        face_id: int = 0,
        bbox: Tuple[int, int, int, int] = None,
        image_id: str = None
    ) -> VisionFERMsg:
        """Create VisionFERMsg message object."""
        return VisionFERMsg(
            timestamp=now_ts(),
            face_id=face_id,
            bbox=bbox,
            emotion=result.emotion_scores,
            image_id=image_id
        )


class FERSmoother:
    """
    FER temporal smoother.
    
    Features:
    1. EMA smoothing of expression probability distribution
    2. Sliding window smoothing of VA values
    3. Emotion lock mechanism to prevent frequent switching
    """
    
    def __init__(
        self,
        ema_alpha: float = 0.3,
        va_window_size: int = 10,
        switch_threshold: float = 0.15,
        min_confidence: float = 0.4,
        confirm_frames: int = 3,
        bbox_ema_alpha: float = 0.3,
    ):
        """
        参数：
            ema_alpha: EMA 系数，越小越平滑
            va_window_size: VA 滑动窗口大小
            switch_threshold: 情绪切换阈值
            min_confidence: 新情绪最低置信度
            confirm_frames: 确认帧数
            bbox_ema_alpha: 检测框 EMA 平滑系数，用于稳定框位置
        """
        self.ema_alpha = ema_alpha
        self.va_window_size = va_window_size
        self.switch_threshold = switch_threshold
        self.min_confidence = min_confidence
        self.confirm_frames = confirm_frames
        self.bbox_ema_alpha = bbox_ema_alpha
        self.face_states: Dict[int, dict] = {}
        self.num_expressions = 8

        print(f"[FERSmoother] Initialized (alpha={ema_alpha}, threshold={switch_threshold})")
    
    def _get_or_create_state(self, face_id: int) -> dict:
        """Get or create face state."""
        if face_id not in self.face_states:
            self.face_states[face_id] = {
                'smoothed_probs': np.ones(self.num_expressions) / self.num_expressions,
                'va_history': [],
                'locked_expression_idx': 0,
                'locked_confidence': 0.0,
                'last_update': time.time(),
                'detection_count': 0,
                'confirmed': False,
                'bbox': None,
                'bbox_smoothed': None,
            }
        return self.face_states[face_id]
    
    def smooth(self, result: FERResult, face_id: int = 0) -> FERResult:
        """对 FER 结果进行时间平滑"""
        state = self._get_or_create_state(face_id)
        state['last_update'] = time.time()
        
        # Extract current probability distribution
        current_probs = np.zeros(self.num_expressions)
        for i, name in enumerate(FEREngine.EXPRESSION_NAMES):
            label = FEREngine.EXPRESSION_LABELS[i]
            current_probs[i] = result.emotion_scores.scores.get(label, 0.0)
        
        if current_probs.sum() > 0:
            current_probs = current_probs / current_probs.sum()
        
        # EMA smoothing
        state['smoothed_probs'] = (
            self.ema_alpha * current_probs + 
            (1 - self.ema_alpha) * state['smoothed_probs']
        )
        smoothed_probs = state['smoothed_probs']
        
        # Sliding window smooth VA
        state['va_history'].append((result.valence, result.arousal))
        if len(state['va_history']) > self.va_window_size:
            state['va_history'].pop(0)
        
        va_array = np.array(state['va_history'])
        smoothed_valence = float(np.mean(va_array[:, 0]))
        smoothed_arousal = float(np.mean(va_array[:, 1]))
        
        # Emotion lock mechanism
        best_idx = int(np.argmax(smoothed_probs))
        best_confidence = float(smoothed_probs[best_idx])
        locked_idx = state['locked_expression_idx']
        locked_prob = float(smoothed_probs[locked_idx])
        
        should_switch = (
            best_confidence - locked_prob > self.switch_threshold and
            best_confidence > self.min_confidence
        )
        
        if should_switch:
            state['locked_expression_idx'] = best_idx
            state['locked_confidence'] = best_confidence
        else:
            state['locked_confidence'] = locked_prob
        
        final_idx = state['locked_expression_idx']
        final_confidence = state['locked_confidence']
        
        # Build smoothed emotion scores
        smoothed_scores: Dict[EmotionLabel, float] = {}
        for i, label in enumerate(FEREngine.EXPRESSION_LABELS[:self.num_expressions]):
            prob = float(smoothed_probs[i])
            if label in smoothed_scores:
                smoothed_scores[label] = max(smoothed_scores[label], prob)
            else:
                smoothed_scores[label] = prob
        
        return FERResult(
            emotion=FEREngine.EXPRESSION_LABELS[final_idx],
            emotion_scores=EmotionScores(scores=smoothed_scores, confidence=final_confidence),
            valence=smoothed_valence,
            arousal=smoothed_arousal,
            confidence=final_confidence,
            expression_name=FEREngine.EXPRESSION_NAMES[final_idx]
        )

    def _compute_iou(
        self,
        box1: Tuple[int, int, int, int],
        box2: Tuple[int, int, int, int],
    ) -> float:
        """Compute IoU of two rectangles (x1, y1, x2, y2)."""
        x1_1, y1_1, x2_1, y2_1 = box1
        x1_2, y1_2, x2_2, y2_2 = box2
        x1_i = max(x1_1, x1_2)
        y1_i = max(y1_1, y1_2)
        x2_i = min(x2_1, x2_2)
        y2_i = min(y2_1, y2_2)
        if x2_i <= x1_i or y2_i <= y1_i:
            return 0.0
        intersection = (x2_i - x1_i) * (y2_i - y1_i)
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        union = area1 + area2 - intersection
        return intersection / union if union > 0 else 0.0

    def get_face_id_by_iou(
        self,
        bbox: Tuple[int, int, int, int],
        iou_threshold: float = 0.5,
    ) -> int:
        """
        通过 IoU 匹配当前帧检测框与已有轨迹，返回稳定的人脸 ID。
        bbox 格式: (x, y, w, h)。
        """
        x, y, w, h = bbox
        current_box = (x, y, x + w, y + h)
        best_iou = 0.0
        best_id = -1
        for face_id, state in self.face_states.items():
            if state.get('bbox') is None:
                continue
            iou = self._compute_iou(current_box, state['bbox'])
            if iou > best_iou:
                best_iou = iou
                best_id = face_id
        if best_iou >= iou_threshold:
            self.face_states[best_id]['bbox'] = current_box
            return best_id
        new_id = len(self.face_states)
        state = self._get_or_create_state(new_id)
        state['bbox'] = current_box
        return new_id

    def smooth_bbox(
        self,
        bbox: Tuple[int, int, int, int],
        face_id: int,
    ) -> Tuple[int, int, int, int]:
        """
        Apply EMA smoothing to detection box to reduce jitter. bbox format: (x, y, w, h).
        Returns smoothed (x, y, w, h) for cropping and drawing.
        """
        x, y, w, h = bbox
        cx = x + w / 2.0
        cy = y + h / 2.0
        state = self._get_or_create_state(face_id)
        prev = state.get('bbox_smoothed')
        if prev is None:
            state['bbox_smoothed'] = (cx, cy, float(w), float(h))
            return (x, y, w, h)
        ocx, ocy, ow, oh = prev
        ncx = self.bbox_ema_alpha * cx + (1 - self.bbox_ema_alpha) * ocx
        ncy = self.bbox_ema_alpha * cy + (1 - self.bbox_ema_alpha) * ocy
        nw = self.bbox_ema_alpha * w + (1 - self.bbox_ema_alpha) * ow
        nh = self.bbox_ema_alpha * h + (1 - self.bbox_ema_alpha) * oh
        state['bbox_smoothed'] = (ncx, ncy, nw, nh)
        sx = int(round(ncx - nw / 2))
        sy = int(round(ncy - nh / 2))
        return (sx, sy, int(round(nw)), int(round(nh)))

    def smooth_with_confirm(
        self, 
        result: FERResult, 
        face_id: int = 0
    ) -> Tuple[FERResult, bool]:
        """平滑并返回是否确认为人脸"""
        state = self._get_or_create_state(face_id)
        state['detection_count'] += 1
        is_confirmed = state['detection_count'] >= self.confirm_frames
        state['confirmed'] = is_confirmed
        return self.smooth(result, face_id), is_confirmed
    
    def cleanup_stale_faces(self, max_age: float = 2.0):
        """Clean up stale face states."""
        now = time.time()
        stale_ids = [
            fid for fid, state in self.face_states.items()
            if now - state['last_update'] > max_age
        ]
        for fid in stale_ids:
            del self.face_states[fid]
