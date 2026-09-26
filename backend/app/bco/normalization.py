"""Chunk exact substrings without changing the source coordinate system."""
from app.models.document import CanonicalText, TextChunk
from app.config import settings


def exact_canonical(text, source_format):
    chunks = []
    start = 0
    limit = max(256, settings.max_chunk_chars)
    overlap = min(max(0, settings.chunk_overlap_chars), limit // 2)
    while start < len(text):
        end = min(len(text), start + limit)
        if end < len(text):
            boundary = text.rfind("\n\n", start + limit // 2, end)
            if boundary >= 0:
                end = boundary + 2
        chunks.append(TextChunk(text=text[start:end], start_offset=start, end_offset=end,
                                chunk_index=len(chunks), sentences=[text[start:end]]))
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return CanonicalText(full_text=text, chunks=chunks, source_format=source_format)
