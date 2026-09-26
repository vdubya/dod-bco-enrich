from __future__ import annotations

import re

from app.config import settings
from app.models.document import CanonicalText, DocumentFormat, TextChunk


def normalize_whitespace(text: str) -> str:
    # Collapse runs of whitespace (except newlines) to single space
    text = re.sub(r"[^\S\n]+", " ", text)
    # Collapse 3+ newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove spaces adjacent to newlines
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    """Sentence splitter using NuPunkt for legal-domain accuracy.

    NuPunkt handles legal citations (e.g., "42 U.S.C. § 1983", "No. 12-345")
    without incorrectly splitting at abbreviation periods.
    Falls back to regex if nupunkt is not installed.
    """
    try:
        from nupunkt import SentenceTokenizer
        tokenizer = SentenceTokenizer()
        sentences = tokenizer.tokenize(text)
        return [s for s in sentences if s.strip()]
    except ImportError:
        # Fallback to regex if nupunkt not installed
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
        return [p for p in parts if p.strip()]


def build_sentence_index(text: str) -> list[tuple[int, int, str]]:
    """Build a list of (start, end, sentence_text) for all sentences in text.

    Uses the same NuPunkt splitter as the pipeline, so sentence boundaries
    are consistent with the normalization stage.
    """
    sentences = split_sentences(text)
    index: list[tuple[int, int, str]] = []
    position = 0
    for sent in sentences:
        start = text.find(sent, position)
        if start == -1:
            start = position
        end = start + len(sent)
        index.append((start, end, sent))
        position = end
    return index


def find_sentence_for_span(
    sentence_index: list[tuple[int, int, str]],
    span_start: int,
    span_end: int,
) -> str | None:
    """Return the sentence containing the given character span, or None."""
    for sent_start, sent_end, sent_text in sentence_index:
        if sent_start <= span_start and span_end <= sent_end:
            return sent_text
    # Fallback: find the sentence whose overlap with the span is largest
    best = None
    best_overlap = 0
    for sent_start, sent_end, sent_text in sentence_index:
        overlap_start = max(sent_start, span_start)
        overlap_end = min(sent_end, span_end)
        overlap = max(0, overlap_end - overlap_start)
        if overlap > best_overlap:
            best_overlap = overlap
            best = sent_text
    return best


def chunk_text(
    text: str,
    max_chars: int | None = None,
    overlap: int | None = None,
) -> list[TextChunk]:
    if max_chars is None:
        max_chars = settings.max_chunk_chars
    if overlap is None:
        overlap = settings.chunk_overlap_chars

    if len(text) <= max_chars:
        return [
            TextChunk(
                text=text,
                start_offset=0,
                end_offset=len(text),
                chunk_index=0,
            )
        ]

    sentences = split_sentences(text)
    chunks: list[TextChunk] = []
    current_spans: list[tuple[int, int]] = []
    position = 0

    def emit_chunk() -> None:
        start, end = current_spans[0][0], current_spans[-1][1]
        chunks.append(TextChunk(
            text=text[start:end], start_offset=start, end_offset=end,
            chunk_index=len(chunks),
        ))

    for sentence in sentences:
        # Offsets refer to this exact input, including inter-sentence whitespace.
        sent_start = text.find(sentence, position)
        if sent_start == -1:
            raise ValueError("Sentence tokenizer returned text not present in the source")
        sent_end = sent_start + len(sentence)

        if current_spans and sent_end - current_spans[0][0] > max_chars:
            emit_chunk()
            # Retain a suffix of whole sentences only when its actual source
            # length fits the overlap budget and leaves room for the new sentence.
            # An oversized sentence is still emitted intact, on its own.
            retained: list[tuple[int, int]] = []
            for start, end in reversed(current_spans):
                if current_spans[-1][1] - start > overlap or sent_end - start > max_chars:
                    break
                retained.insert(0, (start, end))
            current_spans = retained

        current_spans.append((sent_start, sent_end))
        position = sent_end

    if current_spans:
        emit_chunk()

    return chunks


def normalize_and_chunk(
    raw_text: str, source_format: DocumentFormat = DocumentFormat.PLAIN_TEXT
) -> CanonicalText:
    normalized = normalize_whitespace(raw_text)
    chunks = chunk_text(normalized)

    # Populate sentence boundaries on each chunk
    for chunk in chunks:
        chunk.sentences = split_sentences(chunk.text)

    return CanonicalText(
        full_text=normalized,
        chunks=chunks,
        source_format=source_format,
    )
