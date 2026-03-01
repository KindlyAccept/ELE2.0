# fusion/emotion_fusion.py
"""
Emotion fusion module - Fuses multimodal emotion info into unified emotion state.

Current version:
- Supports SER (speech emotion recognition)
- Supports FER (facial expression recognition)
- Converts discrete emotion labels to continuous VAD space
"""
from __future__ import annotations

from typing import Optional, Dict, Tuple
from utils.message_types import (
    EmotionState,
    EmotionLabel,
    SERMsg,
    VisionFERMsg,
    Modality,
    now_ts,
)


class EmotionFusion:
    """
    Emotion fusion engine.
    
    Features:
    1. Convert discrete emotion labels (happy, sad) to continuous VAD space
    2. Fuse multimodal emotion info (SER + FER)
    3. Provide unified EmotionState interface for dialogue system
    
    VAD model:
    - Valence: positive/negative emotion, [-1, 1]
    - Arousal: activation level, [0, 1]
    - Dominance: sense of control, [-1, 1]
    """
    
    # Discrete emotion label to VAD space mapping (based on NRC VAD Lexicon)
    EMOTION_TO_VAD = {
        EmotionLabel.HAPPY: (0.72, 0.65, 0.48),    # positive, high control
        EmotionLabel.SAD: (-0.56, 0.36, -0.36),   # low V, low A, low D
        EmotionLabel.ANGRY: (-0.62, 0.76, 0.36),  # high A, low V, high D
        EmotionLabel.FEAR: (-0.68, 0.74, -0.54),  # high A, low V, very low D
        EmotionLabel.DISGUST: (-0.60, 0.48, -0.20),  # avoidance, moderate A, low D
        EmotionLabel.SURPRISE: (0.22, 0.72, 0.02),   # mildly positive, high A, neutral D
        EmotionLabel.NEUTRAL: (0.00, 0.30, 0.00),   # neutral anchor
    }
    # Contempt 不在 EmotionLabel 中（FER 专用），单独定义：evaluative / superiority, higher D
    CONTEMPT_VAD = (-0.64, 0.42, 0.34)
    
    def __init__(
        self,
        ser_weight: float = 0.4,
        fer_weight: float = 0.6,
        ser_max_age_s: float = 3.0,
        fer_max_age_s: float = 2.0,
    ):
        """
        Initialize emotion fusion engine.
        
        Args:
            ser_weight: SER modality weight
            fer_weight: FER modality weight
        """
        self.ser_weight = ser_weight
        self.fer_weight = fer_weight
        self.ser_max_age_s = ser_max_age_s
        self.fer_max_age_s = fer_max_age_s
        
        # Store latest emotion data per modality
        self.latest_ser: Optional[SERMsg] = None
        self.latest_fer: Optional[VisionFERMsg] = None
        
        # Track FER raw expression name (includes Contempt)
        self.latest_fer_expression: Optional[str] = None
        
        print("[EmotionFusion] 情感融合引擎初始化完成")
        print(f"  - SER权重: {ser_weight}, FER权重: {fer_weight}")
        print(f"  - SER max age: {ser_max_age_s}s, FER max age: {fer_max_age_s}s")
    
    def update_ser(self, ser_msg: SERMsg) -> None:
        """Update speech emotion recognition result."""
        self.latest_ser = ser_msg
    
    def update_fer(
        self, 
        fer_msg: VisionFERMsg, 
        expression_name: Optional[str] = None
    ) -> None:
        """
        Update facial expression recognition result.
        
        Args:
            fer_msg: VisionFERMsg message
            expression_name: Raw expression name (e.g. "Contempt") for non-standard emotions
        """
        self.latest_fer = fer_msg
        self.latest_fer_expression = expression_name
    
    def get_emotion_state(self) -> EmotionState:
        """
        Get current fused emotion state.
        
        Fusion logic:
        1. Compute VAD for SER and FER separately
        2. Fuse with weighted average
        3. If single modality only, use that modality's result
        """
        has_ser = self._is_fresh(self.latest_ser, self.ser_max_age_s)
        has_fer = self._is_fresh(self.latest_fer, self.fer_max_age_s)
        
        # No data
        if not has_ser and not has_fer:
            return self._get_default_state()
        
        # SER only
        if has_ser and not has_fer:
            return self._ser_to_vad(self.latest_ser)
        
        # FER only
        if has_fer and not has_ser:
            return self._fer_to_vad(self.latest_fer)
        
        # Both present, fuse
        return self._fuse_modalities()
    
    def _get_default_state(self) -> EmotionState:
        """获取默认的中性情感状态"""
        return EmotionState(
            timestamp=now_ts(),
            valence=0.0,
            arousal=0.3,
            dominance=0.0,
            overall_confidence=0.5,
            modality_weights={Modality.AUDIO: 0.5},
        )
    
    def _ser_to_vad(self, ser_msg: SERMsg) -> EmotionState:
        """Convert SER discrete emotion distribution to continuous VAD space."""
        v, a, d = self._emotion_scores_to_vad(ser_msg.emotion.scores)
        
        return EmotionState(
            timestamp=now_ts(),
            valence=v,
            arousal=a,
            dominance=d,
            overall_confidence=ser_msg.emotion.confidence,
            modality_weights={Modality.AUDIO: 1.0},
        )
    
    def _fer_to_vad(self, fer_msg: VisionFERMsg) -> EmotionState:
        """
        将FER的离散情感分布转换为连续VAD空间
        
        特殊处理：如果检测到 Contempt，使用专门的 VAD 映射
        """
        v, a, d = self._emotion_scores_to_vad(
            fer_msg.emotion.scores,
            expression_name=self.latest_fer_expression
        )
        
        return EmotionState(
            timestamp=now_ts(),
            valence=v,
            arousal=a,
            dominance=d,
            overall_confidence=fer_msg.emotion.confidence,
            modality_weights={Modality.VISION: 1.0},
        )
    
    def _emotion_scores_to_vad(
        self, 
        scores: Dict[EmotionLabel, float],
        expression_name: Optional[str] = None
    ) -> Tuple[float, float, float]:
        """
        Convert emotion probability distribution to VAD values.
        
        Args:
            scores: Emotion label to probability mapping
            expression_name: Optional raw expression name (for Contempt handling)
        
        Returns:
            (valence, arousal, dominance) tuple
        """
        valence_sum = 0.0
        arousal_sum = 0.0
        dominance_sum = 0.0
        
        # Iterate standard emotion labels
        for emotion_label, prob in scores.items():
            if emotion_label in self.EMOTION_TO_VAD:
                v, a, d = self.EMOTION_TO_VAD[emotion_label]
                valence_sum += v * prob
                arousal_sum += a * prob
                dominance_sum += d * prob
        
        # 特殊处理 Contempt
        # 如果主要表情是 Contempt，额外贡献其 VAD 值
        if expression_name == "Contempt":
            # Contempt 被映射到了 NEUTRAL，但我们用专门的 VAD 值替代
            # 获取 NEUTRAL 的概率作为 Contempt 的概率
            contempt_prob = scores.get(EmotionLabel.NEUTRAL, 0.0)
            if contempt_prob > 0.3:  # 只有当 Contempt 概率较高时才修正
                # 移除 NEUTRAL 的贡献
                v_n, a_n, d_n = self.EMOTION_TO_VAD[EmotionLabel.NEUTRAL]
                valence_sum -= v_n * contempt_prob
                arousal_sum -= a_n * contempt_prob
                dominance_sum -= d_n * contempt_prob
                
                # Add Contempt contribution
                v_c, a_c, d_c = self.CONTEMPT_VAD
                valence_sum += v_c * contempt_prob
                arousal_sum += a_c * contempt_prob
                dominance_sum += d_c * contempt_prob
        
        return valence_sum, arousal_sum, dominance_sum

    def _is_fresh(self, msg, max_age_s: float) -> bool:
        if msg is None:
            return False
        return (now_ts() - msg.timestamp) <= max_age_s
    
    def _fuse_modalities(self) -> EmotionState:
        """
        Fuse multimodal emotion info.
        Uses weighted average, weights based on:
        1. Preset modality weights
        2. Per-modality confidence
        """
        # Compute SER VAD
        ser_v, ser_a, ser_d = self._emotion_scores_to_vad(
            self.latest_ser.emotion.scores
        )
        ser_conf = self.latest_ser.emotion.confidence
        
        # Compute FER VAD
        fer_v, fer_a, fer_d = self._emotion_scores_to_vad(
            self.latest_fer.emotion.scores,
            expression_name=self.latest_fer_expression
        )
        fer_conf = self.latest_fer.emotion.confidence
        
        # Compute dynamic weights (confidence-adjusted)
        ser_dynamic_weight = self.ser_weight * ser_conf
        fer_dynamic_weight = self.fer_weight * fer_conf
        total_weight = ser_dynamic_weight + fer_dynamic_weight
        
        if total_weight == 0:
            return self._get_default_state()
        
        # Normalize weights
        ser_w = ser_dynamic_weight / total_weight
        fer_w = fer_dynamic_weight / total_weight
        
        # 加权融合
        fused_v = ser_v * ser_w + fer_v * fer_w
        fused_a = ser_a * ser_w + fer_a * fer_w
        fused_d = ser_d * ser_w + fer_d * fer_w
        fused_conf = ser_conf * ser_w + fer_conf * fer_w
        
        return EmotionState(
            timestamp=now_ts(),
            valence=fused_v,
            arousal=fused_a,
            dominance=fused_d,
            overall_confidence=fused_conf,
            modality_weights={
                Modality.AUDIO: ser_w,
                Modality.VISION: fer_w,
            },
        )
    
    def reset(self) -> None:
        """Reset all modality emotion data."""
        self.latest_ser = None
        self.latest_fer = None
        self.latest_fer_expression = None
        print("[EmotionFusion] Emotion state reset")
