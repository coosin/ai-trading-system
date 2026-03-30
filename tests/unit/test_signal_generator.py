import asyncio
import pytest
from unittest.mock import Mock, MagicMock
from src.modules.intelligence.signal_generator.generator import (
    SignalGenerator, SignalType, SignalStatus, TradingSignal
)
from src.modules.intelligence.decision_engine.engine import (
    Decision, DecisionType, RiskLevel
)


class TestSignalGenerator:
    """信号生成器测试类"""

    @pytest.fixture
    def db_manager(self):
        """数据库管理器fixture"""
        return Mock()

    @pytest.fixture
    def config(self):
        """配置fixture"""
        return {
            "risk_rules": {
                "max_position_size": 0.1,
                "max_leverage": 3,
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.1,
                "max_drawdown": 0.2
            },
            "signal_expiry": 300
        }

    @pytest.fixture
    def signal_generator(self, db_manager, config):
        """信号生成器fixture"""
        generator = SignalGenerator(db_manager, config)
        return generator

    @pytest.fixture
    def test_decision(self):
        """测试决策fixture"""
        return Decision(
            decision_type=DecisionType.BUY,
            asset="BTC",
            amount=0.05,  # 在最大仓位限制内
            price=10000.0,
            confidence=0.7,  # 高于最低置信度
            risk_level=RiskLevel.MEDIUM,
            timestamp=1000,
            reason="Test decision",
            metadata={}
        )

    @pytest.mark.asyncio
    async def test_initialization(self, signal_generator):
        """测试初始化"""
        result = await signal_generator.initialize()
        assert result is True
        assert signal_generator.enabled is True

    @pytest.mark.asyncio
    async def test_shutdown(self, signal_generator):
        """测试关闭"""
        await signal_generator.initialize()
        result = await signal_generator.shutdown()
        assert result is True
        assert signal_generator.enabled is False
        assert len(signal_generator.signals) == 0

    @pytest.mark.asyncio
    async def test_generate_signal_disabled(self, signal_generator, test_decision):
        """测试禁用状态下的信号生成"""
        result = await signal_generator.generate_signal(test_decision)
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_signal(self, signal_generator, test_decision):
        """测试生成信号"""
        await signal_generator.initialize()
        signal = await signal_generator.generate_signal(test_decision)
        assert signal is not None
        assert isinstance(signal, TradingSignal)
        assert signal.signal_type == SignalType.BUY
        assert signal.asset == "BTC"
        assert signal.status == SignalStatus.EXECUTED

    @pytest.mark.asyncio
    async def test_generate_signal_risk_rejected(self, signal_generator, test_decision):
        """测试风险管理拒绝的信号"""
        await signal_generator.initialize()
        
        # 修改决策，使其超过最大仓位
        test_decision.amount = 0.2  # 超过最大仓位0.1
        
        signal = await signal_generator.generate_signal(test_decision)
        assert signal is None

    @pytest.mark.asyncio
    async def test_get_signal_status(self, signal_generator, test_decision):
        """测试获取信号状态"""
        await signal_generator.initialize()
        signal = await signal_generator.generate_signal(test_decision)
        assert signal is not None
        
        status = await signal_generator.get_signal_status(signal.signal_id)
        assert status == SignalStatus.EXECUTED

    @pytest.mark.asyncio
    async def test_cancel_signal(self, signal_generator, test_decision):
        """测试取消信号"""
        await signal_generator.initialize()
        
        # 创建一个待处理的信号
        signal = TradingSignal(
            signal_id="test_signal",
            signal_type=SignalType.BUY,
            asset="BTC",
            amount=0.05,
            price=10000.0,
            confidence=0.7,
            timestamp=asyncio.get_event_loop().time(),
            expiry=asyncio.get_event_loop().time() + 300,
            status=SignalStatus.PENDING,
            metadata={}
        )
        signal_generator.signals[signal.signal_id] = signal
        
        # 取消信号
        result = await signal_generator.cancel_signal(signal.signal_id)
        assert result is True
        assert signal.status == SignalStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_signal_not_found(self, signal_generator):
        """测试取消不存在的信号"""
        await signal_generator.initialize()
        result = await signal_generator.cancel_signal("non_existent_signal")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_signal_history(self, signal_generator, test_decision):
        """测试获取信号历史"""
        await signal_generator.initialize()
        
        # 生成多个信号
        for i in range(5):
            await signal_generator.generate_signal(test_decision)
        
        history = await signal_generator.get_signal_history()
        assert len(history) == 5
        assert all(isinstance(s, TradingSignal) for s in history)

    @pytest.mark.asyncio
    async def test_get_performance_metrics(self, signal_generator, test_decision):
        """测试获取性能指标"""
        await signal_generator.initialize()
        
        # 生成一个信号
        await signal_generator.generate_signal(test_decision)
        
        metrics = await signal_generator.get_performance_metrics()
        assert isinstance(metrics, dict)
        assert metrics["total_signals"] == 1
        assert metrics["executed_signals"] == 1
        assert metrics["execution_rate"] == 1.0
        assert metrics["success_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_cleanup_expired_signals(self, signal_generator):
        """测试清理过期信号"""
        await signal_generator.initialize()
        
        # 创建一个过期的信号
        expired_signal = TradingSignal(
            signal_id="expired_signal",
            signal_type=SignalType.BUY,
            asset="BTC",
            amount=0.05,
            price=10000.0,
            confidence=0.7,
            timestamp=asyncio.get_event_loop().time() - 600,  # 10分钟前
            expiry=asyncio.get_event_loop().time() - 300,  # 5分钟前过期
            status=SignalStatus.PENDING,
            metadata={}
        )
        signal_generator.signals[expired_signal.signal_id] = expired_signal
        
        # 清理过期信号
        cleaned_count = await signal_generator._cleanup_expired_signals()
        assert cleaned_count == 1
        assert expired_signal.signal_id not in signal_generator.signals

    def test_decision_to_signal_type(self, signal_generator):
        """测试决策类型转换为信号类型"""
        assert signal_generator._decision_to_signal_type(DecisionType.BUY) == SignalType.BUY
        assert signal_generator._decision_to_signal_type(DecisionType.SELL) == SignalType.SELL
        assert signal_generator._decision_to_signal_type(DecisionType.HOLD) == SignalType.HOLD
        assert signal_generator._decision_to_signal_type(DecisionType.EXIT) == SignalType.EXIT

    def test_is_healthy(self, signal_generator):
        """测试健康状态"""
        assert signal_generator.is_healthy() is False
        
        # 初始化后应该健康
        asyncio.run(signal_generator.initialize())
        assert signal_generator.is_healthy() is True
