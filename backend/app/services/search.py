"""Semantic transcript search backed by Chroma.

Lets an operator ask "find calls where the user was angry about billing" instead
of grepping transcripts. To keep the project runnable with zero external
credentials, the default embedding backend is a deterministic **hashing
vectorizer** (offline, no model download). All Chroma interaction is wrapped so
that any failure degrades to a no-op rather than breaking ingestion.
"""

from __future__ import annotations

import logging
import math
import re
from functools import lru_cache

from app.config import get_settings
from app.schemas.api import SearchHit
from app.schemas.elevenlabs import ConversationData

logger = logging.getLogger("observability.search")
settings = get_settings()

_EMBED_DIM = 512
_COLLECTION = "transcripts"


def _hash_embed(text: str) -> list[float]:
    """Bag-of-words hashing vectorizer, L2-normalized. Cheap and offline."""
    vec = [0.0] * _EMBED_DIM
    for token in re.findall(r"[a-zA-Z']+", text.lower()):
        idx = hash(token) % _EMBED_DIM
        # Sign hashing reduces collisions cancelling each other out.
        sign = 1.0 if (hash(token + "_s") & 1) else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class _HashEmbeddingFunction:
    """Chroma-compatible embedding function (callable taking ``input``)."""

    def __call__(self, input):  # noqa: A002 - name mandated by Chroma protocol
        return [_hash_embed(doc) for doc in input]

    @staticmethod
    def name() -> str:
        return "hashing-vectorizer-v1"


@lru_cache
def _collection():
    """Return the Chroma collection, or ``None`` if unavailable."""
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        return client.get_or_create_collection(
            name=_COLLECTION,
            embedding_function=_HashEmbeddingFunction(),
            metadata={"hnsw:space": "cosine"},
        )
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.warning("Chroma unavailable, semantic search disabled: %s", exc)
        return None


def _transcript_text(data: ConversationData) -> str:
    return "\n".join(f"{t.role}: {t.message}" for t in data.transcript if t.message)


def index_conversation_safe(conversation_id: str, data: ConversationData) -> None:
    """Best-effort indexing of a conversation transcript. Never raises."""
    collection = _collection()
    if collection is None:
        return
    text = _transcript_text(data)
    if not text.strip():
        return
    try:
        collection.upsert(
            ids=[conversation_id],
            documents=[text],
            metadatas=[
                {
                    "conversation_id": conversation_id,
                    "agent_id": data.agent_id,
                    "snippet": text[:240],
                }
            ],
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to index %s: %s", conversation_id, exc)


def search_transcripts(query: str, limit: int = 10) -> list[SearchHit]:
    """Return the conversations most semantically similar to ``query``."""
    collection = _collection()
    if collection is None or not query.strip():
        return []
    try:
        result = collection.query(query_texts=[query], n_results=limit)
    except Exception as exc:  # pragma: no cover
        logger.warning("Search failed: %s", exc)
        return []

    hits: list[SearchHit] = []
    ids = (result.get("ids") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    for i, conv_id in enumerate(ids):
        distance = distances[i] if i < len(distances) else 1.0
        meta = metadatas[i] if i < len(metadatas) else {}
        hits.append(
            SearchHit(
                conversation_id=conv_id,
                score=round(1.0 - distance, 4),  # cosine distance -> similarity
                snippet=(meta or {}).get("snippet", ""),
            )
        )
    return hits
