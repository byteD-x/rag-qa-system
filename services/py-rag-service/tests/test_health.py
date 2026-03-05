import os
from fastapi.testclient import TestClient

from app.main import app

# 设置测试环境的 Qdrant 地址为 localhost（因为测试客户端在本地运行）
os.environ["QDRANT_URL"] = "http://localhost:6333"

client = TestClient(app)


def test_healthz() -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_query_returns_contract_compliant_response() -> None:
    resp = client.post(
        "/v1/rag/query",
        json={
            "question": "请总结文档中的核心结论",
            "scope": {
                "mode": "single",
                "corpus_ids": ["11111111-1111-1111-1111-111111111111"],
                "document_ids": [],
                "allow_common_knowledge": False,
            },
        },
    )
    assert resp.status_code == 200

    body = resp.json()
    assert len(body["answer_sentences"]) >= 1

    citation_ids = {item["citation_id"] for item in body["citations"]}
    for sentence in body["answer_sentences"]:
        assert sentence["evidence_type"] in {"source", "common_knowledge"}
        if sentence["evidence_type"] == "source":
            assert len(sentence["citation_ids"]) >= 1
            for citation_id in sentence["citation_ids"]:
                assert citation_id in citation_ids
        else:
            assert sentence["text"].startswith("【常识补充】")
            assert sentence["citation_ids"] == []


def test_query_rejects_invalid_scope_uuid() -> None:
    resp = client.post(
        "/v1/rag/query",
        json={
            "question": "测试问题",
            "scope": {
                "mode": "single",
                "corpus_ids": ["not-a-uuid"],
                "document_ids": [],
                "allow_common_knowledge": False,
            },
        },
    )

    assert resp.status_code == 422
