from app.rag.pipeline import NO_DOCUMENTS_MESSAGE, _client, answer_question, stream_answer_question


def test_gemini_client_is_cached_not_recreated_per_call():
    """Regression test: genai.Client()'s Models accessor only holds a
    reference to the internal API client, not to the Client wrapper itself.
    A throwaway `genai.Client()` per call gets garbage-collected (and its
    __del__ closes the underlying HTTP client) before the request completes,
    producing 'Cannot send a request, as the client has been closed.' The
    fix is to cache one client for the app's lifetime instead of
    constructing-and-discarding one per call — this test guards against
    that fix being accidentally removed.
    """
    assert _client() is _client()


def test_answer_question_short_circuits_with_no_documents():
    """No network call should happen (and none is mocked here) when the
    vector store is empty — the pipeline should recognize that up front
    instead of sending a near-empty-context prompt to the API."""
    result = answer_question("What is the PTO policy?")
    assert result["answer"] == NO_DOCUMENTS_MESSAGE
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0
    assert result["cost_usd"] == 0.0


def test_stream_answer_question_short_circuits_with_no_documents():
    events = list(stream_answer_question("What is the PTO policy?"))
    assert [e["type"] for e in events] == ["sources", "delta", "done"]
    assert events[0]["sources"] == []
    assert events[1]["text"] == NO_DOCUMENTS_MESSAGE
    assert events[2]["input_tokens"] == 0
