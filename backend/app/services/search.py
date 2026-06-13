"""Semantic transcript search backed by Chroma.

Lets an operator ask "find calls where the user was angry about billing" instead
of grepping transcripts. To keep the project runnable with zero external
credentials, the default embedding backend is a deterministic **hashing
vectorizer** (offline, no model download). All Chroma interaction is wrapped so
that any failure degrades to a no-op rather than breaking ingestion.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
from functools import lru_cache

from app.config import get_settings
from app.schemas.api import SearchHit
from app.schemas.elevenlabs import ConversationData

# Disable Chroma's telemetry phone-home before chromadb is ever imported. Some
# chromadb/posthog version pairs raise a noisy (harmless) "capture() takes 1
# positional argument" error on every event; this silences it at the source.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY_ENABLED", "False")
logging.getLogger("chromadb.telemetry").setLevel(logging.CRITICAL)
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)

logger = logging.getLogger("observability.search")
settings = get_settings()

_EMBED_DIM = 1024
# The embedder version is part of the collection name: changing the embedding
# (e.g. dimensionality) automatically uses a fresh collection instead of clashing
# with vectors written by an older embedder ("dimension X != collection Y").
_COLLECTION = "transcripts_v2_1024"

# Common words carry little signal; dropping them sharpens relevance.
_STOPWORDS = frozenset(
    """a an and are as at be been but by do did for from had has have he her his i if in
    is it its me my no not of on or our she so that the their them they this to up us was
    we were what when where which who will with you your hi hello hey ok okay yeah yes please
    thanks thank just like would could should can about""".split()
)


def _stable_hash(token: str) -> int:
    """Process-independent hash (unlike Python's salted ``hash()``).

    The previous implementation used the built-in ``hash()``, which is randomized
    per process (PYTHONHASHSEED). That meant documents indexed in one process and
    queries embedded in another landed in different hash spaces, making every
    similarity ~0. Hashing with blake2b is deterministic across processes.
    """
    return int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big")


def _hash_embed(text: str) -> list[float]:
    """Deterministic bag-of-words hashing vectorizer, L2-normalized. Offline, no deps."""
    vec = [0.0] * _EMBED_DIM
    for token in re.findall(r"[a-z']{2,}", text.lower()):
        if token in _STOPWORDS:
            continue
        h = _stable_hash(token)
        idx = h % _EMBED_DIM
        # Sign hashing reduces collisions cancelling each other out.
        sign = 1.0 if (h >> 17) & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class _HashEmbeddingFunction:
    """Chroma-compatible embedding function (callable taking ``input``)."""

    def __call__(self, input):  # noqa: A002 - name mandated by Chroma protocol
        return [_hash_embed(doc) for doc in input]

    @staticmethod
    def name() -> str:
        return "hashing-vectorizer-v2"


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
