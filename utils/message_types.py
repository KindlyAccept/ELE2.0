# utils/message_types.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
import json
import time


# ========= 枚举类型（模态 / 情绪标签 / 触摸事件） =========

class Modality(str, Enum):
    VISION = "vision"
    AUDIO = "audio"
    TOUCH = "touch"


class EmotionLabel(str, Enum):
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    FEAR = "fear"
    DISGUST = "disgust"
    SURPRISE = "surprise"
    NEUTRAL = "neutral"


class TouchEventType(str, Enum):
    HEAD_TOUCH = "head_touch"
    HUG = "hug"
    SHAKE = "shake"
    FALL_DOWN = "fall_down"


# ========= 公共基类 =========

@dataclass
class BaseMsg:
    """所有消息都带 timestamp，单位秒（time.time()）"""
    timestamp: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaseMsg":
        return cls(**data)

    @classmethod
    def from_json(cls, s: str) -> "BaseMsg":
        data = json.loads(s)
        return cls.from_dict(data)


# ========= 通用情绪分布结构 =========

@dataclass
class EmotionScores:
    """离散情绪类别的概率分布，例如来自 FER / SER"""
    scores: Dict[EmotionLabel, float]
    confidence: float   # 模型整体置信度（0~1）


# ========= 感知层消息 =========

@dataclass
class VisionFERMsg(BaseMsg):
    """人脸表情识别输出"""
    face_id: int                          # 如果后面做人脸跟踪，可以用这个 id
    bbox: Optional[Tuple[int, int, int, int]]  # (x, y, w, h)，不需要可以设为 None
    emotion: EmotionScores
    image_id: Optional[str] = None        # 可选：这一帧在缓存中的标识


@dataclass
class ASRMsg(BaseMsg):
    """语音识别结果"""
    text: str
    lang: str               # "zh", "en" 等
    confidence: float
    utterance_id: Optional[str] = None    # 这一段语音的 id，方便和 SER 对齐


@dataclass
class SERMsg(BaseMsg):
    """语音情感识别结果（一段语音对应一次）"""
    emotion: EmotionScores
    utterance_id: Optional[str] = None    # 和 ASR 对应的 utterance_id


@dataclass
class TouchEventMsg(BaseMsg):
    """IMU / 触摸事件"""
    event_type: TouchEventType
    intensity: float          # 0~1
    raw_values: Optional[Dict[str, float]] = None  # 可选：原始 IMU 数值等


# ========= 融合层：情绪状态 =========

@dataclass
class EmotionState(BaseMsg):
    """多模态融合后的连续情绪状态（如 Valence-Arousal-Dominance）"""
    valence: float              # [-1, 1]
    arousal: float              # [0, 1] 或 [-1, 1]，看你自己定义
    dominance: float            # 可以先用 0 占位，后续再用
    overall_confidence: float   # 对当前状态的整体置信度

    # 每个模态的权重（可选），例如 {"vision": 0.7, "audio": 0.5}
    modality_weights: Optional[Dict[Modality, float]] = None

    def to_natural_language(self) -> str:
        """给 LLM 用的人类可读描述，方便直接放进 prompt"""
        if self.valence > 0.4:
            mood = "generally happy"
        elif self.valence < -0.4:
            mood = "a bit down"
        else:
            mood = "neutral"

        if self.arousal > 0.6:
            energy = "energetic and active"
        elif self.arousal < 0.3:
            energy = "quiet or tired"
        else:
            energy = "normal"

        return f"The child feels {mood} and seems {energy} (confidence {self.overall_confidence:.2f})."


# ========= 认知层：LLM 输入 / 输出 =========

@dataclass
class LLMRequest(BaseMsg):
    """传给 LLMEngine 的统一请求"""
    user_text: str
    emotion_state: EmotionState
    dialog_history: List[Dict[str, str]]  # [{"role": "user"/"robot", "content": "..."}]
    # 轻量对话状态机状态（可选，用于解决指代消解）
    current_topic: Optional[str] = None
    pending_question: Optional[str] = None
    mentioned_entities: Optional[List[str]] = None  # 提到的实体（如 "dinosaur", "toy", "rocket"）
    last_intent: Optional[str] = None  # 上次的意图（如 "ask_about", "play", "tell_story"）
    retrieved_context: Optional[List[str]] = None  # 知识库检索到的若干条 text，供写进 prompt


@dataclass
class LLMReply(BaseMsg):
    """LLMEngine 输出给上层（对话管理 / 策略）的结果"""
    reply_text: str
    # 给动作/语音使用的“情绪提示”，比如 cheerful / calm / comforting
    emotion_hint: str = "neutral"
    # 可选：高层行为建议，目前即使没有 MCU，也可以记日志用
    suggested_policy: Optional[Dict[str, Any]] = None


# ========= 动作层：TTS 请求 =========

@dataclass
class TTSRequest(BaseMsg):
    """TTS 要求合成并播放的内容"""
    text: str
    emotion_hint: str = "neutral"
    # 可选：是立即播放还是排队等上一个说完
    queue: bool = True


# ========= 工具函数：快速创建带时间戳的消息 =========

def now_ts() -> float:
    return time.time()
