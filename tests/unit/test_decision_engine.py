import asyncio
import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock
from src.modules.intelligence.decision_engine.engine import (
    DecisionEngine, DecisionType, RiskLevel, Decision
)
from src.modules.core.data_pipeline import DataPoint


class TestDecisionEngine:
    """决策引擎测试类"""

    @pytest.fixture
    def db_manager(self):
        """数据库管理器fixture"""
        return Mock()

    @pytest.fixture
    def config(self):
        """配置fixture"""
        return {
            "risk_thresholds": {
                "low": 0.2,
                "medium": 0.4,
                "high": 0.7,
                "extreme": 1.0
            },
            "confidence_threshold": 0.6,
            "models": [
                {"name": "model1"},
                {"name": "model2"}
            ]
        }

    @pytest.fixture
    def decision_engine(self, db_manager, config):
        """决策引擎fixture"""
        engine = DecisionEngine(db_manager, config)
        return engine

    @pytest.mark.asyncio
    async def test_initialization(self, decision_engine):
        """测试初始化"""
        result = await decision_engine.initialize()
        assert result is True
        assert decision_engine.enabled is True
        assert len(decision_engine.models) == 2

    @pytest.mark.asyncio
    async def test_shutdown(self, decision_engine):
        """测试关闭"""
        await decision_engine.initialize()
        result = await decision_engine.shutdown()
        assert result is True
        assert decision_engine.enabled is False
        assert len(decision_engine.models) == 0

    @pytest.mark.asyncio
    async def test_make_decision_disabled(self, decision_engine):
        """测试禁用状态下的决策"""
        result = await decision_engine.make_decision([])
        assert result is None

    @pytest.mark.asyncio
    async def test_make_decision_with_data(self, decision_engine):
        """测试有数据时的决策"""
        await decision_engine.initialize()
        
        # 创建测试数据点
        from datetime import datetime
        data_points = [
            DataPoint(
                timestamp=datetime.fromtimestamp(1000),
                symbol="BTC",
                data={"price": 10000.0},
                source="exchange"
            ),
            DataPoint(
                timestamp=datetime.fromtimestamp(1001),
                symbol="BTC",
                data={"price": 11000.0},
                source="exchange"
            ),
            DataPoint(
                timestamp=datetime.fromtimestamp(1002),
                symbol="BTC",
                data={"price": 12000.0},
                source="exchange"
            )
        ]
        
        decision = await decision_engine.make_decision(data_points)
        assert decision is not None
        assert isinstance(decision, Decision)
        assert decision.asset == "BTC"

    @pytest.mark.asyncio
    async def test_make_decision_hold(self, decision_engine):
        """测试持有决策"""
        # 修改配置降低信心度阈值
        decision_engine.confidence_threshold = 0.9
        await decision_engine.initialize()
        
        data_points = [
            DataPoint(
                timestamp=datetime.fromtimestamp(1000),
                symbol="BTC",
                data={"price": 10000.0},
                source="exchange"
            ),
            DataPoint(
                timestamp=datetime.fromtimestamp(1001),
                symbol="BTC",
                data={"price": 10000.0},
                source="exchange"
            )
        ]
        
        decision = await decision_engine.make_decision(data_points)
        assert decision is not None
        assert decision.decision_type == DecisionType.HOLD

    @pytest.mark.asyncio
    async def test_make_decision_buy(self, decision_engine):
        """测试买入决策"""
        await decision_engine.initialize()
        
        data_points = [
            DataPoint(
                timestamp=datetime.fromtimestamp(1000),
                symbol="BTC",
                data={"price": 10000.0},
                source="exchange"
            ),
            DataPoint(
                timestamp=datetime.fromtimestamp(1001),
                symbol="BTC",
                data={"price": 12000.0},
                source="exchange"
            )
        ]
        
        decision = await decision_engine.make_decision(data_points)
        assert decision is not None
        assert decision.decision_type == DecisionType.BUY

    @pytest.mark.asyncio
    async def test_make_decision_sell(self, decision_engine):
        """测试卖出决策"""
        await decision_engine.initialize()
        
        data_points = [
            DataPoint(
                timestamp=datetime.fromtimestamp(1000),
                symbol="BTC",
                data={"price": 12000.0},
                source="exchange"
            ),
            DataPoint(
                timestamp=datetime.fromtimestamp(1001),
                symbol="BTC",
                data={"price": 10000.0},
                source="exchange"
            )
        ]
        
        decision = await decision_engine.make_decision(data_points)
        assert decision is not None
        assert decision.decision_type == DecisionType.SELL

    @pytest.mark.asyncio
    async def test_get_performance_metrics(self, decision_engine):
        """测试获取性能指标"""
        await decision_engine.initialize()
        metrics = await decision_engine.get_performance_metrics()
        assert isinstance(metrics, dict)
        assert "total_decisions" in metrics
        assert "accuracy" in metrics

    def test_is_healthy(self, decision_engine):
        """测试健康状态"""
        assert decision_engine.is_healthy() is False
        
        # 初始化后应该健康
        asyncio.run(decision_engine.initialize())
        assert decision_engine.is_healthy() is True

    def test_assess_risk(self, decision_engine):
        """测试风险评估"""
        # 低风险
        analysis_result = {"volatility": 0.1}
        risk_level = decision_engine._assess_risk(analysis_result)
        assert risk_level == RiskLevel.LOW
        
        # 中风险
        analysis_result = {"volatility": 0.4}  # 调整为0.4以达到中风险阈值
        risk_level = decision_engine._assess_risk(analysis_result)
        assert risk_level == RiskLevel.MEDIUM
        
        # 高风险
        analysis_result = {"volatility": 0.7}  # 调整为0.7以达到高风险阈值
        risk_level = decision_engine._assess_risk(analysis_result)
        assert risk_level == RiskLevel.HIGH
        
        # 极端风险
        analysis_result = {"volatility": 1.0}  # 调整为1.0以达到极端风险阈值
        risk_level = decision_engine._assess_risk(analysis_result)
        assert risk_level == RiskLevel.EXTREME

    @pytest.mark.asyncio
    async def test_analyze_data(self, decision_engine):
        """测试数据分析"""
        await decision_engine.initialize()
        
        data_points = [
            DataPoint(
                timestamp=datetime.fromtimestamp(1000),
                symbol="BTC",
                data={"price": 10000.0},
                source="exchange"
            ),
            DataPoint(
                timestamp=datetime.fromtimestamp(1001),
                symbol="BTC",
                data={"price": 11000.0},
                source="exchange"
            )
        ]
        
        analysis_result = await decision_engine._analyze_data(data_points)
        assert isinstance(analysis_result, dict)
        assert analysis_result["market_trend"] == "up"
        assert "volatility" in analysis_result
        assert "model_predictions" in analysis_result
