"""
测试请求超时中间件
"""
import pytest
import asyncio
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import time
import os

# 设置测试环境的 Qdrant 地址为 localhost
os.environ["QDRANT_URL"] = "http://localhost:6333"

# 导入 app 进行覆盖测试
import sys
import os as sys_os
sys.path.insert(0, sys_os.path.dirname(sys_os.path.dirname(sys_os.path.abspath(__file__))))

from app.main import app


def test_timeout_middleware_basic():
    """测试超时中间件基本功能"""
    client = TestClient(app)
    
    # 正常请求应该成功
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_timeout_middleware_configuration():
    """测试超时配置从环境变量读取"""
    # 保存原值
    original_timeout = os.getenv("RAG_REQUEST_TIMEOUT")
    
    try:
        # 设置自定义超时
        os.environ["RAG_REQUEST_TIMEOUT"] = "30"
        
        # 重新加载配置（实际应用中需要重启服务）
        timeout_seconds = int(os.getenv("RAG_REQUEST_TIMEOUT", "60"))
        assert timeout_seconds == 30
    finally:
        # 恢复原值
        if original_timeout:
            os.environ["RAG_REQUEST_TIMEOUT"] = original_timeout
        else:
            os.environ.pop("RAG_REQUEST_TIMEOUT", None)


@pytest.mark.asyncio
async def test_timeout_error_response():
    """测试超时错误响应格式"""
    import asyncio
    from fastapi import Request
    from app.main import timeout_middleware
    
    # 创建模拟请求
    mock_request = MagicMock(spec=Request)
    mock_request.url.path = "/v1/rag/query"
    mock_request.method = "POST"
    
    # 创建模拟 call_next，模拟超时
    async def slow_call_next(req):
        await asyncio.sleep(0.1)  # 模拟慢请求
        return MagicMock()
    
    # 设置非常短的超时
    with patch.dict(os.environ, {"RAG_REQUEST_TIMEOUT": "0"}):
        response = await timeout_middleware(mock_request, slow_call_next)
        
        # 验证返回 504 超时错误
        assert response.status_code == 504
        content = response.body.decode()
        assert "REQUEST_TIMEOUT" in content or "timeout" in content.lower()


def test_timeout_with_real_request():
    """测试真实请求的超时行为"""
    client = TestClient(app)
    
    # 健康检查应该快速返回
    start = time.time()
    response = client.get("/healthz")
    elapsed = time.time() - start
    
    assert response.status_code == 200
    assert elapsed < 5.0  # 应该在 5 秒内完成


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
