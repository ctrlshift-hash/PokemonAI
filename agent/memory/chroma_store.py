"""
Vector memory for persistent knowledge.
Tries ChromaDB first; falls back to a simple JSON-based store
if ChromaDB is unavailable (e.g. Python 3.14 compatibility).
"""

import json
import logging
import os
import time
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any

from config import settings
from agent.memory.memory_types import MemoryType

logger = logging.getLogger(__name__)

# ChromaDB is loaded lazily inside ChromaStore.__init__ to avoid
# import-time crashes on Python 3.14 (pydantic v1 compat issue).
_HAS_CHROMA = None  # will be set on first init


class _JsonStore:
    """Simple JSON file-based memory store as a fallback."""

    def __init__(self, path):
        self._path = path
        self._memories = []
        self._load()

    def _load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._memories = json.load(f)
            except Exception:
                self._memories = []

    def _save(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._memories, f, indent=2)

    def add(self, memory_id, text, metadata):
        self._memories.append({
            "id": memory_id,
            "text": text,
            "metadata": metadata,
        })
        self._save()

    def search(self, query, n_results, where=None):
        """Simple substring + similarity search."""
        query_lower = query.lower()
        scored = []
        for mem in self._memories:
            if where:
                if mem["metadata"].get("type") != where.get("type"):
                    continue
            text = mem["text"]
            # Score by substring match + sequence similarity
            score = 0.0
            if query_lower in text.lower():
                score += 0.5
            score += SequenceMatcher(None, query_lower, text.lower()).ratio()
            scored.append((score, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:n_results]

        return {
            "documents": [[m["text"] for _, m in top]],
            "metadatas": [[m["metadata"] for _, m in top]],
            "distances": [[1.0 - s for s, _ in top]],
            "ids": [[m["id"] for _, m in top]],
        }

    def get(self, limit, **kwargs):
        recent = self._memories[-limit:]
        return {
            "ids": [m["id"] for m in recent],
            "documents": [m["text"] for m in recent],
            "metadatas": [m["metadata"] for m in recent],
        }

    def count(self):
        return len(self._memories)


class ChromaStore:
    """Memory store with ChromaDB or JSON fallback."""

    def __init__(self):
        global _HAS_CHROMA
        self._use_chroma = False
        self.collection = None
        self._json_store = None

        # Lazy import ChromaDB to avoid import-time pydantic v1 crash on Python 3.14
        if _HAS_CHROMA is None:
            try:
                import chromadb  # noqa: F811
                _HAS_CHROMA = True
            except Exception:
                _HAS_CHROMA = False
                logger.warning("ChromaDB unavailable - using JSON fallback memory store")

        if _HAS_CHROMA:
            try:
                import chromadb
                from chromadb.config import Settings as ChromaSettings
                self.client = chromadb.PersistentClient(
                    path=str(settings.CHROMA_DIR),
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
                self.collection = self.client.get_or_create_collection(
                    name=settings.MEMORY_COLLECTION,
                    metadata={"hnsw:space": "cosine"},
                )
                self._counter = self.collection.count()
                self._use_chroma = True
                logger.info(f"ChromaDB initialized with {self._counter} memories")
            except Exception as e:
                _HAS_CHROMA = False
                logger.warning(f"ChromaDB init failed ({e}), using JSON fallback")

        if not self._use_chroma:
            json_path = os.path.join(str(settings.CHROMA_DIR), "memories.json")
            self._json_store = _JsonStore(json_path)
            self._counter = self._json_store.count()
            logger.info(f"JSON memory store initialized with {self._counter} memories")

    def add(self, text, category=MemoryType.GENERAL, metadata=None):
        """Store a new memory. Returns the memory ID."""
        if not text or not text.strip():
            return ""

        self._counter += 1
        memory_id = f"mem_{self._counter}_{int(time.time())}"

        meta = {
            "type": category.value if isinstance(category, MemoryType) else str(category),
            "timestamp": datetime.now().isoformat(),
            "unix_time": int(time.time()),
        }
        if metadata:
            for k, v in metadata.items():
                if isinstance(v, (str, int, float, bool)):
                    meta[k] = v
                else:
                    meta[k] = json.dumps(v)

        if self._use_chroma:
            self.collection.add(
                ids=[memory_id],
                documents=[text],
                metadatas=[meta],
            )
        else:
            self._json_store.add(memory_id, text, meta)

        logger.debug(f"Stored memory [{category}]: {text[:80]}")
        return memory_id

    def search(self, query, n_results=None, category=None):
        """Retrieve relevant memories via similarity search."""
        if n_results is None:
            n_results = settings.MEMORY_TOP_K

        where = None
        if category:
            cat_val = category.value if isinstance(category, MemoryType) else str(category)
            where = {"type": cat_val}

        try:
            if self._use_chroma:
                results = self.collection.query(
                    query_texts=[query],
                    n_results=min(n_results, max(self._counter, 1)),
                    where=where,
                )
            else:
                results = self._json_store.search(query, n_results, where)
        except Exception as e:
            logger.warning(f"Memory search failed: {e}")
            return []

        memories = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                memories.append({
                    "content": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0,
                    "id": results["ids"][0][i] if results["ids"] else "",
                })

        return memories

    def get_recent(self, n=5):
        """Get the N most recent memories."""
        try:
            if self._use_chroma:
                results = self.collection.get(
                    limit=n,
                    include=["documents", "metadatas"],
                )
            else:
                results = self._json_store.get(limit=n)
        except Exception:
            return []

        memories = []
        if results["documents"]:
            items = list(zip(
                results["ids"],
                results["documents"],
                results["metadatas"] or [{}] * len(results["documents"]),
            ))
            items.sort(
                key=lambda x: x[2].get("unix_time", 0) if x[2] else 0,
                reverse=True,
            )
            for mid, doc, meta in items[:n]:
                memories.append({
                    "content": doc,
                    "metadata": meta,
                    "id": mid,
                })

        return memories

    def get_context_for_situation(self, situation):
        """Build a context string from relevant memories for the current situation."""
        memories = self.search(situation, n_results=7)
        if not memories:
            return ""

        lines = ["Relevant memories from past experience:"]
        for mem in memories:
            mem_type = mem["metadata"].get("type", "unknown")
            content = mem["content"]
            lines.append(f"  [{mem_type}] {content}")

        return "\n".join(lines)

    @property
    def total_memories(self):
        if self._use_chroma:
            return self.collection.count()
        return self._json_store.count()
