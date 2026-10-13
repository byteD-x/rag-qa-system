#!/usr/bin/env python
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages/python"))

from shared.eval_metrics import recall_at_k_ids, reciprocal_rank
from shared.text_search import score_term_overlap


DEFAULT_SUITE = REPO_ROOT / "tests/fixtures/evals/enterprise-policy-quality-v2.json"
DEFAULT_REPORT = REPO_ROOT / "artifacts/reports/policy-quality-v2-offline.json"
DEFAULT_ONLINE_CASES = REPO_ROOT / "artifacts/reports/policy-quality-v2-online.json"


def parse_sections(corpus: str) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    document = ""
    title = ""
    lines: list[str] = []

    def flush() -> None:
        if not title:
            return
        body = "\n".join(lines).strip()
        if not body or title in sections:
            raise ValueError(f"empty or duplicate section: {title}")
        sections[title] = {"document": document, "text": body}

    for line in corpus.splitlines():
        if line.startswith("## "):
            flush()
            title, lines = "", []
            document = line[3:].strip()
        elif line.startswith("### "):
            flush()
            title, lines = line[4:].strip(), []
        elif title:
            lines.append(line)
    flush()
    return sections


def load_suite(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, str]], list[dict[str, Any]], dict[str, str]]:
    source = path.read_bytes()
    suite = json.loads(source)
    corpus_path = path.parent / str(suite["corpus"])
    corpus_bytes = corpus_path.read_bytes()
    sections = parse_sections(corpus_bytes.decode("utf-8"))
    if not suite.get("dataset_version") or not sections:
        raise ValueError("suite requires dataset_version and nonempty corpus")

    cases: list[dict[str, Any]] = []
    used_questions: set[str] = set()

    def add_case(*, case_id: str, question: str, expected: list[str], terms: list[str], split: str, category: str) -> None:
        question = question.strip()
        if not question or question in used_questions:
            raise ValueError(f"empty or duplicate question: {question}")
        if split not in {"dev", "holdout"}:
            raise ValueError(f"invalid split: {split}")
        if any(section not in sections for section in expected):
            raise ValueError(f"unknown expected section: {expected}")
        evidence = " ".join(sections[section]["text"] for section in expected)
        if any(term not in evidence for term in terms):
            raise ValueError(f"answer/quote term missing from gold evidence: {case_id}")
        used_questions.add(question)
        cases.append(
            {
                "id": case_id,
                "category": category,
                "dataset_version": suite["dataset_version"],
                "split": split,
                "question": question,
                "expected_sections": expected,
                "expected_quote_terms": terms,
                "expected_answer_terms": terms,
                "min_citations": len(expected),
                "must_refuse_without_evidence": not expected,
            }
        )

    for index, group in enumerate(suite["sections"], start=1):
        expected = [str(group["section"])]
        questions = group["questions"]
        answers = group["answers"]
        if len(questions) < 3 or len(answers) != len(questions) or any(not terms for terms in answers):
            raise ValueError(f"insufficient variants or gold answers: {expected}")
        for variant, question in enumerate(questions, start=1):
            add_case(
                case_id=f"quality-single-{index:02d}-{variant}",
                question=str(question),
                expected=expected,
                terms=[str(term) for term in answers[variant - 1]],
                split="holdout" if variant == len(questions) else "dev",
                category="policy_single",
            )

    for index, item in enumerate(suite.get("extra_cases", []), start=1):
        add_case(
            case_id=f"quality-extra-{index:02d}",
            question=str(item["question"]),
            expected=[str(item["section"])],
            terms=[str(term) for term in item["answers"]],
            split="holdout" if index % 2 == 0 else "dev",
            category="policy_single",
        )

    for index, group in enumerate(suite["multi_section"], start=1):
        expected = [str(section) for section in group["sections"]]
        if len(expected) < 2 or len(set(expected)) != len(expected):
            raise ValueError(f"invalid multi-section label: {index}")
        add_case(
            case_id=f"quality-multi-{index:02d}",
            question=str(group["question"]),
            expected=expected,
            terms=[str(term) for term in group["terms"]],
            split="holdout" if index % 2 == 0 else "dev",
            category="policy_multi",
        )

    for index, question in enumerate(suite["unanswerable"], start=1):
        add_case(
            case_id=f"quality-refusal-{index:02d}",
            question=str(question),
            expected=[],
            terms=[],
            split="holdout" if index % 2 == 0 else "dev",
            category="policy_unanswerable",
        )

    hashes = {
        "suite_sha256": hashlib.sha256(source).hexdigest(),
        "corpus_sha256": hashlib.sha256(corpus_bytes).hexdigest(),
    }
    return suite, sections, cases, hashes


def rank_lexical(question: str, sections: dict[str, dict[str, str]]) -> list[str]:
    scored = []
    for title, item in sections.items():
        score = 2.0 * score_term_overlap(question, title) + score_term_overlap(question, item["text"])
        scored.append((title, score))
    return [title for title, score in sorted(scored, key=lambda item: item[1], reverse=True) if score > 0]


def evaluate(cases: list[dict[str, Any]], sections: dict[str, dict[str, str]]) -> dict[str, Any]:
    details: list[dict[str, Any]] = []
    for case in cases:
        expected = set(case["expected_sections"])
        if not expected:
            continue  # 无答案题只用于在线拒答评测；词法召回不能证明拒答能力。
        ranked = rank_lexical(case["question"], sections)
        relevance = [int(title in expected) for title in ranked]
        details.append(
            {
                "id": case["id"],
                "split": case["split"],
                "category": case["category"],
                "expected_sections": case["expected_sections"],
                "top_3": ranked[:3],
                "recall_at_1": recall_at_k_ids(expected, ranked, 1),
                "recall_at_3": recall_at_k_ids(expected, ranked, 3),
                "recall_at_5": recall_at_k_ids(expected, ranked, 5),
                "mrr": reciprocal_rank(relevance),
            }
        )

    summary: dict[str, dict[str, float | int]] = {}
    for label, rows in {
        "overall": details,
        "dev": [row for row in details if row["split"] == "dev"],
        "holdout": [row for row in details if row["split"] == "holdout"],
        "single": [row for row in details if row["category"] == "policy_single"],
        "multi": [row for row in details if row["category"] == "policy_multi"],
    }.items():
        summary[label] = {"count": len(rows)}
        for metric in ("recall_at_1", "recall_at_3", "recall_at_5", "mrr"):
            summary[label][metric] = round(sum(row[metric] for row in rows) / len(rows), 4) if rows else 0.0
    return {"summary": summary, "details": details}


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate annotated policy cases against raw corpus text; export online cases.")
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--online-output", type=Path, default=DEFAULT_ONLINE_CASES)
    args = parser.parse_args()

    suite, sections, cases, hashes = load_suite(args.suite)
    offline = evaluate(cases, sections)
    counts = {category: sum(case["category"] == category for case in cases) for category in ("policy_single", "policy_multi", "policy_unanswerable")}
    split_counts = {split: sum(case["split"] == split for case in cases) for split in ("dev", "holdout")}
    report = {
        "dataset_version": suite["dataset_version"],
        "method": "raw-corpus lexical overlap diagnostic; no vector search, LLM, ACL, or network",
        "section_count": len(sections),
        "case_count": len(cases),
        "case_counts": counts,
        "split_counts": split_counts,
        "hashes": hashes,
        **offline,
    }
    for output, data in ((args.output, report), (args.online_output, cases)):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("dataset_version", "section_count", "case_count", "case_counts", "split_counts", "summary")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
