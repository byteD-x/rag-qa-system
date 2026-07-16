"""记忆优化模块测试 —— 覆盖 memory_importance、user_profile。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from conftest import clear_app_modules


REPO_ROOT = Path(__file__).resolve().parents[1]
GATEWAY_SRC = REPO_ROOT / "apps/services/api-gateway/src"


def _prioritize_sys_path(path: Path) -> None:
    target = str(path)
    try:
        sys.path.remove(target)
    except ValueError:
        pass
    sys.path.insert(0, target)
    clear_app_modules()


def _import_gateway(module_name: str, monkeypatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "https://test.example.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_PRICE_CURRENCY", "CNY")
    monkeypatch.setenv("LLM_PRICE_TIERS_JSON", "[]")
    monkeypatch.setenv("LLM_INPUT_PRICE_PER_1K_TOKENS", "0")
    monkeypatch.setenv("LLM_OUTPUT_PRICE_PER_1K_TOKENS", "0")
    monkeypatch.setenv("LLM_DEFAULT_MAX_TOKENS", "1024")
    monkeypatch.setenv("KB_SERVICE_URL", "http://localhost:8200")
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://test:test@localhost:5432/test")
    monkeypatch.setenv("GATEWAY_GRAPH_CHECKPOINTER", "memory")
    monkeypatch.setenv("GATEWAY_TIMEOUT_SECONDS", "30")
    _prioritize_sys_path(GATEWAY_SRC)
    for name in list(sys.modules.keys()):
        if name.startswith("app."):
            sys.modules.pop(name, None)


# ============================================================================
# 记忆重要性评分测试
# ============================================================================


class TestMemoryImportanceScorer:
    def test_score_preference(self, monkeypatch) -> None:
        _import_gateway("app.memory_importance", monkeypatch)
        from app.memory_importance import MemoryImportanceScorer

        scorer = MemoryImportanceScorer()

        class StubMemory:
            memory_type = "preference"
            confidence = 0.95
            importance = 0.85
            last_accessed_at = 0.0

        detail = scorer.score(StubMemory(), access_count=5, mention_count=3)
        assert detail.composite > 0.5
        assert detail.memory_type_weight > 0.5

    def test_score_with_recency(self, monkeypatch) -> None:
        _import_gateway("app.memory_importance", monkeypatch)
        from app.memory_importance import MemoryImportanceScorer

        scorer = MemoryImportanceScorer()

        class StubMemory:
            memory_type = "fact"
            confidence = 0.8
            importance = 0.6
            last_accessed_at = time.time() - 3600  # 1 小时前

        detail = scorer.score(StubMemory(), access_count=2, mention_count=1)
        # 最近访问应有加分
        assert detail.recency_bonus > 0.0

    def test_decay_factor_new(self, monkeypatch) -> None:
        _import_gateway("app.memory_importance", monkeypatch)
        from app.memory_importance import MemoryImportanceScorer

        scorer = MemoryImportanceScorer()

        class StubMemory:
            memory_type = "preference"
            importance = 0.9
            decay_rate = 0.05
            last_accessed_at = time.time()
            access_count = 0
            created_at = time.time()

        factor = scorer.decay_factor(StubMemory())
        assert factor >= 0.95  # 刚创建的，几乎不衰减

    def test_effective_importance(self, monkeypatch) -> None:
        _import_gateway("app.memory_importance", monkeypatch)
        from app.memory_importance import MemoryImportanceScorer

        scorer = MemoryImportanceScorer()

        class StubMemory:
            memory_type = "preference"
            importance = 0.8
            decay_rate = 0.05
            last_accessed_at = time.time()
            access_count = 0
            created_at = time.time()

        eff = scorer.effective_importance(StubMemory())
        assert eff >= 0.75

    def test_memory_health_needs_review(self, monkeypatch) -> None:
        _import_gateway("app.memory_importance", monkeypatch)
        from app.memory_importance import MemoryImportanceScorer

        scorer = MemoryImportanceScorer()

        class StubMemory:
            memory_type = "knowledge"
            importance = 0.3
            decay_rate = 0.2
            last_accessed_at = time.time() - 90 * 86400  # 90 天前
            access_count = 0
            created_at = time.time() - 90 * 86400

        health = scorer.memory_health(StubMemory())
        assert health.needs_review  # 低重要性 + 长时间未访问

    def test_record_access(self, monkeypatch) -> None:
        _import_gateway("app.memory_importance", monkeypatch)
        from app.memory_importance import MemoryImportanceScorer

        scorer = MemoryImportanceScorer()

        class MutableMemory:
            memory_type = "fact"
            importance = 0.5
            decay_rate = 0.1
            last_accessed_at = 0.0
            access_count = 0

        mem = MutableMemory()
        scorer.record_access(mem)
        assert mem.access_count == 1
        assert mem.last_accessed_at > 0


class TestForgettingCurve:
    def test_forgetting_retention_monotonic(self, monkeypatch) -> None:
        _import_gateway("app.memory_importance", monkeypatch)
        from app.memory_importance import forgetting_retention

        r1 = forgetting_retention(1)  # 1 小时
        r2 = forgetting_retention(24)  # 24 小时
        r3 = forgetting_retention(168)  # 7 天
        assert r1 >= r2 >= r3  # 随时间递减

    def test_high_importance_slower_decay(self, monkeypatch) -> None:
        _import_gateway("app.memory_importance", monkeypatch)
        from app.memory_importance import forgetting_retention

        r_high = forgetting_retention(168, importance=0.9)
        r_low = forgetting_retention(168, importance=0.2)
        assert r_high > r_low  # 高重要性遗忘更慢

    def test_access_count_boosts_retention(self, monkeypatch) -> None:
        _import_gateway("app.memory_importance", monkeypatch)
        from app.memory_importance import forgetting_retention

        r_accessed = forgetting_retention(168, access_count=10)
        r_not = forgetting_retention(168, access_count=0)
        assert r_accessed > r_not  # 多次访问 -> 记忆更强


# ============================================================================
# 用户画像测试
# ============================================================================


class TestUserProfile:
    def test_empty_profile(self, monkeypatch) -> None:
        _import_gateway("app.user_profile", monkeypatch)
        from app.user_profile import UserProfile, UserProfileBuilder

        builder = UserProfileBuilder(store=None)
        profile = UserProfile(user_id="test-user")
        assert profile.user_id == "test-user"
        assert profile.role == ""
        assert profile.total_memories == 0

    def test_summarize_empty(self, monkeypatch) -> None:
        _import_gateway("app.user_profile", monkeypatch)
        from app.user_profile import UserProfile, UserProfileBuilder, summarize_user_profile

        profile = UserProfile(user_id="test")
        summary = summarize_user_profile(profile)
        assert isinstance(summary, str)

    def test_summarize_with_role(self, monkeypatch) -> None:
        _import_gateway("app.user_profile", monkeypatch)
        from app.user_profile import UserProfile, UserProfileBuilder, summarize_user_profile

        profile = UserProfile(
            user_id="test",
            role="后端开发工程师",
            department="支付平台部",
            answer_style="简洁",
            expertise_areas=["微服务", "数据库"],
            known_versions=["v3.0"],
            skill_level="expert",
        )
        summary = summarize_user_profile(profile)
        assert "后端开发工程师" in summary
        assert "支付平台部" in summary
        assert "简洁" in summary


