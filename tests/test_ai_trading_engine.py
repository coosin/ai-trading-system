"""
AI交易引擎单元测试
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from tests.base_test import (
    AsyncTestCase, 
    create_mock_market_data, 
    create_mock_position,
    assert_valid_signal
)


class TestAITradingEngine(AsyncTestCase):
    """AI交易引擎测试"""
    
    @pytest.fixture
    def trading_engine(self, mock_config, mock_exchange, mock_llm_manager):
        """创建交易引擎实例"""
        from src.modules.core.ai_trading_engine import AITradingEngine
        
        engine = AITradingEngine()
        engine.config = mock_config
        engine.exchange = mock_exchange
        engine.llm_integration = mock_llm_manager
        engine.symbols = ["BTC/USDT"]
        engine.positions = {}
        engine._running = False
        
        return engine
    
    @pytest.mark.asyncio
    async def test_collect_market_data_success(self, trading_engine):
        """测试市场数据采集成功"""
        market_data = await trading_engine._collect_market_data("BTC/USDT")
        
        assert market_data is not None
        assert "symbol" in market_data
        assert market_data["symbol"] == "BTC/USDT"
        assert "ticker" in market_data
        assert "balance" in market_data
    
    @pytest.mark.asyncio
    async def test_collect_market_data_timeout(self, trading_engine):
        """测试市场数据采集超时"""
        # 模拟超时
        trading_engine.exchange.get_multi_timeframe_klines = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )
        
        market_data = await trading_engine._collect_market_data("BTC/USDT")
        
        # 应该返回None而不是抛出异常
        assert market_data is None
    
    @pytest.mark.asyncio
    async def test_make_decision_buy_signal(self, trading_engine):
        """测试生成买入信号"""
        from src.modules.core.ai_trading_engine import MarketContext
        
        context = MarketContext(
            symbol="BTC/USDT",
            price=50000.0,
            trend="bullish",
            volatility=0.02,
            volume_24h=1000000.0,
            sentiment="greed"
        )
        
        # 模拟AI返回买入信号
        trading_engine.llm_integration.generate_trading_signal = AsyncMock(
            return_value={
                "signal": "buy",
                "confidence": 0.85,
                "reasoning": "Strong bullish trend"
            }
        )
        
        decision = await trading_engine._make_decision("BTC/USDT", context, None)
        
        assert decision is not None
        assert decision.action.value == "open_long"
        assert decision.confidence >= 0.65
    
    @pytest.mark.asyncio
    async def test_make_decision_low_confidence(self, trading_engine):
        """测试低置信度信号"""
        from src.modules.core.ai_trading_engine import MarketContext
        
        context = MarketContext(
            symbol="BTC/USDT",
            price=50000.0,
            trend="sideways",
            volatility=0.05,
            volume_24h=500000.0,
            sentiment="neutral"
        )
        
        # 模拟AI返回低置信度信号
        trading_engine.llm_integration.generate_trading_signal = AsyncMock(
            return_value={
                "signal": "buy",
                "confidence": 0.5,  # 低于阈值
                "reasoning": "Uncertain market"
            }
        )
        
        decision = await trading_engine._make_decision("BTC/USDT", context, None)
        
        # 低置信度应该返回HOLD
        assert decision is not None
        assert decision.action.value == "hold"

    @pytest.mark.asyncio
    async def test_make_decision_microstructure_spread_gate(self, trading_engine):
        """微结构门控：高点差应拒绝开仓。"""
        from src.modules.core.ai_trading_engine import MarketContext

        context = MarketContext(
            symbol="BTC/USDT",
            price=50000.0,
            trend="bullish",
            volatility=0.02,
            volume_24h=1000000.0,
            sentiment="neutral",
            metadata={
                "market_intelligence": {
                    "spread_bps": 25.0,
                    "depth_imbalance": 0.1,
                    "funding_rate": 0.0001,
                    "open_interest": 1000000.0,
                }
            },
        )
        trading_engine.llm_integration.generate_trading_signal = AsyncMock(
            return_value={"signal": "buy", "confidence": 0.9, "reasoning": "Test buy"}
        )

        decision = await trading_engine._make_decision("BTC/USDT", context, None)
        assert decision is not None
        assert decision.action.value == "hold"
        assert "微结构开仓门控触发" in (decision.reasoning or "")

    @pytest.mark.asyncio
    async def test_make_decision_microstructure_funding_gate(self, trading_engine):
        """微结构门控：极端 funding 应拒绝开仓。"""
        from src.modules.core.ai_trading_engine import MarketContext

        context = MarketContext(
            symbol="BTC/USDT",
            price=50000.0,
            trend="bullish",
            volatility=0.02,
            volume_24h=1000000.0,
            sentiment="neutral",
            metadata={
                "market_intelligence": {
                    "spread_bps": 2.0,
                    "depth_imbalance": 0.1,
                    "funding_rate": 0.005,
                    "open_interest": 1000000.0,
                }
            },
        )
        trading_engine.llm_integration.generate_trading_signal = AsyncMock(
            return_value={"signal": "buy", "confidence": 0.9, "reasoning": "Test buy"}
        )

        decision = await trading_engine._make_decision("BTC/USDT", context, None)
        assert decision is not None
        assert decision.action.value == "hold"
        assert "funding_rate" in (decision.reasoning or "")

    @pytest.mark.asyncio
    async def test_make_decision_microstructure_oi_gate(self, trading_engine):
        """微结构门控：低 open interest 应拒绝开仓。"""
        from src.modules.core.ai_trading_engine import MarketContext

        trading_engine.ai_config["microstructure_min_open_interest"] = 500000.0
        context = MarketContext(
            symbol="BTC/USDT",
            price=50000.0,
            trend="bullish",
            volatility=0.02,
            volume_24h=1000000.0,
            sentiment="neutral",
            metadata={
                "market_intelligence": {
                    "spread_bps": 2.0,
                    "depth_imbalance": 0.1,
                    "funding_rate": 0.0001,
                    "open_interest": 10000.0,
                }
            },
        )
        trading_engine.llm_integration.generate_trading_signal = AsyncMock(
            return_value={"signal": "buy", "confidence": 0.9, "reasoning": "Test buy"}
        )

        decision = await trading_engine._make_decision("BTC/USDT", context, None)
        assert decision is not None
        assert decision.action.value == "hold"
        assert "open_interest" in (decision.reasoning or "")

    @pytest.mark.asyncio
    async def test_make_decision_microstructure_pass_allows_open(self, trading_engine):
        """微结构门控通过时，不应拦截开仓。"""
        from src.modules.core.ai_trading_engine import MarketContext

        trading_engine._calculate_position_size = AsyncMock(return_value=0.001)
        context = MarketContext(
            symbol="BTC/USDT",
            price=50000.0,
            trend="bullish",
            volatility=0.02,
            volume_24h=1000000.0,
            sentiment="neutral",
            metadata={
                "market_intelligence": {
                    "spread_bps": 1.5,
                    "depth_imbalance": 0.1,
                    "funding_rate": 0.0001,
                    "open_interest": 1000000.0,
                }
            },
        )
        trading_engine.llm_integration.generate_trading_signal = AsyncMock(
            return_value={"signal": "buy", "confidence": 0.9, "reasoning": "Test buy"}
        )

        decision = await trading_engine._make_decision("BTC/USDT", context, None)
        assert decision is not None
        assert decision.action.value == "open_long"
    
    @pytest.mark.asyncio
    async def test_risk_check_max_positions(self, trading_engine):
        """测试最大持仓数限制"""
        from src.modules.core.ai_trading_engine import AIDecision, TradeAction
        
        # 设置已有持仓
        trading_engine.positions = {
            "ETH/USDT": create_mock_position("ETH/USDT"),
            "SOL/USDT": create_mock_position("SOL/USDT"),
            "BNB/USDT": create_mock_position("BNB/USDT")
        }
        
        decision = AIDecision(
            action=TradeAction.OPEN_LONG,
            symbol="BTC/USDT",
            price=50000.0,
            quantity=0.1,
            confidence=0.8,
            reasoning="Test"
        )
        
        # 风险检查应该失败（超过最大持仓数）
        passed = await trading_engine._risk_check(decision)
        assert passed is False

    @pytest.mark.asyncio
    async def test_risk_check_denied_by_risk_manager(self, trading_engine):
        """风险管理器返回passed=false时，应阻断下单。"""
        from src.modules.core.ai_trading_engine import AIDecision, TradeAction

        trading_engine.risk_manager = Mock()
        trading_engine.risk_manager.check_order = AsyncMock(
            return_value={"passed": False, "violations": ["max_total_position_exceeded"]}
        )
        trading_engine._refresh_positions_for_risk_gate = AsyncMock()

        decision = AIDecision(
            action=TradeAction.OPEN_LONG,
            symbol="BTC/USDT",
            price=50000.0,
            quantity=0.001,
            confidence=0.9,
            reasoning="Test",
        )

        passed = await trading_engine._risk_check(decision)
        assert passed is False
    
    @pytest.mark.asyncio
    async def test_execute_decision_success(self, trading_engine):
        """测试执行决策成功"""
        from src.modules.core.ai_trading_engine import AIDecision, TradeAction
        
        decision = AIDecision(
            action=TradeAction.OPEN_LONG,
            symbol="BTC/USDT",
            price=50000.0,
            quantity=0.001,
            confidence=0.8,
            reasoning="Test buy",
            stop_loss=49000.0,
            take_profit=52000.0
        )
        
        # 执行决策
        await trading_engine._execute_decision(decision)
        
        # 验证订单已创建
        trading_engine.exchange.create_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_decision_error_result_should_fail(self, trading_engine):
        """回归：交易所返回error时，不应被判定为成功"""
        from src.modules.core.ai_trading_engine import AIDecision, TradeAction

        decision = AIDecision(
            action=TradeAction.OPEN_LONG,
            symbol="BTC/USDT",
            price=50000.0,
            quantity=0.001,
            confidence=0.8,
            reasoning="Test buy"
        )

        trading_engine.exchange.place_order = AsyncMock(
            return_value={"status": "error", "message": "insufficient balance"}
        )
        trading_engine._save_trade_to_memory = AsyncMock()
        trading_engine._update_positions = AsyncMock()

        result = await trading_engine._execute_decision(decision)

        assert result is False
        trading_engine._save_trade_to_memory.assert_not_called()
        trading_engine._update_positions.assert_not_called()

    def test_order_result_success_semantics(self, trading_engine):
        """回归：订单结果成功语义判定"""
        assert trading_engine._is_order_result_success({"status": "error"}) is False
        assert trading_engine._is_order_result_success({"success": False, "error": "x"}) is False
        assert trading_engine._is_order_result_success({"status": "success", "order_id": "123"}) is True
        assert trading_engine._is_order_result_success({"id": "abc"}) is True
    
    @pytest.mark.asyncio
    async def test_update_positions(self, trading_engine):
        """测试更新持仓"""
        # 模拟持仓数据
        trading_engine.exchange.get_positions = AsyncMock(
            return_value=[create_mock_position("BTC/USDT")]
        )
        
        await trading_engine._update_positions()
        
        # 验证持仓已更新
        assert "BTC/USDT" in trading_engine.positions

    @pytest.mark.asyncio
    async def test_update_positions_okx_swap_instid_normalization(self, trading_engine):
        """OKX: instId=BTC-USDT-SWAP 应归一为 BTC/USDT，避免持仓键漂移。"""
        trading_engine.exchange.get_positions = AsyncMock(
            return_value=[
                {
                    "instId": "BTC-USDT-SWAP",
                    "symbol": "BTC/USDT/SWAP",
                    "posSide_raw": "net",
                    "side": "short",
                    "raw_pos": -2.0,
                    "size": 2.0,
                    "avgPx": 60000.0,
                    "markPx": 59900.0,
                    "upl": -10.0,
                    "uplRatio": -0.001,
                }
            ]
        )

        await trading_engine._update_positions()

        assert "BTC/USDT" in trading_engine.positions
        pos = trading_engine.positions["BTC/USDT"]
        assert pos.side == "short"
        assert pos.quantity == 2.0
        # Keep raw instId for audit/debug
        assert getattr(pos, "metadata", {}).get("instId") == "BTC-USDT-SWAP"

    @pytest.mark.asyncio
    async def test_update_positions_okx_net_side_long_from_positive_pos(self, trading_engine):
        """OKX net 模式：pos>0 应被判定为 long。"""
        trading_engine.exchange.get_positions = AsyncMock(
            return_value=[
                {
                    "instId": "ETH-USDT-SWAP",
                    "symbol": "ETH/USDT/SWAP",
                    "posSide_raw": "net",
                    "side": "long",
                    "raw_pos": 3.0,
                    "size": 3.0,
                    "avgPx": 3000.0,
                    "markPx": 3010.0,
                    "uplRatio": 0.005,
                }
            ]
        )

        await trading_engine._update_positions()

        assert "ETH/USDT" in trading_engine.positions
        pos = trading_engine.positions["ETH/USDT"]
        assert pos.side == "long"
        assert pos.quantity == 3.0

    @pytest.mark.asyncio
    async def test_update_positions_okx_net_side_short_from_negative_pos(self, trading_engine):
        """OKX net 模式：pos<0 应被判定为 short。"""
        trading_engine.exchange.get_positions = AsyncMock(
            return_value=[
                {
                    "instId": "SOL-USDT-SWAP",
                    "symbol": "SOL/USDT/SWAP",
                    "posSide_raw": "net",
                    "side": "short",
                    "raw_pos": -4.0,
                    "size": 4.0,
                    "avgPx": 150.0,
                    "markPx": 149.5,
                    "uplRatio": -0.004,
                }
            ]
        )

        await trading_engine._update_positions()

        assert "SOL/USDT" in trading_engine.positions
        pos = trading_engine.positions["SOL/USDT"]
        assert pos.side == "short"
        assert pos.quantity == 4.0

    @pytest.mark.asyncio
    async def test_update_positions_fallback_to_symbol_when_instid_missing(self, trading_engine):
        """兼容适配器缺少 instId 场景：仍可从 symbol 归一化得到正确键。"""
        trading_engine.exchange.get_positions = AsyncMock(
            return_value=[
                {
                    "symbol": "XRP/USDT/SWAP",
                    "side": "long",
                    "size": 10.0,
                    "avgPx": 0.5,
                    "markPx": 0.52,
                    "uplRatio": 0.04,
                }
            ]
        )

        await trading_engine._update_positions()

        assert "XRP/USDT" in trading_engine.positions
        pos = trading_engine.positions["XRP/USDT"]
        assert pos.side == "long"
        assert pos.quantity == 10.0


class TestMarketAnalysis(AsyncTestCase):
    """市场分析测试"""
    
    @pytest.fixture
    def engine_with_indicators(self, mock_config, mock_exchange):
        """创建带技术指标的引擎"""
        from src.modules.core.ai_trading_engine import AITradingEngine
        
        engine = AITradingEngine()
        engine.config = mock_config
        engine.exchange = mock_exchange
        
        return engine
    
    @pytest.mark.asyncio
    async def test_calculate_technical_indicators(self, engine_with_indicators):
        """测试技术指标计算"""
        market_data = create_mock_market_data()
        
        indicators = engine_with_indicators._calculate_technical_indicators(market_data)
        
        assert indicators is not None
        assert hasattr(indicators, 'trend')
        assert hasattr(indicators, 'rsi')
        assert hasattr(indicators, 'macd')
    
    @pytest.mark.asyncio
    async def test_analyze_market_with_indicators(self, engine_with_indicators):
        """测试市场分析"""
        market_data = create_mock_market_data()
        
        context = await engine_with_indicators._analyze_market("BTC/USDT", market_data)
        
        assert context is not None
        assert context.symbol == "BTC/USDT"
        assert context.price > 0
        assert context.trend in ["bullish", "bearish", "sideways"]


class TestRiskManagement(AsyncTestCase):
    """风险管理测试"""
    
    @pytest.fixture
    def risk_manager(self, mock_config):
        """创建风险管理器"""
        from src.modules.core.risk_manager import RiskManager
        
        manager = RiskManager(config_manager=Mock())
        return manager
    
    @pytest.mark.asyncio
    async def test_assess_risk(self, risk_manager):
        """测试风险评估"""
        # TODO: 实现风险评估测试
        pass
    
    @pytest.mark.asyncio
    async def test_position_limit_check(self, risk_manager):
        """测试仓位限制检查"""
        # TODO: 实现仓位限制测试
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
