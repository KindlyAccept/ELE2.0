# cognitive/llm_engine.py
from __future__ import annotations

import random
import re
import json
import threading
import time
from pathlib import Path
from typing import List, Tuple, Optional
import requests

from utils.message_types import EmotionState, LLMRequest, LLMReply, now_ts


_FALLBACK_REPLIES = [
    "That is a great question! Can you tell me more about it?",
    "Hmm, I am still thinking. What do you think?",
    "I am not sure, but I would love to explore that with you!",
    "That sounds interesting! Can you say more?",
    "Let me think... what made you curious about that?",
    "I am learning new things every day! Tell me what you know.",
    "Ooh, that is a tricky one! What is your idea?",
    "I am not certain, but let us figure it out together!",
]


class LLMEngine:
    """Wrapper around hailo-ollama HTTP API (Ollama-compatible /api/chat)."""

    VALID_EMOTIONS = {
        "cheerful", "excited", "playful", "encouraging",
        "comforting", "gentle", "calm", "serious", "sad", "neutral"
    }

    def __init__(
        self,
        model_path: str,          # Model name, e.g. "llama3.2:3b"
        n_ctx: int = 2048,        # kept for API compat
        n_threads: int = 4,       # kept for API compat
        max_tokens: int = 100,
        temperature: float = 0.7,
        top_p: float = 0.8,
        top_k: int = 20,
        repeat_penalty: float = 1.1,
        prompt_config: dict | None = None,
        api_url: str = "http://localhost:8000",
    ):
        self.model_name = model_path
        self.api_url = api_url.rstrip("/")
        self._session = requests.Session()

        print(f"[LLMEngine] Connecting to hailo-ollama: {self.api_url}, model: {self.model_name}")

        # Thread lock: protect config hot-reload and LLM inference concurrency
        self._config_lock = threading.Lock()
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.frequency_penalty = repeat_penalty

        # Load User Profile (Light-RAG)
        self.profile = {}
        try:
            profile_path = Path("Data/user_profile.json")
            if profile_path.exists():
                with open(profile_path, "r", encoding="utf-8") as f:
                    self.profile = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load user profile: {e}")

        if prompt_config is None:
            prompt_config = {}
        self.prompt_system_part = prompt_config.get(
            "system_part",
            "You are a friendly robot talking to a child. "
            "Start your reply with a single tone tag in brackets.\n"
            "Tone options: [cheerful] [excited] [comforting] [gentle] [calm] [neutral]"
        )
        self.prompt_emotion_prefix = prompt_config.get(
            "emotion_prefix",
            "The child feels: {emotion_desc}\n\n"
        )
        self.prompt_user_prefix = prompt_config.get("user_prefix", "Child: ")
        self.prompt_assistant_prefix = prompt_config.get("assistant_prefix", "Robot: [")

        # Last generate duration in seconds (for performance evaluation)
        self.last_generate_duration_s: float | None = None

        # Test connectivity
        try:
            resp = self._session.get(f"{self.api_url}/api/version", timeout=5)
            resp.raise_for_status()
            print(f"[LLMEngine] hailo-ollama ready: {resp.json()}")
        except Exception as e:
            print(f"[LLMEngine] Warning: Cannot reach hailo-ollama at {self.api_url}: {e}")

    def close(self):
        """Close HTTP session. Server lifecycle is managed externally."""
        self._session.close()

    def update_config(
        self,
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        repeat_penalty: float | None = None,
        prompt_config: dict | None = None,
    ) -> None:
        """Dynamically update LLM config (no model reload needed)."""
        with self._config_lock:
            if max_tokens is not None:
                self.max_tokens = max_tokens
            if temperature is not None:
                self.temperature = temperature
            if top_p is not None:
                self.top_p = top_p
            if top_k is not None:
                self.top_k = top_k
            if repeat_penalty is not None:
                self.frequency_penalty = repeat_penalty

            if prompt_config is not None:
                if "system_part" in prompt_config:
                    self.prompt_system_part = prompt_config["system_part"]
                if "emotion_prefix" in prompt_config:
                    self.prompt_emotion_prefix = prompt_config["emotion_prefix"]
                if "user_prefix" in prompt_config:
                    self.prompt_user_prefix = prompt_config["user_prefix"]
                if "assistant_prefix" in prompt_config:
                    self.prompt_assistant_prefix = prompt_config["assistant_prefix"]

    def _get_emotion_strategy(self, es: EmotionState) -> str:
        """Generate dynamic strategy from user emotion state (Valence, Arousal, Dominance)."""
        if es.valence < -0.2:
            if es.dominance < -0.2:
                return "User is feeling negative and low in control (e.g. fearful/sad). STRATEGY: Be empathetic and comforting. Reassure them."
            if es.dominance > 0.3:
                return "User is upset and assertive (e.g. angry). STRATEGY: Acknowledge their feelings. Stay calm and respectful. Do NOT give advice immediately."
            return "User is feeling negative. STRATEGY: Be empathetic and comforting. Do NOT give advice immediately."

        if es.valence > 0.2:
            interests = ", ".join(self.profile.get("user", {}).get("interests", []))
            return f"User is happy. STRATEGY: Share their joy. Mention interests like {interests} if relevant."

        if es.arousal > 0.6:
            if es.dominance < -0.2:
                return "User is highly aroused but low dominance (e.g. fearful). STRATEGY: Be calming and reassuring. Keep sentences short."
            if es.dominance > 0.4:
                return "User is excited/assertive (e.g. angry). STRATEGY: Keep sentences short. Stay calm."
            return "User is excited/aroused. STRATEGY: Keep sentences short. Match their energy."

        return "User is neutral. STRATEGY: Propose a topic to talk about based on their interests."

    def _build_messages(self, req: LLMRequest) -> list:
        """
        构建 Ollama /api/chat 的 messages 列表。

        格式：[{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}, ...]
        系统提示包含角色定义、情感上下文、策略和状态机信息。
        对话历史最近 2 条（1 轮），当前用户输入作为最后一条 user 消息。
        """
        robot_name = self.profile.get("robot", {}).get("name", "Robot")

        # 1. Emotion context
        es = req.emotion_state
        emotion_desc = es.to_natural_language()
        if es.dominance > 0.3:
            emotion_desc += " The child seems in control or assertive."
        elif es.dominance < -0.3:
            emotion_desc += " The child seems less in control or submissive."

        strategy = self._get_emotion_strategy(es)

        # 2. State machine context
        state_lines = []
        if req.current_topic:
            state_lines.append(f"Current topic: {req.current_topic}")
        if req.pending_question:
            state_lines.append(f"Pending question: {req.pending_question}")
        if req.mentioned_entities:
            state_lines.append(f"Recently mentioned: {', '.join(req.mentioned_entities[-3:])}")
        if req.last_intent:
            state_lines.append(f"Last intent: {req.last_intent}")

        # 3. Assemble system content
        system_content = (
            f"{self.prompt_system_part}\n\n"
            f"{self.prompt_emotion_prefix.format(emotion_desc=emotion_desc)}"
            f"{strategy}"
        )
        if state_lines:
            system_content += "\n\nContext:\n" + "\n".join(state_lines)
        if req.retrieved_context:
            system_content += "\n\nSome helpful information (use if relevant):\n"
            for line in req.retrieved_context:
                system_content += f"- {line}\n"

        # 4. Assemble message list
        messages = [{"role": "system", "content": system_content}]

        # Dialogue history (last 2 messages = last 1 turn)
        # Note: dialogue_manager appends current user_text to history before calling LLM,
        # so use [:-1] to exclude the last one (current turn's user message) to avoid duplication.
        history_ctx = req.dialog_history[:-1] if req.dialog_history else []
        for turn in history_ctx[-2:]:
            role = "user" if turn["role"] == "user" else "assistant"
            messages.append({"role": role, "content": turn["content"]})

        # Current user input
        messages.append({"role": "user", "content": req.user_text})

        return messages

    def _parse_response(self, raw_text: str) -> Tuple[Optional[str], str]:
        """
        Parse LLM response text, extract emotion tag and reply content.
        With chat format, model outputs [emotion] text (with full brackets).
        """
        raw_text = raw_text.strip()

        # Primary format: [emotion] text
        match = re.match(r'\[(\w+)\]\s*(.+)', raw_text, re.DOTALL)
        if match:
            emotion = match.group(1).lower()
            reply_text = match.group(2).strip()
            if emotion in self.VALID_EMOTIONS:
                return emotion, reply_text

        # Legacy format: emotion] text (no leading [, legacy)
        match = re.match(r'(\w+)\]\s*(.+)', raw_text, re.DOTALL)
        if match:
            emotion = match.group(1).lower()
            reply_text = match.group(2).strip()
            if emotion in self.VALID_EMOTIONS:
                return emotion, reply_text

        return None, raw_text

    def _fallback_emotion(self, es: EmotionState) -> str:
        """Infer emotion from VAD state when LLM output has no parseable emotion tag."""
        if es.valence > 0.5 and es.arousal > 0.5:
            return "excited"
        if es.valence > 0.3:
            return "cheerful"
        if es.valence < -0.5:
            return "comforting" if es.dominance < 0.2 else "calm"
        if es.valence < -0.2:
            return "gentle" if es.dominance < 0.2 else "calm"
        if es.arousal < 0.3:
            return "calm"
        return "neutral"

    def _count_words(self, text: str) -> int:
        return len(text.split())

    def _split_into_sentences(self, text: str) -> List[str]:
        sentences = re.split(r'[,.!?]+', text)
        return [s.strip() for s in sentences if s.strip()]

    def _has_question(self, text: str) -> bool:
        return '?' in text

    def _apply_child_friendly_constraints(self, text: str) -> str:
        """Apply child-friendly constraints: 2-4 sentences, short, total length <= 300 chars."""
        if not text:
            return "Hello! How can I help you?"

        sentences = self._split_into_sentences(text)
        if not sentences:
            return text

        valid_sentences = []
        for sent in sentences:
            word_count = self._count_words(sent)
            if word_count > 30:
                words = sent.split()[:30]
                sent = " ".join(words) + "..."
            valid_sentences.append(sent)

        if len(valid_sentences) > 4:
            valid_sentences = valid_sentences[:4]
        elif len(valid_sentences) < 2 and len(valid_sentences) > 0:
            if not any(q in valid_sentences[0].lower() for q in ["how", "what", "why", "do you"]):
                valid_sentences.append("That's interesting!")

        reply_text = ". ".join(valid_sentences)
        if not reply_text.endswith(('.', '!', '?')):
            reply_text += "."

        if len(reply_text) > 300:
            if '?' in reply_text:
                parts = reply_text.rsplit('?', 1)
                if len(parts) == 2:
                    reply_text = parts[0][:250] + "?" + parts[1]
            else:
                reply_text = reply_text[:300]

        return reply_text.strip()

    def generate(self, req: LLMRequest) -> LLMReply:
        """
        主接口：从 LLMRequest 生成 LLMReply。

        通过 hailo-ollama /api/chat HTTP 接口调用模型。
        """
        with self._config_lock:
            messages = self._build_messages(req)
            max_tokens = self.max_tokens
            temperature = self.temperature
            top_p = self.top_p
            top_k = self.top_k
            frequency_penalty = self.frequency_penalty

        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "top_k": top_k,
                "repeat_penalty": frequency_penalty,
                "num_predict": max_tokens,
            },
        }

        t0 = time.perf_counter()
        try:
            resp = self._session.post(
                f"{self.api_url}/api/chat",
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            raw_reply = data.get("message", {}).get("content", "").strip()
        except requests.Timeout:
            print("[LLMEngine] Request timed out")
            raw_reply = ""
        except requests.RequestException as e:
            print(f"[LLMEngine] API error: {e}")
            raw_reply = ""

        self.last_generate_duration_s = time.perf_counter() - t0

        if not raw_reply:
            return LLMReply(
                timestamp=now_ts(),
                reply_text=random.choice(_FALLBACK_REPLIES),
                emotion_hint=self._fallback_emotion(req.emotion_state),
                suggested_policy=None,
            )

        # Remove chain-of-thought thinking blocks (DeepSeek-R1 etc.)
        raw_reply = re.sub(r'<think>.*?</think>', '', raw_reply, flags=re.DOTALL).strip()

        emotion_hint, reply_text = self._parse_response(raw_reply)

        if emotion_hint is None:
            emotion_hint = self._fallback_emotion(req.emotion_state)
        elif req.emotion_state.valence < -0.2 and emotion_hint in (
            "cheerful", "excited", "playful",
        ):
            emotion_hint = self._fallback_emotion(req.emotion_state)

        if reply_text.lower().startswith("robot:"):
            reply_text = reply_text[len("robot:"):].strip()

        if len(reply_text) >= 2 and reply_text[0] == '"' and reply_text[-1] == '"':
            reply_text = reply_text[1:-1].strip()

        reply_text = re.sub(r'\([^)]*\)', '', reply_text)
        reply_text = reply_text.strip()

        reply_text = self._apply_child_friendly_constraints(reply_text)

        return LLMReply(
            timestamp=now_ts(),
            reply_text=reply_text,
            emotion_hint=emotion_hint,
            suggested_policy=None,
        )
