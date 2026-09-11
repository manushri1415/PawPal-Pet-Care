"""Split extracted document text into retrievable chunks with provenance.

Vet documents are short and line-oriented (labelled fields, tables flattened to
lines). We chunk on blank-line-separated blocks first, then pack them into
windows of ~``max_chars`` with a small overlap so a field and its value stay
together. Each chunk carries a stable ``chunk_id`` and a human-readable
``section`` label used later for citations.
"""

from __future__ import annotations

import re
from typing import Optional

from pawpal_ai.vectorstore import Chunk

_WS_RE = re.compile(r"[ \t]+")


def _normalize(text: str) -> str:
    lines = [_WS_RE.sub(" ", ln).rstrip() for ln in text.splitlines()]
    return "\n".join(lines).strip()


def chunk_text(
    text: str,
    document_id: str,
    pet_id: str,
    max_chars: int = 600,
    overlap: int = 80,
) -> list[Chunk]:
    """Return a list of :class:`Chunk` for ``text``.

    ``pet_id`` is stamped onto every chunk — it's the owner-scoping tag
    :meth:`VectorStore.retrieve` filters on, so a question about one pet can't
    retrieve another pet's chunks. Required (not defaulted) so a caller can't
    accidentally index a document without it.

    Empty/whitespace-only input yields an empty list (the caller treats that as
    an empty document — a valid, non-crashing outcome)."""
    text = _normalize(text)
    if not text:
        return []

    # Split into blocks on blank lines, then greedily pack blocks into windows.
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    if not blocks:
        blocks = [text]

    chunks: list[Chunk] = []
    buf = ""
    idx = 0
    for block in blocks:
        candidate = f"{buf}\n{block}".strip() if buf else block
        if len(candidate) <= max_chars or not buf:
            buf = candidate
        else:
            chunks.append(_make_chunk(buf, document_id, pet_id, idx))
            idx += 1
            tail = buf[-overlap:] if overlap else ""
            buf = f"{tail}\n{block}".strip()
    if buf:
        chunks.append(_make_chunk(buf, document_id, pet_id, idx))

    # Hard-split any oversized single block so no chunk dwarfs the rest.
    final: list[Chunk] = []
    for ch in chunks:
        if len(ch.text) <= max_chars * 2:
            final.append(ch)
            continue
        for j in range(0, len(ch.text), max_chars):
            piece = ch.text[j : j + max_chars]
            final.append(
                _make_chunk(piece, document_id, pet_id, len(final), section_hint=ch.section)
            )
    return final


def _make_chunk(
    text: str, document_id: str, pet_id: str, idx: int, section_hint: Optional[str] = None
) -> Chunk:
    section = section_hint or _section_label(text, idx)
    return Chunk(
        chunk_id=f"{document_id}#chunk-{idx}",
        document_id=document_id,
        pet_id=pet_id,
        text=text.strip(),
        section=section,
    )


def _section_label(text: str, idx: int) -> str:
    """Best-effort section label: the first short line that looks like a heading
    or field label, else a generic chunk index."""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.endswith(":") or (len(line) <= 40 and line == line.title()):
            return line.rstrip(":")
        break
    return f"chunk {idx + 1}"
