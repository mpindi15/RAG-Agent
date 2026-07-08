"""Text chunking for retrieval.

A small hand-rolled recursive splitter: try to break on paragraph boundaries
first, then lines, then sentences, then fall back to a hard character cut.
Keeps a character overlap between consecutive chunks so context isn't lost
at a chunk boundary.
"""

SEPARATORS = ["\n\n", "\n", ". ", " "]


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 150) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    pieces = _split(text, SEPARATORS)
    chunks: list[str] = []
    current = ""

    for piece in pieces:
        candidate = f"{current}{piece}"
        if len(candidate) <= chunk_size:
            current = candidate
            continue

        if current:
            chunks.append(current.strip())
            # start next chunk with overlap tail of the previous one
            tail = current[-overlap:] if overlap > 0 else ""
            current = f"{tail}{piece}"
        else:
            # single piece longer than chunk_size: hard-cut it
            for start in range(0, len(piece), chunk_size - overlap):
                chunks.append(piece[start : start + chunk_size].strip())
            current = ""

    if current.strip():
        chunks.append(current.strip())

    return [c for c in chunks if c]


def _split(text: str, separators: list[str]) -> list[str]:
    """Split text into pieces using the first separator that actually
    divides it, recursing into over-long pieces with the remaining
    separators. Separators are kept attached to the piece that precedes
    them so chunks read naturally."""
    if not separators:
        return [text]

    sep, rest = separators[0], separators[1:]
    if sep not in text:
        return _split(text, rest)

    raw_parts = text.split(sep)
    pieces = [p + sep for p in raw_parts[:-1]] + [raw_parts[-1]]

    result: list[str] = []
    for piece in pieces:
        if len(piece) > 2000 and rest:
            result.extend(_split(piece, rest))
        elif piece:
            result.append(piece)
    return result
