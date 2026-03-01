# action/tts_engine.py
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
import threading
import time
import re
from utils.message_types import TTSRequest


class TTSEngine:
    """Text-to-speech engine using Piper with EN_GB semaine voice."""

    def __init__(self, voice_name: str = "en_GB-semaine-medium"):
        """
        Initialize Piper TTS engine.
        
        Args:
            voice_name: Piper voice model name (default: EN_GB semaine)
        """
        self.voice_name = voice_name
        
        # Set model storage directory (relative to project root)
        project_root = Path(__file__).parent.parent
        self.model_dir = project_root / "Data" / "Models" / "piper_semaine"
        
        # Model file paths
        self.model_path = self.model_dir / f"{voice_name}.onnx"
        self.config_path = self.model_dir / f"{voice_name}.onnx.json"
        
        # Verify model files exist
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Voice model not found at {self.model_path}. "
                f"Please ensure the model files are in {self.model_dir}"
            )
        
        print(f"[TTS] Loaded voice model: {self.model_path}")
        
        # Initialize audio player
        try:
            import pygame
            pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
            self.player = "pygame"
            self.pygame = pygame
            print(f"[TTS] Initialized with pygame audio backend")
        except ImportError:
            # Fallback: use system aplay (built-in on Raspberry Pi)
            self.player = "aplay"
            print(f"[TTS] Initialized with aplay audio backend")

        self._stop_event = threading.Event()
        self._play_lock = threading.Lock()
        self._play_thread: threading.Thread | None = None
        self._aplay_proc: subprocess.Popen | None = None
        
        # Volume setting (0-100, default 50) and cache to avoid reading file on every play
        self._volume = 50
        self._volume_last_load: float = 0.0
        self._VOLUME_CACHE_SECONDS: float = 1.0
        self._load_volume()

    def _clean_text(self, text: str) -> str:
        """
        Clean text: remove special characters and emoji.
        
        Filters:
        - Emoji symbols
        - Control characters (except newline, tab, etc.)
        - Special Unicode characters
        - Excess whitespace
        - [word] form emotion tags (remove from start/middle/end to avoid TTS reading them)
        
        Args:
            text: Raw text
        
        Returns:
            Cleaned text
        """
        if not text:
            return ""
        
        # 1. Remove emoji (Unicode ranges)
        # Emoji ranges: U+1F300-U+1F9FF, U+1F600-U+1F64F, U+1F680-U+1F6FF, etc.
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # Emoticons
            "\U0001F300-\U0001F5FF"  # Symbols and pictographs
            "\U0001F680-\U0001F6FF"  # Transport and map symbols
            "\U0001F1E0-\U0001F1FF"  # Flags
            "\U00002702-\U000027B0"  # Misc symbols
            "\U000024C2-\U0001F251"  # Enclosed chars
            "\U0001F900-\U0001F9FF"  # Supplemental symbols
            "\U0001FA00-\U0001FA6F"  # Extended symbols
            "\U0001FA70-\U0001FAFF"  # Extended symbols
            "\U00002600-\U000026FF"  # Misc symbols
            "\U00002700-\U000027BF"  # Dingbats
            "]+",
            flags=re.UNICODE
        )
        text = emoji_pattern.sub('', text)
        
        # 2. Remove control chars (keep newline, tab, carriage return)
        # Keep: \n (0x0A), \r (0x0D), \t (0x09)
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]', '', text)
        
        # 3. Remove other special Unicode (zero-width, invisible, etc.)
        # Remove zero-width space, non-breaking space, zero-width hyphen, etc.
        text = re.sub(r'[\u200B-\u200D\uFEFF\u2060]', '', text)
        
        # 4. 规范化空白字符（多个空格合并为一个，保留换行）
        text = re.sub(r'[ \t]+', ' ', text)  # 多个空格/制表符合并
        text = re.sub(r'\n\s*\n', '\n\n', text)  # 多个换行合并为两个
        
        # 5. Remove all [word] form emotion tags (start/middle/end), avoid TTS reading them
        text = re.sub(r'\[\w+\]\s*', '', text)
        text = re.sub(r'[ \t]+', ' ', text)  # Merge spaces after tag removal
        
        # 6. Strip leading/trailing whitespace
        text = text.strip()
        
        # 7. If text empty, return default prompt
        if not text:
            return "Hello."
        
        return text

    def speak(self, req: TTSRequest):
        """
        Synthesize and play speech.
        
        Args:
            req: TTSRequest with text and emotion hint
        """
        # Clean text: remove special chars and emoji
        cleaned_text = self._clean_text(req.text)
        
        # Log if text changed after cleaning
        if cleaned_text != req.text:
            print(f"[TTS] Text cleaned: '{req.text}' -> '{cleaned_text}'")
        
        print(f"[TTS - {req.emotion_hint}] {cleaned_text}")

        # Always interrupt current playback for responsiveness.
        self.stop()

        def _worker():
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
                    tmp_path = tmp_file.name

                params = self._get_emotion_params(req.emotion_hint)
                self._synthesize(cleaned_text, tmp_path, params)  # Use cleaned text
                if not self._stop_event.is_set():
                    self._play_audio(tmp_path)

            except Exception as e:
                print(f"[TTS Error] {e}")
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        self._stop_event.clear()
        self._play_thread = threading.Thread(target=_worker, daemon=True)
        self._play_thread.start()

    def _get_emotion_params(self, emotion_hint: str) -> dict:
        """
        根据情感提示返回 Piper 合成参数
        
        Args:
            emotion_hint: 情感提示，支持以下类型：
                - cheerful: 欢快愉悦
                - excited: 兴奋激动
                - playful: 顽皮好玩
                - encouraging: 鼓励支持
                - comforting: 安慰抚慰
                - gentle: 温柔体贴
                - calm: 平静安详
                - serious: 认真严肃
                - sad: 悲伤低落
                - neutral: 中性正常
                
        Returns:
            包含 Piper 参数的字典
        """
        emotion_params = {
            # ===== Active/positive =====
            "cheerful": {
                "length_scale": 0.85,    # 15% faster
                "noise_scale": 0.667,    # Standard variation
                "noise_w": 0.8,          # Higher pitch variation (livelier)
            },
            "excited": {
                "length_scale": 0.75,    # 25% faster
                "noise_scale": 0.8,      # Larger variation
                "noise_w": 0.9,          # Very high pitch variation (very lively)
            },
            "playful": {
                "length_scale": 0.8,     # 20% faster
                "noise_scale": 0.75,     # Larger variation (playful)
                "noise_w": 0.85,         # High pitch variation (playful)
            },
            "encouraging": {
                "length_scale": 0.9,     # 10% faster
                "noise_scale": 0.7,      # Slightly higher variation (positive)
                "noise_w": 0.75,         # Slightly higher pitch (encouraging)
            },
            
            # ===== 平静温和类 =====
            "comforting": {
                "length_scale": 1.15,    # 15% slower
                "noise_scale": 0.333,    # Smoother speech
                "noise_w": 0.5,          # Less pitch variation (gentler)
            },
            "gentle": {
                "length_scale": 1.1,     # 10% slower
                "noise_scale": 0.4,      # Smooth (gentle)
                "noise_w": 0.55,         # Less pitch variation (soft)
            },
            "calm": {
                "length_scale": 1.2,     # 20% slower
                "noise_scale": 0.35,     # Very smooth
                "noise_w": 0.45,         # Very little pitch variation (calm)
            },
            
            # ===== Neutral/other =====
            "neutral": {
                "length_scale": 1.0,     # Normal speed
                "noise_scale": 0.667,    # Standard variation
                "noise_w": 0.667,        # Standard pitch
            },
            "serious": {
                "length_scale": 1.05,    # 5% slower
                "noise_scale": 0.5,      # Less variation (serious)
                "noise_w": 0.6,          # Less pitch variation (earnest)
            },
            
            # ===== Low/sad =====
            "sad": {
                "length_scale": 1.3,     # 语速很慢 30%
                "noise_scale": 0.25,     # 很少变化（低沉）
                "noise_w": 0.35,         # 很少音调变化（悲伤）
            },
        }
        
        return emotion_params.get(emotion_hint, emotion_params["neutral"])

    def _synthesize(self, text: str, output_path: str, params: dict):
        """
        Synthesize speech using Piper CLI.
        
        Args:
            text: Text to synthesize
            output_path: Output audio file path
            params: Piper synthesis params
        """
        cmd = [
            "piper",
            "--model", str(self.model_path),
            "--output_file", output_path,
            "--length_scale", str(params["length_scale"]),
            "--noise_scale", str(params["noise_scale"]),
            "--noise_w", str(params["noise_w"]),
        ]
        
        # Pass text via stdin
        result = subprocess.run(
            cmd, 
            input=text.encode('utf-8'), 
            capture_output=True,
            check=True
        )

    def _load_volume(self) -> None:
        """从文件加载音量设置并更新缓存时间戳。"""
        try:
            project_root = Path(__file__).parent.parent
            volume_file = project_root / "web_monitor" / "backend" / "data" / "audio_volume.txt"
            if volume_file.exists():
                with open(volume_file, "r") as f:
                    volume_str = f.read().strip()
                    volume = int(volume_str)
                    self._volume = max(0, min(100, volume))
                    print(f"[TTS] Loaded volume setting: {self._volume}%")
        except Exception as e:
            print(f"[TTS] Failed to load volume setting: {e}, using default 50%")
        self._volume_last_load = time.time()

    def _get_volume(self) -> float:
        """Get current volume (0.0-1.0). Uses cache, re-reads file only when > _VOLUME_CACHE_SECONDS since last load."""
        if time.time() - self._volume_last_load > self._VOLUME_CACHE_SECONDS:
            self._load_volume()
        return self._volume / 100.0
    
    def _play_audio(self, audio_path: str):
        """
        播放音频文件
        
        Args:
            audio_path: 音频文件路径
        """
        volume = self._get_volume()
        
        if self.player == "pygame":
            # Use pygame to play
            self.pygame.mixer.music.load(audio_path)
            # Set volume (0.0-1.0)
            self.pygame.mixer.music.set_volume(volume)
            self.pygame.mixer.music.play()
            
            # Wait for playback to finish
            while self.pygame.mixer.music.get_busy():
                if self._stop_event.is_set():
                    self.pygame.mixer.music.stop()
                    break
                self.pygame.time.Clock().tick(10)
        else:
            # 使用 aplay（树莓派系统自带）
            # aplay 不支持直接设置音量，需要通过 ALSA mixer 控制
            # 这里我们使用 amixer 来设置系统音量
            # 注意：这会影响系统全局音量，不是理想的方案
            # 更好的方案是使用 sox 或 ffmpeg 在播放前调整音频音量
            try:
                # Compute ALSA volume (0-100 to 0%-100%)
                volume_percent = int(volume * 100)
                # Set master volume (may need adjustment for hardware)
                subprocess.run(
                    ["amixer", "set", "Master", f"{volume_percent}%"],
                    capture_output=True,
                    check=False
                )
            except Exception as e:
                print(f"[TTS] Warning: Failed to set ALSA volume: {e}")
            
            with self._play_lock:
                self._aplay_proc = subprocess.Popen(["aplay", "-q", audio_path])
            while True:
                if self._stop_event.is_set():
                    with self._play_lock:
                        if self._aplay_proc and self._aplay_proc.poll() is None:
                            self._aplay_proc.terminate()
                    break
                with self._play_lock:
                    proc = self._aplay_proc
                if proc is None or proc.poll() is not None:
                    break
                time.sleep(0.05)

    def is_speaking(self) -> bool:
        """Check if audio is currently playing."""
        if self.player == "pygame":
            try:
                return self.pygame.mixer.music.get_busy()
            except Exception:
                return False
        else:
            with self._play_lock:
                return self._aplay_proc is not None and self._aplay_proc.poll() is None

    def stop(self):
        """Interrupt current playback."""
        self._stop_event.set()
        if self.player == "pygame":
            try:
                self.pygame.mixer.music.stop()
            except Exception:
                pass
        else:
            with self._play_lock:
                if self._aplay_proc and self._aplay_proc.poll() is None:
                    self._aplay_proc.terminate()

    def shutdown(self):
        """Release audio backend resources."""
        self.stop()
        if self.player == "pygame":
            try:
                self.pygame.mixer.music.stop()
                self.pygame.mixer.quit()
            except Exception:
                pass