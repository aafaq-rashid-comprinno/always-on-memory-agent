"""
Text chunking utilities for large input handling.
"""

import hashlib


def chunk_text(text: str, max_chars: int = 3000, overlap: int = 200) -> list[str]:
    """
    Split text into chunks that fit comfortably in the model context.

    Uses paragraph boundaries when possible, falls back to sentence
    boundaries, then hard character splits.

    Args:
        text: The full text to chunk.
        max_chars: Maximum characters per chunk.
        overlap: Characters of overlap between chunks for context continuity.

    Returns:
        List of text chunks.
    """
    if len(text) <= max_chars:
        return [text]

    chunks = []
    paragraphs = text.split("\n\n")
    current_chunk = ""

    for para in paragraphs:
        # If a single paragraph exceeds max, split it further
        if len(para) > max_chars:
            # Flush current chunk
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
                current_chunk = ""

            # Split long paragraph by sentences
            sentences = _split_sentences(para)
            for sentence in sentences:
                if len(current_chunk) + len(sentence) > max_chars:
                    if current_chunk.strip():
                        chunks.append(current_chunk.strip())
                    # Start new chunk with overlap from end of previous
                    if chunks and overlap > 0:
                        current_chunk = chunks[-1][-overlap:] + "\n" + sentence
                    else:
                        current_chunk = sentence
                else:
                    current_chunk += " " + sentence if current_chunk else sentence

        elif len(current_chunk) + len(para) + 2 > max_chars:
            # Adding this paragraph would exceed limit
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            # Start new chunk with overlap
            if chunks and overlap > 0:
                current_chunk = chunks[-1][-overlap:] + "\n\n" + para
            else:
                current_chunk = para
        else:
            current_chunk += "\n\n" + para if current_chunk else para

    # Don't forget the last chunk
    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def compute_text_hash(text: str) -> str:
    """Compute a stable hash for deduplication."""
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]


def _split_sentences(text: str) -> list[str]:
    """Simple sentence splitter."""
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s for s in sentences if s.strip()]
