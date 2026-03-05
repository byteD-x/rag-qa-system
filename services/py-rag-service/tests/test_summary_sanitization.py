from app.main import sanitize_summary


def test_sanitize_summary_rejects_evidence_dump_format() -> None:
    raw = "[1] file=tmp-chat-e2e.txt loc=text:1 chapter one ... [2] file=tmp-chat-e2e.txt loc=text:1"
    assert sanitize_summary(raw) == ""


def test_sanitize_summary_keeps_normal_short_answer() -> None:
    raw = "  RAG 是将检索与生成结合的问答方案。  "
    assert sanitize_summary(raw) == "RAG 是将检索与生成结合的问答方案。"
