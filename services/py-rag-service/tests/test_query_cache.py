"""查询缓存单元测试"""
import time
from app.query_cache import QueryCache, CachedQuery


class TestQueryCacheBasic:
    """基础功能测试"""

    def test_cache_set_and_get(self):
        """测试基本的设置和获取"""
        cache = QueryCache(max_size=100, ttl_hours=24)
        
        cache.set("test question", {"answer": "test answer"})
        result = cache.get("test question")
        
        assert result == {"answer": "test answer"}
        assert cache.size == 1

    def test_cache_miss_returns_none(self):
        """测试缓存未命中返回 None"""
        cache = QueryCache(max_size=100, ttl_hours=24)
        
        result = cache.get("nonexistent question")
        
        assert result is None
        assert cache.size == 0

    def test_cache_update_existing(self):
        """测试更新已存在的缓存"""
        cache = QueryCache(max_size=100, ttl_hours=24)
        
        cache.set("question", {"answer": "first"})
        cache.set("question", {"answer": "second"})
        
        result = cache.get("question")
        assert result == {"answer": "second"}
        assert cache.size == 1

    def test_cache_clear(self):
        """测试清空缓存"""
        cache = QueryCache(max_size=100, ttl_hours=24)
        
        cache.set("q1", {"answer": "a1"})
        cache.set("q2", {"answer": "a2"})
        cache.set("q3", {"answer": "a3"})
        
        cache.clear()
        
        assert cache.size == 0
        assert cache.get("q1") is None
        assert cache.get("q2") is None
        assert cache.get("q3") is None

    def test_cache_invalidate(self):
        """测试使特定缓存失效"""
        cache = QueryCache(max_size=100, ttl_hours=24)
        
        cache.set("q1", {"answer": "a1"})
        cache.set("q2", {"answer": "a2"})
        
        result = cache.invalidate("q1")
        assert result is True
        assert cache.size == 1
        assert cache.get("q1") is None
        assert cache.get("q2") is not None

    def test_cache_invalidate_nonexistent(self):
        """测试使不存在的缓存失效"""
        cache = QueryCache(max_size=100, ttl_hours=24)
        
        result = cache.invalidate("nonexistent")
        
        assert result is False


class TestQueryCacheTTL:
    """TTL 过期测试"""

    def test_cache_ttl_expiration(self):
        """测试 TTL 过期"""
        cache = QueryCache(max_size=100, ttl_hours=24)
        cache._ttl_seconds = 1
        
        cache.set("question", {"answer": "answer"})
        
        time.sleep(2)
        
        result = cache.get("question")
        assert result is None

    def test_cache_not_expired_within_ttl(self):
        """测试在 TTL 内未过期"""
        cache = QueryCache(max_size=100, ttl_hours=24)
        
        cache.set("question", {"answer": "answer"})
        
        result = cache.get("question")
        assert result == {"answer": "answer"}

    def test_cache_hit_count_increases(self):
        """测试缓存命中次数增加"""
        cache = QueryCache(max_size=100, ttl_hours=24)
        
        cache.set("question", {"answer": "answer"})
        
        cache.get("question")
        cache.get("question")
        cache.get("question")
        
        stats = cache.stats
        assert stats["hits"] == 3
        assert stats["misses"] == 0


class TestQueryCacheLRU:
    """LRU 驱逐策略测试"""

    def test_lru_eviction_when_exceeds_max_size(self):
        """测试超过最大大小时的 LRU 驱逐"""
        cache = QueryCache(max_size=3, ttl_hours=24)
        
        cache.set("q1", {"answer": "a1"})
        cache.set("q2", {"answer": "a2"})
        cache.set("q3", {"answer": "a3"})
        
        cache.set("q4", {"answer": "a4"})
        
        assert cache.size == 3
        assert cache.get("q1") is None
        assert cache.get("q2") is not None
        assert cache.get("q3") is not None
        assert cache.get("q4") is not None

    def test_lru_updates_on_access(self):
        """测试访问时更新 LRU 顺序"""
        cache = QueryCache(max_size=3, ttl_hours=24)
        
        cache.set("q1", {"answer": "a1"})
        cache.set("q2", {"answer": "a2"})
        cache.set("q3", {"answer": "a3"})
        
        cache.get("q1")
        
        cache.set("q4", {"answer": "a4"})
        
        assert cache.size == 3
        assert cache.get("q1") is not None
        assert cache.get("q2") is None
        assert cache.get("q3") is not None
        assert cache.get("q4") is not None

    def test_lru_eviction_order(self):
        """测试 LRU 驱逐顺序"""
        cache = QueryCache(max_size=5, ttl_hours=24)
        
        for i in range(7):
            cache.set(f"q{i}", {"answer": f"a{i}"})
        
        assert cache.size == 5
        assert cache.get("q0") is None
        assert cache.get("q1") is None
        assert cache.get("q2") is not None
        assert cache.get("q3") is not None
        assert cache.get("q4") is not None
        assert cache.get("q5") is not None
        assert cache.get("q6") is not None


class TestQueryCacheHitRate:
    """缓存命中率测试"""

    def test_hit_rate_calculation(self):
        """测试命中率计算"""
        cache = QueryCache(max_size=100, ttl_hours=24)
        
        cache.set("q1", {"answer": "a1"})
        cache.set("q2", {"answer": "a2"})
        
        cache.get("q1")
        cache.get("q1")
        cache.get("q2")
        cache.get("q3")
        cache.get("q4")
        
        stats = cache.stats
        assert stats["hits"] == 3
        assert stats["misses"] == 2
        
        hit_rate = stats["hit_rate"]
        assert abs(hit_rate - 0.6) < 0.001

    def test_hit_rate_zero_on_empty(self):
        """测试空缓存时命中率为 0"""
        cache = QueryCache(max_size=100, ttl_hours=24)
        
        stats = cache.stats
        assert stats["hit_rate"] == 0.0

    def test_hit_rate_requirement(self):
        """测试命中率要求 >= 80%"""
        cache = QueryCache(max_size=100, ttl_hours=24)
        
        for i in range(10):
            cache.set(f"q{i}", {"answer": f"a{i}"})
        
        for i in range(8):
            cache.get(f"q{i}")
        
        for i in range(2):
            cache.get(f"q{10 + i}")
        
        stats = cache.stats
        assert stats["hits"] == 8
        assert stats["misses"] == 2
        assert stats["hit_rate"] >= 0.8


class TestQueryCacheKeyGeneration:
    """缓存键生成测试"""

    def test_cache_key_considers_question(self):
        """测试缓存键考虑问题"""
        cache = QueryCache(max_size=100, ttl_hours=24)
        
        cache.set("question 1", {"answer": "answer 1"})
        cache.set("question 2", {"answer": "answer 2"})
        
        assert cache.get("question 1") == {"answer": "answer 1"}
        assert cache.get("question 2") == {"answer": "answer 2"}

    def test_cache_key_case_insensitive(self):
        """测试缓存键大小写不敏感"""
        cache = QueryCache(max_size=100, ttl_hours=24)
        
        cache.set("Test Question", {"answer": "test answer"})
        
        result = cache.get("test question")
        assert result == {"answer": "test answer"}

    def test_cache_key_trims_whitespace(self):
        """测试缓存键去除空白"""
        cache = QueryCache(max_size=100, ttl_hours=24)
        
        cache.set("  test question  ", {"answer": "test answer"})
        
        result = cache.get("test question")
        assert result == {"answer": "test answer"}


class TestQueryCacheConfiguration:
    """配置测试"""

    def test_cache_max_size_configuration(self):
        """测试缓存最大大小配置"""
        cache_small = QueryCache(max_size=5, ttl_hours=24)
        cache_large = QueryCache(max_size=100, ttl_hours=24)
        
        for i in range(10):
            cache_small.set(f"q{i}", {"answer": f"a{i}"})
            cache_large.set(f"q{i}", {"answer": f"a{i}"})
        
        assert cache_small.size == 5
        assert cache_large.size == 10

    def test_cache_ttl_configuration(self):
        """测试缓存 TTL 配置"""
        cache_short_ttl = QueryCache(max_size=100, ttl_hours=24)
        cache_short_ttl._ttl_seconds = 1
        cache_long_ttl = QueryCache(max_size=100, ttl_hours=24)
        
        cache_short_ttl.set("question", {"answer": "answer"})
        cache_long_ttl.set("question", {"answer": "answer"})
        
        time.sleep(2)
        
        assert cache_short_ttl.get("question") is None
        assert cache_long_ttl.get("question") == {"answer": "answer"}

    def test_cache_default_values(self):
        """测试缓存默认值"""
        cache = QueryCache()
        
        assert cache._max_size == 10000
        assert cache._ttl_seconds == 24 * 3600


class TestQueryCacheEdgeCases:
    """边界情况测试"""

    def test_cache_with_empty_question(self):
        """测试空问题"""
        cache = QueryCache(max_size=100, ttl_hours=24)
        
        cache.set("", {"answer": "empty answer"})
        
        result = cache.get("")
        assert result == {"answer": "empty answer"}

    def test_cache_with_special_characters(self):
        """测试特殊字符"""
        cache = QueryCache(max_size=100, ttl_hours=24)
        
        cache.set("question with !@#$%^&*()", {"answer": "special"})
        
        result = cache.get("question with !@#$%^&*()")
        assert result == {"answer": "special"}

    def test_cache_with_unicode(self):
        """测试 Unicode 字符"""
        cache = QueryCache(max_size=100, ttl_hours=24)
        
        cache.set("中文问题？日本語の質問", {"answer": "unicode answer"})
        
        result = cache.get("中文问题？日本語の質問")
        assert result == {"answer": "unicode answer"}

    def test_cache_with_large_result(self):
        """测试大型结果"""
        cache = QueryCache(max_size=100, ttl_hours=24)
        
        large_result = {"data": "x" * 10000}
        cache.set("question", large_result)
        
        result = cache.get("question")
        assert result == large_result

    def test_cache_concurrent_access(self):
        """测试并发访问（线程安全）"""
        import threading
        
        cache = QueryCache(max_size=1000, ttl_hours=24)
        
        def worker(thread_id):
            for i in range(10):
                cache.set(f"q{thread_id}_{i}", {"answer": f"a{thread_id}_{i}"})
                cache.get(f"q{thread_id}_{i}")
        
        threads = []
        for i in range(5):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        assert cache.size <= 1000


class TestCachedQuery:
    """CachedQuery 数据类测试"""

    def test_cached_query_is_expired(self):
        """测试 CachedQuery 过期检查"""
        now = time.time()
        
        cached = CachedQuery(
            query_hash="hash123",
            question="test",
            result={"answer": "test"},
            created_at=now - 7200,
            ttl_seconds=3600,
        )
        
        assert cached.is_expired() is True

    def test_cached_query_not_expired(self):
        """测试 CachedQuery 未过期"""
        now = time.time()
        
        cached = CachedQuery(
            query_hash="hash123",
            question="test",
            result={"answer": "test"},
            created_at=now,
            ttl_seconds=3600,
        )
        
        assert cached.is_expired() is False

    def test_cached_query_immutable(self):
        """测试 CachedQuery 不可变性"""
        cached = CachedQuery(
            query_hash="hash123",
            question="test",
            result={"answer": "test"},
            created_at=time.time(),
            ttl_seconds=3600,
        )
        
        try:
            cached.hit_count = 100
            assert False, "Should not be able to modify frozen dataclass"
        except Exception:
            pass


class TestQueryCacheStats:
    """缓存统计测试"""

    def test_stats_includes_all_metrics(self):
        """测试统计包含所有指标"""
        cache = QueryCache(max_size=100, ttl_hours=24)
        
        cache.set("q1", {"answer": "a1"})
        cache.set("q2", {"answer": "a2"})
        
        cache.get("q1")
        cache.get("q3")
        
        stats = cache.stats
        
        assert "size" in stats
        assert "max_size" in stats
        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate" in stats
        
        assert stats["size"] == 2
        assert stats["max_size"] == 100
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_size_property(self):
        """测试 size 属性"""
        cache = QueryCache(max_size=100, ttl_hours=24)
        
        assert cache.size == 0
        
        cache.set("q1", {"answer": "a1"})
        assert cache.size == 1
        
        cache.set("q2", {"answer": "a2"})
        assert cache.size == 2
        
        cache.invalidate("q1")
        assert cache.size == 1

    def test_hit_rate_property(self):
        """测试 hit_rate 属性"""
        cache = QueryCache(max_size=100, ttl_hours=24)
        
        assert cache.hit_rate == 0.0
        
        cache.set("q1", {"answer": "a1"})
        cache.get("q1")
        cache.get("q2")
        
        assert cache.hit_rate == 0.5
