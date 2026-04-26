from __future__ import annotations

import re

CHUNK_MAX_TOKENS = 512
CHUNK_OVERLAP_TOKENS = 50
_CHARS_PER_TOKEN = 4


def chunk_markdown(
    text: str,
    max_tokens: int = CHUNK_MAX_TOKENS,
    overlap_tokens: int = CHUNK_OVERLAP_TOKENS,
) -> list[str]:
    """Split markdown into overlapping chunks, respecting heading and paragraph boundaries."""
    sections = _split_sections(text)
    chunks: list[str] = []
    for section in sections:
        chunks.extend(_chunk_section(section, max_tokens, overlap_tokens))
    return chunks if chunks else [text]


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _split_sections(markdown: str) -> list[str]:
    """Split at heading boundaries, keeping each heading with its content."""
    parts = re.split(r"(?m)(?=^#{1,3} )", markdown)
    return [p.strip() for p in parts if p.strip()]


def _chunk_section(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    """Split a single section into overlapping chunks at paragraph boundaries."""
    if _estimate_tokens(text) <= max_tokens:
        return [text]

    max_chars = max_tokens * _CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * _CHARS_PER_TOKEN
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        candidate = (current + "\n\n" + para).strip() if current else para

        if _estimate_tokens(candidate) <= max_tokens:
            current = candidate
        elif _estimate_tokens(para) > max_tokens:
            # Paragraph alone exceeds limit — flush current, then char-split the paragraph
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(para), max_chars - overlap_chars):
                piece = para[i : i + max_chars].strip()
                if piece:
                    chunks.append(piece)
        else:
            # Para fits alone but combined with current it doesn't — flush with overlap
            chunks.append(current)
            overlap_text = current[-overlap_chars:] if len(current) > overlap_chars else current
            current = (overlap_text + "\n\n" + para).strip() if overlap_text else para

    if current:
        chunks.append(current)

    return chunks if chunks else [text[:max_chars]]
