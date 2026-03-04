from worker.chunking import ParsedSegment, chunk_segments
from worker.embedding import hash_embedding, resolve_provider_base_url


def test_chunk_segments_with_overlap() -> None:
    text = " ".join([f"w{i}" for i in range(1, 1001)])
    chunks = chunk_segments([ParsedSegment(text=text, page_or_loc="text:1")], chunk_tokens=200, overlap_tokens=50)
    assert len(chunks) > 1
    assert chunks[0].token_count == 200
    assert chunks[1].token_count == 200
    assert chunks[0].chunk_index == 0
    assert chunks[1].chunk_index == 1


def test_hash_embedding_dimension_and_norm() -> None:
    vec = hash_embedding("hello world", 64)
    assert len(vec) == 64
    assert abs(sum(v * v for v in vec) - 1.0) < 1e-6


def test_resolve_provider_base_url() -> None:
    assert resolve_provider_base_url("deepseek", "") == "https://api.deepseek.com/v1"
    assert resolve_provider_base_url("custom", "https://llm.example.com/v1") == "https://llm.example.com/v1"
