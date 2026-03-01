#!/usr/bin/env python3
# utils/build_embedding_cache.py
"""
预计算知识库条目的 Embedding 向量，存储到 knowledge/cache/ 目录。

用法:
    python -m utils.build_embedding_cache [--config CONFIG_PATH]

或直接运行:
    python utils/build_embedding_cache.py

该脚本会：
1. 从 config.yaml 读取 embedding 模型路径
2. 从 knowledge/meta.json 加载所有条目
3. 使用 llama-cpp-python 对每条条目生成向量
4. 将向量矩阵保存到 knowledge/cache/entry_embeddings.npy
5. 将元信息保存到 knowledge/cache/cache_meta.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import List

import numpy as np

# 添加项目根目录到 path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from utils.config import load_config


def compute_sources_hash(meta: dict) -> str:
    """计算 sources 列表的 hash，用于检测知识库变更"""
    sources_str = json.dumps(meta.get("sources", []), sort_keys=True)
    return hashlib.md5(sources_str.encode()).hexdigest()[:16]


def load_entries(knowledge_root: Path, meta: dict) -> List[dict]:
    """按 meta.json 的 sources 顺序加载所有条目（与 retriever 一致）"""
    entries = []
    sources = meta.get("sources", [])
    for src in sources:
        file_path = knowledge_root / src["file"]
        if not file_path.exists():
            print(f"  Warning: {file_path} not found, skipping...")
            continue
        try:
            with file_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            for entry in data.get("entries", []):
                entry = dict(entry)
                entry["_topic"] = src.get("topic")
                entry["_subtopic"] = src.get("subtopic")
                entries.append(entry)
        except Exception as e:
            print(f"  Warning: Failed to load {file_path}: {e}")
            continue
    return entries


def entry_to_text(entry: dict) -> str:
    """将条目转换为待编码的文本（与检索目标一致）"""
    text = entry.get("text", "")
    keywords = entry.get("keywords") or []
    hints = entry.get("question_hints") or []
    parts = [text]
    if keywords:
        parts.append(" ".join(keywords))
    if hints:
        parts.append(" ".join(hints))
    return " ".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Build embedding cache for knowledge base")
    parser.add_argument("--config", type=str, default=None, help="Path to config.yaml")
    parser.add_argument("--embedding-model", type=str, default=None, 
                        help="Override embedding model path from config")
    parser.add_argument("--knowledge-root", type=str, default=None,
                        help="Override knowledge root directory")
    args = parser.parse_args()

    # 加载配置
    cfg = load_config(args.config)
    
    # 确定路径
    embedding_model_path = args.embedding_model or cfg.get("models", {}).get("embedding", "")
    knowledge_root = Path(args.knowledge_root) if args.knowledge_root else (project_root / "knowledge")
    
    if not embedding_model_path:
        print("Error: No embedding model path specified in config or arguments.")
        print("Please set 'models.embedding' in config.yaml or use --embedding-model")
        sys.exit(1)
    
    embedding_model_path = Path(embedding_model_path)
    if not embedding_model_path.exists():
        print(f"Error: Embedding model not found: {embedding_model_path}")
        print("Please download the model first.")
        sys.exit(1)
    
    meta_path = knowledge_root / "meta.json"
    if not meta_path.exists():
        print(f"Error: meta.json not found at {meta_path}")
        sys.exit(1)
    
    print("=" * 60)
    print("Building Embedding Cache for Knowledge Base")
    print("=" * 60)
    print(f"  Embedding model: {embedding_model_path}")
    print(f"  Knowledge root:  {knowledge_root}")
    
    # 加载 meta.json
    with meta_path.open("r", encoding="utf-8") as f:
        meta = json.load(f)
    
    # 加载所有条目
    print("\n[1/4] Loading knowledge entries...")
    entries = load_entries(knowledge_root, meta)
    print(f"  Loaded {len(entries)} entries")
    
    if not entries:
        print("Error: No entries found in knowledge base.")
        sys.exit(1)
    
    # 准备文本
    print("\n[2/4] Preparing texts for embedding...")
    texts = [entry_to_text(e) for e in entries]
    print(f"  Prepared {len(texts)} texts")
    
    # 加载 embedding 模型
    print("\n[3/4] Loading embedding model (this may take a moment)...")
    try:
        from llama_cpp import Llama
    except ImportError:
        print("Error: llama-cpp-python not installed.")
        print("Please install with: pip install llama-cpp-python")
        sys.exit(1)
    
    try:
        # embedding=True 启用 embedding 模式
        # n_ctx 设小一点节省内存，条目文本一般不长
        llm = Llama(
            model_path=str(embedding_model_path),
            embedding=True,
            n_ctx=512,
            n_threads=4,
            verbose=False,
        )
        print("  Model loaded successfully")
    except Exception as e:
        print(f"Error: Failed to load embedding model: {e}")
        sys.exit(1)
    
    # 生成向量
    print("\n[4/4] Generating embeddings...")
    embeddings = []
    for i, text in enumerate(texts):
        if (i + 1) % 20 == 0 or i == 0 or i == len(texts) - 1:
            print(f"  Processing {i + 1}/{len(texts)}...")
        try:
            result = llm.create_embedding(text)
            # llama-cpp-python 返回格式：{"data": [{"embedding": [...], ...}], ...}
            if isinstance(result, dict) and "data" in result:
                vec = result["data"][0]["embedding"]
            else:
                # 可能是直接返回向量
                vec = result
            embeddings.append(vec)
        except Exception as e:
            print(f"  Warning: Failed to embed entry {i}: {e}")
            # 用零向量占位，保持索引对齐
            if embeddings:
                embeddings.append([0.0] * len(embeddings[0]))
            else:
                print("Error: First entry failed, cannot continue.")
                sys.exit(1)
    
    # 转换为 numpy 数组
    embeddings_np = np.array(embeddings, dtype=np.float32)
    print(f"  Generated embeddings: shape {embeddings_np.shape}")
    
    # 保存
    cache_dir_name = meta.get("retrieval", {}).get("cache_dir", "cache")
    cache_dir = knowledge_root / cache_dir_name
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    embeddings_path = cache_dir / "entry_embeddings.npy"
    np.save(embeddings_path, embeddings_np)
    print(f"\n  Saved embeddings to: {embeddings_path}")
    
    # 保存元信息
    cache_meta = {
        "embedding_model_path": str(embedding_model_path),
        "embedding_dim": int(embeddings_np.shape[1]),
        "n_entries": len(entries),
        "sources_hash": compute_sources_hash(meta),
        "version": meta.get("version", "1.0"),
    }
    cache_meta_path = cache_dir / "cache_meta.json"
    with cache_meta_path.open("w", encoding="utf-8") as f:
        json.dump(cache_meta, f, indent=2)
    print(f"  Saved cache meta to: {cache_meta_path}")
    
    print("\n" + "=" * 60)
    print("Done! Embedding cache built successfully.")
    print(f"  Total entries: {len(entries)}")
    print(f"  Embedding dim:  {embeddings_np.shape[1]}")
    print(f"  Cache location: {cache_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
