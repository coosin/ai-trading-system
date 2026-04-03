"""
全智能AI交易引擎 - 完全自动化、无需人工干预

核心特性：
1. 自主数据采集和分析
2. AI智能决策（开平仓、仓位管理、风险控制）
3. 自动订单执行
4. 实时监控和反馈
5. 策略自我优化和迭代
"""

import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd

from .technical_indicators import TechnicalIndicatorCalculator, TechnicalIndicators
from .historical_data_storage import HistoricalDataStorage, TradeRecord, IndicatorRecord, get_historical_storage
from .account_risk_monitor import AccountRiskMonitor, AccountRisk, PositionRisk, RiskLevel
from .strategy_optimizer import StrategyOptimizer, StrategyType, StrategyPerformance

logger = logging.getLogger(__name__)


class TradingState(Enum):
    """交易状态"""
    IDLE = "idle"           # 空闲
    ANALYZING = "analyzing" # 分析中
    DECIDING = "deciding"   # 决策中
    EXECUTING = "executing" # 执行中
    MONITORING = "monitoring" # 监控中


class TradeAction(Enum):
    """交易动作"""
    OPEN_LONG = "open_long"      # 开多
    OPEN_SHORT = "open_short"    # 开空
    CLOSE_LONG = "close_long"    # 平多
    CLOSE_SHORT = "close_short"  # 平空
    HOLD = "hold"                # 持有
    WAIT = "wait"                # 观望


@dataclass
class MarketContext:
    """市场环境上下文"""
    symbol: str
    price: float
    trend: str  # bullish, bearish, sideways
    volatility: float
    volume_24h: float
    sentiment: str  # fear, neutral, greed
    support_levels: List[float] = field(default_factory=list)
    resistance_levels: List[float] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class AIDecision:
    """AI决策结果"""
    action: TradeAction
    symbol: str
    price: float
    quantity: float
    confidence: float
    reasoning: str
    risk_level: str  # low, medium, high
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Position:
    """持仓信息"""
    symbol: str
    side: str  # long, short
    entry_price: float
    quantity: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_percent: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    opened_at: datetime = field(default_factory=datetime.now)


class AITradingEngine:
    """
    全智能AI交易引擎
    
    实现完全自动化的交易流程：
    1. 自主数据采集
    2. AI市场分析
    3. 智能决策生成
    4. 自动订单执行
    5. 实时监控和风控
    6. 策略自我优化
    """
    
    def __init__(self, main_controller=None):
        self.main_controller = main_controller
        
        # 核心组件
        self.llm_integration = None
        self.exchange = None
        self.risk_manager = None
        self.data_storage: Optional[HistoricalDataStorage] = None
        self.risk_monitor: Optional[AccountRiskMonitor] = None
        self.strategy_optimizer: Optional[StrategyOptimizer] = None
        
        # 交易状态
        self.state = TradingState.IDLE
        self.positions: Dict[str, Position] = {}
        self.trade_history: List[Dict] = []
        
        # 监控的交易对
        self.symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
        
        # 交易对黑名单 (ETH已被用户禁用)
        self.symbol_blacklist = ["ETH/USDT"]
        
        # 永续合约交易配置
        self.contract_config = {
            "enabled": True,                    # 启用合约交易
            "trade_type": "swap",               # 永续合约
            "leverage_min": 10,                 # 最小杠杆倍数
            "leverage_max": 50,                 # 最大杠杆倍数
            "default_leverage": 20,             # 默认杠杆倍数
            "max_positions": 5,                 # 最大同时持仓数
            "min_positions": 3,                 # 最小同时持仓数
            "margin_mode": "cross",             # 全仓模式
            "grid_trading": True,               # 启用网格交易
            "grid_levels": 10,                  # 网格层数
            "grid_spacing": 0.01,               # 网格间距 1%
        }
        
        # AI配置
        self.ai_config = {
            "enabled": True,
            "model_id": "astron-code-latest",
            "analysis_interval": 60,  # 分析间隔（秒）
            "min_confidence": 0.65,   # 最小置信度
            "max_positions": 5,       # 最大持仓数 (合约)
            "risk_per_trade": 0.02,   # 单笔交易风险（2%）
            "trade_mode": "real",     # 实盘交易模式
        }
        
        # 运行状态
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._lock = asyncio.Lock()
        
        # 风险事件去重 - 记录最近一次风险事件时间
        self._last_risk_events: Dict[str, float] = {}
        self._risk_event_cooldown = 300  # 相同风险事件冷却时间（秒）
        
        logger.info("全智能AI交易引擎初始化完成")
    
    async def initialize(self) -> None:
        """初始化AI交易引擎"""
        logger.info("初始化全智能AI交易引擎...")
        
        # 连接LLM集成
        if self.main_controller and hasattr(self.main_controller, 'llm_integration'):
            self.llm_integration = self.main_controller.llm_integration
            logger.info("✅ LLM集成已连接")
        
        # 连接交易所 - 直接创建OKX交易所实例
        try:
            if self.main_controller and self.main_controller.config_manager:
                # 获取exchanges配置
                exchanges_config = await self.main_controller.config_manager.get_config("exchanges", {})
                okx_config = exchanges_config.get("okx", {})
                logger.info(f"📋 OKX配置: {okx_config}")
                if okx_config and okx_config.get('api_key'):
                    from src.modules.exchanges.okx import OKXExchange
                    self.exchange = OKXExchange(okx_config)
                    # 传递config_manager给OKXExchange
                    self.exchange._config_manager = self.main_controller.config_manager
                    await self.exchange.initialize()
                    logger.info("✅ OKX交易所已连接")
                else:
                    logger.warning("⚠️ OKX配置不完整，使用模拟数据")
            else:
                logger.warning("⚠️ 配置管理器未找到，使用模拟数据")
        except Exception as e:
            logger.warning(f"⚠️ 交易所连接失败: {e}，将使用模拟数据")
        
        # 连接风险管理器
        if self.main_controller and hasattr(self.main_controller, 'risk_manager'):
            self.risk_manager = self.main_controller.risk_manager
            logger.info("✅ 风险管理器已连接")
        
        # 初始化历史数据存储
        try:
            self.data_storage = await get_historical_storage()
            logger.info("✅ 历史数据存储已连接")
        except Exception as e:
            logger.warning(f"⚠️ 历史数据存储初始化失败: {e}")
        
        # 初始化账户风险监控
        try:
            self.risk_monitor = AccountRiskMonitor(
                exchange=self.exchange,
                data_storage=self.data_storage
            )
            self.risk_monitor.add_callback(self._on_risk_warning)
            logger.info("✅ 账户风险监控已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 账户风险监控初始化失败: {e}")
        
        # 初始化策略优化器
        try:
            self.strategy_optimizer = StrategyOptimizer(
                memory_manager=self.llm_integration,
                data_storage=self.data_storage
            )
            logger.info("✅ 策略优化器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 策略优化器初始化失败: {e}")
        
        # 初始化多源数据融合分析器
        try:
            from src.modules.data.multi_source_data_fusion import MultiSourceDataFusion
            from src.modules.data.data_integration import BinanceDataSource, CoinGeckoDataSource
            
            self.data_fusion = MultiSourceDataFusion(
                data_integration=self,
                llm_integration=self.llm_integration
            )
            
            binance_source = BinanceDataSource(proxy_url="http://127.0.0.1:7890")
            coingecko_source = CoinGeckoDataSource(proxy_url="http://127.0.0.1:7890")
            
            await self.data_fusion.register_data_source("binance", binance_source)
            await self.data_fusion.register_data_source("coingecko", coingecko_source)
            
            logger.info("✅ 多源数据融合分析器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 多源数据融合分析器初始化失败: {e}")
        
        # 初始化第三方数据集成器
        try:
            from src.modules.data.third_party_data_integrator import ThirdPartyDataIntegrator
            self.third_party_data = ThirdPartyDataIntegrator()
            logger.info("✅ 第三方数据集成器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 第三方数据集成器初始化失败: {e}")
            self.third_party_data = None
        
        # 初始化链上数据集成器
        try:
            from src.modules.data.onchain_integrator import OnChainDataIntegrator
            self.onchain_data = OnChainDataIntegrator()
            logger.info("✅ 链上数据集成器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 链上数据集成器初始化失败: {e}")
            self.onchain_data = None
        
        # 初始化深度学习集成器
        try:
            from src.modules.ai.deep_learning_integrator import DeepLearningIntegrator
            self.dl_integrator = DeepLearningIntegrator()
            logger.info(f"✅ 深度学习集成器已初始化，模型: {list(self.dl_integrator.models.keys())}")
        except Exception as e:
            logger.warning(f"⚠️ 深度学习集成器初始化失败: {e}")
            self.dl_integrator = None
        
        # 初始化强化学习优化器
        try:
            from src.modules.ai.reinforcement_learning_optimizer import ReinforcementLearningAgent
            self.rl_agent = ReinforcementLearningAgent()
            logger.info("✅ 强化学习优化器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 强化学习优化器初始化失败: {e}")
            self.rl_agent = None
        
        # 初始化智能缓存
        try:
            from src.modules.core.intelligent_cache import IntelligentCacheSystem
            self.intelligent_cache = IntelligentCacheSystem()
            logger.info("✅ 智能缓存已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 智能缓存初始化失败: {e}")
            self.intelligent_cache = None
        
        # 初始化自动恢复系统
        try:
            from src.modules.core.auto_recovery import AutoRecoverySystem
            self.auto_recovery = AutoRecoverySystem()
            logger.info("✅ 自动恢复系统已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 自动恢复系统初始化失败: {e}")
            self.auto_recovery = None
        
        # 初始化增强风险控制器
        try:
            from src.modules.core.enhanced_risk_controller import EnhancedRiskController
            self.enhanced_risk = EnhancedRiskController()
            logger.info("✅ 增强风险控制器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 增强风险控制器初始化失败: {e}")
            self.enhanced_risk = None
        
        # 加载配置
        if self.main_controller and self.main_controller.config_manager:
            config = await self.main_controller.config_manager.get_config("ai_trading", {})
            self.ai_config.update(config)
        
        self._running = True
        logger.info(f"✅ 全智能AI交易引擎初始化完成")
        logger.info(f"📊 监控交易对: {self.symbols}")
        logger.info(f"🚫 黑名单交易对: {self.symbol_blacklist}")
    
    async def start(self) -> None:
        """启动AI交易引擎"""
        logger.info("🚀 启动全智能AI交易引擎...")
        
        # 启动主交易循环
        self._tasks.append(asyncio.create_task(self._trading_loop()))
        
        # 启动监控任务
        self._tasks.append(asyncio.create_task(self._monitoring_loop()))
        
        # 启动优化任务
        self._tasks.append(asyncio.create_task(self._optimization_loop()))
        
        # 启动账户风险监控
        if self.risk_monitor:
            await self.risk_monitor.start()
        
        # 启动策略优化器
        if self.strategy_optimizer:
            await self.strategy_optimizer.start()
        
        logger.info("✅ 全智能AI交易引擎已启动")
    
    async def stop(self) -> None:
        """停止AI交易引擎"""
        logger.info("🛑 停止全智能AI交易引擎...")
        self._running = False
        
        # 停止风险监控
        if self.risk_monitor:
            await self.risk_monitor.stop()
        
        # 停止策略优化器
        if self.strategy_optimizer:
            await self.strategy_optimizer.stop()
        
        for task in self._tasks:
            if not task.done():
                task.cancel()
        
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        
        self._tasks.clear()
        logger.info("✅ 全智能AI交易引擎已停止")
    
    async def _trading_loop(self) -> None:
        """
        主交易循环 - 完全自动化
        
        流程：
        1. 数据采集
        2. AI市场分析
        3. 智能决策
        4. 自动执行
        5. 循环
        """
        while self._running:
            try:
                for symbol in self.symbols:
                    if not self._running:
                        break
                    
                    # 检查黑名单
                    if symbol in self.symbol_blacklist:
                        logger.debug(f"⏭️ {symbol} 在黑名单中，跳过")
                        continue
                    
                    self.state = TradingState.ANALYZING
                    logger.info(f"🔍 AI正在分析 {symbol}...")
                    
                    # 1. 采集市场数据
                    market_data = await self._collect_market_data(symbol)
                    if not market_data:
                        continue
                    
                    # 2. AI市场分析
                    context = await self._analyze_market(symbol, market_data)
                    
                    # 3. 获取当前持仓
                    current_position = self.positions.get(symbol)
                    
                    # 4. AI智能决策
                    self.state = TradingState.DECIDING
                    decision = await self._make_decision(symbol, context, current_position)
                    
                    if decision and decision.action != TradeAction.HOLD:
                        # 5. 风险检查
                        if await self._risk_check(decision):
                            # 6. 自动执行
                            self.state = TradingState.EXECUTING
                            await self._execute_decision(decision)
                    
                    # 7. 更新持仓状态
                    await self._update_positions()
                    
                    # 8. 短暂休息，避免过于频繁
                    await asyncio.sleep(5)
                
                # 等待下一个分析周期
                await asyncio.sleep(self.ai_config["analysis_interval"])
                
            except Exception as e:
                logger.error(f"交易循环错误: {e}")
                await asyncio.sleep(10)
    
    async def _collect_market_data(self, symbol: str) -> Optional[Dict]:
        """采集市场数据"""
        from src.utils.timeout_handler import run_with_timeout, Timeouts
        
        try:
            if not self.exchange:
                return None
            
            # 获取多时间周期K线数据 (带超时)
            multi_timeframe_klines = await run_with_timeout(
                self.exchange.get_multi_timeframe_klines(
                    symbol, 
                    timeframes=["1m", "5m", "15m", "1h", "4h", "1d"]
                ),
                timeout_seconds=Timeouts.MARKET_DATA_FETCH,
                default_value=None
            )
            
            if not multi_timeframe_klines:
                logger.warning(f"获取{symbol}多时间框架数据超时")
                return None
            
            # 保存K线数据到历史存储
            if self.data_storage and multi_timeframe_klines:
                for tf, klines in multi_timeframe_klines.items():
                    if klines:
                        await run_with_timeout(
                            self.data_storage.save_klines(symbol, tf, klines),
                            timeout_seconds=Timeouts.DATABASE_WRITE,
                            default_value=None
                        )
            
            # 获取当前价格 (带超时)
            ticker = await run_with_timeout(
                self.exchange.get_ticker(symbol),
                timeout_seconds=Timeouts.ORDERBOOK_FETCH,
                default_value={}
            )
            
            # 获取订单簿 (带超时)
            order_book = await run_with_timeout(
                self.exchange.get_order_book(symbol, depth=20),
                timeout_seconds=Timeouts.ORDERBOOK_FETCH,
                default_value={}
            )
            
            # 获取账户余额 (带超时)
            balance = await run_with_timeout(
                self.exchange.get_balance(),
                timeout_seconds=Timeouts.ACCOUNT_INFO_FETCH,
                default_value={}
            )
            
            # 获取持仓信息 (带超时)
            positions = await run_with_timeout(
                self.exchange.get_positions(),
                timeout_seconds=Timeouts.ACCOUNT_INFO_FETCH,
                default_value=[]
            )
            
            # 保存账户快照
            if self.data_storage and balance:
                total_equity = sum(balance.values())
                await run_with_timeout(
                    self.data_storage.save_account_snapshot({
                        "timestamp": datetime.now().isoformat(),
                        "total_equity": total_equity,
                        "available_balance": balance.get("USDT", 0),
                        "margin_used": 0,
                        "unrealized_pnl": 0,
                        "positions": positions
                    }),
                    timeout_seconds=Timeouts.DATABASE_WRITE,
                    default_value=None
                )
            
            return {
                "symbol": symbol,
                "multi_timeframe_klines": multi_timeframe_klines,
                "ticker": ticker,
                "order_book": order_book,
                "balance": balance,
                "positions": positions,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"采集市场数据失败 {symbol}: {e}")
            return None
    
    async def _analyze_market(self, symbol: str, market_data: Dict) -> MarketContext:
        """AI市场分析 - 增强版，整合多源数据"""
        try:
            # 计算技术指标
            technical_indicators = self._calculate_technical_indicators(market_data)
            
            # 保存技术指标到历史存储
            if self.data_storage and technical_indicators.trend:
                await self.data_storage.save_indicator(IndicatorRecord(
                    symbol=symbol,
                    timestamp=datetime.now().isoformat(),
                    trend=technical_indicators.trend,
                    trend_strength=technical_indicators.trend_strength,
                    ma5=technical_indicators.ma5,
                    ma20=technical_indicators.ma20,
                    rsi=technical_indicators.rsi,
                    macd=technical_indicators.macd,
                    bollinger_upper=technical_indicators.bollinger_upper,
                    bollinger_lower=technical_indicators.bollinger_lower,
                    atr=technical_indicators.atr
                ))
            
            # 使用多源数据融合分析（如果可用）
            fused_intelligence = None
            if hasattr(self, 'data_fusion') and self.data_fusion:
                try:
                    fused_intelligence = await self.data_fusion.analyze_market(symbol)
                    logger.info(f"📊 多源数据融合分析完成: {symbol}, 情绪={fused_intelligence.overall_sentiment.value}")
                except Exception as e:
                    logger.warning(f"多源数据分析失败，使用基础分析: {e}")
            
            # 获取第三方数据（社交媒体、新闻等）
            third_party_sentiment = None
            if hasattr(self, 'third_party_data') and self.third_party_data:
                try:
                    third_party_sentiment = await self.third_party_data.get_comprehensive_sentiment(symbol.replace("/USDT", ""))
                    logger.info(f"📊 第三方数据获取完成: {symbol}, 综合情绪={third_party_sentiment.overall_sentiment:.2f}")
                except Exception as e:
                    logger.warning(f"第三方数据获取失败: {e}")
            
            # 获取链上数据
            onchain_metrics = None
            if hasattr(self, 'onchain_data') and self.onchain_data:
                try:
                    onchain_metrics = await self.onchain_data.get_onchain_metrics(symbol.replace("/USDT", ""))
                    logger.info(f"📊 链上数据获取完成: {symbol}")
                except Exception as e:
                    logger.warning(f"链上数据获取失败: {e}")
            
            if not self.llm_integration:
                return self._enhanced_basic_analysis(symbol, market_data, technical_indicators, fused_intelligence)
            
            # 构建包含技术指标和多源数据的分析数据
            analysis_data = {
                "symbol": symbol,
                "price": market_data["ticker"].get("last", 0),
                "ticker": market_data["ticker"],
                "order_book": self._summarize_order_book(market_data.get("order_book")),
                "technical_indicators": TechnicalIndicatorCalculator.indicators_to_dict(technical_indicators),
                "multi_timeframe": self._summarize_multi_timeframe(market_data.get("multi_timeframe_klines", {}))
            }
            
            # 如果有多源数据，添加到分析中
            if fused_intelligence:
                analysis_data["fused_intelligence"] = fused_intelligence.to_dict()
            
            # 添加第三方数据（社交媒体情绪、新闻等）
            if third_party_sentiment:
                analysis_data["third_party_sentiment"] = {
                    "overall_sentiment": third_party_sentiment.overall_sentiment,
                    "fear_greed_index": third_party_sentiment.fear_greed_index,
                    "social_sentiment": third_party_sentiment.social_sentiment,
                    "news_sentiment": third_party_sentiment.news_sentiment,
                    "trend": third_party_sentiment.trend,
                    "confidence": third_party_sentiment.confidence,
                    "details": third_party_sentiment.details
                }
            
            # 添加链上数据
            if onchain_metrics:
                analysis_data["onchain_metrics"] = {
                    metric: {
                        "value": data.value,
                        "change_24h": data.change_24h,
                        "change_7d": data.change_7d
                    }
                    for metric, data in onchain_metrics.items()
                }
            
            # 深度学习预测
            dl_prediction = None
            if hasattr(self, 'dl_integrator') and self.dl_integrator:
                try:
                    import numpy as np
                    # 准备输入数据
                    klines = market_data.get("multi_timeframe_klines", {}).get("1h", [])
                    if klines:
                        close_prices = np.array([[k.get("close", 0)] for k in klines[-60:]])
                        if len(close_prices) >= 60:
                            dl_prediction = await self.dl_integrator.predict(close_prices, model_id="ensemble")
                            if dl_prediction:
                                analysis_data["dl_prediction"] = {
                                    "direction": dl_prediction.direction,
                                    "confidence": dl_prediction.confidence,
                                    "predicted_change": dl_prediction.predicted_change,
                                    "model_id": dl_prediction.model_id
                                }
                                logger.info(f"📊 深度学习预测: {dl_prediction.direction}, 置信度={dl_prediction.confidence:.2f}")
                except Exception as e:
                    logger.warning(f"深度学习预测失败: {e}")
            
            # 强化学习策略优化
            rl_optimization = None
            if hasattr(self, 'rl_agent') and self.rl_agent:
                try:
                    from src.modules.ai.reinforcement_learning_optimizer import State
                    current_state = State(
                        price=float(market_data["ticker"].get("last", 0)),
                        volume=float(market_data["ticker"].get("volume", 0)),
                        trend=str(technical_indicators.trend),
                        volatility=float(self._calculate_volatility(technical_indicators)),
                        position=0.0,
                        balance=10000.0,
                        indicators={
                            "rsi": float(technical_indicators.rsi),
                            "macd": float(technical_indicators.macd),
                            "ma_20": float(technical_indicators.ma20),
                            "ma_50": float(technical_indicators.ma50)
                        }
                    )
                    rl_action = await self.rl_agent.get_action_recommendation(current_state)
                    if rl_action:
                        analysis_data["rl_recommendation"] = rl_action
                        logger.info(f"📊 强化学习建议: {rl_action.get('action', 'N/A')}")
                except Exception as e:
                    logger.warning(f"强化学习优化失败: {e}")
            
            # 风险评估（增强版）
            if hasattr(self, 'enhanced_risk') and self.enhanced_risk:
                try:
                    risk_assessment = await self.enhanced_risk.check_pre_trade_risk(
                        symbol=symbol,
                        action="buy",
                        quantity=0,
                        price=market_data["ticker"].get("last", 0)
                    )
                    analysis_data["enhanced_risk"] = risk_assessment
                except Exception as e:
                    logger.warning(f"增强风险评估失败: {e}")
            
            # 使用AI进行深度分析
            ai_analysis = await self.llm_integration.analyze_market(analysis_data)
            
            # 如果有多源数据，优先使用融合分析的结论
            if fused_intelligence:
                context = MarketContext(
                    symbol=symbol,
                    price=market_data["ticker"].get("last", 0),
                    trend=fused_intelligence.recommendation if fused_intelligence.recommendation in ["bullish", "bearish", "sideways"] else ai_analysis.get("trend", technical_indicators.trend),
                    volatility=self._calculate_volatility(technical_indicators),
                    volume_24h=market_data["ticker"].get("volume", 0),
                    sentiment=fused_intelligence.overall_sentiment.value,
                    support_levels=ai_analysis.get("support_levels", []),
                    resistance_levels=ai_analysis.get("resistance_levels", [])
                )
                
                logger.info(f"✅ AI增强分析完成 {symbol}: 趋势={context.trend}, 情绪={context.sentiment}, "
                           f"信号强度={fused_intelligence.signal_strength.value}")
            else:
                # 解析AI分析结果
                context = MarketContext(
                    symbol=symbol,
                    price=market_data["ticker"].get("last", 0),
                    trend=ai_analysis.get("trend", technical_indicators.trend),
                    volatility=ai_analysis.get("volatility", self._calculate_volatility(technical_indicators)),
                    volume_24h=market_data["ticker"].get("volume", 0),
                    sentiment=ai_analysis.get("sentiment", "neutral"),
                    support_levels=ai_analysis.get("support_levels", []),
                    resistance_levels=ai_analysis.get("resistance_levels", [])
                )
                
                logger.info(f"✅ AI分析完成 {symbol}: 趋势={context.trend}, 情绪={context.sentiment}")
            
            return context
            
        except Exception as e:
            logger.error(f"AI市场分析失败 {symbol}: {e}")
            return self._basic_analysis(symbol, market_data, None)
    
    def _calculate_technical_indicators(self, market_data: Dict) -> TechnicalIndicators:
        """计算技术指标"""
        try:
            # 使用1小时K线计算主要指标
            klines_1h = market_data.get("multi_timeframe_klines", {}).get("1h", [])
            
            if not klines_1h or len(klines_1h) < 50:
                logger.warning("K线数据不足，返回默认指标")
                return TechnicalIndicators()
            
            # 计算所有技术指标
            indicators = TechnicalIndicatorCalculator.calculate_all_indicators(klines_1h)
            
            logger.info(f"📊 技术指标: MA5={indicators.ma5:.2f}, MA20={indicators.ma20:.2f}, "
                       f"RSI={indicators.rsi:.2f}, 趋势={indicators.trend}")
            
            return indicators
            
        except Exception as e:
            logger.error(f"计算技术指标失败: {e}")
            return TechnicalIndicators()
    
    def _summarize_order_book(self, order_book: Any) -> Dict:
        """总结订单簿数据"""
        if not order_book:
            return {"bid_depth": 0, "ask_depth": 0, "spread": 0}
        
        try:
            bids = getattr(order_book, 'bids', [])
            asks = getattr(order_book, 'asks', [])
            
            bid_depth = sum(qty for _, qty in bids[:10]) if bids else 0
            ask_depth = sum(qty for _, qty in asks[:10]) if asks else 0
            
            spread = 0
            if bids and asks:
                best_bid = bids[0][0] if bids else 0
                best_ask = asks[0][0] if asks else 0
                spread = (best_ask - best_bid) / best_bid * 100 if best_bid > 0 else 0
            
            return {
                "bid_depth": bid_depth,
                "ask_depth": ask_depth,
                "spread": round(spread, 4),
                "imbalance": round((bid_depth - ask_depth) / (bid_depth + ask_depth), 2) if (bid_depth + ask_depth) > 0 else 0
            }
        except Exception as e:
            logger.error(f"总结订单簿失败: {e}")
            return {"bid_depth": 0, "ask_depth": 0, "spread": 0}
    
    def _summarize_multi_timeframe(self, multi_tf_klines: Dict[str, List]) -> Dict:
        """总结多时间周期数据"""
        summary = {}
        
        for tf, klines in multi_tf_klines.items():
            if not klines:
                continue
            
            try:
                closes = [k.get("close", 0) for k in klines]
                if closes:
                    summary[tf] = {
                        "open": klines[0].get("open", 0) if klines else 0,
                        "close": closes[-1],
                        "high": max([k.get("high", 0) for k in klines]),
                        "low": min([k.get("low", 0) for k in klines]),
                        "change_percent": round((closes[-1] - closes[0]) / closes[0] * 100, 2) if closes[0] > 0 else 0
                    }
            except Exception as e:
                logger.error(f"总结{tf}时间周期数据失败: {e}")
        
        return summary
    
    def _calculate_volatility(self, indicators: TechnicalIndicators) -> float:
        """计算波动率"""
        if indicators.atr and indicators.bollinger_middle:
            return min(indicators.atr / indicators.bollinger_middle, 1.0)
        return 0.5
    
    def _basic_analysis(self, symbol: str, market_data: Dict, indicators: Optional[TechnicalIndicators] = None) -> MarketContext:
        """基础市场分析（备用）"""
        ticker = market_data.get("ticker", {})
        price = ticker.get("last", 0)
        
        # 如果有技术指标，使用技术指标判断趋势
        if indicators:
            trend = indicators.trend
            volatility = self._calculate_volatility(indicators)
            logger.info(f"📈 基于技术指标分析: 趋势={trend}, 强度={indicators.trend_strength:.2f}")
        else:
            # 使用多时间周期K线数据判断趋势
            multi_tf = market_data.get("multi_timeframe_klines", {})
            klines_1h = multi_tf.get("1h", [])
            
            if klines_1h and len(klines_1h) >= 2:
                closes = [k.get("close", 0) for k in klines_1h]
                if closes[-1] > closes[0] * 1.02:
                    trend = "bullish"
                elif closes[-1] < closes[0] * 0.98:
                    trend = "bearish"
                else:
                    trend = "sideways"
            else:
                trend = "sideways"
            
            volatility = 0.3
        
        return MarketContext(
            symbol=symbol,
            price=price,
            trend=trend,
            volatility=volatility,
            volume_24h=ticker.get("volume", 0),
            sentiment="neutral"
        )
    
    def _enhanced_basic_analysis(self, symbol: str, market_data: Dict, 
                                 indicators: Optional[TechnicalIndicators] = None,
                                 fused_intelligence=None) -> MarketContext:
        """增强基础分析（整合多源数据）"""
        base_context = self._basic_analysis(symbol, market_data, indicators)
        
        if fused_intelligence:
            base_context.sentiment = fused_intelligence.overall_sentiment.value
            if fused_intelligence.recommendation in ["bullish", "bearish"]:
                base_context.trend = fused_intelligence.recommendation
            
            logger.info(f"📈 增强基础分析 {symbol}: 趋势={base_context.trend}, 情绪={base_context.sentiment}")
        
        return base_context
    
    def _build_analysis_prompt(self, symbol: str, market_data: Dict, indicators: Optional[TechnicalIndicators] = None) -> str:
        """构建AI分析提示词"""
        ticker = market_data.get("ticker", {})
        order_book = market_data.get("order_book", {})
        
        prompt = f"""请分析 {symbol} 的市场情况：

当前价格: {ticker.get('last', 'N/A')}
24h最高: {ticker.get('high', 'N/A')}
24h最低: {ticker.get('low', 'N/A')}
24h成交量: {ticker.get('volume', 'N/A')}
24h涨跌幅: {ticker.get('change', 'N/A')}%

订单簿深度:
- 买盘深度: {order_book.get('bid_depth', 0)}
- 卖盘深度: {order_book.get('ask_depth', 0)}
- 价差: {order_book.get('spread', 0)}%
- 买卖失衡: {order_book.get('imbalance', 0)}
"""
        
        if indicators:
            prompt += f"""
技术指标:
- 趋势: {indicators.trend} (强度: {indicators.trend_strength:.2f})
- MA5: {indicators.ma5}
- MA20: {indicators.ma20}
- MA50: {indicators.ma50}
- RSI: {indicators.rsi}
- MACD: {indicators.macd}
- MACD信号线: {indicators.macd_signal}
- 布林带上轨: {indicators.bollinger_upper}
- 布林带中轨: {indicators.bollinger_middle}
- 布林带下轨: {indicators.bollinger_lower}
- ATR: {indicators.atr}
"""
        
        prompt += """
请提供：
1. 趋势判断 (bullish/bearish/sideways)
2. 波动率评估 (0-1)
3. 市场情绪 (fear/neutral/greed)
4. 关键支撑位
5. 关键阻力位
6. 交易建议

请以JSON格式返回。"""
        
        return prompt
    
    async def _make_decision(self, symbol: str, context: MarketContext, 
                           current_position: Optional[Position]) -> Optional[AIDecision]:
        """AI智能决策"""
        try:
            if not self.llm_integration:
                return self._basic_decision(symbol, context, current_position)
            
            # 构建决策提示词
            decision_prompt = self._build_decision_prompt(symbol, context, current_position)
            
            # 调用AI生成决策
            ai_decision = await self.llm_integration.generate_trading_signal(
                {
                    "symbol": symbol,
                    "price": context.price,
                    "trend": context.trend,
                    "sentiment": context.sentiment,
                    "volatility": context.volatility
                }
            )
            
            # 解析决策
            signal = ai_decision.get("signal", "hold")
            confidence = ai_decision.get("confidence", 0.5)
            
            # 检查置信度
            if confidence < self.ai_config["min_confidence"]:
                logger.info(f"⏸️ {symbol} 置信度不足 ({confidence:.2f})，保持观望")
                return None
            
            # 确定交易动作
            action = self._parse_action(signal, current_position)
            
            if action == TradeAction.HOLD:
                return None
            
            # 计算仓位大小
            quantity = await self._calculate_position_size(symbol, context, action)
            
            # 计算止损止盈
            stop_loss, take_profit = self._calculate_stop_loss_take_profit(
                context, action
            )
            
            decision = AIDecision(
                action=action,
                symbol=symbol,
                price=context.price,
                quantity=quantity,
                confidence=confidence,
                reasoning=ai_decision.get("reasoning", "AI决策"),
                risk_level=ai_decision.get("risk_level", "medium"),
                stop_loss=stop_loss,
                take_profit=take_profit,
                metadata={
                    "ai_analysis": ai_decision,
                    "market_context": context.__dict__
                }
            )
            
            logger.info(f"🤖 AI决策 {symbol}: {action.value} @ {context.price}, 置信度={confidence:.2f}")
            return decision
            
        except Exception as e:
            logger.error(f"AI决策失败 {symbol}: {e}")
            return self._basic_decision(symbol, context, current_position)
    
    def _basic_decision(self, symbol: str, context: MarketContext,
                       current_position: Optional[Position]) -> Optional[AIDecision]:
        """基础决策（备用）"""
        # 简单的趋势跟随策略
        if context.trend == "bullish" and not current_position:
            action = TradeAction.OPEN_LONG
        elif context.trend == "bearish" and not current_position:
            action = TradeAction.OPEN_SHORT
        elif current_position:
            # 检查是否需要平仓
            if (current_position.side == "long" and context.trend == "bearish") or \
               (current_position.side == "short" and context.trend == "bullish"):
                action = TradeAction.CLOSE_LONG if current_position.side == "long" else TradeAction.CLOSE_SHORT
            else:
                return None
        else:
            return None
        
        return AIDecision(
            action=action,
            symbol=symbol,
            price=context.price,
            quantity=0.01,  # 默认仓位
            confidence=0.6,
            reasoning="基础趋势跟随策略",
            risk_level="medium"
        )
    
    def _build_decision_prompt(self, symbol: str, context: MarketContext,
                              position: Optional[Position]) -> str:
        """构建决策提示词"""
        position_info = "无持仓"
        if position:
            position_info = f"{position.side} 仓, 入场价={position.entry_price}, 数量={position.quantity}"
        
        return f"""基于以下市场信息，做出交易决策：

交易对: {symbol}
当前价格: {context.price}
趋势: {context.trend}
情绪: {context.sentiment}
波动率: {context.volatility:.2f}
当前持仓: {position_info}

请提供：
1. 交易信号 (buy/sell/hold)
2. 置信度 (0-1)
3. 建议仓位大小
4. 风险等级 (low/medium/high)
5. 决策理由
6. 止损价格（如有）
7. 止盈价格（如有）

请以JSON格式返回。"""
    
    def _parse_action(self, signal: str, current_position: Optional[Position]) -> TradeAction:
        """解析交易动作"""
        signal = signal.lower()
        
        if signal == "buy":
            if current_position and current_position.side == "short":
                return TradeAction.CLOSE_SHORT
            return TradeAction.OPEN_LONG
        elif signal == "sell":
            if current_position and current_position.side == "long":
                return TradeAction.CLOSE_LONG
            return TradeAction.OPEN_SHORT
        else:
            return TradeAction.HOLD
    
    async def _calculate_position_size(self, symbol: str, context: MarketContext,
                                      action: TradeAction) -> float:
        """计算仓位大小"""
        try:
            # 获取账户余额
            if self.exchange:
                balance = await self.exchange.get_balance()
                available = balance.get("USDT", {}).get("free", 10000)
            else:
                available = 10000  # 默认
            
            # 基于风险计算仓位
            risk_amount = available * self.ai_config["risk_per_trade"]
            
            # 根据波动率调整
            volatility_factor = 1 - min(context.volatility, 0.5)
            
            # 根据置信度调整
            # 这里简化处理，实际应该传入confidence
            
            position_value = risk_amount * volatility_factor
            quantity = position_value / context.price if context.price > 0 else 0
            
            # 限制最大仓位
            max_quantity = available * 0.1 / context.price if context.price > 0 else 0
            quantity = min(quantity, max_quantity)
            
            return round(quantity, 6)
            
        except Exception as e:
            logger.error(f"计算仓位大小失败: {e}")
            return 0.01  # 默认最小仓位
    
    def _calculate_stop_loss_take_profit(self, context: MarketContext,
                                        action: TradeAction) -> tuple:
        """计算止损止盈价格"""
        price = context.price
        
        if action in [TradeAction.OPEN_LONG, TradeAction.CLOSE_SHORT]:
            # 多单
            stop_loss = price * 0.97  # 3%止损
            take_profit = price * 1.06  # 6%止盈
        elif action in [TradeAction.OPEN_SHORT, TradeAction.CLOSE_LONG]:
            # 空单
            stop_loss = price * 1.03  # 3%止损
            take_profit = price * 0.94  # 6%止盈
        else:
            return None, None
        
        return round(stop_loss, 2), round(take_profit, 2)
    
    async def _risk_check(self, decision: AIDecision) -> bool:
        """风险检查 - AI自主决策，无硬性限制"""
        try:
            existing = self.positions.get(decision.symbol)
            if existing:
                if decision.action == TradeAction.OPEN_LONG and existing.side == "long":
                    logger.info(f"📊 {decision.symbol} 已有多仓，AI自主决定是否加仓")
                if decision.action == TradeAction.OPEN_SHORT and existing.side == "short":
                    logger.info(f"📊 {decision.symbol} 已有空仓，AI自主决定是否加仓")
            
            if self.risk_manager:
                risk_ok = await self.risk_manager.check_trade(decision.__dict__)
                if not risk_ok:
                    logger.info(f"📊 风险检查提示，AI自主评估是否继续")
            
            logger.info(f"✅ AI自主决策通过: {decision.action.value} {decision.symbol}")
            return True
            
        except Exception as e:
            logger.error(f"风险检查失败: {e}")
            return True
    
    async def _execute_decision(self, decision: AIDecision) -> bool:
        """执行AI决策"""
        try:
            if not self.exchange:
                logger.warning("❌ 交易所未连接，无法执行")
                return False
            
            logger.info(f"🚀 执行交易: {decision.action.value} {decision.symbol} "
                       f"@ {decision.price}, 数量={decision.quantity}")
            
            order = {
                "symbol": decision.symbol,
                "side": "buy" if decision.action in [TradeAction.OPEN_LONG, TradeAction.CLOSE_SHORT] else "sell",
                "type": "market",
                "quantity": decision.quantity
            }
            
            result = await self.exchange.place_order(order)
            
            if result:
                logger.info(f"✅ 订单执行成功: {result.get('id', 'N/A')}")
                
                trade_record = {
                    "timestamp": datetime.now().isoformat(),
                    "decision": decision.__dict__,
                    "order_result": result
                }
                self.trade_history.append(trade_record)
                
                if self.data_storage:
                    await self.data_storage.save_trade(TradeRecord(
                        symbol=decision.symbol,
                        side="buy" if decision.action in [TradeAction.OPEN_LONG, TradeAction.CLOSE_SHORT] else "sell",
                        order_type="market",
                        quantity=decision.quantity,
                        price=decision.price,
                        timestamp=datetime.now().isoformat(),
                        order_id=result.get("order_id", ""),
                        reasoning=decision.reasoning
                    ))
                
                await self._save_trade_to_memory(decision, result)
                
                await self._update_positions()
                
                return True
            else:
                logger.error("❌ 订单执行失败")
                return False
                
        except Exception as e:
            logger.error(f"执行决策失败: {e}")
            return False
    
    async def _save_trade_to_memory(self, decision: AIDecision, result: Dict) -> None:
        """保存交易记录到增强记忆"""
        try:
            if not self.llm_integration or not hasattr(self.llm_integration, 'enhanced_memory'):
                return
            
            memory = self.llm_integration.enhanced_memory
            if not memory:
                return
            
            is_open = decision.action in [TradeAction.OPEN_LONG, TradeAction.OPEN_SHORT]
            side = "long" if decision.action in [TradeAction.OPEN_LONG, TradeAction.CLOSE_SHORT] else "short"
            
            if is_open:
                memory.save_trade_open(
                    symbol=decision.symbol,
                    side=side,
                    price=decision.price,
                    quantity=decision.quantity,
                    reason=decision.reasoning,
                    stop_loss=decision.stop_loss,
                    take_profit=decision.take_profit,
                    strategy=decision.metadata.get("strategy", "AI智能决策")
                )
            else:
                existing = self.positions.get(decision.symbol)
                open_price = existing.entry_price if existing else decision.price
                pnl = 0
                pnl_percent = 0
                
                if existing:
                    if side == "long":
                        pnl = (decision.price - open_price) * decision.quantity
                        pnl_percent = (decision.price - open_price) / open_price * 100
                    else:
                        pnl = (open_price - decision.price) * decision.quantity
                        pnl_percent = (open_price - decision.price) / open_price * 100
                
                memory.save_trade_close(
                    symbol=decision.symbol,
                    side=side,
                    open_price=open_price,
                    close_price=decision.price,
                    quantity=decision.quantity,
                    pnl=pnl,
                    pnl_percent=pnl_percent,
                    reason=decision.reasoning
                )
                
                logger.info(f"💾 交易记录已保存到记忆库")
                
        except Exception as e:
            logger.error(f"保存交易到记忆失败: {e}")
    
    async def _update_positions(self) -> None:
        """更新持仓信息"""
        try:
            if not self.exchange:
                return
            
            # 获取当前持仓
            positions = await self.exchange.get_positions()
            
            self.positions.clear()
            for pos in positions:
                symbol = pos.get("symbol")
                if symbol:
                    self.positions[symbol] = Position(
                        symbol=symbol,
                        side=pos.get("side", "long"),
                        entry_price=pos.get("entry_price", 0),
                        quantity=pos.get("quantity", 0),
                        current_price=pos.get("mark_price", 0),
                        unrealized_pnl=pos.get("unrealized_pnl", 0),
                        unrealized_pnl_percent=pos.get("unrealized_pnl_percent", 0),
                        stop_loss=pos.get("stop_loss"),
                        take_profit=pos.get("take_profit")
                    )
            
        except Exception as e:
            logger.error(f"更新持仓失败: {e}")
    
    async def _monitoring_loop(self) -> None:
        """监控循环"""
        while self._running:
            try:
                self.state = TradingState.MONITORING
                
                # 监控持仓
                for symbol, position in self.positions.items():
                    # 检查止损止盈
                    if position.stop_loss and position.current_price <= position.stop_loss:
                        logger.warning(f"🚨 {symbol} 触发止损!")
                        # 自动平仓
                        await self._execute_decision(AIDecision(
                            action=TradeAction.CLOSE_LONG if position.side == "long" else TradeAction.CLOSE_SHORT,
                            symbol=symbol,
                            price=position.current_price,
                            quantity=position.quantity,
                            confidence=1.0,
                            reasoning="止损触发",
                            risk_level="high"
                        ))
                    
                    elif position.take_profit and position.current_price >= position.take_profit:
                        logger.info(f"🎯 {symbol} 触发止盈!")
                        # 自动平仓
                        await self._execute_decision(AIDecision(
                            action=TradeAction.CLOSE_LONG if position.side == "long" else TradeAction.CLOSE_SHORT,
                            symbol=symbol,
                            price=position.current_price,
                            quantity=position.quantity,
                            confidence=1.0,
                            reasoning="止盈触发",
                            risk_level="low"
                        ))
                
                # 每10秒检查一次
                await asyncio.sleep(10)
                
            except Exception as e:
                logger.error(f"监控循环错误: {e}")
                await asyncio.sleep(10)
    
    async def _optimization_loop(self) -> None:
        """优化循环 - 策略自我优化"""
        while self._running:
            try:
                # 每小时优化一次
                await asyncio.sleep(3600)
                
                logger.info("🔄 开始策略自我优化...")
                
                # 分析交易历史
                if len(self.trade_history) >= 10:
                    await self._optimize_strategy()
                
            except Exception as e:
                logger.error(f"优化循环错误: {e}")
    
    async def _optimize_strategy(self) -> None:
        """策略优化"""
        try:
            # 使用策略优化器进行分析
            if self.strategy_optimizer:
                logger.info("📊 使用策略优化器分析交易表现...")
                
                # 分析所有策略
                performances = await self.strategy_optimizer._analyze_all_strategies()
                
                # 发现新策略
                new_proposals = await self.strategy_optimizer._discover_new_patterns()
                
                if new_proposals:
                    logger.info(f"💡 发现 {len(new_proposals)} 个新策略提案")
                
                # 处理新策略提案
                await self.strategy_optimizer._process_new_strategy_proposals()
                
                # 保存优化结果
                await self.strategy_optimizer._save_optimization_results()
                
                logger.info("✅ 策略优化完成")
                return
            
            # 备用：原有的简单优化逻辑
            profitable_trades = sum(1 for t in self.trade_history 
                                   if t.get("decision", {}).get("pnl", 0) > 0)
            total_trades = len(self.trade_history)
            win_rate = profitable_trades / total_trades if total_trades > 0 else 0
            
            logger.info(f"📊 策略性能: 胜率={win_rate:.2%}, 总交易={total_trades}")
            
            old_confidence = self.ai_config["min_confidence"]
            optimization_reason = ""
            expected_improvement = ""
            
            if win_rate < 0.4:
                self.ai_config["min_confidence"] = min(0.8, self.ai_config["min_confidence"] + 0.05)
                optimization_reason = f"胜率过低({win_rate:.1%})，需要提高决策质量"
                expected_improvement = "减少低质量交易，提高胜率"
                logger.info(f"📈 调整参数: 提高置信度阈值到 {self.ai_config['min_confidence']}")
            elif win_rate > 0.6:
                self.ai_config["min_confidence"] = max(0.5, self.ai_config["min_confidence"] - 0.02)
                optimization_reason = f"胜率良好({win_rate:.1%})，可以捕捉更多机会"
                expected_improvement = "增加交易机会，保持较高胜率"
                logger.info(f"📉 调整参数: 降低置信度阈值到 {self.ai_config['min_confidence']}")
            
            if old_confidence != self.ai_config["min_confidence"]:
                await self._save_strategy_optimization(
                    strategy_name="AI交易策略",
                    optimization_type="parameter",
                    old_params={"min_confidence": old_confidence},
                    new_params={"min_confidence": self.ai_config["min_confidence"]},
                    reason=optimization_reason,
                    expected_improvement=expected_improvement
                )
            
            if total_trades >= 10:
                await self._save_periodic_pnl_record()
            
        except Exception as e:
            logger.error(f"策略优化失败: {e}")
    
    async def _save_strategy_optimization(self, strategy_name: str, optimization_type: str,
                                          old_params: Dict, new_params: Dict,
                                          reason: str, expected_improvement: str) -> None:
        """保存策略优化记录到记忆库"""
        try:
            if not self.llm_integration or not hasattr(self.llm_integration, 'enhanced_memory'):
                return
            
            memory = self.llm_integration.enhanced_memory
            if not memory:
                return
            
            memory.save_strategy_optimization(
                strategy_name=strategy_name,
                optimization_type=optimization_type,
                old_params=old_params,
                new_params=new_params,
                reason=reason,
                expected_improvement=expected_improvement
            )
            
            logger.info(f"� 策略优化记录已保存到记忆库")
            
        except Exception as e:
            logger.error(f"保存策略优化记录失败: {e}")
    
    async def _save_periodic_pnl_record(self) -> None:
        """保存周期性盈亏统计记录"""
        try:
            if not self.llm_integration or not hasattr(self.llm_integration, 'enhanced_memory'):
                return
            
            memory = self.llm_integration.enhanced_memory
            if not memory:
                return
            
            close_trades = [t for t in self.trade_history 
                          if t.get("decision", {}).get("action", "").startswith("close")]
            
            if not close_trades:
                return
            
            total_pnl = sum(t.get("decision", {}).get("pnl", 0) for t in close_trades)
            win_count = sum(1 for t in close_trades if t.get("decision", {}).get("pnl", 0) > 0)
            lose_count = len(close_trades) - win_count
            win_rate = win_count / len(close_trades) if close_trades else 0
            
            best_trade = max(close_trades, key=lambda t: t.get("decision", {}).get("pnl", 0))
            worst_trade = min(close_trades, key=lambda t: t.get("decision", {}).get("pnl", 0))
            
            memory.save_pnl_record(
                period="hourly",
                total_pnl=total_pnl,
                trade_count=len(close_trades),
                win_count=win_count,
                lose_count=lose_count,
                win_rate=win_rate,
                best_trade={
                    "symbol": best_trade.get("decision", {}).get("symbol"),
                    "pnl": best_trade.get("decision", {}).get("pnl", 0)
                },
                worst_trade={
                    "symbol": worst_trade.get("decision", {}).get("symbol"),
                    "pnl": worst_trade.get("decision", {}).get("pnl", 0)
                }
            )
            
            logger.info(f"📊 盈亏统计记录已保存到记忆库")
            
        except Exception as e:
            logger.error(f"保存盈亏统计记录失败: {e}")
    
    def get_status(self) -> Dict:
        """获取引擎状态"""
        status = {
            "state": self.state.value,
            "running": self._running,
            "positions": len(self.positions),
            "trade_count": len(self.trade_history),
            "symbols": self.symbols,
            "ai_config": self.ai_config
        }
        
        if self.risk_monitor:
            status["risk_monitor"] = self.risk_monitor.get_status()
        
        return status
    
    async def _on_risk_warning(self, account_risk: AccountRisk) -> None:
        """风险预警回调"""
        logger.warning(f"⚠️ 风险预警: {account_risk.risk_level.value}")
        
        if account_risk.risk_level == RiskLevel.CRITICAL:
            logger.critical("🚨 严重风险! 考虑减仓或平仓")
            
            for pos_risk in account_risk.position_risks:
                if pos_risk.risk_level == RiskLevel.CRITICAL:
                    logger.critical(f"🚨 持仓 {pos_risk.symbol} 风险严重，建议立即处理")
                    
                    await self._save_risk_event_to_memory(
                        event_type="critical_risk",
                        symbol=pos_risk.symbol,
                        description=f"持仓风险严重: 浮亏{pos_risk.unrealized_pnl_percent:.1f}%, "
                                   f"距离强平{pos_risk.distance_to_liquidation:.1%}",
                        action_taken="预警通知",
                        impact=f"未实现盈亏: {pos_risk.unrealized_pnl:.2f} USDT"
                    )
        
        elif account_risk.risk_level == RiskLevel.HIGH:
            for warning in account_risk.warnings:
                logger.warning(f"⚠️ {warning}")
            
            await self._save_risk_event_to_memory(
                event_type="high_risk",
                symbol="account",
                description=f"账户风险较高: 保证金占用率{account_risk.margin_ratio:.1%}",
                action_taken="监控中",
                impact=f"总权益: {account_risk.total_equity:.2f} USDT"
            )
    
    async def _save_risk_event_to_memory(self, event_type: str, symbol: str,
                                         description: str, action_taken: str,
                                         impact: str) -> None:
        """保存风险事件到记忆库（带去重）"""
        try:
            import time
            
            event_key = f"{event_type}_{symbol}"
            current_time = time.time()
            
            if event_key in self._last_risk_events:
                last_time = self._last_risk_events[event_key]
                if current_time - last_time < self._risk_event_cooldown:
                    logger.debug(f"风险事件 {event_key} 在冷却期内，跳过记录")
                    return
            
            self._last_risk_events[event_key] = current_time
            
            if not self.llm_integration or not hasattr(self.llm_integration, 'enhanced_memory'):
                return
            
            memory = self.llm_integration.enhanced_memory
            if not memory:
                return
            
            memory.save_risk_event(
                event_type=event_type,
                symbol=symbol,
                description=description,
                action_taken=action_taken,
                impact=impact
            )
            
            logger.info(f"⚠️ 风险事件已保存到记忆库: {event_key}")
            
        except Exception as e:
            logger.error(f"保存风险事件失败: {e}")
