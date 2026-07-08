from app.rag.pipeline import _client


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
