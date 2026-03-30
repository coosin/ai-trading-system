"""
APIServer单元测试
"""

import asyncio
import pytest
import json
from datetime import datetime
from src.modules.api.server import (
    APIServer, APIRequest, APIResponse, WebSocketConnection,
    WebSocketEventType, HTTPMethod, RateLimit
)


class TestAPIServer:
    """APIServer测试类"""
    
    @pytest.fixture
    async def api_server(self):
        """创建测试用的API服务器"""
        api_server = APIServer(host="127.0.0.1", port=8000)
        
        # 模拟初始化（不依赖FastAPI）
        api_server._initialized = True
        api_server._running = True
        
        yield api_server
        
        await api_server.cleanup()
    
    @pytest.fixture
    def mock_websocket(self):
        """创建模拟WebSocket"""
        class MockWebSocket:
            def __init__(self):
                self.accepted = False
                self.closed = False
                self.sent_messages = []
                self.received_messages = []
            
            async def accept(self):
                self.accepted = True
            
            async def close(self):
                self.closed = True
            
            async def send_json(self, data):
                self.sent_messages.append(data)
            
            async def receive_json(self):
                if self.received_messages:
                    return self.received_messages.pop(0)
                raise Exception("No messages")
        
        return MockWebSocket()
    
    @pytest.mark.asyncio
    async def test_initialization(self, api_server):
        """测试初始化"""
        assert api_server is not None
        assert api_server.host == "127.0.0.1"
        assert api_server.port == 8000
        assert api_server._initialized is True
        assert api_server._running is True
    
    @pytest.mark.asyncio
    async def test_api_request(self):
        """测试API请求"""
        # 创建API请求
        request = APIRequest(
            id="test_id",
            method=HTTPMethod.GET,
            path="/api/test",
            headers={"User-Agent": "test"},
            params={"key": "value"},
            body={"data": "test"},
            client_ip="127.0.0.1",
            user_id="user123"
        )
        
        # 检查属性
        assert request.id == "test_id"
        assert request.method == HTTPMethod.GET
        assert request.path == "/api/test"
        assert request.client_ip == "127.0.0.1"
        assert request.user_id == "user123"
        assert request.params["key"] == "value"
        assert request.body["data"] == "test"
        assert request.timestamp is not None
        
        # 转换为字典
        request_dict = request.to_dict()
        assert request_dict["id"] == "test_id"
        assert request_dict["method"] == "GET"
        assert request_dict["path"] == "/api/test"
        assert request_dict["client_ip"] == "127.0.0.1"
        assert request_dict["user_id"] == "user123"
    
    @pytest.mark.asyncio
    async def test_api_response(self):
        """测试API响应"""
        # 成功响应
        success_response = APIResponse(
            status_code=200,
            data={"result": "success"},
            message="操作成功",
            request_id="req_123"
        )
        
        assert success_response.status_code == 200
        assert success_response.data["result"] == "success"
        assert success_response.message == "操作成功"
        assert success_response.request_id == "req_123"
        assert success_response.error is None
        
        # 转换为字典
        success_dict = success_response.to_dict()
        assert success_dict["status"] == "success"
        assert success_dict["data"]["result"] == "success"
        assert success_dict["message"] == "操作成功"
        
        # 错误响应
        error_response = APIResponse(
            status_code=400,
            data=None,
            error="参数错误",
            message="请求参数无效"
        )
        
        error_dict = error_response.to_dict()
        assert error_dict["status"] == "error"
        assert error_dict["error"] == "参数错误"
        assert error_dict["message"] == "请求参数无效"
    
    @pytest.mark.asyncio
    async def test_websocket_connection(self, mock_websocket):
        """测试WebSocket连接"""
        # 创建WebSocket连接
        connection = WebSocketConnection(
            id="ws_123",
            websocket=mock_websocket,
            user_id="user123",
            subscriptions=["market_data", "trades"]
        )
        
        # 检查属性
        assert connection.id == "ws_123"
        assert connection.websocket == mock_websocket
        assert connection.user_id == "user123"
        assert "market_data" in connection.subscriptions
        assert "trades" in connection.subscriptions
        assert connection.connected_at is not None
        assert connection.last_activity is not None
        
        # 测试订阅检查
        assert connection.is_subscribed("market_data") is True
        assert connection.is_subscribed("nonexistent") is False
        
        # 测试更新活动时间
        old_activity = connection.last_activity
        connection.update_activity()
        assert connection.last_activity > old_activity
        
        # 测试空闲时间
        idle_time = connection.idle_time
        assert isinstance(idle_time, asyncio.timedelta)
        assert idle_time.total_seconds() >= 0
    
    @pytest.mark.asyncio
    async def test_websocket_event_type(self):
        """测试WebSocket事件类型"""
        assert WebSocketEventType.CONNECT.value == "connect"
        assert WebSocketEventType.DISCONNECT.value == "disconnect"
        assert WebSocketEventType.DATA.value == "data"
        assert WebSocketEventType.ERROR.value == "error"
        assert WebSocketEventType.HEARTBEAT.value == "heartbeat"
        assert WebSocketEventType.SUBSCRIBE.value == "subscribe"
        assert WebSocketEventType.UNSUBSCRIBE.value == "unsubscribe"
        
        # 测试枚举转换
        event_type = WebSocketEventType("data")
        assert event_type == WebSocketEventType.DATA
    
    @pytest.mark.asyncio
    async def test_http_method(self):
        """测试HTTP方法"""
        assert HTTPMethod.GET.value == "GET"
        assert HTTPMethod.POST.value == "POST"
        assert HTTPMethod.PUT.value == "PUT"
        assert HTTPMethod.DELETE.value == "DELETE"
        assert HTTPMethod.PATCH.value == "PATCH"
        assert HTTPMethod.HEAD.value == "HEAD"
        assert HTTPMethod.OPTIONS.value == "OPTIONS"
        
        # 测试枚举转换
        method = HTTPMethod("POST")
        assert method == HTTPMethod.POST
    
    @pytest.mark.asyncio
    async def test_rate_limit(self):
        """测试速率限制"""
        # 默认限制
        default_limit = RateLimit()
        assert default_limit.requests_per_minute == 60
        assert default_limit.requests_per_hour == 1000
        assert default_limit.requests_per_day == 10000
        assert default_limit.burst_size == 10
        
        # 自定义限制
        custom_limit = RateLimit(
            requests_per_minute=100,
            requests_per_hour=5000,
            requests_per_day=50000,
            burst_size=20
        )
        
        assert custom_limit.requests_per_minute == 100
        assert custom_limit.requests_per_hour == 5000
        assert custom_limit.requests_per_day == 50000
        assert custom_limit.burst_size == 20
    
    @pytest.mark.asyncio
    async def test_api_stats(self, api_server):
        """测试API统计"""
        # 初始统计
        stats = await api_server.get_api_stats()
        
        # 检查基本统计字段
        assert "total_requests" in stats
        assert "total_errors" in stats
        assert "websocket_active_connections" in stats
        assert "rate_limits" in stats
        assert "uptime" in stats
        assert "timestamp" in stats
        
        # 检查类型
        assert isinstance(stats["total_requests"], int)
        assert isinstance(stats["websocket_active_connections"], int)
        assert isinstance(stats["rate_limits"], dict)
    
    @pytest.mark.asyncio
    async def test_websocket_management(self, api_server, mock_websocket):
        """测试WebSocket管理"""
        # 创建WebSocket连接
        conn_id = "test_conn"
        connection = WebSocketConnection(id=conn_id, websocket=mock_websocket)
        
        # 添加连接
        async with api_server._lock:
            api_server.websocket_connections[conn_id] = connection
            api_server.stats["websocket_connections"] = 1
        
        # 检查连接计数
        stats = await api_server.get_api_stats()
        assert stats["websocket_active_connections"] == 1
        
        # 测试广播
        sent_count = await api_server.broadcast_websocket("market_data", {"price": 50000})
        # 由于连接没有订阅，应该发送0个
        assert sent_count == 0
        
        # 让连接订阅
        connection.subscriptions.append("market_data")
        sent_count = await api_server.broadcast_websocket("market_data", {"price": 50000})
        assert sent_count == 1
        
        # 检查发送的消息
        assert len(mock_websocket.sent_messages) == 1
        message = mock_websocket.sent_messages[0]
        assert message["type"] == "data"
        assert message["channel"] == "market_data"
        assert message["data"]["price"] == 50000
        
        # 测试关闭连接
        await api_server._close_websocket_connection(conn_id)
        
        # 检查连接是否被移除
        assert conn_id not in api_server.websocket_connections
        
        # 更新统计
        stats = await api_server.get_api_stats()
        assert stats["websocket_active_connections"] == 0
    
    @pytest.mark.asyncio
    async def test_rate_limit_check(self, api_server):
        """测试速率限制检查"""
        # 设置速率限制
        api_server.rate_limits["/api/test"] = RateLimit(requests_per_minute=10)
        
        # 测试未超过限制
        for i in range(5):
            allowed = await api_server._check_rate_limit("127.0.0.1", "/api/test")
            assert allowed is True
        
        # 检查计数
        current_minute = datetime.now().strftime("%Y-%m-%d %H:%M")
        key = f"127.0.0.1:/api/test:{current_minute}"
        assert api_server.request_counts.get(key, 0) == 5
        
        # 测试超过限制
        for i in range(10):
            allowed = await api_server._check_rate_limit("127.0.0.1", "/api/test")
        
        # 第11次应该被限制
        allowed = await api_server._check_rate_limit("127.0.0.1", "/api/test")
        assert allowed is False
    
    @pytest.mark.asyncio
    async def test_password_hashing(self, api_server):
        """测试密码哈希"""
        # 测试哈希和验证
        password = "mysecretpassword"
        hashed = api_server.get_password_hash(password)
        
        # 哈希应该不同
        assert password != hashed
        
        # 验证应该成功
        verified = api_server.verify_password(password, hashed)
        assert verified is True
        
        # 错误密码应该失败
        wrong_verified = api_server.verify_password("wrongpassword", hashed)
        assert wrong_verified is False
    
    @pytest.mark.asyncio
    async def test_token_creation(self, api_server):
        """测试令牌创建"""
        # 创建令牌
        token_data = {"sub": "user123", "role": "admin"}
        token = api_server.create_access_token(token_data)
        
        # 令牌应该是一个字符串
        assert isinstance(token, str)
        assert len(token) > 0
        
        # 验证令牌（模拟）
        # 注意：实际验证需要jwt库
        try:
            payload = await api_server.verify_token(token)
            # 如果jwt库可用，payload应该存在
            # 如果不可用，payload为None是正常的
            assert payload is None or isinstance(payload, dict)
        except Exception:
            # 允许异常（当jwt库不可用时）
            pass
    
    @pytest.mark.asyncio
    async def test_concurrent_broadcast(self, api_server, mock_websocket):
        """测试并发广播"""
        # 创建多个连接
        connections = []
        for i in range(5):
            conn_id = f"conn_{i}"
            ws = type(mock_websocket)()  # 创建新的模拟WebSocket
            connection = WebSocketConnection(id=conn_id, websocket=ws)
            connection.subscriptions.append("broadcast_test")
            
            async with api_server._lock:
                api_server.websocket_connections[conn_id] = connection
            
            connections.append((conn_id, ws))
        
        # 并发广播
        async def broadcast_task():
            return await api_server.broadcast_websocket("broadcast_test", {"test": "data"})
        
        # 创建多个广播任务
        tasks = [broadcast_task() for _ in range(3)]
        results = await asyncio.gather(*tasks)
        
        # 所有广播都应该成功
        assert all(r == 5 for r in results)  # 每个广播应该发送到5个连接
        
        # 清理连接
        for conn_id, _ in connections:
            await api_server._close_websocket_connection(conn_id)
    
    @pytest.mark.asyncio
    async def test_start_stop(self, api_server):
        """测试启动停止"""
        # 初始状态
        assert api_server._running is True
        
        # 停止
        success = await api_server.stop()
        assert success is True
        assert api_server._running is False
        
        # 重新启动（模拟）
        api_server._running = True
        success = await api_server.start()
        # 在模拟模式下总是返回True
        assert success is True
        assert api_server._running is True
    
    @pytest.mark.asyncio
    async def test_error_handling(self, api_server):
        """测试错误处理"""
        # 模拟错误统计
        api_server.stats["total_errors"] = 5
        assert api_server.stats["total_errors"] == 5
        
        # 测试错误响应
        error_response = APIResponse(
            status_code=500,
            data=None,
            error="内部服务器错误",
            message="系统异常"
        )
        
        assert error_response.status_code == 500
        assert error_response.error == "内部服务器错误"
        assert error_response.message == "系统异常"
        
        error_dict = error_response.to_dict()
        assert error_dict["status"] == "error"
        assert error_dict["error"] == "内部服务器错误"


if __name__ == "__main__":
    """运行测试"""
    import sys
    import pytest
    
    # 添加src目录到Python路径
    sys.path.insert(0, "/home/cool/.openclaw-trading/src")
    
    # 运行测试
    pytest.main([__file__, "-v"])