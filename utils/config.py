from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _expand_paths(config: Dict[str, Any]) -> Dict[str, Any]:
    project_root = Path(config.get("paths", {}).get("project_root", Path(__file__).resolve().parent.parent))

    def _expand(value: Any, key_path: str = "") -> Any:
        if isinstance(value, str):
            expanded = os.path.expandvars(os.path.expanduser(value))
            # Resolve relative paths against project_root for model/path keys
            path_keys = ("models_dir", "tts_dir", "embedding", "whisper", "hubert", "fer")
            if key_path in path_keys and expanded and not os.path.isabs(expanded):
                return str((project_root / expanded).resolve())
            return expanded
        if isinstance(value, dict):
            return {k: _expand(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [_expand(v, key_path) for v in value]
        return value

    return _expand(config)


def load_config(config_path: str | None = None) -> Dict[str, Any]:
    project_root = Path(__file__).resolve().parent.parent
    defaults: Dict[str, Any] = {
        "paths": {
            "project_root": str(project_root),
            "models_dir": str(project_root / "Data" / "Models"),
            "tts_dir": str(project_root / "Data" / "Models" / "piper_semaine"),
        },
        "models": {
            "llm": str(project_root / "Data" / "Models" / "LLMs" / "qwen2.5-0.5b-instruct-q4_k_m.gguf"),
            "embedding": str(project_root / "Data" / "Models" / "LLMs" / "Qwen3-Embedding-0.6B-Q8_0.gguf"),
            "whisper": str(project_root / "Data" / "Models" / "whisper-base"),
            "hubert": str(project_root / "Data" / "Models" / "hubert-emotion"),
            "fer": str(project_root / "Data" / "Models" / "enet" / "enet_b0_8_va_mtl.onnx"),
        },
        "audio": {
            "device": "default",
            "rate": 16000,
            "channels": 1,
            "vad_threshold": 500,
            "silence_duration": 1.0,
        },
        "asr": {
            "compute_type": "int8",
            "language": "en",
            "beam_size": 5,
            "vad_filter": True,
        },
        "ser": {
            "sample_rate": 16000,
        },
        "vision": {
            "width": 1280,
            "height": 720,
            "framerate": 30,
            "face": {
                "confidence_threshold": 0.55,
            },
            "fer": {
                "ema_alpha": 0.4,
                "confirm_frames": 2,
            },
        },
        "fusion": {
            "ser_weight": 0.4,
            "fer_weight": 0.6,
            "ser_max_age_s": 3.0,
            "fer_max_age_s": 2.0,
        },
        "streaming": {
            "enabled": True,
            "pre_speech_ms": 200,
            "start_speech_ms": 200,
            "end_silence_ms": 600,
            "min_speech_ms": 300,
            "max_utterance_s": 8.0,
        },
        "llm": {
            "n_ctx": 2048,
            "n_threads": 4,
            "max_tokens": 100,
            "temperature": 0.7,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
            "prompt": {
                "system_part": "You are a friendly robot talking to a child. Start your reply with a single tone tag in brackets.\nTone options: [cheerful] [excited] [comforting] [gentle] [calm] [neutral]\nExample: [cheerful] Hello! Nice to see you!",
                "emotion_prefix": "The child feels: {emotion_desc}\n\n",
                "history_format": "{role}: {content}\n",
                "user_prefix": "Child: ",
                "assistant_prefix": "Robot: [",
            },
        },
        "tts": {
            "voice_name": "en_GB-semaine-medium",
        },
        "web": {
            "enabled": True,
            "base_url": "http://127.0.0.1:8000",
            "timeout_s": 0.8,
            "frame_fps": 30,
            "jpeg_quality": 80,
        },
    }

    cfg_path = Path(config_path) if config_path else project_root / "config.yaml"
    if not cfg_path.exists():
        return defaults

    with cfg_path.open("r", encoding="utf-8") as f:
        user_cfg = yaml.safe_load(f) or {}

    merged = _deep_merge(defaults, user_cfg)
    
    merged = _expand_paths(merged)
    return merged
