from worker.config import build_worker_config


def test_build_worker_config_defaults(monkeypatch) -> None:
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("INGEST_QUEUE_KEY", raising=False)
    monkeypatch.delenv("WORKER_POLL_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("WORKER_MAX_RETRIES", raising=False)
    monkeypatch.delenv("EMBEDDING_DIM", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("LLM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("LLM_MAX_RETRIES", raising=False)
    monkeypatch.delenv("LLM_RETRY_DELAY_MILLISECONDS", raising=False)

    cfg = build_worker_config()
    assert cfg.redis_url == "redis://redis:6379/0"
    assert cfg.ingest_queue_key == "ingest_jobs"
    assert cfg.poll_interval_seconds == 5
    assert cfg.worker_max_retries == 3
    assert cfg.embedding_dim == 256
    assert cfg.llm_provider == "openai"
    assert cfg.llm_base_url == ""
    assert cfg.llm_api_key == ""
    assert cfg.llm_embedding_model == ""
    assert cfg.llm_timeout_seconds == 30
    assert cfg.llm_max_retries == 2
    assert cfg.llm_retry_delay_milliseconds == 600


def test_build_worker_config_overrides(monkeypatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://custom:6379/1")
    monkeypatch.setenv("INGEST_QUEUE_KEY", "queue-x")
    monkeypatch.setenv("WORKER_POLL_INTERVAL_SECONDS", "9")
    monkeypatch.setenv("WORKER_MAX_RETRIES", "5")
    monkeypatch.setenv("EMBEDDING_DIM", "128")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_EMBEDDING_MODEL", "deepseek-embedding")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "18")
    monkeypatch.setenv("LLM_MAX_RETRIES", "4")
    monkeypatch.setenv("LLM_RETRY_DELAY_MILLISECONDS", "1200")

    cfg = build_worker_config()
    assert cfg.redis_url == "redis://custom:6379/1"
    assert cfg.ingest_queue_key == "queue-x"
    assert cfg.poll_interval_seconds == 9
    assert cfg.worker_max_retries == 5
    assert cfg.embedding_dim == 128
    assert cfg.llm_provider == "deepseek"
    assert cfg.llm_base_url == "https://api.deepseek.com/v1"
    assert cfg.llm_api_key == "sk-test"
    assert cfg.llm_embedding_model == "deepseek-embedding"
    assert cfg.llm_timeout_seconds == 18
    assert cfg.llm_max_retries == 4
    assert cfg.llm_retry_delay_milliseconds == 1200
