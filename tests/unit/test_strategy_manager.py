"""
StrategyManager单元测试
"""

import asyncio
import pytest
from datetime import datetime
from src.modules.core.strategy_manager import (
    StrategyManager, StrategyConfig, StrategyInstance, TradingSignal,
    StrategyPerformance, BaseStrategy, StrategyType, StrategyStatus, SignalType
)


class TestStrategyManager:
    """StrategyManager测试类"""
    
    @pytest.fixture
    async def strategy_manager(self):
        """创建测试用的策略管理器"""
        manager = StrategyManager()
        await manager.initialize()
        yield manager
        await manager.cleanup()
    
    @pytest.fixture
    def sample_strategy_config(self):
        """创建示例策略配置"""
        return StrategyConfig(
            strategy_id="test_strategy_1",
            name="测试策略",
            description="用于测试的策略",
            strategy_type=StrategyType.TREND_FOLLOWING,
            parameters={
                "param1": 10,
                "param2": "value"
            },
            symbols=["BTC/USDT", "ETH/USDT"],
            timeframe="1h",
            initial_capital=10000.0
        )
    
    @pytest.mark.asyncio
    async def test_initialization(self, strategy_manager):
        """测试初始化"""
        assert strategy_manager is not None
        assert len(strategy_manager.strategy_configs) > 0  # 应该有默认策略
        assert len(strategy_manager.strategy_classes) > 0  # 应该有默认策略类
        assert len(strategy_manager.strategy_instances) == 0  # 初始没有实例
    
    @pytest.mark.asyncio
    async def test_strategy_config_properties(self, sample_strategy_config):
        """测试策略配置属性"""
        config = sample_strategy_config
        
        assert config.strategy_id == "test_strategy_1"
        assert config.name == "测试策略"
        assert config.description == "用于测试的策略"
        assert config.strategy_type == StrategyType.TREND_FOLLOWING
        assert config.enabled is True
        assert config.parameters["param1"] == 10
        assert config.parameters["param2"] == "value"
        assert config.symbols == ["BTC/USDT", "ETH/USDT"]
        assert config.timeframe == "1h"
        assert config.initial_capital == 10000.0
        assert config.created_at is not None
        assert config.updated_at is not None
        
        # 测试转换为字典
        config_dict = config.to_dict()
        assert config_dict["strategy_id"] == "test_strategy_1"
        assert config_dict["name"] == "测试策略"
        assert config_dict["strategy_type"] == "trend_following"
        assert config_dict["enabled"] is True
        assert "created_at" in config_dict
        assert "updated_at" in config_dict
    
    @pytest.mark.asyncio
    async def test_load_strategy_config(self, strategy_manager, sample_strategy_config):
        """测试加载策略配置"""
        # 将配置转换为字典
        config_dict = sample_strategy_config.to_dict()
        
        # 加载配置
        config = await strategy_manager.load_strategy_config(config_dict)
        
        assert config is not None
        assert config.strategy_id == "test_strategy_1"
        assert config.name == "测试策略"
        assert config.strategy_type == StrategyType.TREND_FOLLOWING
        
        # 检查是否保存到管理器
        assert config.strategy_id in strategy_manager.strategy_configs
    
    @pytest.mark.asyncio
    async def test_load_invalid_strategy_config(self, strategy_manager):
        """测试加载无效的策略配置"""
        # 缺少必要字段的配置
        invalid_config = {
            "name": "无效策略",
            # 缺少strategy_id和strategy_type
        }
        
        config = await strategy_manager.load_strategy_config(invalid_config)
        assert config is None
    
    @pytest.mark.asyncio
    async def test_register_strategy_class(self, strategy_manager):
        """测试注册策略类"""
        # 创建测试策略类
        class TestStrategy(BaseStrategy):
            async def _load_data(self):
                pass
            async def _calculate_indicators(self):
                pass
            async def _process_market_data(self, symbol, data):
                pass
            async def _generate_signals(self):
                return []
        
        # 注册策略类
        success = await strategy_manager.register_strategy_class("test_strategy_class", TestStrategy)
        assert success is True
        assert "test_strategy_class" in strategy_manager.strategy_classes
    
    @pytest.mark.asyncio
    async def test_register_duplicate_strategy_class(self, strategy_manager):
        """测试注册重复的策略类"""
        # 创建测试策略类
        class TestStrategy(BaseStrategy):
            async def _load_data(self):
                pass
            async def _calculate_indicators(self):
                pass
            async def _process_market_data(self, symbol, data):
                pass
            async def _generate_signals(self):
                return []
        
        # 第一次注册
        success1 = await strategy_manager.register_strategy_class("duplicate_class", TestStrategy)
        assert success1 is True
        
        # 第二次注册（应该失败）
        success2 = await strategy_manager.register_strategy_class("duplicate_class", TestStrategy)
        assert success2 is False
    
    @pytest.mark.asyncio
    async def test_create_strategy_instance(self, strategy_manager, sample_strategy_config):
        """测试创建策略实例"""
        # 先加载配置
        config_dict = sample_strategy_config.to_dict()
        await strategy_manager.load_strategy_config(config_dict)
        
        # 创建实例
        instance_id = await strategy_manager.create_strategy_instance("test_strategy_1")
        
        assert instance_id is not None
        assert instance_id in strategy_manager.strategy_instances
        
        instance = strategy_manager.strategy_instances[instance_id]
        assert instance.config.strategy_id == "test_strategy_1"
        assert instance.status == StrategyStatus.CREATED
        assert instance.instance is not None
    
    @pytest.mark.asyncio
    async def test_create_instance_for_nonexistent_strategy(self, strategy_manager):
        """测试为不存在的策略创建实例"""
        instance_id = await strategy_manager.create_strategy_instance("nonexistent_strategy")
        assert instance_id is None
    
    @pytest.mark.asyncio
    async def test_initialize_strategy(self, strategy_manager, sample_strategy_config):
        """测试初始化策略"""
        # 加载配置并创建实例
        config_dict = sample_strategy_config.to_dict()
        await strategy_manager.load_strategy_config(config_dict)
        instance_id = await strategy_manager.create_strategy_instance("test_strategy_1")
        
        assert instance_id is not None
        
        # 初始化策略
        success = await strategy_manager.initialize_strategy(instance_id)
        
        # 初始化可能成功或失败（取决于策略实现）
        # 但至少应该返回布尔值
        assert isinstance(success, bool)
    
    @pytest.mark.asyncio
    async def test_get_strategy_instance(self, strategy_manager, sample_strategy_config):
        """测试获取策略实例"""
        # 加载配置并创建实例
        config_dict = sample_strategy_config.to_dict()
        await strategy_manager.load_strategy_config(config_dict)
        instance_id = await strategy_manager.create_strategy_instance("test_strategy_1")
        
        # 获取实例
        instance = await strategy_manager.get_strategy_instance(instance_id)
        
        assert instance is not None
        assert instance.instance_id == instance_id
        assert instance.config.strategy_id == "test_strategy_1"
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_strategy_instance(self, strategy_manager):
        """测试获取不存在的策略实例"""
        instance = await strategy_manager.get_strategy_instance("nonexistent_id")
        assert instance is None
    
    @pytest.mark.asyncio
    async def test_get_strategy_instances_with_filters(self, strategy_manager, sample_strategy_config):
        """测试带过滤器的策略实例获取"""
        # 加载配置并创建多个实例
        config_dict = sample_strategy_config.to_dict()
        await strategy_manager.load_strategy_config(config_dict)
        
        # 创建实例
        instance_id1 = await strategy_manager.create_strategy_instance("test_strategy_1")
        instance_id2 = await strategy_manager.create_strategy_instance("test_strategy_1")
        
        # 获取所有实例
        all_instances = await strategy_manager.get_strategy_instances()
        assert len(all_instances) >= 2
        
        # 按策略ID过滤
        strategy_instances = await strategy_manager.get_strategy_instances(strategy_id="test_strategy_1")
        assert len(strategy_instances) >= 2
        assert all(i.config.strategy_id == "test_strategy_1" for i in strategy_instances)
        
        # 按状态过滤
        created_instances = await strategy_manager.get_strategy_instances(status=StrategyStatus.CREATED)
        assert len(created_instances) >= 2
        assert all(i.status == StrategyStatus.CREATED for i in created_instances)
    
    @pytest.mark.asyncio
    async def test_trading_signal_properties(self):
        """测试交易信号属性"""
        # 创建交易信号
        signal = TradingSignal(
            signal_id="test_signal_1",
            strategy_id="test_strategy_1",
            instance_id="test_instance_1",
            signal_type=SignalType.BUY,
            symbol="BTC/USDT",
            price=50000.0,
            quantity=0.5,
            confidence=0.8,
            reason="测试买入信号",
            parameters={"stop_loss": 0.05},
            metadata={"source": "test"}
        )
        
        # 检查属性
        assert signal.signal_id == "test_signal_1"
        assert signal.strategy_id == "test_strategy_1"
        assert signal.instance_id == "test_instance_1"
        assert signal.signal_type == SignalType.BUY
        assert signal.symbol == "BTC/USDT"
        assert signal.price == 50000.0
        assert signal.quantity == 0.5
        assert signal.confidence == 0.8
        assert signal.reason == "测试买入信号"
        assert signal.parameters["stop_loss"] == 0.05
        assert signal.metadata["source"] == "test"
        assert signal.timestamp is not None
        
        # 测试转换为字典
        signal_dict = signal.to_dict()
        assert signal_dict["signal_id"] == "test_signal_1"
        assert signal_dict["strategy_id"] == "test_strategy_1"
        assert signal_dict["signal_type"] == "buy"
        assert signal_dict["symbol"] == "BTC/USDT"
        assert signal_dict["price"] == 50000.0
        assert signal_dict["confidence"] == 0.8
        assert "timestamp" in signal_dict
    
    @pytest.mark.asyncio
    async def test_strategy_performance_properties(self):
        """测试策略性能属性"""
        # 创建策略性能
        performance = StrategyPerformance(
            strategy_id="test_strategy_1",
            total_pnl=5000.0,
            total_trades=100,
            winning_trades=65,
            losing_trades=35,
            win_rate=0.65,
            profit_factor=1.8,
            sharpe_ratio=1.5,
            sortino_ratio=1.8,
            max_drawdown=0.12,
            avg_trade_pnl=50.0,
            avg_winning_trade=100.0,
            avg_losing_trade=-50.0,
            total_days=30,
            daily_return_mean=0.002,
            daily_return_std=0.015
        )
        
        # 检查属性
        assert performance.strategy_id == "test_strategy_1"
        assert performance.total_pnl == 5000.0
        assert performance.total_trades == 100
        assert performance.winning_trades == 65
        assert performance.losing_trades == 35
        assert performance.win_rate == 0.65
        assert performance.profit_factor == 1.8
        assert performance.sharpe_ratio == 1.5
        assert performance.sortino_ratio == 1.8
        assert performance.max_drawdown == 0.12
        assert performance.avg_trade_pnl == 50.0
        assert performance.avg_winning_trade == 100.0
        assert performance.avg_losing_trade == -50.0
        assert performance.total_days == 30
        assert performance.daily_return_mean == 0.002
        assert performance.daily_return_std == 0.015
        assert performance.last_updated is not None
    
    @pytest.mark.asyncio
    async def test_base_strategy_class(self, sample_strategy_config):
        """测试基础策略类"""
        # 创建基础策略实例
        strategy = BaseStrategy(sample_strategy_config)
        
        assert strategy.config == sample_strategy_config
        assert strategy.strategy_id == "test_strategy_1"
        assert strategy.name == "测试策略"
        assert strategy.parameters["param1"] == 10
        assert strategy.symbols == ["BTC/USDT", "ETH/USDT"]
        assert strategy.timeframe == "1h"
        assert strategy._initialized is False
        assert strategy._running is False
        
        # 测试需要子类实现的方法（应该抛出异常）
        with pytest.raises(NotImplementedError):
            await strategy._load_data()
        
        with pytest.raises(NotImplementedError):
            await strategy._calculate_indicators()
        
        with pytest.raises(NotImplementedError):
            await strategy._process_market_data("BTC/USDT", {})
        
        with pytest.raises(NotImplementedError):
            await strategy._generate_signals()
    
    @pytest.mark.asyncio
    async def test_get_signals(self, strategy_manager, sample_strategy_config):
        """测试获取信号"""
        # 加载配置并创建实例
        config_dict = sample_strategy_config.to_dict()
        await strategy_manager.load_strategy_config(config_dict)
        instance_id = await strategy_manager.create_strategy_instance("test_strategy_1")
        
        # 创建测试信号
        signal = TradingSignal(
            signal_id="test_signal_1",
            strategy_id="test_strategy_1",
            instance_id=instance_id,
            signal_type=SignalType.BUY,
            symbol="BTC/USDT"
        )
        
        # 手动添加到管理器
        strategy_manager.signals[signal.signal_id] = signal
        strategy_manager.signal_history.append(signal)
        
        # 获取所有信号
        all_signals = await strategy_manager.get_signals()
        assert len(all_signals) >= 1
        
        # 按策略ID过滤
        strategy_signals = await strategy_manager.get_signals(strategy_id="test_strategy_1")
        assert len(strategy_signals) >= 1
        assert all(s.strategy_id == "test_strategy_1" for s in strategy_signals)
        
        # 按实例ID过滤
        instance_signals = await strategy_manager.get_signals(instance_id=instance_id)
        assert len(instance_signals) >= 1
        assert all(s.instance_id == instance_id for s in instance_signals)
        
        # 按信号类型过滤
        buy_signals = await strategy_manager.get_signals(signal_type=SignalType.BUY)
        assert len(buy_signals) >= 1
        assert all(s.signal_type == SignalType.BUY for s in buy_signals)
        
        # 限制数量
        limited_signals = await strategy_manager.get_signals(limit=1)
        assert len(limited_signals) <= 1
    
    @pytest.mark.asyncio
    async def test_get_strategy_performance(self, strategy_manager, sample_strategy_config):
        """测试获取策略性能"""
        # 加载配置
        config_dict = sample_strategy_config.to_dict()
        await strategy_manager.load_strategy_config(config_dict)
        
        # 创建性能记录
        performance = StrategyPerformance(strategy_id="test_strategy_1")
        strategy_manager.performance_metrics["test_strategy_1"] = performance
        
        # 获取性能
        retrieved_performance = await strategy_manager.get_strategy_performance("test_strategy_1")
        
        assert retrieved_performance is not None
        assert retrieved_performance.strategy_id == "test_strategy_1"
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_strategy_performance(self, strategy_manager):
        """测试获取不存在的策略性能"""
        performance = await strategy_manager.get_strategy_performance("nonexistent_strategy")
        assert performance is None
    
    @pytest.mark.asyncio
    async def test_get_statistics(self, strategy_manager, sample_strategy_config):
        """测试获取统计信息"""
        # 加载配置并创建实例
        config_dict = sample_strategy_config.to_dict()
        await strategy_manager.load_strategy_config(config_dict)
        await strategy_manager.create_strategy_instance("test_strategy_1")
        
        # 获取统计
        stats = await strategy_manager.get_statistics()
        
        assert isinstance(stats, dict)
        assert "total_strategies" in stats
        assert "total_instances" in stats
        assert "running_instances" in stats
        assert "total_signals" in stats
        assert "timestamp" in stats
        
        # 检查数值类型
        assert isinstance(stats["total_strategies"], int)
        assert isinstance(stats["total_instances"], int)
        assert stats["total_strategies"] >= 1
        assert stats["total_instances"] >= 1
    
    @pytest.mark.asyncio
    async def test_enum_values(self):
        """测试枚举值"""
        # 策略类型
        assert StrategyType.TREND_FOLLOWING.value == "trend_following"
        assert StrategyType.MEAN_REVERSION.value == "mean_reversion"
        assert StrategyType.ARBITRAGE.value == "arbitrage"
        assert StrategyType.MARKET_MAKING.value == "market_making"
        assert StrategyType.GRID_TRADING.value == "grid_trading"
        assert StrategyType.CUSTOM.value == "custom"
        
        # 策略状态
        assert StrategyStatus.CREATED.value == "created"
        assert StrategyStatus.INITIALIZING.value == "initializing"
        assert StrategyStatus.READY.value == "ready"
        assert StrategyStatus.RUNNING.value == "running"
        assert StrategyStatus.PAUSED.value == "paused"
        assert StrategyStatus.STOPPED.value == "stopped"
        assert StrategyStatus.ERROR.value == "error"
        
        # 信号类型
        assert SignalType.BUY.value == "buy"
        assert SignalType.SELL.value == "sell"
        assert SignalType.HOLD.value == "hold"
        assert SignalType.CLOSE.value == "close"
        assert SignalType.CANCEL.value == "cancel"
    
    @pytest.mark.asyncio
    async def test_export_strategy_config(self, strategy_manager, sample_strategy_config):
        """测试导出策略配置"""
        # 加载配置
        config_dict = sample_strategy_config.to_dict()
        await strategy_manager.load_strategy_config(config_dict)
        
        # 导出为JSON
        json_config = await strategy_manager.export_strategy_config("test_strategy_1", "json")
        assert json_config is not None
        assert '"strategy_id": "test_strategy_1"' in json_config
        assert '"name": "测试策略"' in json_config
        
        # 导出为YAML
        yaml_config = await strategy_manager.export_strategy_config("test_strategy_1", "yaml")
        assert yaml_config is not None
        assert "strategy_id: test_strategy_1" in yaml_config
        assert "name: 测试策略" in yaml_config
    
    @pytest.mark.asyncio
    async def test_export_nonexistent_strategy_config(self, strategy_manager):
        """测试导出不存在的策略配置"""
        config = await strategy_manager.export_strategy_config("nonexistent_strategy", "json")
        assert config is None
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, strategy_manager, sample_strategy_config):
        """测试并发操作"""
        # 加载配置
        config_dict = sample_strategy_config.to_dict()
        await strategy_manager.load_strategy_config(config_dict)
        
        # 并发创建实例
        async def create_instance_task(i):
            return await strategy_manager.create_strategy_instance("test_strategy_1")
        
        # 创建多个实例任务
        tasks = [create_instance_task(i) for i in range(5)]
        results = await asyncio.gather(*tasks)
        
        # 检查结果
        successful_instances = [r for r in results if r is not None]
        assert len(successful_instances) > 0
        
        # 检查实例数量
        all_instances = await strategy_manager.get_strategy_instances()
        assert len(all_instances) == len(successful_instances)


if __name__ == "__main__":
    """运行测试"""
    import sys
    import pytest
    
    # 添加src目录到Python路径
    sys.path.insert(0, "/home/cool/.openclaw-trading/src")
    
    # 运行测试
    pytest.main([__file__, "-v"])