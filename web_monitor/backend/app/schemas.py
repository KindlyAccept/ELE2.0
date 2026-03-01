from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel, Field


class Offer(BaseModel):
    sdp: str
    type: str


class EmotionEvent(BaseModel):
    timestamp: float
    label: str
    confidence: float
    scores: Dict[str, float] = Field(default_factory=dict)


class FusionEvent(BaseModel):
    timestamp: float
    valence: float
    arousal: float
    dominance: float
    confidence: float
    label: Optional[str] = None


class ASREvent(BaseModel):
    timestamp: float
    text: str
    confidence: float


class DialogueEvent(BaseModel):
    timestamp: float
    role: str
    content: str
    emotion_label: Optional[str] = None
    valence: Optional[float] = None
    arousal: Optional[float] = None
    dominance: Optional[float] = None
