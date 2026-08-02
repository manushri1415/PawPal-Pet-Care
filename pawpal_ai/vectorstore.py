"""A dependency-light local vector store for RAG retrieval.

Why not Chroma/FAISS? Both need to compile native wheels (hnswlib -> MSVC),
which fails on stock Windows + Python 3.13 and breaks "runs on a grader's
machine". Vet documents are short, so we don't need an ANN index — a pure
NumPy cosine scan over a handful of chunks is instant and fully reproducible.

**Embeddings** here are deterministic *feature-hashing* embeddings: each chunk's
word + word-bigram tokens are hashed into a fixed-dimension vector with TF
weighting, then L2-normalized. This is a real (if classical) text embedding —
the "hashing trick" — and needs no model download, no API key, and no compiler.
The :class:`VectorStore` interface is deliberately small so a neural-embedding
backend could be dropped in later without touching the rest of the pipeline.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

import numpy as np

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_EMBED_DIM = 512


def _tokens(text: str) -> list[str]:
    words = _TOKEN_RE.findall(text.lower())
    bigrams = [f"{a}_{b}" for a, b in zip(words, words[1:])]
    return words + bigrams


def embed(text: str, dim: int = _EMBED_DIM) -> np.ndarray:
    """Deterministic feature-hashing embedding (TF-weighted, L2-normalized)."""
    vec = np.zeros(dim, dtype=np.float32)
    for tok in _tokens(text):
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 8) % 2 == 0 else -1.0  # signed hashing reduces collisions
        vec[idx] += sign
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec /= norm
    return vec


@dataclass
class Chunk:
    """One retrievable passage plus its provenance metadata."""

    chunk_id: str
    document_id: str
    text: str
    section: Optional[str] = None


@dataclass
class RetrievedChunk:
    chunk: Chunk
    score: float


@dataclass
class VectorStore:
    """In-memory cosine-similarity store over embedded chunks.

    Not persisted to disk on purpose: we re-index a document's chunks each time
    it is processed (documents are small and processed once), which keeps the
    store trivially reproducible and side-effect-free for tests.
    """

    dim: int = _EMBED_DIM
    _chunks: list[Chunk] = field(default_factory=list)
    _matrix: Optional[np.ndarray] = None

    def add(self, chunks: Iterable[Chunk]) -> None:
        new = list(chunks)
        if not new:
            return
        self._chunks.extend(new)
        vecs = np.vstack([embed(c.text, self.dim) for c in new])
        self._matrix = vecs if self._matrix is None else np.vstack([self._matrix, vecs])

    def __len__(self) -> int:
        return len(self._chunks)

    def retrieve(
        self, query: str, k: int = 4, document_id: Optional[str] = None
    ) -> list[RetrievedChunk]:
        """Return the top-``k`` chunks by cosine similarity to ``query``.

        ``k <= 0`` returns nothing (used by the retrieval-ablation experiment to
        prove that retrieval actually changes downstream extraction)."""
        if k <= 0 or self._matrix is None or not self._chunks:
            return []
        q = embed(query, self.dim)
        scores = self._matrix @ q  # cosine (all rows already L2-normalized)
        order = np.argsort(-scores)
        results: list[RetrievedChunk] = []
        for i in order:
            chunk = self._chunks[int(i)]
            if document_id is not None and chunk.document_id != document_id:
                continue
            results.append(RetrievedChunk(chunk=chunk, score=float(scores[int(i)])))
            if len(results) >= k:
                break
        return results

    def all_chunks(self, document_id: Optional[str] = None) -> list[Chunk]:
        if document_id is None:
            return list(self._chunks)
        return [c for c in self._chunks if c.document_id == document_id]
