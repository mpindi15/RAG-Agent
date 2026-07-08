from app.rag.chunking import chunk_text


def test_short_text_returns_single_chunk():
    text = "This is a short document."
    chunks = chunk_text(text, chunk_size=1000, overlap=150)
    assert chunks == [text]


def test_empty_text_returns_no_chunks():
    assert chunk_text("", chunk_size=1000, overlap=150) == []
    assert chunk_text("   \n  ", chunk_size=1000, overlap=150) == []


def test_long_text_is_split_into_multiple_chunks():
    text = "\n\n".join(f"Paragraph {i}. " + ("Sentence filler word. " * 20) for i in range(20))
    chunks = chunk_text(text, chunk_size=500, overlap=50)

    assert len(chunks) > 1
    for c in chunks:
        # allow slight overshoot since we don't split mid-word
        assert len(c) <= 600


def test_no_content_is_lost_across_chunks():
    text = "\n\n".join(f"Paragraph {i} with some content to pad it out a bit." for i in range(30))
    chunks = chunk_text(text, chunk_size=300, overlap=30)
    joined = " ".join(chunks)
    for i in range(30):
        assert f"Paragraph {i} " in joined


def test_overlap_present_between_consecutive_chunks():
    text = "\n\n".join(f"Paragraph {i} with enough words to matter here." for i in range(15))
    chunks = chunk_text(text, chunk_size=200, overlap=40)
    assert len(chunks) > 1
    # the tail of chunk N should share some text with the head of chunk N+1
    for a, b in zip(chunks, chunks[1:]):
        tail = a[-40:]
        assert any(word in b[:80] for word in tail.split()[:3])
