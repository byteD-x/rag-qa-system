from pathlib import Path

from worker.parser import parse_document


def test_parse_txt(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("line1\nline2", encoding="utf-8")
    segments = parse_document(file_path, "txt")
    assert len(segments) == 1
    assert "line1" in segments[0].text
    assert segments[0].page_or_loc == "text:1"