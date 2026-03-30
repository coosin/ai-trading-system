"""
MainController单元测试
"""

import asyncio
import json
from datetime import datetime

import pytest

from src.modules.main_controller import (
    EventType,
    HealthCheckResult,
    HealthStatus,
    MainController,
    ModuleInfo,
    ModuleStatus,
    SystemEvent,
)


class TestMainController:
    """MainController测试类"""

    @pytest.fixture
    async def controller(self):
        """创建测试用的主控制器"""
        controller = MainController()
        await controller.initialize()
        yield controller
        await controller.cleanup()

    @pytest.fixture
    def mock_module(self):
        """创建模拟模块"""

        class MockModule:
            def __init__(self, name):
                self.name = name
                self.initialized = False
                self.started = False
                self.stopped = False
                self.cleaned_up = False

            async def initialize(self):
                self.initialized = True
                return True

            async def start(self):
                self.started = True
                return True

            async def stop(self):
                self.stopped = True
                return True

            async def cleanup(self):
                self.cleaned_up = True
                return True

        return MockModule("test_module")

    @pytest.mark.asyncio
    async def test_initialization(self, controller):
        """测试初始化"""
        assert controller is not None
        assert controller.system_status == ModuleStatus.STOPPED
        assert len(controller.modules) == 0
        assert len(controller.event_handlers) > 0  # 应该有默认处理器

    @pytest.mark.asyncio
    async def test_register_module(self, controller, mock_module):
        """测试注册模块"""
        # 注册模块
        success = controller.register_module("test_module", mock_module)
        assert success is True
        assert "test_module" in controller.modules

        # 检查模块信息
        module_info = controller.modules["test_module"]
        assert module_info.name == "test_module"
        assert module_info.module == mock_module
        assert module_info.status == ModuleStatus.STOPPED
        assert module_info.health_status == HealthStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_register_module_with_dependencies(self, controller, mock_module):
        """测试注册带依赖的模块"""
        # 注册模块1
        controller.register_module("module1", mock_module)

        # 注册模块2（依赖模块1）
        success = controller.register_module("module2", mock_module, dependencies=["module1"])

        assert success is True
        assert "module2" in controller.module_dependencies
        assert controller.module_dependencies["module2"] == ["module1"]

    @pytest.mark.asyncio
    async def test_register_duplicate_module(self, controller, mock_module):
        """测试注册重复模块"""
        # 第一次注册
        success1 = controller.register_module("duplicate", mock_module)
        assert success1 is True

        # 第二次注册（应该失败）
        success2 = controller.register_module("duplicate", mock_module)
        assert success2 is False

    @pytest.mark.asyncio
    async def test_start_module(self, controller, mock_module):
        """测试启动模块"""
        # 注册模块
        controller.register_module("test_module", mock_module)

        # 启动模块
        success = await controller.start_module("test_module")
        assert success is True

        # 检查模块状态
        module_info = controller.modules["test_module"]
        assert module_info.status == ModuleStatus.RUNNING
        assert module_info.start_time is not None
        assert module_info.health_status == HealthStatus.HEALTHY

        # 检查模块方法是否被调用
        assert mock_module.initialized is True
        assert mock_module.started is True

    @pytest.mark.asyncio
    async def test_start_nonexistent_module(self, controller):
        """测试启动不存在的模块"""
        success = await controller.start_module("nonexistent")
        assert success is False

    @pytest.mark.asyncio
    async def test_stop_module(self, controller, mock_module):
        """测试停止模块"""
        # 注册并启动模块
        controller.register_module("test_module", mock_module)
        await controller.start_module("test_module")

        # 停止模块
        success = await controller.stop_module("test_module")
        assert success is True

        # 检查模块状态
        module_info = controller.modules["test_module"]
        assert module_info.status == ModuleStatus.STOPPED
        assert module_info.stop_time is not None

        # 检查模块方法是否被调用
        assert mock_module.stopped is True

    @pytest.mark.asyncio
    async def test_restart_module(self, controller, mock_module):
        """测试重启模块"""
        # 注册并启动模块
        controller.register_module("test_module", mock_module)
        await controller.start_module("test_module")

        # 重置模拟模块状态
        mock_module.stopped = False
        mock_module.started = False

        # 重启模块
        success = await controller.restart_module("test_module")
        assert success is True

        # 检查模块方法是否被调用
        assert mock_module.stopped is True  # 先停止
        assert mock_module.started is True  # 再启动

    @pytest.mark.asyncio
    async def test_start_all_modules(self, controller, mock_module):
        """测试启动所有模块"""
        # 注册多个模块
        for i in range(3):
            module = type(mock_module)(f"module_{i}")
            controller.register_module(f"module_{i}", module)

        # 启动所有模块
        success = await controller.start_all_modules()
        assert success is True

        # 检查所有模块状态
        for i in range(3):
            module_info = controller.modules[f"module_{i}"]
            assert module_info.status == ModuleStatus.RUNNING

    @pytest.mark.asyncio
    async def test_stop_all_modules(self, controller, mock_module):
        """测试停止所有模块"""
        # 注册并启动多个模块
        for i in range(3):
            module = type(mock_module)(f"module_{i}")
            controller.register_module(f"module_{i}", module)
            await controller.start_module(f"module_{i}")

        # 停止所有模块
        success = await controller.stop_all_modules()
        assert success is True

        # 检查所有模块状态
        for i in range(3):
            module_info = controller.modules[f"module_{i}"]
            assert module_info.status == ModuleStatus.STOPPED

    @pytest.mark.asyncio
    async def test_emit_event(self, controller):
        """测试发送事件"""
        # 捕获事件
        captured_events = []

        async def event_handler(event: SystemEvent):
            captured_events.append(event)

        # 注册事件处理器
        controller.register_event_handler(EventType.DATA_RECEIVED, event_handler)

        # 发送事件
        await controller.emit_event(EventType.DATA_RECEIVED, "test_source", {"data": "test_data"})

        # 等待事件处理
        await asyncio.sleep(0.1)

        # 检查事件是否被捕获
        assert len(captured_events) == 1
        event = captured_events[0]
        assert event.type == EventType.DATA_RECEIVED
        assert event.source == "test_source"
        assert event.data["data"] == "test_data"

    @pytest.mark.asyncio
    async def test_register_event_handler(self, controller):
        """测试注册事件处理器"""
        # 创建处理器
        call_count = 0

        def test_handler(event):
            nonlocal call_count
            call_count += 1

        # 注册处理器
        controller.register_event_handler(EventType.SYSTEM_START, test_handler)

        # 发送事件
        await controller.emit_event(EventType.SYSTEM_START, "test", {})
        await asyncio.sleep(0.1)

        # 检查处理器是否被调用
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_get_system_status(self, controller, mock_module):
        """测试获取系统状态"""
        # 注册并启动模块
        controller.register_module("test_module", mock_module)
        await controller.start_module("test_module")

        # 获取系统状态
        status = await controller.get_system_status()

        # 检查状态信息
        assert "system_status" in status
        assert "module_count" in status
        assert "running_modules" in status
        assert "module_statuses" in status
        assert "metrics" in status

        # 检查模块状态
        assert status["module_count"] == 1
        assert status["running_modules"] == 1
        assert "test_module" in status["module_statuses"]

        module_status = status["module_statuses"]["test_module"]
        assert module_status["status"] == ModuleStatus.RUNNING.value
        assert module_status["health"] == HealthStatus.HEALTHY.value

    @pytest.mark.asyncio
    async def test_get_event_history(self, controller):
        """测试获取事件历史"""
        # 发送多个事件
        for i in range(5):
            await controller.emit_event(EventType.HEARTBEAT, "test", {"index": i})

        # 等待事件处理
        await asyncio.sleep(0.1)

        # 获取事件历史
        history = await controller.get_event_history(limit=3)

        # 检查历史记录
        assert len(history) == 3
        for event in history:
            assert event["type"] == EventType.HEARTBEAT.value
            assert event["source"] == "test"

    @pytest.mark.asyncio
    async def test_register_health_check(self, controller):
        """测试注册健康检查"""

        # 创建健康检查函数
        def health_check():
            return HealthCheckResult(
                module_name="test_module", status=HealthStatus.HEALTHY, message="All good"
            )

        # 注册健康检查
        controller.register_health_check("test_module", health_check)

        # 检查是否注册成功
        assert "test_module" in controller.health_checks
        assert controller.health_checks["test_module"] == health_check

    @pytest.mark.asyncio
    async def test_module_info_properties(self):
        """测试模块信息属性"""
        # 创建模块信息
        module_info = ModuleInfo(
            name="test_module", module=None, status=ModuleStatus.RUNNING, start_time=datetime.now()
        )

        # 检查属性
        assert module_info.name == "test_module"
        assert module_info.status == ModuleStatus.RUNNING
        assert module_info.start_time is not None

        # 检查运行时间
        uptime = module_info.uptime
        assert uptime is not None
        assert uptime.total_seconds() >= 0

        # 检查健康状态
        module_info.health_status = HealthStatus.HEALTHY
        assert module_info.is_healthy is True

        module_info.health_status = HealthStatus.CRITICAL
        assert module_info.is_healthy is False

    @pytest.mark.asyncio
    async def test_system_event(self):
        """测试系统事件"""
        # 创建事件
        event = SystemEvent(
            id="test_id",
            type=EventType.DATA_RECEIVED,
            source="test_source",
            data={"key": "value"},
            priority=5,
        )

        # 检查属性
        assert event.id == "test_id"
        assert event.type == EventType.DATA_RECEIVED
        assert event.source == "test_source"
        assert event.data["key"] == "value"
        assert event.priority == 5
        assert event.timestamp is not None

        # 转换为字典
        event_dict = event.to_dict()
        assert event_dict["id"] == "test_id"
        assert event_dict["type"] == EventType.DATA_RECEIVED.value
        assert event_dict["source"] == "test_source"
        assert event_dict["data"]["key"] == "value"
        assert event_dict["priority"] == 5

    @pytest.mark.asyncio
    async def test_health_check_result(self):
        """测试健康检查结果"""
        # 创建健康检查结果
        result = HealthCheckResult(
            module_name="test_module",
            status=HealthStatus.HEALTHY,
            message="All systems operational",
            metrics={"cpu_usage": 0.3, "memory_usage": 0.5},
        )

        # 检查属性
        assert result.module_name == "test_module"
        assert result.status == HealthStatus.HEALTHY
        assert result.message == "All systems operational"
        assert result.metrics["cpu_usage"] == 0.3
        assert result.metrics["memory_usage"] == 0.5
        assert result.timestamp is not None

    @pytest.mark.asyncio
    async def test_module_dependency_resolution(self, controller, mock_module):
        """测试模块依赖解析"""
        # 注册有依赖关系的模块
        module1 = type(mock_module)("module1")
        module2 = type(mock_module)("module2")
        module3 = type(mock_module)("module3")

        controller.register_module("module1", module1)
        controller.register_module("module2", module2, dependencies=["module1"])
        controller.register_module("module3", module3, dependencies=["module1", "module2"])

        # 启动系统（应该按依赖顺序启动）
        success = await controller.start_system()
        assert success is True

        # 检查模块启动顺序
        # module1 应该先启动
        # module2 依赖 module1，应该在 module1 之后启动
        # module3 依赖 module1 和 module2，应该最后启动

    @pytest.mark.asyncio
    async def test_error_handling(self, controller):
        """测试错误处理"""

        # 创建会抛出异常的模块
        class ErrorModule:
            async def start(self):
                raise RuntimeError("模拟启动错误")

        # 注册并尝试启动
        controller.register_module("error_module", ErrorModule())
        success = await controller.start_module("error_module")

        # 应该启动失败
        assert success is False

        # 检查错误信息
        module_info = controller.modules["error_module"]
        assert module_info.status == ModuleStatus.ERROR
        assert module_info.error_count == 1
        assert module_info.last_error == "模拟启动错误"

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, controller, mock_module):
        """测试并发操作"""
        # 注册多个模块
        modules = []
        for i in range(5):
            module = type(mock_module)(f"module_{i}")
            controller.register_module(f"module_{i}", module)
            modules.append(module)

        # 并发启动所有模块
        async def start_module_task(name):
            return await controller.start_module(name)

        tasks = [start_module_task(f"module_{i}") for i in range(5)]
        results = await asyncio.gather(*tasks)

        # 所有模块都应该启动成功
        assert all(results)

        # 检查所有模块状态
        for i in range(5):
            module_info = controller.modules[f"module_{i}"]
            assert module_info.status == ModuleStatus.RUNNING


if __name__ == "__main__":
    """运行测试"""
    import sys

    import pytest

    # 添加src目录到Python路径
    sys.path.insert(0, "/home/cool/.openclaw-trading/src")

    # 运行测试
    pytest.main([__file__, "-v"])
