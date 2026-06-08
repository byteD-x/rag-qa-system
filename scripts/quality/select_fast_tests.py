from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path, PurePosixPath


REPO_ROOT = Path(__file__).resolve().parents[2]

_EXACT_TARGETS: dict[str, list[str]] = {
    "apps/services/api-gateway/src/app/agent_guardrails.py": [
        "tests/test_platform_ecosystem_phase2.py",
    ],
    "apps/services/api-gateway/src/app/agent_error_recovery.py": [
        "tests/test_agent_metacognition.py::TestErrorClassifier",
        "tests/test_agent_metacognition.py::TestRecoveryAction",
        "tests/test_agent_metacognition.py::TestErrorRecoveryEngine",
    ],
    "apps/services/api-gateway/src/app/agent_metacognition.py": [
        "tests/test_agent_metacognition.py",
    ],
    "apps/services/api-gateway/src/app/agent_orchestrator.py": [
        "tests/test_agent_orchestration.py",
    ],
    "apps/services/api-gateway/src/app/agent_reflection.py": [
        "tests/test_agent_capabilities.py::TestAgentReflection",
        "tests/test_agent_capabilities.py::TestIntegration::test_reflection_result_can_trigger_retry",
    ],
    "apps/services/api-gateway/src/app/business_tools.py": [
        "tests/test_agent_capabilities.py::TestToolRegistry::test_business_tools_register_idempotently",
        "tests/test_agent_capabilities.py::TestIntegration::test_business_tools_can_extend_agent_runtime_contract",
    ],
    "apps/services/api-gateway/src/app/api_key_manager.py": [
        "tests/test_platform_ecosystem_phase2.py::TestAPIKeyManager",
    ],
    "apps/services/api-gateway/src/app/complexity_classifier.py": [
        "tests/test_inference_optimization.py::TestComplexityClassifier",
        "tests/test_inference_optimization.py::TestInferenceIntegration::test_complexity_drives_cache_decision",
    ],
    "apps/services/api-gateway/src/app/context_compressor.py": [
        "tests/test_context_optimization.py::TestExtractiveCompressor",
    ],
    "apps/services/api-gateway/src/app/context_prioritizer.py": [
        "tests/test_context_optimization.py::TestContextPrioritizer",
        "tests/test_context_optimization.py::TestQuestionFeatures",
    ],
    "apps/services/api-gateway/src/app/context_window.py": [
        "tests/test_context_optimization.py::TestEstimateTokens",
        "tests/test_context_optimization.py::TestContextWindowManager",
    ],
    "apps/services/api-gateway/src/app/cost_attribution.py": [
        "tests/test_cost_management.py::TestCostAttribution",
    ],
    "apps/services/api-gateway/src/app/cost_budget.py": [
        "tests/test_agent_orchestration.py::TestCostEstimation",
        "tests/test_agent_orchestration.py::TestCostBudgetController",
    ],
    "apps/services/api-gateway/src/app/gateway_admin_routes.py": [
        "tests/test_backend_infra.py",
        "tests/test_backend_infra.py::test_import_provider_billing_route_imports_records_and_audits",
    ],
    "apps/services/api-gateway/src/app/gateway_analytics_routes.py": [
        "tests/test_backend_infra.py::test_gateway_usage_stats_includes_provider_billing",
        "tests/test_backend_infra.py::test_gateway_dashboard_route_returns_extended_payload",
    ],
    "apps/services/api-gateway/src/app/gateway_provider_billing.py": [
        "tests/test_backend_infra.py::test_provider_billing_import_request_normalizes_records",
        "tests/test_backend_infra.py::test_import_provider_billing_route_imports_records_and_audits",
        "tests/test_backend_infra.py::test_gateway_usage_stats_includes_provider_billing",
    ],
    "apps/services/api-gateway/src/app/gateway_runtime.py": [
        "tests/test_backend_infra.py",
        "tests/test_chat_workflow_resume_and_budget.py",
    ],
    "apps/services/api-gateway/src/app/gateway_schemas.py": [
        "tests/test_backend_infra.py",
        "tests/test_chat_workflow_resume_and_budget.py",
        "tests/test_platform_and_connector_extensions.py",
    ],
    "apps/services/api-gateway/src/app/gateway_chat_service.py": [
        "tests/test_backend_infra.py",
        "tests/test_chat_workflow_resume_and_budget.py",
    ],
    "apps/services/api-gateway/src/app/gateway_graph.py": [
        "tests/test_langgraph_runtime.py",
    ],
    "apps/services/api-gateway/src/app/gateway_handoff.py": [
        "tests/test_backend_infra.py::test_local_handoff_queue_claims_highest_priority_matching_skill_group",
        "tests/test_backend_infra.py::test_local_handoff_queue_does_not_claim_same_session_twice",
        "tests/test_backend_infra.py::test_claim_next_handoff_route_returns_claim_result_and_audit",
    ],
    "apps/services/api-gateway/src/app/governance_metrics.py": [
        "tests/test_governance_metrics.py",
        "tests/test_inference_optimization.py::test_gateway_metrics_summary_includes_response_cache",
    ],
    "apps/services/api-gateway/src/app/gateway_mcp_adapter.py": [
        "tests/test_mcp_adapter.py",
    ],
    "apps/services/api-gateway/src/app/gateway_mcp_routes.py": [
        "tests/test_backend_infra.py::test_gateway_mcp_route_lists_readonly_tools_and_writes_audit",
        "tests/test_backend_infra.py::test_gateway_mcp_route_calls_tool_and_blocks_non_object_arguments",
        "tests/test_backend_infra.py::test_gateway_mcp_route_requires_chat_permission",
    ],
    "apps/services/api-gateway/src/app/gateway_pricing.py": [
        "tests/test_gateway_pricing.py",
    ],
    "apps/services/api-gateway/src/app/hallucination_detector.py": [
        "tests/test_platform_ecosystem.py::TestHallucinationDetector",
    ],
    "apps/services/api-gateway/src/app/instruction_evaluator.py": [
        "tests/test_platform_ecosystem_phase2.py::TestInstructionABEvaluator",
    ],
    "apps/services/api-gateway/src/app/instruction_hotreload.py": [
        "tests/test_platform_ecosystem_phase2.py::TestInstructionHotReloader",
    ],
    "apps/services/api-gateway/src/app/instruction_merger.py": [
        "tests/test_platform_ecosystem.py::TestInstructionMerger",
    ],
    "apps/services/api-gateway/src/app/memory_extractor.py": [
        "tests/test_agent_capabilities.py::TestMemoryExtractor",
        "tests/test_agent_capabilities.py::TestIntegration::test_memory_store_upsert_and_search",
        "tests/test_memory_enhancement.py",
    ],
    "apps/services/api-gateway/src/app/memory_importance.py": [
        "tests/test_memory_enhancement.py::TestMemoryImportanceScorer",
        "tests/test_memory_enhancement.py::TestForgettingCurve",
    ],
    "apps/services/api-gateway/src/app/memory_injection.py": [
        "tests/test_memory_enhancement.py::TestMemoryInjector",
    ],
    "apps/services/api-gateway/src/app/model_health.py": [
        "tests/test_inference_optimization.py::TestModelHealth",
        "tests/test_inference_optimization.py::TestInferenceIntegration::test_model_health_informs_routing",
    ],
    "apps/services/api-gateway/src/app/pii_detector.py": [
        "tests/test_platform_ecosystem_phase2.py::TestPIIDetector",
    ],
    "apps/services/api-gateway/src/app/request_coalescer.py": [
        "tests/test_inference_optimization.py::TestRequestCoalescer",
    ],
    "apps/services/api-gateway/src/app/scene_templates.py": [
        "tests/test_platform_ecosystem.py::TestSceneTemplates",
    ],
    "apps/services/api-gateway/src/app/task_decomposer.py": [
        "tests/test_agent_capabilities.py::TestTaskDecomposer",
        "tests/test_agent_capabilities.py::TestIntegration::test_decomposition_result_feeds_agent",
    ],
    "apps/services/api-gateway/src/app/ttft_optimizer.py": [
        "tests/test_platform_ecosystem_phase2.py::TestTTFTTracker",
    ],
    "apps/services/api-gateway/src/app/semantic_cache.py": [
        "tests/test_inference_optimization.py::TestSemanticCache",
        "tests/test_inference_optimization.py::TestInferenceIntegration::test_cache_invalidate_on_document_update",
    ],
    "apps/services/api-gateway/src/app/tool_discovery.py": [
        "tests/test_platform_ecosystem_phase2.py",
    ],
    "apps/services/api-gateway/src/app/tool_pipeline.py": [
        "tests/test_platform_ecosystem_phase2.py",
    ],
    "apps/services/api-gateway/src/app/tool_registry.py": [
        "tests/test_agent_capabilities.py::TestToolRegistry",
        "tests/test_agent_capabilities.py::TestIntegration::test_tool_registry_compatible_with_agent",
        "tests/test_agent_capabilities.py::TestIntegration::test_business_tools_can_extend_agent_runtime_contract",
    ],
    "apps/services/api-gateway/src/app/tool_sandbox.py": [
        "tests/test_platform_ecosystem_phase2.py",
    ],
    "apps/services/api-gateway/src/app/tool_workflow.py": [
        "tests/test_tool_workflow.py",
        "tests/test_backend_infra.py::test_gateway_tool_workflow_route_passes_workflow_mode",
    ],
    "apps/services/api-gateway/src/app/user_profile.py": [
        "tests/test_memory_enhancement.py::TestUserProfile",
    ],
    "apps/services/knowledge-base/src/app/kb_api_support.py": [
        "tests/test_backend_infra.py::test_kb_readiness_checks_require_storage",
    ],
    "apps/services/knowledge-base/src/app/kb_system_routes.py": [
        "tests/test_backend_infra.py::test_kb_metrics_route_refreshes_snapshot_and_exports_shared_metrics",
    ],
    "apps/services/knowledge-base/src/app/kb_connector_scheduler.py": [
        "tests/test_backend_infra.py::test_connector_scheduler_manager_runs_only_when_active",
    ],
    "apps/services/knowledge-base/src/app/kb_connector_sync.py": [
        "tests/test_kb_local_sync.py",
        "tests/test_kb_notion_sync.py",
        "tests/test_platform_and_connector_extensions.py::test_execute_url_sync_dry_run_builds_text_candidates",
        "tests/test_platform_and_connector_extensions.py::test_execute_sql_sync_dry_run_converts_rows_to_documents",
    ],
    "apps/services/knowledge-base/src/app/kb_local_sync.py": [
        "tests/test_kb_local_sync.py",
    ],
    "apps/services/knowledge-base/src/app/kb_notion_sync.py": [
        "tests/test_kb_notion_sync.py",
    ],
    "apps/services/knowledge-base/src/app/kb_support.py": [
        "tests/test_backend_infra.py::test_kb_readiness_checks_require_storage",
    ],
    "apps/services/knowledge-base/src/app/kb_sql_sync.py": [
        "tests/test_platform_and_connector_extensions.py::test_execute_sql_sync_dry_run_converts_rows_to_documents",
    ],
    "apps/services/knowledge-base/src/app/kb_url_sync.py": [
        "tests/test_platform_and_connector_extensions.py::test_execute_url_sync_dry_run_builds_text_candidates",
    ],
    "apps/services/knowledge-base/src/app/kb_version_assist.py": [
        "tests/test_visual_stack.py::test_build_version_assist_marks_high_confidence_continuous_version_for_auto_apply",
        "tests/test_visual_stack.py::test_build_version_assist_respects_manual_version_metadata",
    ],
    "apps/services/knowledge-base/src/app/vector_store.py": [
        "tests/test_backend_infra.py::test_search_vector_evidence_degrades_when_qdrant_query_fails",
        "tests/test_backend_infra.py::test_kb_readiness_checks_require_storage",
    ],
    "packages/python/shared/metrics.py": [
        "tests/test_shared_metrics.py",
        "tests/test_backend_infra.py::test_gateway_tool_workflow_route_records_failure_metrics",
        "tests/test_backend_infra.py::test_kb_metrics_route_refreshes_snapshot_and_exports_shared_metrics",
    ],
    "packages/python/shared/qdrant_store.py": [
        "tests/test_backend_infra.py::test_qdrant_runtime_config_uses_safe_defaults",
        "tests/test_backend_infra.py::test_qdrant_runtime_config_masks_sensitive_endpoint_and_key",
        "tests/test_backend_infra.py::test_qdrant_runtime_config_falls_back_for_invalid_numbers",
        "tests/test_backend_infra.py::test_qdrant_point_id_is_stable_uuid",
    ],
    "scripts/quality/run_pytest_groups.py": [
        "tests/test_eval_pipeline.py",
    ],
    "scripts/quality/select_fast_tests.py": [
        "tests/test_eval_pipeline.py",
    ],
    "scripts/generate_api_route_index.py": [
        "tests/test_api_route_index.py",
    ],
    "scripts/inspect_diagnostics_support_package.py": [
        "tests/test_diagnostics_support_package.py",
    ],
    "docs/API_ROUTE_INDEX.md": [
        "tests/test_api_route_index.py",
    ],
    "scripts/quality/ci-check.ps1": [
        "tests/test_eval_pipeline.py",
    ],
    "scripts/observability/rag-daily-report.py": [
        "tests/test_observability_report.py",
    ],
    "scripts/dev/common.ps1": [
        "tests/test_eval_pipeline.py",
    ],
    "scripts/dev/preflight.ps1": [
        "tests/test_eval_pipeline.py",
    ],
    ".dockerignore": [
        "tests/test_container_assets.py",
    ],
}


def select_targets(changed_paths: list[str]) -> list[str]:
    targets: list[str] = []
    for changed_path in changed_paths:
        targets.extend(targets_for_changed_path(changed_path))
    return normalize_targets(targets)


def targets_for_changed_path(changed_path: str) -> list[str]:
    path = normalize_repo_path(changed_path)
    if not path:
        return []
    if _is_test_file(path):
        return [path]
    if path in _EXACT_TARGETS:
        targets = list(_EXACT_TARGETS[path])
        if _is_fastapi_route_source(path):
            targets.append("tests/test_api_route_index.py")
        return targets
    if path.startswith("apps/services/api-gateway/database/migrations/"):
        return ["tests/test_backend_infra.py"]
    if path.startswith("apps/services/api-gateway/src/app/") and path.endswith(".py"):
        targets = ["tests/test_backend_infra.py"]
        if _is_fastapi_route_source(path):
            targets.append("tests/test_api_route_index.py")
        return targets
    if path.startswith("apps/services/knowledge-base/src/app/connectors/local"):
        return ["tests/test_kb_local_sync.py"]
    if path.startswith("apps/services/knowledge-base/src/app/connectors/notion"):
        return ["tests/test_kb_notion_sync.py"]
    if path.startswith("apps/services/knowledge-base/src/app/") and path.endswith(".py"):
        targets = ["tests/test_ai_platform_capabilities.py", "tests/test_backend_infra.py"]
        if _is_fastapi_route_source(path):
            targets.append("tests/test_api_route_index.py")
        return targets
    if path.startswith("packages/python/shared/") and path.endswith(".py"):
        return ["tests/test_shared_stack.py", "tests/test_backend_infra.py"]
    if path.startswith("scripts/evaluation/") and path.endswith(".py"):
        return ["tests/test_eval_pipeline.py"]
    if path.startswith("scripts/quality/") and path.endswith(".py"):
        return ["tests/test_eval_pipeline.py"]
    if path in {"pyproject.toml", "requirements.txt"} or path.endswith(".lock"):
        return ["tests"]
    return []


def normalize_targets(targets: list[str]) -> list[str]:
    exact_deduped: list[str] = []
    seen: set[str] = set()
    for target in targets:
        normalized = normalize_target(target)
        if not normalized or normalized in seen:
            continue
        exact_deduped.append(normalized)
        seen.add(normalized)

    pruned: list[str] = []
    for index, target in enumerate(exact_deduped):
        if any(_covers(other, target) for other_index, other in enumerate(exact_deduped) if other_index != index):
            continue
        pruned.append(target)
    return pruned


def normalize_target(target: str) -> str:
    raw = str(target or "").strip()
    if not raw:
        return ""
    path_part, separator, node_part = raw.partition("::")
    normalized_path = normalize_repo_path(path_part)
    if not normalized_path:
        return ""
    return f"{normalized_path}{separator}{node_part}" if separator else normalized_path


def normalize_repo_path(path: str) -> str:
    raw = str(path or "").strip().replace("\\", "/")
    if not raw:
        return ""
    path_part = Path(raw)
    try:
        resolved = path_part.resolve()
        return resolved.relative_to(REPO_ROOT.resolve()).as_posix()
    except (OSError, ValueError):
        pass
    if path_part.is_absolute():
        return path_part.as_posix()
    while raw.startswith("./"):
        raw = raw[2:]
    return raw.strip("/")


def _is_fastapi_route_source(path: str) -> bool:
    return (
        path.startswith("apps/services/api-gateway/src/app/")
        or path.startswith("apps/services/knowledge-base/src/app/")
    ) and path.endswith("routes.py")


def changed_paths_from_git(*, staged: bool = False, base: str = "") -> list[str]:
    if base:
        command = ["git", "diff", "--name-only", f"{base}...HEAD"]
    elif staged:
        command = ["git", "diff", "--name-only", "--cached"]
    else:
        command = ["git", "diff", "--name-only", "HEAD"]
    completed = subprocess.run(command, cwd=REPO_ROOT, check=True, text=True, capture_output=True)
    return _dedupe_paths(completed.stdout.splitlines())


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select focused pytest targets from changed repository paths.")
    parser.add_argument("changed_paths", nargs="*", help="Changed files. Defaults to git diff --name-only HEAD.")
    parser.add_argument("--base", default="", help="Select changed files from git diff --name-only BASE...HEAD.")
    parser.add_argument("--staged", action="store_true", help="Use staged changes instead of working tree changes.")
    parser.add_argument("--fallback", default="", help="Target to output when no focused pytest target is selected.")
    parser.add_argument("--json", action="store_true", help="Print a JSON payload instead of newline-separated targets.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    changed_paths = _dedupe_paths(args.changed_paths) if args.changed_paths else changed_paths_from_git(staged=args.staged, base=args.base)
    targets = select_targets(changed_paths)
    if not targets and args.fallback:
        targets = normalize_targets([args.fallback])
    if args.json:
        print(json.dumps({"changed_paths": changed_paths, "targets": targets}, ensure_ascii=False, indent=2))
        return 0
    for target in targets:
        print(target)
    return 0


def _covers(covering_target: str, candidate_target: str) -> bool:
    if "::" in covering_target:
        return _covers_nodeid(covering_target, candidate_target)
    covering_path = _target_path(covering_target)
    candidate_path = _target_path(candidate_target)
    if covering_path == candidate_path:
        return "::" in candidate_target
    if not _is_directory_target(covering_target):
        return False
    return candidate_path.startswith(f"{covering_path.rstrip('/')}/")


def _covers_nodeid(covering_target: str, candidate_target: str) -> bool:
    if "::" not in candidate_target:
        return False
    if candidate_target == covering_target:
        return False
    if candidate_target.startswith(f"{covering_target}::"):
        return True
    return candidate_target.startswith(f"{covering_target}[")


def _target_path(target: str) -> str:
    return normalize_repo_path(target.split("::", 1)[0])


def _is_directory_target(target: str) -> bool:
    if "::" in target:
        return False
    path = _target_path(target)
    repo_path = REPO_ROOT / path
    if repo_path.exists():
        return repo_path.is_dir()
    return PurePosixPath(path).suffix == ""


def _is_test_file(path: str) -> bool:
    name = PurePosixPath(path).name
    return path.startswith("tests/") and name.startswith("test_") and name.endswith(".py")


def _dedupe_paths(paths: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for path in paths:
        normalized = normalize_repo_path(path)
        if not normalized or normalized in seen:
            continue
        result.append(normalized)
        seen.add(normalized)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
