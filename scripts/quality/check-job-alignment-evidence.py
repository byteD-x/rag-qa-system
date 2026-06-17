#!/usr/bin/env python3
"""Validate that job-alignment portfolio claims still have local evidence."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class EvidenceCheck:
    path: str
    keywords: tuple[str, ...] = ()


EVIDENCE_CHECKS = (
    EvidenceCheck(
        "docs/job-driven-project-enhancement.md",
        ("岗位画像", "RAG", "AI Agent", "验证命令", "最终结论"),
    ),
    EvidenceCheck(
        "docs/README.md",
        ("基于岗位画像优化项目", "面试演示手册", "生产边界说明"),
    ),
    EvidenceCheck(
        "docs/reference/job-interview-demo-runbook.md",
        ("10 分钟", "smoke_eval.py", "strict_refusal", "citation alignment"),
    ),
    EvidenceCheck(
        "docs/reference/job-production-boundary.md",
        ("生产边界", "fallback_route_key", "SKIP LOCKED", "不说"),
    ),
    EvidenceCheck(
        "docs/reference/job-retrieval-ablation-report.md",
        ("recall@1", "recall@3", "mrr", "ndcg@3"),
    ),
    EvidenceCheck(
        "docs/reference/job-readiness-summary.md",
        ("check-job-readiness.py", "passed", "partial", "failed"),
    ),
    EvidenceCheck(
        "scripts/quality/check-job-readiness.py",
        ("build_job_readiness_report", "job_retrieval_ablation.json", "agent_smoke_evidence_pack.json"),
    ),
    EvidenceCheck(
        "scripts/quality/generate-job-readiness-evidence.py",
        ("build_steps", "verify-agent-smoke-evidence.py", "check-job-readiness.py"),
    ),
    EvidenceCheck(
        "README.md",
        ("企业级 AI 问答平台", "RAG", "Agent", "最快验证路径", "环境诊断", "离线证据链", "完整本地闭环", "make doctor", "make job-evidence"),
    ),
    EvidenceCheck(
        "AI_HIGHLIGHTS.md",
        ("RAG检索增强", "Agent工具框架", "模型路由", "评测与可观测"),
    ),
    EvidenceCheck(
        "packages/python/shared/retrieval.py",
        ("EvidenceBlock", "RetrievalStats", "weighted_rrf"),
    ),
    EvidenceCheck(
        "packages/python/shared/grounded_answering.py",
        ("classify_evidence", "refusal", "ensure_citation_markers"),
    ),
    EvidenceCheck(
        "packages/python/shared/model_routing.py",
        ("resolve_model_route_plan", "fallback_route_key", "execute_with_model_route_fallback"),
    ),
    EvidenceCheck(
        "apps/services/api-gateway/src/app/agent_orchestrator.py",
        ("ExecutionPlan", "SubTask", "OrchestrationResult"),
    ),
    EvidenceCheck(
        "apps/services/api-gateway/src/app/tool_registry.py",
        ("ToolRegistry", "ToolDefinition", "get_llm_tools"),
    ),
    EvidenceCheck(
        "apps/services/api-gateway/src/app/tool_workflow.py",
        ("run_tool_workflow", "WORKFLOW_MODE_PLAN_REFLECT_REPAIR", "plan_reflect_repair"),
    ),
    EvidenceCheck(
        "apps/services/api-gateway/src/app/gateway_mcp_adapter.py",
        ("tools/list", "tools/call"),
    ),
    EvidenceCheck(
        "apps/services/api-gateway/src/app/semantic_cache.py",
        ("SemanticCache", "corpus_key", "corpus_ids", "similarity"),
    ),
    EvidenceCheck(
        "apps/services/api-gateway/src/app/model_health.py",
        ("ModelHealth", "circuit", "latency"),
    ),
    EvidenceCheck(
        "tests/test_eval_pipeline.py",
        ("citation_alignment", "faithfulness", "recall_at_"),
    ),
    EvidenceCheck(
        "tests/test_agent_capabilities.py",
        ("ToolRegistry", "TaskDecomposer", "AgentReflection"),
    ),
    EvidenceCheck(
        "tests/test_inference_optimization.py",
        ("SemanticCache", "ModelHealth", "RequestCoalescer"),
    ),
    EvidenceCheck(
        "tests/fixtures/evals/retrieval-ablation-fixture.json",
        ("expected_unit_ids", "candidates"),
    ),
    EvidenceCheck(
        ".github/workflows/ci.yml",
        ("Job readiness evidence", "generate-job-readiness-evidence.py", "Docker compose config"),
    ),
    EvidenceCheck(
        "docker-compose.yml",
        ("kb-service", "qdrant", "gateway"),
    ),
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def validate_check(root: Path, check: EvidenceCheck) -> list[str]:
    path = root / check.path
    if not path.exists():
        return [f"{check.path}: missing file"]
    if not path.is_file():
        return [f"{check.path}: not a file"]

    try:
        text = read_text(path)
    except UnicodeDecodeError as exc:
        return [f"{check.path}: invalid UTF-8 at byte {exc.start}"]

    failures: list[str] = []
    for keyword in check.keywords:
        if keyword not in text:
            failures.append(f"{check.path}: missing keyword {keyword!r}")
    return failures


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help=f"repository root to scan (default: {REPO_ROOT})",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = args.root.resolve()
    failures: list[str] = []

    for check in EVIDENCE_CHECKS:
        failures.extend(validate_check(root, check))

    if failures:
        print("Job-alignment evidence check failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(f"Job-alignment evidence check passed. Checked {len(EVIDENCE_CHECKS)} evidence files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
