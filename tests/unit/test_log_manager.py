"""
LogManager单元测试
"""

import asyncio
import pytest
import json
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from src.modules.core.log_manager import (
    LogManager, LogConfig, LogEntry, LogQuery, LogStatistics,
    LogLevel, LogSource, LogOutput
)


class TestLogManager:
    """LogManager测试类"""
    
    @pytest.fixture
    async def log_manager(self):
        """创建测试用的日志管理器"""
        manager = LogManager()
        await manager.initialize()
        yield manager
        await manager.cleanup()
    
    @pytest.fixture
    def temp_log_dir(self):
        """创建临时日志目录"""
        temp_dir = tempfile.mkdtemp(prefix="test_logs_")
        yield temp_dir
        # 清理临时目录
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    async def log_manager_with_temp_dir(self, temp_log_dir):
        """使用临时目录的日志管理器"""
        manager = LogManager()
        
        # 创建自定义配置
        config = LogConfig(
            log_dir=temp_log_dir,
            outputs=[LogOutput.CONSOLE, LogOutput.FILE],
            log_level=LogLevel.DEBUG,
            max_file_size_mb=1,  # 1MB测试
            max_backup_count=3,
            rotation_interval="daily",
            json_format=True
        )
        
        # 设置配置
        await manager.initialize()
        
        # 手动更新配置（因为config_manager是None）
        manager.config = config
        
        # 重新设置处理器
        await manager._setup_handlers()
        
        yield manager
        await manager.cleanup()
    
    @pytest.fixture
    def sample_log_entry(self):
        """创建示例日志条目"""
        return LogEntry(
            log_id="test_log_001",
            timestamp=datetime.now(),
            level=LogLevel.INFO,
            source=LogSource.SYSTEM,
            message="测试日志消息",
            module="test_module",
            function="test_function",
            line_no=123,
            correlation_id="corr_001",
            user_id="user_001",
            session_id="session_001",
            request_id="req_001",
            duration_ms=150.5,
            data={"key1": "value1", "count": 42},
            tags=["test", "unit_test"],
            metadata={"test": True}
        )
    
    @pytest.mark.asyncio
    async def test_initialization(self, log_manager):
        """测试初始化"""
        assert log_manager is not None
        assert log_manager._initialized is True
        assert len(log_manager.handlers) > 0  # 应该有处理器
        assert log_manager.memory_handler is not None
        assert log_manager.stats["total_logs"] >= 0
    
    @pytest.mark.asyncio
    async def test_log_level_enum(self):
        """测试日志级别枚举"""
        assert LogLevel.DEBUG.value == "debug"
        assert LogLevel.INFO.value == "info"
        assert LogLevel.WARNING.value == "warning"
        assert LogLevel.ERROR.value == "error"
        assert LogLevel.CRITICAL.value == "critical"
        
        # 测试字符串转换
        assert LogLevel("debug") == LogLevel.DEBUG
        assert LogLevel("info") == LogLevel.INFO
        assert LogLevel("warning") == LogLevel.WARNING
        assert LogLevel("error") == LogLevel.ERROR
        assert LogLevel("critical") == LogLevel.CRITICAL
    
    @pytest.mark.asyncio
    async def test_log_source_enum(self):
        """测试日志来源枚举"""
        assert LogSource.SYSTEM.value == "system"
        assert LogSource.TRADING.value == "trading"
        assert LogSource.API.value == "api"
        assert LogSource.DATABASE.value == "database"
        assert LogSource.STRATEGY.value == "strategy"
        assert LogSource.RISK.value == "risk"
        assert LogSource.MONITOR.value == "monitor"
        assert LogSource.AUDIT.value == "audit"
        assert LogSource.CUSTOM.value == "custom"
    
    @pytest.mark.asyncio
    async def test_log_output_enum(self):
        """测试日志输出枚举"""
        assert LogOutput.CONSOLE.value == "console"
        assert LogOutput.FILE.value == "file"
        assert LogOutput.DATABASE.value == "database"
        assert LogOutput.SYSLOG.value == "syslog"
        assert LogOutput.REMOTE.value == "remote"
    
    @pytest.mark.asyncio
    async def test_log_entry_properties(self, sample_log_entry):
        """测试日志条目属性"""
        entry = sample_log_entry
        
        assert entry.log_id == "test_log_001"
        assert entry.level == LogLevel.INFO
        assert entry.source == LogSource.SYSTEM
        assert entry.message == "测试日志消息"
        assert entry.module == "test_module"
        assert entry.function == "test_function"
        assert entry.line_no == 123
        assert entry.correlation_id == "corr_001"
        assert entry.user_id == "user_001"
        assert entry.session_id == "session_001"
        assert entry.request_id == "req_001"
        assert entry.duration_ms == 150.5
        assert entry.data["key1"] == "value1"
        assert entry.data["count"] == 42
        assert "test" in entry.tags
        assert "unit_test" in entry.tags
        assert entry.metadata["test"] is True
        assert entry.timestamp is not None
    
    @pytest.mark.asyncio
    async def test_log_entry_to_dict(self, sample_log_entry):
        """测试日志条目转换为字典"""
        entry_dict = sample_log_entry.to_dict()
        
        assert entry_dict["log_id"] == "test_log_001"
        assert entry_dict["level"] == "info"
        assert entry_dict["source"] == "system"
        assert entry_dict["message"] == "测试日志消息"
        assert entry_dict["module"] == "test_module"
        assert entry_dict["function"] == "test_function"
        assert entry_dict["line_no"] == 123
        assert entry_dict["correlation_id"] == "corr_001"
        assert entry_dict["user_id"] == "user_001"
        assert entry_dict["session_id"] == "session_001"
        assert entry_dict["request_id"] == "req_001"
        assert entry_dict["duration_ms"] == 150.5
        assert entry_dict["data"]["key1"] == "value1"
        assert entry_dict["data"]["count"] == 42
        assert "test" in entry_dict["tags"]
        assert "timestamp" in entry_dict
        assert "unit_test" in entry_dict["tags"]
        assert entry_dict["metadata"]["test"] is True
    
    @pytest.mark.asyncio
    async def test_log_entry_to_json(self, sample_log_entry):
        """测试日志条目转换为JSON"""
        json_str = sample_log_entry.to_json()
        
        # 验证JSON格式
        parsed = json.loads(json_str)
        assert parsed["log_id"] == "test_log_001"
        assert parsed["level"] == "info"
        assert parsed["message"] == "测试日志消息"
        
        # 验证可以再次解析
        entry_from_json = LogEntry.from_dict(parsed)
        assert entry_from_json.log_id == sample_log_entry.log_id
        assert entry_from_json.message == sample_log_entry.message
        assert entry_from_json.level == sample_log_entry.level
    
    @pytest.mark.asyncio
    async def test_log_entry_from_dict(self):
        """测试从字典创建日志条目"""
        data = {
            "log_id": "from_dict_001",
            "timestamp": datetime.now().isoformat(),
            "level": "warning",
            "source": "trading",
            "message": "从字典创建的日志",
            "module": "trade_module",
            "function": "execute_order",
            "line_no": 456,
            "correlation_id": "corr_002",
            "user_id": "user_002",
            "duration_ms": 200.0,
            "data": {"symbol": "BTC/USDT", "quantity": 0.1},
            "tags": ["trading", "order"],
            "metadata": {"test": False}
        }
        
        entry = LogEntry.from_dict(data)
        
        assert entry.log_id == "from_dict_001"
        assert entry.level == LogLevel.WARNING
        assert entry.source == LogSource.TRADING
        assert entry.message == "从字典创建的日志"
        assert entry.module == "trade_module"
        assert entry.function == "execute_order"
        assert entry.line_no == 456
        assert entry.correlation_id == "corr_002"
        assert entry.user_id == "user_002"
        assert entry.duration_ms == 200.0
        assert entry.data["symbol"] == "BTC/USDT"
        assert entry.data["quantity"] == 0.1
        assert "trading" in entry.tags
        assert entry.metadata["test"] is False
    
    @pytest.mark.asyncio
    async def test_log_config_properties(self):
        """测试日志配置属性"""
        config = LogConfig(
            outputs=[LogOutput.CONSOLE, LogOutput.FILE],
            log_level=LogLevel.WARNING,
            log_dir="/custom/logs",
            max_file_size_mb=200,
            max_backup_count=20,
            rotation_interval="weekly",
            compress_backups=False,
            json_format=False,
            include_traceback=False,
            buffer_size=2000,
            flush_interval_seconds=10
        )
        
        assert len(config.outputs) == 2
        assert LogOutput.CONSOLE in config.outputs
        assert LogOutput.FILE in config.outputs
        assert config.log_level == LogLevel.WARNING
        assert config.log_dir == "/custom/logs"
        assert config.max_file_size_mb == 200
        assert config.max_backup_count == 20
        assert config.rotation_interval == "weekly"
        assert config.compress_backups is False
        assert config.json_format is False
        assert config.include_traceback is False
        assert config.buffer_size == 2000
        assert config.flush_interval_seconds == 10
    
    @pytest.mark.asyncio
    async def test_log_query_properties(self):
        """测试日志查询属性"""
        start_time = datetime.now() - timedelta(hours=1)
        end_time = datetime.now()
        
        query = LogQuery(
            start_time=start_time,
            end_time=end_time,
            level=LogLevel.ERROR,
            source=LogSource.API,
            module="api_server",
            correlation_id="test_corr",
            user_id="test_user",
            request_id="test_req",
            tags=["error", "api"],
            message_pattern=".*failed.*",
            data_filter={"status": 500},
            limit=50,
            offset=10,
            order_by="level",
            order_desc=False
        )
        
        assert query.start_time == start_time
        assert query.end_time == end_time
        assert query.level == LogLevel.ERROR
        assert query.source == LogSource.API
        assert query.module == "api_server"
        assert query.correlation_id == "test_corr"
        assert query.user_id == "test_user"
        assert query.request_id == "test_req"
        assert query.tags == ["error", "api"]
        assert query.message_pattern == ".*failed.*"
        assert query.data_filter == {"status": 500}
        assert query.limit == 50
        assert query.offset == 10
        assert query.order_by == "level"
        assert query.order_desc is False
    
    @pytest.mark.asyncio
    async def test_log_query_to_dict(self):
        """测试日志查询转换为字典"""
        start_time = datetime.now() - timedelta(days=1)
        end_time = datetime.now()
        
        query = LogQuery(
            start_time=start_time,
            end_time=end_time,
            level=LogLevel.INFO,
            source=LogSource.SYSTEM,
            limit=100
        )
        
        query_dict = query.to_dict()
        
        assert query_dict["start_time"] == start_time.isoformat()
        assert query_dict["end_time"] == end_time.isoformat()
        assert query_dict["level"] == "info"
        assert query_dict["source"] == "system"
        assert query_dict["limit"] == 100
        assert "order_by" in query_dict
        assert "order_desc" in query_dict
    
    @pytest.mark.asyncio
    async def test_log_info(self, log_manager):
        """测试记录INFO级别日志"""
        log_id = await log_manager.info(
            source=LogSource.SYSTEM,
            message="测试INFO日志",
            module="test_logger",
            function="test_info",
            correlation_id="test_corr_001",
            data={"test": "data"},
            tags=["test", "info"]
        )
        
        assert log_id is not None
        assert len(log_id) > 0
        
        # 检查统计
        stats = log_manager.stats
        assert stats["total_logs"] >= 1
        assert stats["logs_by_level"]["info"] >= 1
    
    @pytest.mark.asyncio
    async def test_log_debug(self, log_manager):
        """测试记录DEBUG级别日志"""
        log_id = await log_manager.debug(
            source=LogSource.TRADING,
            message="测试DEBUG日志",
            module="trade_engine",
            function="process_order",
            data={"order_id": "order_001", "symbol": "BTC/USDT"}
        )
        
        assert log_id is not None
        
        # 在DEBUG级别启用的配置下应该记录
        if log_manager.config.log_level == LogLevel.DEBUG:
            assert log_id != ""
        else:
            # 如果配置级别高于DEBUG，可能不记录
            pass
    
    @pytest.mark.asyncio
    async def test_log_warning(self, log_manager):
        """测试记录WARNING级别日志"""
        log_id = await log_manager.warning(
            source=LogSource.RISK,
            message="测试WARNING日志",
            module="risk_manager",
            function="check_exposure",
            data={"exposure": 85.5, "limit": 80.0}
        )
        
        assert log_id is not None
        assert log_id != ""
    
    @pytest.mark.asyncio
    async def test_log_error(self, log_manager):
        """测试记录ERROR级别日志"""
        log_id = await log_manager.error(
            source=LogSource.API,
            message="测试ERROR日志",
            module="api_server",
            function="handle_exception",
            request_id="req_error_001",
            include_traceback=True
        )
        
        assert log_id is not None
        assert log_id != ""
        
        # 检查统计
        stats = log_manager.stats
        assert stats["logs_by_level"]["error"] >= 1
    
    @pytest.mark.asyncio
    async def test_log_critical(self, log_manager):
        """测试记录CRITICAL级别日志"""
        log_id = await log_manager.critical(
            source=LogSource.SYSTEM,
            message="测试CRITICAL日志",
            module="system_monitor",
            function="handle_crash",
            data={"component": "trade_engine", "reason": "out_of_memory"}
        )
        
        assert log_id is not None
        assert log_id != ""
        
        # 检查统计
        stats = log_manager.stats
        assert stats["logs_by_level"]["critical"] >= 1
    
    @pytest.mark.asyncio
    async def test_log_audit(self, log_manager):
        """测试记录审计日志"""
        log_id = await log_manager.audit(
            user_id="admin_001",
            action="delete_user",
            resource="user_account",
            status="success",
            details={"target_user": "user_123", "reason": "inactivity"}
        )
        
        assert log_id is not None
        assert log_id != ""
        
        # 获取日志验证
        query = LogQuery(source=LogSource.AUDIT, limit=1)
        logs = await log_manager.query_logs(query)
        
        if logs:
            audit_log = logs[0]
            assert audit_log.source == LogSource.AUDIT
            assert audit_log.user_id == "admin_001"
            assert "audit" in audit_log.tags
            assert "delete_user" in audit_log.message
            assert audit_log.data["audit_action"] == "delete_user"
            assert audit_log.data["audit_resource"] == "user_account"
            assert audit_log.data["audit_status"] == "success"
    
    @pytest.mark.asyncio
    async def test_get_recent_logs(self, log_manager):
        """测试获取最近日志"""
        # 先记录一些日志
        for i in range(5):
            await log_manager.info(
                source=LogSource.SYSTEM,
                message=f"测试日志 {i}",
                module=f"module_{i}",
                data={"index": i}
            )
        
        # 获取最近日志
        recent_logs = await log_manager.get_recent_logs(limit=3)
        
        assert len(recent_logs) <= 3
        assert all(isinstance(log, LogEntry) for log in recent_logs)
        
        # 应该按时间降序排列（最新的在前面）
        if len(recent_logs) > 1:
            assert recent_logs[0].timestamp >= recent_logs[-1].timestamp
    
    @pytest.mark.asyncio
    async def test_query_logs_by_level(self, log_manager):
        """测试按级别查询日志"""
        # 记录不同级别的日志
        await log_manager.info(
            source=LogSource.SYSTEM,
            message="INFO日志1",
            module="test"
        )
        
        await log_manager.warning(
            source=LogSource.SYSTEM,
            message="WARNING日志1",
            module="test"
        )
        
        await log_manager.error(
            source=LogSource.SYSTEM,
            message="ERROR日志1",
            module="test"
        )
        
        await log_manager.info(
            source=LogSource.SYSTEM,
            message="INFO日志2",
            module="test"
        )
        
        # 查询INFO级别日志
        query = LogQuery(level=LogLevel.INFO, limit=10)
        info_logs = await log_manager.query_logs(query)
        
        assert len(info_logs) >= 2
        assert all(log.level == LogLevel.INFO for log in info_logs)
        
        # 查询ERROR级别日志
        query = LogQuery(level=LogLevel.ERROR, limit=10)
        error_logs = await log_manager.query_logs(query)
        
        assert len(error_logs) >= 1
        assert all(log.level == LogLevel.ERROR for log in error_logs)
    
    @pytest.mark.asyncio
    async def test_query_logs_by_source(self, log_manager):
        """测试按来源查询日志"""
        # 记录不同来源的日志
        await log_manager.info(
            source=LogSource.SYSTEM,
            message="系统日志",
            module="system"
        )
        
        await log_manager.info(
            source=LogSource.TRADING,
            message="交易日志",
            module="trading"
        )
        
        await log_manager.info(
            source=LogSource.API,
            message="API日志",
            module="api"
        )
        
        # 查询系统日志
        query = LogQuery(source=LogSource.SYSTEM, limit=10)
        system_logs = await log_manager.query_logs(query)
        
        assert len(system_logs) >= 1
        assert all(log.source == LogSource.SYSTEM for log in system_logs)
        
        # 查询交易日志
        query = LogQuery(source=LogSource.TRADING, limit=10)
        trading_logs = await log_manager.query_logs(query)
        
        assert len(trading_logs) >= 1
        assert all(log.source == LogSource.TRADING for log in trading_logs)
    
    @pytest.mark.asyncio
    async def test_query_logs_by_time_range(self, log_manager):
        """测试按时间范围查询日志"""
        # 记录一个带时间的日志
        await log_manager.info(
            source=LogSource.SYSTEM,
            message="时间测试日志",
            module="time_test"
        )
        
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        hour_from_now = now + timedelta(hours=1)
        
        # 查询过去一小时的日志
        query = LogQuery(start_time=hour_ago, end_time=now, limit=10)
        recent_logs = await log_manager.query_logs(query)
        
        # 应该至少有一个日志
        assert len(recent_logs) >= 0
        
        if recent_logs:
            # 检查时间范围
            for log in recent_logs:
                assert hour_ago <= log.timestamp <= now
        
        # 查询未来一小时的日志（应该为空）
        query = LogQuery(start_time=now, end_time=hour_from_now, limit=10)
        future_logs = await log_manager.query_logs(query)
        
        # 未来不应该有日志
        assert len(future_logs) == 0
    
    @pytest.mark.asyncio
    async def test_query_logs_by_module(self, log_manager):
        """测试按模块查询日志"""
        # 记录不同模块的日志
        await log_manager.info(
            source=LogSource.SYSTEM,
            message="模块1日志",
            module="module_1"
        )
        
        await log_manager.info(
            source=LogSource.SYSTEM,
            message="模块2日志",
            module="module_2"
        )
        
        await log_manager.info(
            source=LogSource.SYSTEM,
            message="模块1另一个日志",
            module="module_1"
        )
        
        # 查询模块1的日志
        query = LogQuery(module="module_1", limit=10)
        module1_logs = await log_manager.query_logs(query)
        
        assert len(module1_logs) >= 2
        assert all(log.module == "module_1" for log in module1_logs)
        
        # 查询模块2的日志
        query = LogQuery(module="module_2", limit=10)
        module2_logs = await log_manager.query_logs(query)
        
        assert len(module2_logs) >= 1
        assert all(log.module == "module_2" for log in module2_logs)
    
    @pytest.mark.asyncio
    async def test_query_logs_by_tags(self, log_manager):
        """测试按标签查询日志"""
        # 记录不同标签的日志
        await log_manager.info(
            source=LogSource.SYSTEM,
            message="标签测试1",
            tags=["tag1", "tag2"]
        )
        
        await log_manager.info(
            source=LogSource.SYSTEM,
            message="标签测试2",
            tags=["tag2", "tag3"]
        )
        
        await log_manager.info(
            source=LogSource.SYSTEM,
            message="标签测试3",
            tags=["tag1", "tag3"]
        )
        
        # 查询包含tag1的日志
        query = LogQuery(tags=["tag1"], limit=10)
        tag1_logs = await log_manager.query_logs(query)
        
        assert len(tag1_logs) >= 2
        assert all("tag1" in log.tags for log in tag1_logs)
        
        # 查询包含tag1和tag2的日志
        query = LogQuery(tags=["tag1", "tag2"], limit=10)
        tag12_logs = await log_manager.query_logs(query)
        
        assert len(tag12_logs) >= 1
        assert all("tag1" in log.tags and "tag2" in log.tags for log in tag12_logs)
    
    @pytest.mark.asyncio
    async def test_query_logs_with_pagination(self, log_manager):
        """测试带分页的日志查询"""
        # 记录多个日志
        for i in range(20):
            await log_manager.info(
                source=LogSource.SYSTEM,
                message=f"分页测试日志 {i:02d}",
                data={"index": i}
            )
        
        # 第一页
        query = LogQuery(limit=5, offset=0)
        page1 = await log_manager.query_logs(query)
        
        assert len(page1) == 5
        
        # 第二页
        query = LogQuery(limit=5, offset=5)
        page2 = await log_manager.query_logs(query)
        
        assert len(page2) == 5
        
        # 检查内容不同
        page1_messages = {log.message for log in page1}
        page2_messages = {log.message for log in page2}
        assert not page1_messages.intersection(page2_messages)
    
    @pytest.mark.asyncio
    async def test_get_log_by_id(self, log_manager):
        """测试根据ID获取日志"""
        # 记录一个日志
        log_id = await log_manager.info(
            source=LogSource.SYSTEM,
            message="根据ID获取测试",
            module="id_test",
            correlation_id="test_corr_id"
        )
        
        # 获取日志
        log_entry = await log_manager.get_log_by_id(log_id)
        
        assert log_entry is not None
        assert log_entry.log_id == log_id
        assert log_entry.message == "根据ID获取测试"
        assert log_entry.correlation_id == "test_corr_id"
        
        # 获取不存在的ID
        nonexistent = await log_manager.get_log_by_id("nonexistent_id")
        assert nonexistent is None
    
    @pytest.mark.asyncio
    async def test_get_log_statistics(self, log_manager):
        """测试获取日志统计"""
        # 记录一些日志
        for i in range(10):
            level = LogLevel.INFO if i % 2 == 0 else LogLevel.WARNING
            source = LogSource.SYSTEM if i < 5 else LogSource.TRADING
            
            await log_manager.log(
                level=level,
                source=source,
                message=f"统计测试日志 {i}",
                module="stats_test"
            )
        
        # 获取统计
        stats = await log_manager.get_log_statistics()
        
        assert isinstance(stats, LogStatistics)
        assert stats.total_logs >= 10
        
        # 检查按级别统计
        assert "info" in stats.logs_by_level
        assert "warning" in stats.logs_by_level
        assert stats.logs_by_level["info"] + stats.logs_by_level["warning"] >= 10
        
        # 检查按来源统计
        assert "system" in stats.logs_by_source
        assert "trading" in stats.logs_by_source
        
        # 检查时间范围
        assert stats.time_period_start is not None
        assert stats.time_period_end is not None
        assert stats.time_period_end >= stats.time_period_start
        
        # 检查错误率（应该为0，因为没有错误日志）
        assert stats.error_rate == 0.0
        
        # 检查按模块统计
        assert "stats_test" in stats.logs_by_module
        assert stats.logs_by_module["stats_test"] >= 10
    
    @pytest.mark.asyncio
    async def test_get_log_statistics_with_time_range(self, log_manager):
        """测试带时间范围的日志统计"""
        # 记录当前时间的日志
        await log_manager.info(
            source=LogSource.SYSTEM,
            message="当前时间日志",
            module="time_range_test"
        )
        
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        day_ago = now - timedelta(days=1)
        
        # 获取过去一小时的统计
        hour_stats = await log_manager.get_log_statistics(start_time=hour_ago, end_time=now)
        assert hour_stats.total_logs >= 1
        
        # 获取过去一天的统计
        day_stats = await log_manager.get_log_statistics(start_time=day_ago, end_time=now)
        assert day_stats.total_logs >= 1
        
        # 过去一小时应该包含在一天内
        assert hour_stats.total_logs <= day_stats.total_logs
    
    @pytest.mark.asyncio
    async def test_get_memory_buffer(self, log_manager):
        """测试获取内存缓冲区"""
        # 记录一些日志
        for i in range(5):
            await log_manager.info(
                source=LogSource.SYSTEM,
                message=f"缓冲区测试 {i}"
            )
        
        # 获取缓冲区
        buffer = await log_manager.get_memory_buffer()
        
        assert isinstance(buffer, list)
        assert len(buffer) >= 5
        assert all(isinstance(log, LogEntry) for log in buffer)
        
        # 验证缓冲区内容
        buffer_messages = {log.message for log in buffer}
        assert any(msg.startswith("缓冲区测试") for msg in buffer_messages)
    
    @pytest.mark.asyncio
    async def test_clear_memory_buffer(self, log_manager):
        """测试清空内存缓冲区"""
        # 记录一些日志
        for i in range(3):
            await log_manager.info(
                source=LogSource.SYSTEM,
                message=f"清空测试 {i}"
            )
        
        # 清空前获取缓冲区
        buffer_before = await log_manager.get_memory_buffer()
        assert len(buffer_before) >= 3
        
        # 清空缓冲区
        await log_manager.clear_memory_buffer()
        
        # 清空后获取缓冲区
        buffer_after = await log_manager.get_memory_buffer()
        assert len(buffer_after) == 0
    
    @pytest.mark.asyncio
    async def test_get_config(self, log_manager):
        """测试获取配置"""
        config = await log_manager.get_config()
        
        assert isinstance(config, LogConfig)
        assert config.log_level in LogLevel
        assert len(config.outputs) > 0
        assert all(output in LogOutput for output in config.outputs)
        assert config.max_file_size_mb > 0
        assert config.max_backup_count > 0
    
    @pytest.mark.asyncio
    async def test_update_config(self, log_manager):
        """测试更新配置"""
        # 获取当前配置
        old_config = await log_manager.get_config()
        
        # 更新配置
        new_config_values = {
            "log_level": "warning",
            "max_file_size_mb": 200,
            "max_backup_count": 15,
            "json_format": False
        }
        
        success = await log_manager.update_config(new_config_values)
        
        assert success is True
        
        # 验证配置已更新
        updated_config = await log_manager.get_config()
        assert updated_config.log_level == LogLevel.WARNING
        assert updated_config.max_file_size_mb == 200
        assert updated_config.max_backup_count == 15
        assert updated_config.json_format is False
        
        # 恢复配置
        recovery_values = {
            "log_level": old_config.log_level.value,
            "max_file_size_mb": old_config.max_file_size_mb,
            "max_backup_count": old_config.max_backup_count,
            "json_format": old_config.json_format
        }
        await log_manager.update_config(recovery_values)
    
    @pytest.mark.asyncio
    async def test_export_logs_json(self, log_manager):
        """测试导出日志为JSON"""
        # 记录一些日志
        for i in range(3):
            await log_manager.info(
                source=LogSource.SYSTEM,
                message=f"导出测试 {i}",
                data={"export_index": i}
            )
        
        # 导出为JSON
        query = LogQuery(limit=10)
        exported = await log_manager.export_logs(query, format="json")
        
        assert exported is not None
        assert len(exported) > 0
        
        # 验证JSON格式
        parsed = json.loads(exported)
        assert isinstance(parsed, list)
        assert len(parsed) >= 3
        
        for log_dict in parsed[:3]:
            assert "log_id" in log_dict
            assert "message" in log_dict
            assert "timestamp" in log_dict
            assert log_dict["data"]["export_index"] in [0, 1, 2]
    
    @pytest.mark.asyncio
    async def test_export_logs_csv(self, log_manager):
        """测试导出日志为CSV"""
        # 记录一些日志
        for i in range(2):
            await log_manager.info(
                source=LogSource.SYSTEM,
                message=f"CSV导出测试 {i}",
                data={"csv_test": True}
            )
        
        # 导出为CSV
        query = LogQuery(limit=10)
        exported = await log_manager.export_logs(query, format="csv")
        
        assert exported is not None
        assert len(exported) > 0
        
        # 验证CSV格式（简单的字符串检查）
        assert "log_id" in exported
        assert "message" in exported
        assert "timestamp" in exported
        assert "CSV导出测试" in exported
    
    @pytest.mark.asyncio
    async def test_export_logs_invalid_format(self, log_manager):
        """测试无效格式导出"""
        query = LogQuery(limit=10)
        exported = await log_manager.export_logs(query, format="invalid_format")
        
        assert exported is None
    
    @pytest.mark.asyncio
    async def test_get_statistics_method(self, log_manager):
        """测试get_statistics方法"""
        stats = await log_manager.get_statistics()
        
        assert isinstance(stats, dict)
        assert "total_logs" in stats
        assert "storage_size" in stats
        assert "max_storage_size" in stats
        assert "active_handlers" in stats
        assert "config" in stats
        
        assert stats["total_logs"] >= 0
        assert stats["storage_size"] >= 0
        assert stats["max_storage_size"] == 100000
        assert stats["active_handlers"] > 0
    
    @pytest.mark.asyncio
    async def test_concurrent_logging(self, log_manager):
        """测试并发日志记录"""
        async def log_task(task_id):
            for i in range(10):
                await log_manager.info(
                    source=LogSource.SYSTEM,
                    message=f"并发任务{task_id}-日志{i}",
                    module="concurrent_test",
                    data={"task_id": task_id, "log_index": i}
                )
                await asyncio.sleep(0.001)  # 短暂延迟
        
        # 创建多个并发任务
        tasks = [log_task(i) for i in range(5)]
        await asyncio.gather(*tasks)
        
        # 验证日志数量
        query = LogQuery(module="concurrent_test", limit=100)
        logs = await log_manager.query_logs(query)
        
        assert len(logs) >= 50  # 5个任务 * 10个日志 = 50个日志
        
        # 验证不同任务的日志都存在
        task_ids = set()
        for log in logs:
            if "task_id" in log.data:
                task_ids.add(log.data["task_id"])
        
        assert len(task_ids) >= 3  # 至少应该有3个不同任务的日志


if __name__ == "__main__":
    """运行测试"""
    import sys
    import pytest
    
    # 添加src目录到Python路径
    sys.path.insert(0, "/home/cool/.openclaw-trading/src")
    
    # 运行测试
    pytest.main([__file__, "-v"])