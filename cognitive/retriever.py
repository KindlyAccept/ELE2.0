# cognitive/retriever.py
"""Knowledge retriever with embedding-first + keyword fallback strategy."""
from __future__ import annotations

import hashlib
import time
import json
import random
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np


class KnowledgeRetriever:
    """
    Retrieves knowledge entries using embedding similarity (primary) 
    with keyword matching as fallback.
    
    Strategy:
    1. If embedding cache exists and model is available -> use embedding search
    2. If embedding fails or no results -> fallback to keyword search
    3. If both fail -> return empty (caller handles "I don't know" response)
    """

    def __init__(
        self,
        knowledge_root: Path | str,
        meta_path: str = "meta.json",
        embedding_model_path: Optional[str] = None,
    ):
        """
        Args:
            knowledge_root: Root directory containing meta.json and source files.
            meta_path: Path to meta JSON relative to knowledge_root.
            embedding_model_path: Path to GGUF embedding model (optional).
        """
        self.root = Path(knowledge_root)
        self.meta = self._load_meta(self.root / meta_path)
        self.entries: List[dict] = []
        self._load_sources()
        
        # Retrieval config
        retrieval_cfg = self.meta.get("retrieval", {})
        self._max_chunks = retrieval_cfg.get("max_chunks_per_query", 3)
        self._max_chars = retrieval_cfg.get("max_chars_per_chunk", 300)
        self._strategy = retrieval_cfg.get("strategy", "embedding")  # embedding / keyword / hybrid
        self._cache_dir = retrieval_cfg.get("cache_dir", "cache")
        
        # Embedding components (lazy loaded)
        self._embeddings: Optional[np.ndarray] = None
        self._embed_model = None
        self._embedding_model_path = embedding_model_path
        self._embedding_ready = False
        
        # Try to initialize embedding
        if self._strategy in ("embedding", "hybrid") and embedding_model_path:
            self._init_embedding(embedding_model_path)

        # Last retrieve duration in seconds (for performance evaluation; set on each retrieve())
        self.last_retrieve_duration_s: float | None = None

    def _load_meta(self, path: Path) -> dict:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _load_sources(self) -> None:
        """Load all entries from sources (order must match cache building)."""
        sources = self.meta.get("sources", [])
        for src in sources:
            file_path = self.root / src["file"]
            if not file_path.exists():
                continue
            try:
                with file_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                for entry in data.get("entries", []):
                    entry = dict(entry)
                    entry["_topic"] = src.get("topic")
                    entry["_subtopic"] = src.get("subtopic")
                    self.entries.append(entry)
            except Exception:
                continue

    def _compute_sources_hash(self) -> str:
        """Compute hash of sources for cache validation."""
        sources_str = json.dumps(self.meta.get("sources", []), sort_keys=True)
        return hashlib.md5(sources_str.encode()).hexdigest()[:16]

    def _init_embedding(self, model_path: str) -> None:
        """Initialize embedding model and load cache."""
        model_path = Path(model_path)
        cache_dir = self.root / self._cache_dir
        embeddings_path = cache_dir / "entry_embeddings.npy"
        cache_meta_path = cache_dir / "cache_meta.json"
        
        # Check if model exists
        if not model_path.exists():
            print(f"[Retriever] Embedding model not found: {model_path}")
            print("[Retriever] Will use keyword search as fallback.")
            return
        
        # Check if cache exists
        if not embeddings_path.exists() or not cache_meta_path.exists():
            print(f"[Retriever] Embedding cache not found at {cache_dir}")
            print("[Retriever] Run 'python -m utils.build_embedding_cache' to build cache.")
            print("[Retriever] Will use keyword search as fallback.")
            return
        
        # Load and validate cache
        try:
            with cache_meta_path.open("r", encoding="utf-8") as f:
                cache_meta = json.load(f)
            
            # Validate cache
            if cache_meta.get("n_entries") != len(self.entries):
                print(f"[Retriever] Cache entry count mismatch: {cache_meta.get('n_entries')} vs {len(self.entries)}")
                print("[Retriever] Please rebuild cache with 'python -m utils.build_embedding_cache'")
                return
            
            current_hash = self._compute_sources_hash()
            if cache_meta.get("sources_hash") != current_hash:
                print("[Retriever] Knowledge base sources changed since cache was built.")
                print("[Retriever] Please rebuild cache with 'python -m utils.build_embedding_cache'")
                return
            
            # Load embeddings
            self._embeddings = np.load(embeddings_path)
            if self._embeddings.shape[0] != len(self.entries):
                print("[Retriever] Embeddings shape mismatch, cache may be corrupted.")
                self._embeddings = None
                return
            
            print(f"[Retriever] Loaded embedding cache: {self._embeddings.shape}")
            
        except Exception as e:
            print(f"[Retriever] Failed to load embedding cache: {e}")
            return
        
        # Load embedding model for query encoding
        try:
            from llama_cpp import Llama
            self._embed_model = Llama(
                model_path=str(model_path),
                embedding=True,
                n_ctx=512,
                n_threads=4,
                verbose=False,
            )
            self._embedding_ready = True
            print("[Retriever] Embedding model loaded for query encoding.")
        except Exception as e:
            print(f"[Retriever] Failed to load embedding model: {e}")
            self._embeddings = None  # Can't use cache without model
            return

    def _embed_query(self, query: str) -> Optional[np.ndarray]:
        """Embed a single query string."""
        if not self._embed_model:
            return None
        try:
            result = self._embed_model.create_embedding(query)
            if isinstance(result, dict) and "data" in result:
                vec = result["data"][0]["embedding"]
            else:
                vec = result
            return np.array(vec, dtype=np.float32)
        except Exception as e:
            print(f"[Retriever] Failed to embed query: {e}")
            return None

    def _cosine_similarity(self, query_vec: np.ndarray, embeddings: np.ndarray) -> np.ndarray:
        """Compute cosine similarity between query and all embeddings."""
        # Normalize
        query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-9)
        embed_norms = embeddings / (np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-9)
        # Dot product
        similarities = np.dot(embed_norms, query_norm)
        return similarities

    def _retrieve_by_embedding(
        self,
        query: str,
        current_topic: Optional[str] = None,
        max_n: int = 3,
    ) -> List[Tuple[float, dict]]:
        """Retrieve using embedding similarity."""
        if not self._embedding_ready or self._embeddings is None:
            return []
        
        # Build query string (include topic for better matching)
        query_str = query
        if current_topic:
            query_str = f"{query} {current_topic}"
        
        # Embed query
        query_vec = self._embed_query(query_str)
        if query_vec is None:
            return []
        
        # Compute similarities
        similarities = self._cosine_similarity(query_vec, self._embeddings)
        
        # Get top-k indices
        top_indices = np.argsort(similarities)[::-1][:max_n * 2]  # Get more for filtering
        
        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            if score > 0.1:  # Minimum threshold
                results.append((score, self.entries[idx]))
            if len(results) >= max_n:
                break
        
        return results

    def _score_entry(self, entry: dict, query_lower: str, topic_lower: str) -> float:
        """Score entry using keyword matching."""
        score = 0.0
        keywords = entry.get("keywords") or []
        hints = entry.get("question_hints") or []
        text = (entry.get("text") or "").lower()

        for k in keywords:
            if k.lower() in query_lower or query_lower in k.lower():
                score += 1.0
            if k.lower() in text and k.lower() in query_lower:
                score += 0.5
        for h in hints:
            if h.lower() in query_lower or query_lower in h.lower():
                score += 1.5
            for w in h.lower().split():
                if len(w) > 2 and w in query_lower:
                    score += 0.3
        if topic_lower:
            et = (entry.get("topic") or "").lower()
            es = (entry.get("_subtopic") or "").lower()
            if topic_lower in et or topic_lower in es or et in topic_lower or es in topic_lower:
                score += 1.0
        for w in query_lower.split():
            if len(w) > 2 and w in text:
                score += 0.2
        return score

    def _retrieve_by_keyword(
        self,
        query: str,
        current_topic: Optional[str] = None,
        max_n: int = 3,
    ) -> List[Tuple[float, dict]]:
        """Retrieve using keyword matching."""
        if not query or not self.entries:
            return []
        
        query_lower = query.lower().strip()
        topic_lower = (current_topic or "").lower().strip()
        
        scored: List[Tuple[float, dict]] = []
        for e in self.entries:
            s = self._score_entry(e, query_lower, topic_lower)
            if s > 0:
                scored.append((s, e))
        
        if not scored:
            return []
        
        # Sort by score descending
        scored.sort(key=lambda x: -x[0])
        
        # Randomize ties
        i = 0
        out: List[Tuple[float, dict]] = []
        while i < len(scored):
            j = i
            while j < len(scored) and scored[j][0] == scored[i][0]:
                j += 1
            group = scored[i:j]
            random.shuffle(group)
            out.extend(group)
            i = j
        out.sort(key=lambda x: -x[0])
        
        return out[:max_n]

    def retrieve(
        self,
        query: str,
        current_topic: Optional[str] = None,
        *,
        max_chunks: Optional[int] = None,
        max_chars_per_chunk: Optional[int] = None,
    ) -> List[str]:
        """
        Retrieve relevant knowledge entries.
        
        Strategy: embedding-first with keyword fallback.
        
        Returns:
            List of entry texts (truncated if needed).
        """
        if not query or not self.entries:
            self.last_retrieve_duration_s = 0.0
            return []

        t0 = time.perf_counter()
        max_n = max_chunks if max_chunks is not None else self._max_chunks
        max_c = max_chars_per_chunk if max_chars_per_chunk is not None else self._max_chars

        results: List[Tuple[float, dict]] = []

        # Try embedding first (if available)
        if self._strategy in ("embedding", "hybrid") and self._embedding_ready:
            results = self._retrieve_by_embedding(query, current_topic, max_n)

        # Fallback to keyword if embedding failed or returned nothing
        if not results:
            results = self._retrieve_by_keyword(query, current_topic, max_n)

        # Extract and truncate texts
        output: List[str] = []
        for _, entry in results:
            text = (entry.get("text") or "").strip()
            if not text:
                continue
            if max_c and len(text) > max_c:
                text = text[: max_c - 3].rsplit(" ", 1)[0] + "..."
            output.append(text)

        self.last_retrieve_duration_s = time.perf_counter() - t0
        return output
