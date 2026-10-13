from __future__ import annotations

import asyncio
import importlib
import importlib.util
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from langchain_core.documents import Document

from shared.eval_metrics import recall_at_k_ids

from conftest import prioritize_service_src


ROOT = Path(__file__).resolve().parents[1]


def _load_file(name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def test_kb_database_reuses_pool_and_closes_it(monkeypatch, tmp_path: Path) -> None:
    db_module = _load_file("kb_perf_db", "apps/services/knowledge-base/src/app/db.py")
    pools = []

    class FakePool:
        def __init__(self, dsn, **kwargs):
            self.dsn = dsn
            self.kwargs = kwargs
            self.opened = False
            self.closed = False
            pools.append(self)

        def open(self):
            self.opened = True

        @contextmanager
        def connection(self):
            yield self

        def close(self):
            self.closed = True

    monkeypatch.setattr(db_module, "ConnectionPool", FakePool)
    monkeypatch.setenv("KB_DB_POOL_MAX_SIZE", "4")
    db = db_module.KBDatabase("test-dsn", tmp_path)
    assert not pools
    with ThreadPoolExecutor(max_workers=8) as executor:
        assert len({id(pool) for pool in executor.map(lambda _: db._get_pool(), range(16))}) == 1
    with db.connect() as conn:
        assert conn is pools[0]
    assert pools[0].opened and pools[0].kwargs["max_size"] == 4
    db.close()
    assert pools[0].closed
    assert db._get_pool() is not pools[0]
    db.close()


def test_retrieval_executor_is_bounded_and_reused(monkeypatch) -> None:
    prioritize_service_src(ROOT / "apps/services/knowledge-base/src")
    retrieve = importlib.import_module("app.retrieve")
    monkeypatch.setenv("KB_RETRIEVAL_WORKERS", "3")
    try:
        first = retrieve._get_retrieval_executor()
        assert retrieve._get_retrieval_executor() is first
        def work():
            time.sleep(0.01)
            return 1
        assert sum(first.map(lambda _: work(), range(12))) == 12
        assert first._max_workers == 3
    finally:
        retrieve.close_retrieval_executor()
    assert retrieve._get_retrieval_executor() is not first
    retrieve.close_retrieval_executor()


def test_three_retrieval_signals_still_run_concurrently(monkeypatch) -> None:
    prioritize_service_src(ROOT / "apps/services/knowledge-base/src")
    retrieve = importlib.import_module("app.retrieve")
    barrier = threading.Barrier(3)

    class FakeRetriever:
        def __init__(self, **kwargs):
            pass

        def invoke(self, query):
            barrier.wait(timeout=2)
            return [Document(page_content=query)]

    def fake_vector(**kwargs):
        barrier.wait(timeout=2)
        return [Document(page_content="vector")], [], []

    monkeypatch.setattr(retrieve, "StructureRetriever", FakeRetriever)
    monkeypatch.setattr(retrieve, "FTSRetriever", FakeRetriever)
    monkeypatch.setattr(retrieve, "search_vector_documents", fake_vector)
    try:
        state = retrieve._run_signal_retrievers({
            "base_id": "test", "question": "policy", "doc_ids": ["doc"],
            "rewrite": SimpleNamespace(retrieval_query="policy", focus_query="policy"),
        })
        assert set(state["signal_documents"]) == {"structure", "fts", "vector"}
        assert all(state["signal_documents"].values())
    finally:
        retrieve.close_retrieval_executor()


def test_concurrency_benchmark_refills_free_slots(monkeypatch) -> None:
    benchmark = _load_file(
        "retrieval_benchmark_test", "scripts/evaluation/benchmark-retrieval-concurrency.py"
    )
    started = {}
    finished = {}
    questions_seen = {}
    active = 0
    peak = 0

    async def fake_send_request(client, *, request_id, **kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        started[request_id] = time.perf_counter()
        questions_seen[request_id] = kwargs["payload"]["question"]
        await asyncio.sleep(0.04 if request_id == 1 else 0.005)
        finished[request_id] = time.perf_counter()
        active -= 1
        return {"request_id": request_id, "ok": True, "latency_ms": 1, "retrieval_ms": 1, "selected_candidates": 1, "status_code": 200, "error": {}}

    monkeypatch.setattr(benchmark, "send_request", fake_send_request)
    rows, _ = asyncio.run(benchmark.run_concurrency_benchmark(
        retrieve_url="http://localhost/unused", headers={}, payload={"question": "a"},
        total_requests=4, concurrency=2, timeout_seconds=1, questions=["a", "b"],
    ))
    assert [row["request_id"] for row in rows] == [1, 2, 3, 4]
    assert peak == 2
    assert started[3] < finished[1]
    assert questions_seen == {1: "a", 2: "b", 3: "a", 4: "b"}


def test_concurrency_summary_excludes_errors_from_success_p95() -> None:
    benchmark = _load_file("retrieval_benchmark_summary_test", "scripts/evaluation/benchmark-retrieval-concurrency.py")
    rows = [
        {"ok": True, "latency_ms": 100, "retrieval_ms": 60, "selected_candidates": 1, "status_code": 200, "error": {}},
        {"ok": False, "latency_ms": 1, "retrieval_ms": 0, "selected_candidates": 0, "status_code": 429, "error": {"code": "limited"}},
    ]
    summary, errors = benchmark.summarize_results(
        total_requests=2, concurrency=2, wall_time_seconds=1.0, results=rows,
    )
    assert summary["latency"]["p95_ms"] == 100
    assert summary["success_throughput_rps"] == 1
    assert summary["nonempty_retrieval_rate"] == 1
    assert errors[0]["status_code"] == 429


def test_recall_counts_missing_expected_evidence() -> None:
    assert recall_at_k_ids({"a", "b"}, ["a", "noise", "a"], 3) == 0.5
    ablation = _load_file("retrieval_ablation_perf_test", "scripts/evaluation/run-retrieval-ablation.py")
    case = {"expected_unit_ids": ["a", "b"]}
    ranked = [type("Candidate", (), {"unit_id": "a"})()]
    assert ablation.score_ranking(case, ranked)["recall_at_3"] == 0.5


def test_online_recall_counts_missing_sections() -> None:
    evaluation = _load_file("eval_long_rag_perf_test", "scripts/evaluation/eval-long-rag.py")
    case = {"expected_sections": ["A", "B"]}
    citations = [{"section_title": "A"}, {"section_title": "A"}]
    assert evaluation._section_recall_at_k(case, citations, 3) == 0.5
    row = evaluation.score_case(case, {
        "citations": citations,
        "answer_mode": "grounded",
        "cost": {"estimated_cost": 0.012, "currency": "USD"},
    }, latency_ms=25.0)
    assert row["recall_at_3"] == 0.5
    assert evaluation.summarize_results([row])["overall"]["estimated_cost_per_1000_requests"] == {"USD": 12.0}


def test_retrieval_cache_is_acl_aware_and_reuses_result() -> None:
    cache_module = _load_file(
        "retrieval_cache_perf_test",
        "apps/services/knowledge-base/src/app/retrieval_cache.py",
    )
    cache = cache_module.RetrievalResultCache(ttl_seconds=30, max_entries=4)
    calls = {"count": 0}

    def compute() -> dict[str, str]:
        calls["count"] += 1
        return {"answer": "department scoped"}

    key = cache_module.build_retrieval_cache_key(
        base_id="base-1",
        question="  Expense   Flow ",
        document_ids=["doc-2", "doc-1"],
        limit=8,
        user_department="Finance",
    )
    assert cache.get_or_compute(key, compute) == ({"answer": "department scoped"}, False)
    assert cache.get_or_compute(key, compute) == ({"answer": "department scoped"}, True)
    assert calls["count"] == 1

    other_scope = cache_module.build_retrieval_cache_key(
        base_id="base-1",
        question="expense flow",
        document_ids=["doc-1", "doc-2"],
        limit=8,
        user_department="HR",
    )
    assert other_scope != key
    assert cache.stats().hits == 1


def test_retrieval_cache_coalesces_duplicate_inflight_work() -> None:
    cache_module = _load_file(
        "retrieval_cache_coalesce_test",
        "apps/services/knowledge-base/src/app/retrieval_cache.py",
    )
    cache = cache_module.RetrievalResultCache(ttl_seconds=30, max_entries=4, wait_seconds=1)
    calls = {"count": 0}
    lock = threading.Lock()
    started = threading.Event()
    release = threading.Event()

    def compute() -> dict[str, bool]:
        with lock:
            calls["count"] += 1
        started.set()
        release.wait(timeout=1)
        return {"ok": True}

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(cache.get_or_compute, "same", compute) for _ in range(8)]
        assert started.wait(timeout=1)
        time.sleep(0.03)
        release.set()
        values = [future.result() for future in futures]
    assert all(value == {"ok": True} for value, _hit in values)
    assert any(not hit for _value, hit in values)
    assert any(hit for _value, hit in values)
    assert calls["count"] == 1
    assert cache.stats().coalesced >= 1
