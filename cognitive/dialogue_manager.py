# cognitive/dialogue_manager.py
from __future__ import annotations

from typing import List, Dict, Optional
import re
import threading

from utils.message_types import (
    EmotionState,
    LLMRequest,
    LLMReply,
    TTSRequest,
    now_ts,
)
from cognitive.llm_engine import LLMEngine
from cognitive.retriever import KnowledgeRetriever
from action.tts_engine import TTSEngine
from fusion.emotion_fusion import EmotionFusion
from utils.http_reporter import HttpReporter


class DialogueManager:
    """High-level dialogue manager with lightweight state machine."""

    # Max dialogue history turns (each turn = user + robot = 2 records)
    MAX_HISTORY_TURNS: int = 20

    def __init__(
        self, 
        llm_engine: LLMEngine, 
        tts_engine: TTSEngine,
        emotion_fusion: EmotionFusion,
        reporter: HttpReporter | None = None,
        retriever: KnowledgeRetriever | None = None,
        use_fast_reaction: bool = True,
    ):
        self.llm_engine = llm_engine
        self.tts_engine = tts_engine
        self.emotion_fusion = emotion_fusion
        self.reporter = reporter
        self.retriever = retriever
        self.use_fast_reaction = use_fast_reaction
        self.history: List[Dict[str, str]] = []

        # Serialize LLM calls: prevent voice thread and text input main thread from hitting hailo-ollama concurrently
        self._llm_lock = threading.Lock()

        # Lightweight dialogue state machine state
        self.current_topic: Optional[str] = None  # Current topic
        self.pending_question: Optional[str] = None  # Pending question to answer
        self.mentioned_entities: List[str] = []  # Mentioned entities (e.g. "dinosaur", "toy")
        self.last_intent: Optional[str] = None  # Last intent
        self.last_emotion_hint: Optional[str] = None  # TTS emotion hint from last turn

    def _get_current_emotion_state(self) -> EmotionState:
        """Get current emotion state from EmotionFusion module."""
        return self.emotion_fusion.get_emotion_state()

    def _extract_entities(self, text: str) -> List[str]:
        """Extract entities from text (simple keyword matching)."""
        # Common entity vocabulary for children
        entity_keywords = [
            "dinosaur", "dino", "toy", "toys", "robot", "rocket", "car", "ball",
            "book", "story", "game", "drawing", "picture", "friend", "mom", "dad",
            "dog", "cat", "bird", "fish", "park", "school", "home", "room"
        ]
        text_lower = text.lower()
        found = []
        for keyword in entity_keywords:
            if keyword in text_lower:
                found.append(keyword)
        return found

    def _detect_intent(self, text: str) -> Optional[str]:
        """Simple intent detection."""
        text_lower = text.lower().strip()
        
        # Asking question
        if any(text_lower.startswith(q) for q in ["what", "why", "how", "when", "where", "who", "can you", "tell me"]):
            return "ask_question"
        # Request action
        if any(text_lower.startswith(r) for r in ["let's", "let us", "play", "draw", "sing", "read"]):
            return "request_action"
        # Describe/state
        if any(text_lower.startswith(d) for d in ["i", "my", "this", "that", "it"]):
            return "describe"
        # Reference (this one, that one)
        if text_lower in ["this", "that", "it", "this one", "that one", "what about this", "what about that", "how about it"]:
            return "reference"
        
        return None

    def _resolve_reference(self, text: str) -> str:
        """Resolve coreference: convert 'what about this?' to full question."""
        text_lower = text.lower().strip()
        
        # If referential short phrase, try to recover from context
        if text_lower in ["this", "that", "it", "this one", "that one"]:
            if self.pending_question:
                # If there is a pending question, might be follow-up
                return f"Tell me more about {self.pending_question.lower()}"
            elif self.current_topic:
                # If there is current topic, follow up on topic
                return f"Tell me more about {self.current_topic.lower()}"
            elif self.mentioned_entities:
                # If entities mentioned, follow up on last one
                return f"Tell me more about {self.mentioned_entities[-1]}"
            else:
                # Cannot resolve, return original text
                return text
        
        # Variants like "what about this?", "and that?"
        if text_lower in ["what about this", "what about that", "how about it", "and this", "and that"]:
            if self.mentioned_entities:
                return f"Tell me about {self.mentioned_entities[-1]}"
            elif self.current_topic:
                return f"Tell me more about {self.current_topic.lower()}"
        
        return text

    def _update_state(self, user_text: str, assistant_reply: str) -> None:
        """Update dialogue state."""
        # Extract entities
        entities = self._extract_entities(user_text)
        if entities:
            # Deduplicate and add to list (keep last 10)
            for e in entities:
                if e not in self.mentioned_entities:
                    self.mentioned_entities.append(e)
            self.mentioned_entities = self.mentioned_entities[-10:]
        
        # Detect intent
        intent = self._detect_intent(user_text)
        if intent:
            self.last_intent = intent
        
        # Update topic (extract from user input or assistant reply)
        # Simple strategy: if entity mentioned, use it as topic
        if entities:
            self.current_topic = entities[-1]
        
        # Update pending question
        if intent == "ask_question":
            # Remove question mark, use as pending question
            self.pending_question = user_text.replace("?", "").strip()
        elif intent == "reference":
            # Referential question, recover from context
            resolved = self._resolve_reference(user_text)
            if resolved != user_text:
                self.pending_question = resolved
        else:
            # If assistant answered question, clear pending question
            if self.pending_question and "?" not in assistant_reply:
                self.pending_question = None

    def _check_fast_reaction(self, text: str, es: EmotionState) -> str | None:
        """
        Fast Reaction Layer: Intercepts specific patterns or extreme emotions
        to provide immediate feedback without calling the LLM.
        """
        text_lower = text.lower().strip()
        # Strip trailing punctuation so "Good morning!" and "Good morning" both match greeting rules
        text_normalized = text_lower.rstrip(".!?")
        
        # 1. Extreme Emotion Guardrails (use dominance to distinguish extreme sadness/fear vs anger)
        if es.valence < -0.7:
            if es.dominance < -0.2:
                return "You look really upset. Do you want to take a break?"
            return "I can see you are very upset. I am here to listen."
        if es.arousal > 0.8 and es.valence < -0.2:
            if es.dominance < -0.2:
                return "I can see you are upset. Take your time. I am here."
            return "I can see you are angry. I will listen quietly."

        # 2. Keyword Matching (Latency < 10ms)
        # Greetings (use text_normalized to match, avoid "Good morning!" going to RAG due to punctuation)
        greetings = ["hello", "hi", "hey", "good morning", "good afternoon"]
        if any(text_normalized == g or text_normalized.startswith(g + " ") for g in greetings) and len(text.split()) <= 4:
            return "Hello! It is nice to see you."

        # Self-identification
        if "your name" in text_lower:
            return "I am EmoBot, your robot friend."

        # Stop commands (use text_normalized so "bye!" etc. also match)
        if text_normalized in ["stop", "quiet", "shut up", "pause", "bye", "goodbye"]:
            return "Okay, goodbye for now."

        # Gratitude
        if "thank you" in text_lower or "thanks" in text_lower:
            return "You are welcome!"

        return None

    def _trim_history(self) -> None:
        """Trim dialogue history to keep last MAX_HISTORY_TURNS turns (each turn = user+robot = 2 records)."""
        max_records = self.MAX_HISTORY_TURNS * 2
        if len(self.history) > max_records:
            self.history = self.history[-max_records:]

    def process_user_text(self, user_text: str) -> str:
        """Main entry point: handle one user utterance.

        Uses a lock to serialise calls: the streaming-voice thread and the
        text-input main thread must not reach hailo-ollama concurrently, as
        simultaneous requests cause it to reload the model and time out.
        If the lock is already held (LLM busy), the new request is dropped
        and a brief busy message is returned instead of queuing indefinitely.
        """
        if not self._llm_lock.acquire(blocking=False):
            print(f"[DialogueManager] LLM busy, dropping: '{user_text}'")
            return ""

        try:
            return self._process_user_text_locked(user_text)
        finally:
            self._llm_lock.release()

    def _process_user_text_locked(self, user_text: str) -> str:
        """Actual processing, called only when _llm_lock is held."""
        # Clear per-turn timing tags so performance scripts can tell if RAG/LLM were used this turn
        if self.retriever is not None:
            self.retriever.last_retrieve_duration_s = None
        self.llm_engine.last_generate_duration_s = None

        # 1) Resolve coreference
        resolved_text = self._resolve_reference(user_text)
        if resolved_text != user_text:
            print(f"[StateMachine] Resolved reference: '{user_text}' -> '{resolved_text}'")
            user_text = resolved_text
        
        # 2) Update history & trim to prevent unbounded growth
        self.history.append({"role": "user", "content": user_text})
        self._trim_history()

        # 3) Get current emotion state from fusion module
        emotion_state = self._get_current_emotion_state()

        if self.reporter is not None:
            self.reporter.report_dialogue("user", user_text, emotion_state)

        # === FAST REACTION LAYER START ===
        fast_reply = self._check_fast_reaction(user_text, emotion_state) if self.use_fast_reaction else None
        if fast_reply:
            print(f"[FastReaction] Hit: {fast_reply}")
            
            # a) Update history
            self.history.append({"role": "robot", "content": fast_reply})
            
            # b) Update state
            self._update_state(user_text, fast_reply)
            
            # c) Report
            if self.reporter is not None:
                self.reporter.report_dialogue("robot", fast_reply, emotion_state)
            
            # d) Determine emotion hint for TTS (VAD: use dominance to distinguish comforting vs calm when negative)
            hint = "neutral"
            if emotion_state.valence > 0.3:
                hint = "cheerful"
            elif emotion_state.valence < -0.3:
                hint = "comforting" 
                if emotion_state.dominance < 0.2:
                    hint = "calm"
            
            self.last_emotion_hint = hint

            # e) Call TTS
            tts_req = TTSRequest(
                timestamp=now_ts(),
                text=fast_reply,
                emotion_hint=hint,
                queue=True,
            )
            self.tts_engine.speak(tts_req)
            
            return fast_reply
        # === FAST REACTION LAYER END ===

        # 4) Retrieve from knowledge base (RAG)
        retrieved: List[str] = []
        if self.retriever:
            retrieved = self.retriever.retrieve(
                user_text,
                current_topic=self.current_topic,
            )

        # 5) Build LLM request with state information
        req = LLMRequest(
            timestamp=now_ts(),
            user_text=user_text,
            emotion_state=emotion_state,
            dialog_history=self.history,
            current_topic=self.current_topic,
            pending_question=self.pending_question,
            mentioned_entities=self.mentioned_entities if self.mentioned_entities else None,
            last_intent=self.last_intent,
            retrieved_context=retrieved if retrieved else None,
        )

        # 6) Call LLM
        reply: LLMReply = self.llm_engine.generate(req)
        self.last_emotion_hint = reply.emotion_hint

        # 7) Save robot reply into history
        self.history.append({"role": "robot", "content": reply.reply_text})
        
        # 8) Update state after getting reply
        self._update_state(user_text, reply.reply_text)

        if self.reporter is not None:
            self.reporter.report_dialogue("robot", reply.reply_text, emotion_state)

        # 9) Call TTS
        tts_req = TTSRequest(
            timestamp=now_ts(),
            text=reply.reply_text,
            emotion_hint=reply.emotion_hint,
            queue=True,
        )
        self.tts_engine.speak(tts_req)

        return reply.reply_text
