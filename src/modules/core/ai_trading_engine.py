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
from ..exchanges.exchange_base import Order

logger = logging.getLogger(__name__)

from src.modules.memory.memory_schema import base_metadata, kind_tag, symbol_tag, tags

# Risk/loop defaults to avoid magic numbers scattered in methods
DEFAULT_MAX_POSITIONS = 5
DEFAULT_ANALYSIS_INTERVAL_SECONDS = 120
DEFAULT_LOOP_SLEEP_SECONDS = 5
DEFAULT_STOP_LOSS_LONG_RATIO = 0.97
DEFAULT_STOP_LOSS_SHORT_RATIO = 1.03
DEFAULT_TAKE_PROFIT_LONG_RATIO = 1.06
DEFAULT_TAKE_PROFIT_SHORT_RATIO = 0.94


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
    metadata: Dict[str, Any] = field(default_factory=dict)
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
    risk_level: str = "medium"  # low, medium, high
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
        
        # 统一交易历史服务（新增）
        self.trade_history_service = None
        
        # 监控的交易对
        self.symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
        self._use_dynamic_symbols = True
        self._dynamic_symbol_refresh_seconds = 300
        self._max_dynamic_symbols = 12
        self._last_symbol_sync_at: Optional[datetime] = None
        
        # 交易对黑名单
        self.symbol_blacklist = []
        
        self.contract_config = {
            "enabled": True,
            "trade_type": "swap",
            "leverage_min": 10,
            "leverage_max": 50,
            "default_leverage": 20,
            "max_positions": DEFAULT_MAX_POSITIONS,
            "min_positions": 1,
            "margin_mode": "cross",
            "grid_trading": False,
            "grid_levels": 5,
            "grid_spacing": 0.02,
        }
        
        self.ai_config = {
            "enabled": True,
            "model_id": "astron-code-latest",
            "analysis_interval": DEFAULT_ANALYSIS_INTERVAL_SECONDS,
            "min_confidence": 0.75,
            "max_positions": DEFAULT_MAX_POSITIONS,
            "max_same_direction_positions": 5,
            "max_hedged_positions": 8,
            "risk_per_trade": 0.01,
            "max_symbol_position_ratio": 0.2,
            "max_total_exposure_ratio": 0.8,
            "trade_mode": "real",
            "auto_risk_management": True,
            "critical_risk_auto_close": True,
            # 自动强平保护闸：默认仅在“非常接近强平”时自动平仓，避免把普通浮亏当成强制平仓。
            "critical_risk_auto_close_liq_only": True,
            "critical_risk_auto_close_max_liq_distance": 0.02,
            "critical_risk_auto_close_min_loss_pct": 25.0,
            "max_loss_per_position": 0.05,
            "daily_loss_limit": 0.10,
            "max_drawdown_limit": 0.15,
            "min_data_quality_for_open": 0.38,
            "low_quality_confidence_penalty": 0.08,
            "fallback_open_min_quality": 0.55,
            "fallback_open_block_seconds": 45,
        }
        
        # 运行状态
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._lock = asyncio.Lock()
        
        # 风险事件去重 - 记录最近一次风险事件时间
        self._last_risk_events: Dict[str, float] = {}
        self._risk_event_cooldown = 300  # 相同风险事件冷却时间（秒）
        
        # 自动平仓去重 - 避免重复平仓
        self._auto_close_attempts: Dict[str, float] = {}
        self._auto_close_cooldown = 60  # 自动平仓冷却时间（秒）
        self._empty_position_reads = 0
        self._wallet_snapshot: Dict[str, Any] = {}
        self._sltp_bound_keys: set[str] = set()
        self._last_market_route: Dict[str, Dict[str, Any]] = {}
        self._execution_observability: Dict[str, Any] = {
            "reconcile_total": 0,
            "reconcile_success": 0,
            "reconcile_timeout_like": 0,
            "reconcile_avg_ms": 0.0,
            "fallback_blocked_opens": 0,
            "last_reconcile_ms": 0.0,
            "last_reconcile_symbol": None,
            "last_reconcile_action": None,
        }
        
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
            okx_config = {}
            
            # 优先从环境变量读取配置
            import os
            api_key = os.getenv('OKX_API_KEY')
            secret = os.getenv('OKX_SECRET')
            passphrase = os.getenv('OKX_PASSPHRASE')
            
            if api_key and secret and passphrase:
                okx_config = {
                    'api_key': api_key,
                    'api_secret': secret,  # 注意：ExchangeBase期望的键名是api_secret
                    'api_passphrase': passphrase,  # 注意：ExchangeBase期望的键名是api_passphrase
                    'testnet': False
                }
                logger.info("✅ 从环境变量加载OKX配置")
            else:
                # 从配置管理器读取
                if self.main_controller and self.main_controller.config_manager:
                    exchanges_config = await self.main_controller.config_manager.get_config("exchanges", {})
                    okx_config = exchanges_config.get("okx", {})
                    logger.info(f"📋 从配置文件加载OKX配置")
            
            if okx_config and okx_config.get('api_key'):
                from src.modules.exchanges.okx import OKXExchange
                self.exchange = OKXExchange(okx_config)
                # 传递config_manager给OKXExchange
                if self.main_controller and self.main_controller.config_manager:
                    self.exchange._config_manager = self.main_controller.config_manager
                await self.exchange.initialize()
                logger.info("✅ OKX交易所已连接")
            else:
                logger.warning("⚠️ OKX配置不完整，使用模拟数据")
                logger.warning(f"   API Key: {'已设置' if api_key else '未设置'}")
                logger.warning(f"   Secret: {'已设置' if secret else '未设置'}")
                logger.warning(f"   Passphrase: {'已设置' if passphrase else '未设置'}")
        except Exception as e:
            logger.warning(f"⚠️ 交易所连接失败: {e}，将使用模拟数据")
            import traceback
            logger.debug(traceback.format_exc())
        
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
                config={"memory_manager": self.llm_integration, "data_storage": self.data_storage}
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
            
            proxy_url = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY") or "http://host.docker.internal:7890"
            
            binance_source = BinanceDataSource(proxy_url=proxy_url)
            coingecko_source = CoinGeckoDataSource(proxy_url=proxy_url)
            
            # register_data_source is synchronous; awaiting it causes NoneType await errors.
            self.data_fusion.register_data_source("binance", binance_source)
            self.data_fusion.register_data_source("coingecko", coingecko_source)
            
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
            if isinstance(config, dict):
                symbols = config.get("symbols")
                if isinstance(symbols, list) and symbols:
                    self.symbols = symbols
                self._use_dynamic_symbols = bool(
                    config.get("dynamic_symbol_universe", self._use_dynamic_symbols)
                )
                self._dynamic_symbol_refresh_seconds = int(
                    config.get(
                        "dynamic_symbol_refresh_seconds",
                        self._dynamic_symbol_refresh_seconds,
                    )
                    or self._dynamic_symbol_refresh_seconds
                )
                self._max_dynamic_symbols = int(
                    config.get("max_dynamic_symbols", self._max_dynamic_symbols)
                    or self._max_dynamic_symbols
                )
                contract_config = config.get("contract_config", {})
                if isinstance(contract_config, dict):
                    self.contract_config.update(contract_config)
                ai_cfg = config.get("ai_config", {})
                if isinstance(ai_cfg, dict):
                    self.ai_config.update(ai_cfg)
        await self._sync_symbols_from_selector(force=True)
        
        self._running = True
        logger.info(f"✅ 全智能AI交易引擎初始化完成")
        logger.info(f"📊 监控交易对: {self.symbols}")
        logger.info(f"🚫 黑名单交易对: {self.symbol_blacklist}")

    async def _autonomous_trading_execution_allowed(self) -> bool:
        """
        S1：当 single_write_owner 为 ai_core 时，本引擎不得并行跑自主开平仓循环，
        避免与 AICoreDecisionEngine 争夺实盘写入权。
        若 ai_brain.enable_secondary_controller=true，则显式允许并行主循环（用户手动开启双控）。
        """
        mc = self.main_controller
        if not mc or not hasattr(mc, "get_ai_managed_config"):
            return True
        try:
            policy = await mc.get_ai_managed_config("ai_brain", {})
            if bool(policy.get("enable_secondary_controller", False)):
                return True
            swo = str(
                policy.get("single_write_owner") or policy.get("primary_controller") or "ai_core"
            ).strip().lower()
            return swo != "ai_core"
        except Exception:
            return True
    
    async def start(self) -> None:
        """启动AI交易引擎"""
        logger.info("🚀 启动全智能AI交易引擎...")
        await self._bootstrap_live_state_takeover()
        
        # 启动主交易循环（受 single_write_owner 约束）
        if await self._autonomous_trading_execution_allowed():
            self._tasks.append(asyncio.create_task(self._trading_loop()))
        else:
            try:
                pol = await self.main_controller.get_ai_managed_config("ai_brain", {})
                swo = pol.get("single_write_owner", "ai_core")
            except Exception:
                swo = "ai_core"
            logger.info(
                "⏭️ 已跳过 AI 交易引擎主循环（single_write_owner=%s，实盘由 ai_core 独占）",
                swo,
            )
        
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
                await self._sync_symbols_from_selector(force=False)
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
                    await asyncio.sleep(DEFAULT_LOOP_SLEEP_SECONDS)
                
                # 等待下一个分析周期
                await asyncio.sleep(self.ai_config["analysis_interval"])
                
            except Exception as e:
                logger.error(f"交易循环错误: {e}")
                await asyncio.sleep(10)

    async def _sync_symbols_from_selector(self, force: bool = False) -> None:
        """按周期从动态选币器同步交易对，避免长期固定币对。"""
        if not self._use_dynamic_symbols:
            return
        now = datetime.now()
        if (
            not force
            and self._last_symbol_sync_at
            and (now - self._last_symbol_sync_at).total_seconds()
            < max(30, self._dynamic_symbol_refresh_seconds)
        ):
            return
        mc = self.main_controller
        selector = getattr(mc, "dynamic_symbol_selector", None) if mc else None
        if not selector or not hasattr(selector, "get_trading_symbols"):
            self._last_symbol_sync_at = now
            return
        try:
            symbols = await selector.get_trading_symbols()
            symbols = [str(s) for s in symbols if s]
            if symbols:
                symbols = symbols[: max(1, int(self._max_dynamic_symbols or 12))]
                if symbols != self.symbols:
                    self.symbols = symbols
                    logger.info(f"🔁 动态交易对同步完成: {self.symbols}")
        except Exception as e:
            logger.debug(f"动态交易对同步失败: {e}")
        finally:
            self._last_symbol_sync_at = now
    
    async def _collect_market_data(self, symbol: str) -> Optional[Dict]:
        """采集市场数据"""
        from src.utils.timeout_handler import run_with_timeout, Timeouts
        
        try:
            if not self.exchange:
                return None

            async def _call_exchange(method_name: str, *args, default_value=None, timeout_seconds: float = 10, **kwargs):
                method = getattr(self.exchange, method_name, None)
                if not callable(method):
                    return default_value
                try:
                    result = method(*args, **kwargs)
                    if asyncio.iscoroutine(result) or hasattr(result, "__await__"):
                        return await run_with_timeout(
                            result,
                            timeout_seconds=timeout_seconds,
                            default_value=default_value,
                        )
                    # 避免把未配置的 Mock 返回值当成真实数据
                    if type(result).__module__.startswith("unittest.mock"):
                        return default_value
                    return result
                except asyncio.TimeoutError:
                    return default_value
                except Exception as e:
                    logger.warning(f"调用交易所方法失败 {method_name}: {e}")
                    return default_value

            # 若交易所实现了异步多周期K线接口，则其超时/失败视为采集失败；否则退化为基础采集
            mt_method = getattr(self.exchange, "get_multi_timeframe_klines", None)
            mt_is_async = False
            if callable(mt_method):
                mt_is_async = asyncio.iscoroutinefunction(mt_method) or mt_method.__class__.__name__ == "AsyncMock"
            if mt_is_async:
                multi_timeframe_klines = await _call_exchange(
                    "get_multi_timeframe_klines",
                    symbol,
                    timeframes=["1m", "5m", "15m", "1h", "4h", "1d"],
                    timeout_seconds=Timeouts.MARKET_DATA_FETCH,
                    default_value=None,
                )
                if not multi_timeframe_klines:
                    logger.warning(f"获取{symbol}多时间框架数据超时")
                    return None
            else:
                multi_timeframe_klines = {}
            
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
            ticker = await _call_exchange(
                "get_ticker",
                symbol,
                timeout_seconds=Timeouts.ORDERBOOK_FETCH,
                default_value={},
            )
            # 获取增强实时快照（主通道），失败时不影响主流程
            realtime_snapshot = await _call_exchange(
                "get_realtime_market_data",
                symbol,
                timeout_seconds=Timeouts.ORDERBOOK_FETCH,
                default_value=None,
            )
            if isinstance(realtime_snapshot, dict) and realtime_snapshot:
                # 记录主备路由质量，供后续决策/执行链可观测
                self._last_market_route[symbol] = {
                    "route_channel": realtime_snapshot.get("route_channel", "unknown"),
                    "route_fallback": bool(realtime_snapshot.get("route_fallback", False)),
                    "quality_score": float(realtime_snapshot.get("quality_score", 0.0) or 0.0),
                    "latency_ms": int(realtime_snapshot.get("latency_ms", 0) or 0),
                    "ts": datetime.now().isoformat(),
                }
                # 当常规 ticker 缺失时，用增强快照补齐，避免数据断档
                if not ticker:
                    close_px = float(realtime_snapshot.get("close", 0) or 0)
                    if close_px > 0:
                        extras = realtime_snapshot.get("market_extras", {}) or {}
                        ticker = {
                            "symbol": symbol,
                            "last": close_px,
                            "bid": float(extras.get("best_bid", 0) or 0),
                            "ask": float(extras.get("best_ask", 0) or 0),
                            "volume": float(realtime_snapshot.get("volume", 0) or 0),
                            "timestamp": int(time.time() * 1000),
                        }
            
            # 获取订单簿 (带超时)
            order_book = await _call_exchange(
                "get_order_book",
                symbol,
                depth=20,
                timeout_seconds=Timeouts.ORDERBOOK_FETCH,
                default_value={},
            )
            
            # 获取账户余额 (带超时)
            balance = await _call_exchange(
                "get_balance",
                timeout_seconds=Timeouts.ACCOUNT_INFO_FETCH,
                default_value={},
            )
            
            # 获取持仓信息 (带超时)
            positions = await _call_exchange(
                "get_positions",
                timeout_seconds=Timeouts.ACCOUNT_INFO_FETCH,
                default_value=[],
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
                "realtime_snapshot": realtime_snapshot if isinstance(realtime_snapshot, dict) else {},
                "market_route": self._last_market_route.get(symbol, {}),
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
            
            # 使用统一数据源中心快照（优先），将分散渠道结果统一给交易决策链。
            unified_snapshot = None
            try:
                hub = getattr(self.main_controller, "data_source_hub", None) if self.main_controller else None
                if hub and hasattr(hub, "get_unified_snapshot"):
                    unified_snapshot = await hub.get_unified_snapshot(symbol)
            except Exception as e:
                logger.warning(f"统一数据源快照获取失败: {e}")

            # 统一分析入口：MarketIntelligenceEngine（分析模块）
            mi_view = None
            try:
                mi = getattr(self.main_controller, "market_intelligence", None) if self.main_controller else None
                if mi and hasattr(mi, "get_symbol_view"):
                    mi_view = await mi.get_symbol_view(symbol, include_snapshot=False)
            except Exception as e:
                logger.debug(f"MarketIntelligenceEngine 获取失败(降级): {e}")

            # 使用多源数据融合分析（如果可用）
            fused_intelligence = None
            if hasattr(self, 'data_fusion') and self.data_fusion:
                try:
                    fused_intelligence = await self.data_fusion.analyze_market(symbol)
                    if isinstance(fused_intelligence, dict):
                        sentiment_val = fused_intelligence.get("sentiment", 0.5)
                        logger.info(f"📊 多源数据融合分析完成: {symbol}, 情绪={sentiment_val}")
                    else:
                        logger.info(f"📊 多源数据融合分析完成: {symbol}, 情绪={getattr(fused_intelligence, 'overall_sentiment', 0.5)}")
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
            if unified_snapshot:
                analysis_data["unified_snapshot"] = unified_snapshot
            if mi_view is not None:
                try:
                    analysis_data["market_intelligence"] = mi_view.to_dict() if hasattr(mi_view, "to_dict") else {}
                except Exception:
                    analysis_data["market_intelligence"] = {}
            
            # 如果有多源数据，添加到分析中
            if fused_intelligence:
                if isinstance(fused_intelligence, dict):
                    analysis_data["fused_intelligence"] = fused_intelligence
                elif hasattr(fused_intelligence, 'to_dict'):
                    analysis_data["fused_intelligence"] = fused_intelligence.to_dict()
                else:
                    analysis_data["fused_intelligence"] = dict(fused_intelligence.__dict__) if hasattr(fused_intelligence, '__dict__') else {}
            
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
                if isinstance(fused_intelligence, dict):
                    fi_trend = fused_intelligence.get("trend", "neutral")
                    fi_sentiment = fused_intelligence.get("sentiment", 0.5) or 0.5
                    context = MarketContext(
                        symbol=symbol,
                        price=market_data["ticker"].get("last", 0),
                        trend=fi_trend if fi_trend in ["bullish", "bearish", "sideways"] else ai_analysis.get("trend", technical_indicators.trend),
                        volatility=self._calculate_volatility(technical_indicators),
                        volume_24h=market_data["ticker"].get("volume", 0),
                        sentiment="greed" if fi_sentiment > 0.6 else "fear" if fi_sentiment < 0.4 else "neutral",
                        support_levels=ai_analysis.get("support_levels", []),
                        resistance_levels=ai_analysis.get("resistance_levels", []),
                        metadata={
                            "unified_snapshot": unified_snapshot or {},
                            "analysis_data": analysis_data,
                            "market_route": market_data.get("market_route", {}),
                            "realtime_snapshot": market_data.get("realtime_snapshot", {}),
                        },
                    )
                    logger.info(f"✅ AI增强分析完成 {symbol}: 趋势={context.trend}, 情绪={context.sentiment}")
                else:
                    fi_recommendation = getattr(fused_intelligence, 'recommendation', None)
                    fi_sentiment = getattr(fused_intelligence, 'overall_sentiment', None)
                    fi_signal = getattr(fused_intelligence, 'signal_strength', None)
                    
                    context = MarketContext(
                        symbol=symbol,
                        price=market_data["ticker"].get("last", 0),
                        trend=fi_recommendation if fi_recommendation in ["bullish", "bearish", "sideways"] else ai_analysis.get("trend", technical_indicators.trend),
                        volatility=self._calculate_volatility(technical_indicators),
                        volume_24h=market_data["ticker"].get("volume", 0),
                        sentiment=getattr(fi_sentiment, 'value', str(fi_sentiment)) if fi_sentiment else "neutral",
                        support_levels=ai_analysis.get("support_levels", []),
                        resistance_levels=ai_analysis.get("resistance_levels", []),
                        metadata={
                            "unified_snapshot": unified_snapshot or {},
                            "analysis_data": analysis_data,
                            "market_route": market_data.get("market_route", {}),
                            "realtime_snapshot": market_data.get("realtime_snapshot", {}),
                        },
                    )
                    logger.info(f"✅ AI增强分析完成 {symbol}: 趋势={context.trend}, 情绪={context.sentiment}, "
                               f"信号强度={getattr(fi_signal, 'value', 'N/A') if fi_signal else 'N/A'}")
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
                    resistance_levels=ai_analysis.get("resistance_levels", []),
                    metadata={
                        "unified_snapshot": unified_snapshot or {},
                        "analysis_data": analysis_data,
                        "market_route": market_data.get("market_route", {}),
                        "realtime_snapshot": market_data.get("realtime_snapshot", {}),
                    },
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
            indicators = TechnicalIndicatorCalculator.calculate_all(klines_1h)
            
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
            if isinstance(fused_intelligence, dict):
                sentiment = fused_intelligence.get("sentiment", 0.5)
                trend = fused_intelligence.get("trend", "neutral")
                base_context.sentiment = "greed" if sentiment > 0.6 else "fear" if sentiment < 0.4 else "neutral"
                if trend in ["bullish", "bearish"]:
                    base_context.trend = trend
            else:
                if hasattr(fused_intelligence, 'overall_sentiment'):
                    base_context.sentiment = getattr(fused_intelligence.overall_sentiment, 'value', str(fused_intelligence.overall_sentiment))
                if hasattr(fused_intelligence, 'recommendation') and fused_intelligence.recommendation in ["bullish", "bearish"]:
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
            recent_lessons = await self._recall_trade_lessons(symbol=symbol, limit=3)
            
            # 调用AI生成决策
            snap = context.metadata.get("unified_snapshot", {}) if isinstance(context.metadata, dict) else {}
            data_quality = (snap.get("数据质量评估") or {}) if isinstance(snap, dict) else {}
            # Prefer MarketIntelligenceEngine output instead of data-hub analysis fields.
            mi_view = None
            try:
                mc = getattr(self, "main_controller", None)
                mi = getattr(mc, "market_intelligence", None) if mc else None
                if mi and hasattr(mi, "get_symbol_view"):
                    mi_view = await mi.get_symbol_view(symbol, include_snapshot=False)
            except Exception:
                mi_view = None
            ai_decision = await self.llm_integration.generate_trading_signal(
                {
                    "symbol": symbol,
                    "price": context.price,
                    "trend": context.trend,
                    "sentiment": context.sentiment,
                    "volatility": context.volatility,
                    "unified_data_quality": data_quality,
                    "market_intelligence": (mi_view.to_dict() if mi_view and hasattr(mi_view, "to_dict") else None),
                    "recent_lessons": recent_lessons,
                    "decision_prompt": decision_prompt,
                }
            )
            
            # 解析决策
            signal = ai_decision.get("signal", "hold")
            confidence = ai_decision.get("confidence", 0.5)
            
            # 检查置信度
            if confidence < self.ai_config["min_confidence"]:
                logger.info(f"⏸️ {symbol} 置信度不足 ({confidence:.2f})，保持观望")
                return AIDecision(
                    action=TradeAction.HOLD,
                    symbol=symbol,
                    price=context.price,
                    quantity=0.0,
                    confidence=confidence,
                    reasoning=ai_decision.get("reasoning", "置信度不足，观望"),
                    risk_level=ai_decision.get("risk_level", "medium"),
                    metadata={"ai_analysis": ai_decision, "market_context": context.__dict__},
                )
            
            # 确定交易动作
            action = self._parse_action(signal, current_position)

            # 数据质量软门控：保留 AI 决策自由，仅降低置信度并记录风险提示。
            snap = context.metadata.get("unified_snapshot", {}) if isinstance(context.metadata, dict) else {}
            quality = ((snap.get("数据质量评估") or {}).get("score")) if isinstance(snap, dict) else None
            min_q = float(self.ai_config.get("min_data_quality_for_open", 0.38))
            if action in [TradeAction.OPEN_LONG, TradeAction.OPEN_SHORT]:
                try:
                    q = float(quality) if quality is not None else 0.0
                except Exception:
                    q = 0.0
                if q < min_q:
                    penalty = float(self.ai_config.get("low_quality_confidence_penalty", 0.08))
                    confidence = max(0.05, float(confidence) - penalty)
                    ai_decision["reasoning"] = (
                        f"{ai_decision.get('reasoning', '')} | 数据质量偏低({q:.2f}<{min_q:.2f})，已降权但继续由AI自主决策"
                    )
            
            if action == TradeAction.HOLD:
                return AIDecision(
                    action=TradeAction.HOLD,
                    symbol=symbol,
                    price=context.price,
                    quantity=0.0,
                    confidence=confidence,
                    reasoning=ai_decision.get("reasoning", "观望"),
                    risk_level=ai_decision.get("risk_level", "medium"),
                    metadata={"ai_analysis": ai_decision, "market_context": context.__dict__},
                )
            
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
                    "market_context": context.__dict__,
                    "recent_lessons": recent_lessons,
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
                usdt = balance.get("USDT", 10000) if isinstance(balance, dict) else 10000
                if isinstance(usdt, dict):
                    available = float(usdt.get("free", usdt.get("available", 10000)) or 10000)
                else:
                    available = float(usdt or 10000)
            else:
                available = 10000  # 默认

            equity = max(available, self._estimate_total_equity_fallback(available))
            total_exposure = self._estimate_total_exposure()
            symbol_exposure = self._estimate_symbol_exposure(symbol)
            
            # 基于风险计算仓位
            risk_amount = available * self.ai_config["risk_per_trade"]
            
            # 根据波动率调整
            volatility_factor = 1 - min(context.volatility, 0.5)
            
            # 根据置信度调整
            # 这里简化处理，实际应该传入confidence
            
            position_value = risk_amount * volatility_factor
            if action in [TradeAction.OPEN_LONG, TradeAction.OPEN_SHORT]:
                # 分散和资金链保护：单币和总敞口双限制
                max_symbol_ratio = float(self.ai_config.get("max_symbol_position_ratio", 0.2) or 0.2)
                max_total_ratio = float(self.ai_config.get("max_total_exposure_ratio", 0.8) or 0.8)
                symbol_room_value = max(0.0, equity * max_symbol_ratio - symbol_exposure)
                total_room_value = max(0.0, equity * max_total_ratio - total_exposure)
                position_value = min(position_value, symbol_room_value, total_room_value)

            quantity = position_value / context.price if context.price > 0 else 0
            if quantity <= 0:
                return 0.0
            
            return round(quantity, 6)
            
        except Exception as e:
            logger.error(f"计算仓位大小失败: {e}")
            return 0.01  # 默认最小仓位
    
    def _calculate_stop_loss_take_profit(self, context: MarketContext,
                                        action: TradeAction) -> tuple:
        """计算止损止盈价格"""
        price = context.price
        vol = max(0.0, min(float(context.volatility or 0.0), 0.20))
        stop_loss_pct = max(0.015, min(0.06, 0.015 + vol * 0.35))
        take_profit_pct = max(0.03, min(0.12, stop_loss_pct * 1.8))
        
        if action in [TradeAction.OPEN_LONG, TradeAction.CLOSE_SHORT]:
            # 多单
            stop_loss = price * (1 - stop_loss_pct)
            take_profit = price * (1 + take_profit_pct)
        elif action in [TradeAction.OPEN_SHORT, TradeAction.CLOSE_LONG]:
            # 空单
            stop_loss = price * (1 + stop_loss_pct)
            take_profit = price * (1 - take_profit_pct)
        else:
            return None, None
        
        return round(stop_loss, 2), round(take_profit, 2)
    
    async def _risk_check(self, decision: AIDecision) -> bool:
        """风险检查"""
        try:
            # 对新开仓执行最大持仓数限制（优先读取外部配置，兼容测试）
            if decision.action in [TradeAction.OPEN_LONG, TradeAction.OPEN_SHORT]:
                # 数据路由联动硬门控：当处于回退通道且质量过低时，短时阻断开仓。
                md = decision.metadata or {}
                mc = md.get("market_context", {}) if isinstance(md, dict) else {}
                mm = mc.get("metadata", {}) if isinstance(mc, dict) else {}
                route = mm.get("market_route", {}) if isinstance(mm, dict) else {}
                route_fallback = bool(route.get("route_fallback", False))
                try:
                    route_quality = float(route.get("quality_score", 0.0) or 0.0)
                except Exception:
                    route_quality = 0.0
                fb_min_q = float(self.ai_config.get("fallback_open_min_quality", 0.55) or 0.55)
                if route_fallback and route_quality < fb_min_q:
                    self._execution_observability["fallback_blocked_opens"] = int(
                        self._execution_observability.get("fallback_blocked_opens", 0)
                    ) + 1
                    logger.warning(
                        "📊 回退通道质量不足，阻断开仓: symbol=%s quality=%.2f threshold=%.2f",
                        decision.symbol,
                        route_quality,
                        fb_min_q,
                    )
                    return False

                max_same = int(self.ai_config.get("max_same_direction_positions", 5) or 5)
                max_hedged = int(self.ai_config.get("max_hedged_positions", 8) or 8)
                max_positions = int(self.ai_config.get("max_positions", DEFAULT_MAX_POSITIONS) or DEFAULT_MAX_POSITIONS)
                long_cnt, short_cnt = self._count_open_directions()
                opening_long = decision.action == TradeAction.OPEN_LONG
                opening_short = decision.action == TradeAction.OPEN_SHORT

                if opening_long and long_cnt >= max_same and decision.symbol not in self.positions:
                    logger.info(f"📊 同向多仓已达上限({max_same})，拒绝新开多: {decision.symbol}")
                    return False
                if opening_short and short_cnt >= max_same and decision.symbol not in self.positions:
                    logger.info(f"📊 同向空仓已达上限({max_same})，拒绝新开空: {decision.symbol}")
                    return False

                # 仅单方向时使用基础上限；双方向对冲并存时可放宽到 max_hedged
                has_both_directions = long_cnt > 0 and short_cnt > 0
                total_cap = max_hedged if has_both_directions else max_positions
                if len(self.positions) >= total_cap and decision.symbol not in self.positions:
                    logger.info(f"📊 持仓数已达上限({total_cap})，拒绝新开仓: {decision.symbol}")
                    return False

                # 资金链保护：检查本次开仓后是否超总敞口
                projected_value = float(decision.quantity or 0.0) * float(decision.price or 0.0)
                if projected_value > 0:
                    available = 10000.0
                    if self.exchange:
                        try:
                            balance = await self.exchange.get_balance()
                            usdt = balance.get("USDT", 10000) if isinstance(balance, dict) else 10000
                            if isinstance(usdt, dict):
                                available = float(usdt.get("free", usdt.get("available", 10000)) or 10000)
                            else:
                                available = float(usdt or 10000)
                        except Exception:
                            pass
                    equity = max(available, self._estimate_total_equity_fallback(available))
                    max_total_ratio = float(self.ai_config.get("max_total_exposure_ratio", 0.8) or 0.8)
                    if self._estimate_total_exposure() + projected_value > equity * max_total_ratio:
                        logger.info("📊 总敞口保护触发，拒绝开仓: %s", decision.symbol)
                        return False

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

    def _count_open_directions(self) -> tuple:
        long_cnt = 0
        short_cnt = 0
        for pos in self.positions.values():
            side = getattr(pos, "side", "")
            if side == "long":
                long_cnt += 1
            elif side == "short":
                short_cnt += 1
        return long_cnt, short_cnt

    def _estimate_total_exposure(self) -> float:
        total = 0.0
        for pos in self.positions.values():
            qty = float(getattr(pos, "quantity", 0.0) or 0.0)
            px = float(getattr(pos, "current_price", 0.0) or getattr(pos, "entry_price", 0.0) or 0.0)
            total += abs(qty * px)
        return total

    def _estimate_symbol_exposure(self, symbol: str) -> float:
        pos = self.positions.get(symbol)
        if not pos:
            return 0.0
        qty = float(getattr(pos, "quantity", 0.0) or 0.0)
        px = float(getattr(pos, "current_price", 0.0) or getattr(pos, "entry_price", 0.0) or 0.0)
        return abs(qty * px)

    def _estimate_total_equity_fallback(self, available: float) -> float:
        # 没有完整账户权益时，使用可用余额 + 持仓名义价值作为保守估算。
        return float(available or 0.0) + self._estimate_total_exposure()

    async def _recall_trade_lessons(self, symbol: str, limit: int = 3) -> List[str]:
        """读取近期交易经验/教训，注入到决策上下文。"""
        mc = self.main_controller
        gateway = getattr(mc, "memory_gateway", None) if mc else None
        if not gateway or not hasattr(gateway, "recall"):
            return []
        try:
            rows = await gateway.recall(
                query=f"{symbol} 交易 复盘 经验 教训 策略优化",
                limit=max(1, int(limit)),
                min_importance=0.55,
            )
            out: List[str] = []
            for r in rows or []:
                content = str(getattr(r, "content", "") or "").strip()
                if content:
                    out.append(content[:180])
            return out[: max(1, int(limit))]
        except Exception:
            return []
    
    async def _execute_decision(self, decision: AIDecision) -> bool:
        """执行AI决策"""
        try:
            if not self.exchange:
                logger.warning("❌ 交易所未连接，无法执行")
                return False
            
            if isinstance(decision, dict):
                logger.error(f"❌ 决策对象格式错误（字典），期望AIDecision对象: {decision}")
                return False
            
            if not hasattr(decision, 'symbol') or not hasattr(decision, 'action'):
                logger.error(f"❌ 决策对象缺少必要属性: {type(decision)}")
                return False

            meta = getattr(decision, "metadata", None) or {}
            mc = self.main_controller
            if mc and hasattr(mc, "get_ai_managed_config"):
                try:
                    policy = await mc.get_ai_managed_config("ai_brain", {})
                    swo = str(
                        policy.get("single_write_owner") or policy.get("primary_controller") or "ai_core"
                    ).strip().lower()
                    enable_secondary = bool(policy.get("enable_secondary_controller", False))
                    if swo == "ai_core" and not meta.get("auto_close") and not enable_secondary:
                        logger.warning(
                            "AITradingEngine: 跳过执行（single_write_owner=ai_core，仅保留风险自动平仓；"
                            "若需双控请设置 ai_brain.enable_secondary_controller=true）"
                        )
                        return False
                except Exception:
                    pass
            
            logger.info(f"🚀 执行交易: {decision.action.value} {decision.symbol} "
                       f"@ {decision.price}, 数量={decision.quantity}")
            
            # 确定仓位方向
            is_close = decision.action in [TradeAction.CLOSE_LONG, TradeAction.CLOSE_SHORT]
            if decision.action in [TradeAction.OPEN_LONG, TradeAction.CLOSE_LONG]:
                pos_side = "long"
            elif decision.action in [TradeAction.OPEN_SHORT, TradeAction.CLOSE_SHORT]:
                pos_side = "short"
            else:
                pos_side = "net"
            
            order = Order(
                order_id="",
                symbol=decision.symbol,
                side="buy" if decision.action in [TradeAction.OPEN_LONG, TradeAction.CLOSE_SHORT] else "sell",
                order_type="market",
                quantity=decision.quantity,
                price=decision.price
            )
            
            # 添加元数据用于OKX下单
            order.metadata = {
                "posSide": pos_side,
                "is_close": is_close,
                "market_route": (decision.metadata or {}).get("market_context", {}).get("metadata", {}).get("market_route", {}),
            }

            # S1：优先经 ExecutionGateway，与 ai_core 策略一致；无 Gateway 时再直连交易所
            result = None
            gw = getattr(mc, "execution_gateway", None) if mc else None
            lev = int(self.contract_config.get("default_leverage", 20))
            if gw:
                try:
                    if is_close:
                        result = await gw.close_swap(
                            decision.symbol,
                            pos_side,
                            None,
                            "ai_trading_engine",
                            "aitrading_close",
                            context={
                                "decision_reasoning": getattr(decision, "reasoning", None),
                                "confidence": getattr(decision, "confidence", None),
                                "risk_level": getattr(decision, "risk_level", None),
                                "metadata": getattr(decision, "metadata", None),
                            },
                        )
                    else:
                        result = await gw.open_swap(
                            decision.symbol,
                            pos_side,
                            float(decision.quantity),
                            lev,
                            "ai_trading_engine",
                            "aitrading_open",
                            margin_mode="cross",
                            price=None,
                            context={
                                "decision_reasoning": getattr(decision, "reasoning", None),
                                "confidence": getattr(decision, "confidence", None),
                                "risk_level": getattr(decision, "risk_level", None),
                                "metadata": getattr(decision, "metadata", None),
                            },
                        )
                except Exception as e:
                    logger.warning("AITradingEngine: ExecutionGateway 执行异常: %s", e)
                    result = None
                if isinstance(result, dict):
                    err = str(result.get("error") or "")
                    if "policy_denied" in err or "open_policy_denied" in err:
                        logger.warning("AITradingEngine: S1 策略拒绝: %s", err)
                        return False

            if (result is None or not self._is_order_result_success(result)) and not gw:
                place_order = getattr(self.exchange, "place_order", None)
                create_order = getattr(self.exchange, "create_order", None)
                place_is_async = callable(place_order) and (
                    asyncio.iscoroutinefunction(place_order) or place_order.__class__.__name__ == "AsyncMock"
                )

                if place_is_async:
                    result = await place_order(order)
                elif callable(create_order):
                    side = "buy" if decision.action in [TradeAction.OPEN_LONG, TradeAction.CLOSE_SHORT] else "sell"
                    maybe = create_order(
                        decision.symbol,
                        side,
                        "market",
                        decision.quantity,
                        decision.price,
                    )
                    if asyncio.iscoroutine(maybe) or hasattr(maybe, "__await__"):
                        result = await maybe
                    else:
                        result = maybe
            elif result is None or not self._is_order_result_success(result):
                logger.error(
                    "AITradingEngine: Gateway 已启用但下单未成功，已跳过直连兜底 symbol=%s",
                    decision.symbol,
                )
                return False
            
            if self._is_order_result_success(result):
                order_id = ""
                if isinstance(result, dict):
                    order_id = result.get("id") or result.get("order_id") or "N/A"
                logger.info(f"✅ 订单执行成功: {order_id}")
                
                trade_record = {
                    "timestamp": datetime.now().isoformat(),
                    "decision": decision.__dict__,
                    "order_result": result
                }
                self.trade_history.append(trade_record)
                
                # 保存到统一交易历史服务（新增）
                if hasattr(self, 'trade_history_service') and self.trade_history_service:
                    try:
                        side = "buy" if decision.action in [TradeAction.OPEN_LONG, TradeAction.CLOSE_SHORT] else "sell"
                        await self.trade_history_service.record_trade_dict({
                            "order_id": result.get("order_id", ""),
                            "symbol": decision.symbol,
                            "side": side,
                            "order_type": "market",
                            "quantity": decision.quantity,
                            "price": decision.price,
                            "cost": decision.quantity * decision.price,
                            "reasoning": decision.reasoning,
                            "strategy": decision.metadata.get("strategy", "AI智能决策"),
                            "stop_loss": decision.stop_loss,
                            "take_profit": decision.take_profit,
                            "leverage": self.contract_config.get("default_leverage", 20),
                            "status": "filled",
                            "metadata": {
                                "decision_action": decision.action.value,
                                "confidence": decision.confidence,
                                "risk_level": decision.risk_level
                            }
                        })
                        logger.debug("✓ 交易已记录到统一交易历史服务")
                    except Exception as trade_svc_error:
                        logger.warning(f"⚠️ 记录到交易历史服务失败: {trade_svc_error}")
                
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
                
                await self._post_order_reconcile(decision, result)
                
                is_open = decision.action in [TradeAction.OPEN_LONG, TradeAction.OPEN_SHORT]
                if is_open and decision.stop_loss and decision.take_profit:
                    await self._create_stop_loss_order(decision)
                
                return True
            else:
                logger.error(f"❌ 订单执行失败: {result}")
                return False
                
        except Exception as e:
            logger.error(f"执行决策失败: {e}", exc_info=True)
            return False

    async def _post_order_reconcile(self, decision: AIDecision, order_result: Optional[Dict[str, Any]] = None) -> None:
        """
        下单后主动作一致性对账：
        - 重试同步持仓/钱包，减少“订单成功但本地状态未接管”的窗口
        - 对开仓/平仓分别做最小一致性检查
        """
        started = time.time()
        target_symbol = decision.symbol
        is_open = decision.action in [TradeAction.OPEN_LONG, TradeAction.OPEN_SHORT]
        is_close = decision.action in [TradeAction.CLOSE_LONG, TradeAction.CLOSE_SHORT]
        order_id = ""
        if isinstance(order_result, dict):
            order_id = str(order_result.get("order_id") or order_result.get("id") or "").strip()

        # 下单确认补偿：优先核验订单状态（如果交易所提供接口）
        if order_id:
            try:
                if hasattr(self.exchange, "get_order"):
                    _ = await self.exchange.get_order(order_id, target_symbol)
                elif hasattr(self.exchange, "get_open_orders_strict"):
                    _ = await self.exchange.get_open_orders_strict(target_symbol)
                elif hasattr(self.exchange, "get_open_orders"):
                    _ = await self.exchange.get_open_orders(target_symbol)
            except Exception as e:
                logger.debug("下单确认补偿检查失败(order_id=%s): %s", order_id, e)

        for attempt in range(1, 4):
            await self._update_positions()
            pos = self.positions.get(target_symbol)
            has_pos = bool(pos and float(getattr(pos, "quantity", 0) or 0) > 1e-12)

            if is_open and has_pos:
                self._update_reconcile_observability(
                    elapsed_ms=(time.time() - started) * 1000.0,
                    success=True,
                    symbol=target_symbol,
                    action=decision.action.value,
                )
                return
            if is_close and not has_pos:
                self._update_reconcile_observability(
                    elapsed_ms=(time.time() - started) * 1000.0,
                    success=True,
                    symbol=target_symbol,
                    action=decision.action.value,
                )
                return

            await asyncio.sleep(1.2 * attempt)

        self._update_reconcile_observability(
            elapsed_ms=(time.time() - started) * 1000.0,
            success=False,
            symbol=target_symbol,
            action=decision.action.value,
        )
        logger.warning(
            "下单后对账未完全收敛: symbol=%s action=%s final_has_pos=%s",
            target_symbol,
            decision.action.value,
            bool(self.positions.get(target_symbol)),
        )

    def _update_reconcile_observability(self, elapsed_ms: float, success: bool, symbol: str, action: str) -> None:
        obs = self._execution_observability
        total = int(obs.get("reconcile_total", 0)) + 1
        ok = int(obs.get("reconcile_success", 0)) + (1 if success else 0)
        if not success:
            obs["reconcile_timeout_like"] = int(obs.get("reconcile_timeout_like", 0)) + 1
        prev_avg = float(obs.get("reconcile_avg_ms", 0.0) or 0.0)
        obs["reconcile_total"] = total
        obs["reconcile_success"] = ok
        obs["reconcile_avg_ms"] = ((prev_avg * (total - 1)) + float(elapsed_ms)) / max(1, total)
        obs["last_reconcile_ms"] = round(float(elapsed_ms), 2)
        obs["last_reconcile_symbol"] = symbol
        obs["last_reconcile_action"] = action

    def _is_order_result_success(self, result: Any) -> bool:
        """Normalize exchange order response success semantics."""
        if result is None:
            return False
        if isinstance(result, bool):
            return result
        if isinstance(result, dict):
            # Common failure shapes
            if result.get("success") is False:
                return False
            status = str(result.get("status", "")).lower()
            if status in {"error", "failed", "fail"}:
                return False
            if "error" in result and result.get("error"):
                return False
            message = str(result.get("message", "")).lower()
            if "error" in message or "failed" in message:
                return False
            # Common success shapes
            if result.get("success") is True:
                return True
            if status in {"ok", "success", "filled"}:
                return True
            if result.get("order_id") or result.get("id"):
                return True
            return False
        # Non-dict truthy values from mocks/adapters
        return bool(result)
    
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
                await memory.add_memory(
                    memory_type="trade_record",
                    content=f"开仓: {decision.symbol} {side} @ {decision.price} qty={decision.quantity}",
                    summary=f"📈 开仓 {decision.symbol} {side} @{decision.price}",
                    metadata=base_metadata(
                        source_module="ai_trading_engine",
                        kind="trade_open",
                        symbol=decision.symbol,
                        extra={
                            "side": side,
                            "price": decision.price,
                            "quantity": decision.quantity,
                            "reason": decision.reasoning,
                            "stop_loss": decision.stop_loss,
                            "take_profit": decision.take_profit,
                            "strategy": (getattr(decision, "metadata", {}) or {}).get("strategy", "AI智能决策"),
                            "result": result,
                        },
                    ),
                    importance=0.9,
                    source_module="ai_trading_engine",
                    tags=tags(kind_tag("trade"), kind_tag("open"), symbol_tag(decision.symbol)),
                )
            else:
                existing = self.positions.get(decision.symbol)
                
                if isinstance(existing, dict):
                    logger.warning(f"⚠️ {decision.symbol} 持仓数据格式错误（字典），使用默认价格")
                    open_price = decision.price
                else:
                    open_price = existing.entry_price if existing else decision.price
                
                pnl = 0
                pnl_percent = 0
                
                if existing and not isinstance(existing, dict):
                    if side == "long":
                        pnl = (decision.price - open_price) * decision.quantity
                        pnl_percent = (decision.price - open_price) / open_price * 100
                    else:
                        pnl = (open_price - decision.price) * decision.quantity
                        pnl_percent = (open_price - decision.price) / open_price * 100
                
                await memory.add_memory(
                    memory_type="trade_record",
                    content=f"平仓: {decision.symbol} {side} {open_price}->{decision.price} qty={decision.quantity} pnl={pnl:.4f}({pnl_percent:.2f}%)",
                    summary=f"📉 平仓 {decision.symbol} pnl={pnl_percent:.2f}%",
                    metadata=base_metadata(
                        source_module="ai_trading_engine",
                        kind="trade_close",
                        symbol=decision.symbol,
                        extra={
                            "side": side,
                            "open_price": open_price,
                            "close_price": decision.price,
                            "quantity": decision.quantity,
                            "pnl": pnl,
                            "pnl_percent": pnl_percent,
                            "reason": decision.reasoning,
                            "result": result,
                        },
                    ),
                    importance=0.9,
                    source_module="ai_trading_engine",
                    tags=tags(kind_tag("trade"), kind_tag("close"), symbol_tag(decision.symbol)),
                )
                
                logger.info(f"💾 交易记录已保存到记忆库")
                
        except Exception as e:
            logger.error(f"保存交易到记忆失败: {e}")
    
    async def _create_stop_loss_order(self, decision) -> bool:
        """创建止损止盈订单"""
        try:
            if not self.main_controller:
                logger.warning("主控制器未设置，无法创建止损止盈订单")
                return False
            
            stop_loss_manager = self.main_controller.get_stop_loss_manager()
            if not stop_loss_manager:
                logger.warning("止损管理器未初始化，无法创建止损止盈订单")
                return False
            
            side = "long" if decision.action in [TradeAction.OPEN_LONG, TradeAction.CLOSE_SHORT] else "short"
            
            from .stop_loss_take_profit import StopLossConfig, TakeProfitConfig, StopType, TakeProfitType
            
            sl_config = StopLossConfig(
                stop_type=StopType.FIXED,
                stop_value=decision.stop_loss,
                enable_breakeven=True,
                breakeven_trigger=0.02
            )
            
            tp_config = TakeProfitConfig(
                tp_type=TakeProfitType.FIXED,
                tp_value=decision.take_profit
            )
            
            order = await stop_loss_manager.create_order(
                symbol=decision.symbol,
                side=side,
                entry_price=decision.price,
                quantity=decision.quantity,
                stop_loss_config=sl_config,
                take_profit_config=tp_config,
                metadata={"decision_id": decision.metadata.get("decision_id", "")}
            )
            
            logger.info(f"✅ 止损止盈订单已创建: {decision.symbol}")
            logger.info(f"   止损价: {order.stop_loss_price:.4f}")
            logger.info(f"   止盈价: {order.take_profit_price:.4f}")
            
            return True
            
        except Exception as e:
            logger.error(f"创建止损止盈订单失败: {e}")
            return False

    async def execute_trade(
        self,
        symbol: str,
        side: str,
        quantity: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        reasoning: str = "",
    ) -> Optional[Dict[str, Any]]:
        """
        外部模块（主动性扫描、ProactiveActionTrigger 等）统一开仓入口。
        经 ExecutionGateway、source=system，与 S1 一致；成功后可注册 StopLossTakeProfitManager。
        """
        mc = self.main_controller
        gw = getattr(mc, "execution_gateway", None) if mc else None
        if not gw or not self.exchange:
            logger.warning("execute_trade: 无 ExecutionGateway 或交易所，跳过")
            return None
        s = str(side or "long").strip().lower()
        if s in ("buy", "b"):
            s = "long"
        if s in ("sell", "s"):
            s = "short"
        qty = float(quantity or 0.01)
        lev = int(self.contract_config.get("default_leverage", 20))
        res = await gw.open_swap(
            symbol,
            s,
            qty,
            lev,
            "system",
            reasoning or "execute_trade",
            margin_mode="cross",
            price=None,
            context={
                "requested_stop_loss": stop_loss,
                "requested_take_profit": take_profit,
                "reasoning": reasoning,
            },
        )
        if not res.get("success"):
            return res
        if (
            mc
            and stop_loss is not None
            and take_profit is not None
            and getattr(mc, "stop_loss_manager", None)
        ):
            try:
                from .stop_loss_take_profit import (
                    StopLossConfig,
                    TakeProfitConfig,
                    StopType,
                    TakeProfitType,
                )

                t = await self.exchange.get_ticker(
                    symbol if "/" in str(symbol) else str(symbol).replace("-", "/")
                )
                entry = float((t or {}).get("last") or (t or {}).get("close") or 0)
                if entry <= 0:
                    return res
                sl_c = StopLossConfig(stop_type=StopType.FIXED, stop_value=float(stop_loss))
                tp_c = TakeProfitConfig(tp_type=TakeProfitType.FIXED, tp_value=float(take_profit))
                await mc.stop_loss_manager.create_order(
                    symbol=symbol if "/" in str(symbol) else str(symbol).replace("-", "/"),
                    side=s,
                    entry_price=entry,
                    quantity=qty,
                    stop_loss_config=sl_c,
                    take_profit_config=tp_c,
                    metadata={"source": "execute_trade", "reasoning": reasoning},
                )
            except Exception as e:
                logger.warning("execute_trade: 止盈止损注册失败（不影响成交）: %s", e)
        return res
    
    async def _update_positions(self) -> None:
        """更新持仓信息 - 从交易所实时获取"""
        try:
            if not self.exchange:
                return
            
            positions = await self.exchange.get_positions()
            if positions is None:
                return
            if not isinstance(positions, list):
                logger.warning("持仓返回格式异常，跳过本次同步")
                return
            
            existing_symbols = set(self.positions.keys())
            new_symbols = set()
            valid_rows = 0
            
            for pos in positions:
                symbol = (
                    pos.get("symbol")
                    or pos.get("instId")
                    or pos.get("instrument_id")
                    or pos.get("inst_id")
                )
                if not symbol:
                    continue
                symbol = str(symbol).replace("-", "/")
                
                size = float(pos.get("size", 0) or pos.get("quantity", 0) or 0)
                
                if size == 0:
                    continue
                valid_rows += 1
                
                new_symbols.add(symbol)
                
                existing_pos = self.positions.get(symbol)
                
                if isinstance(existing_pos, dict):
                    logger.warning(f"⚠️ {symbol} 持仓数据格式错误，重新创建")
                    existing_pos = None
                
                old_stop_loss = existing_pos.stop_loss if existing_pos else None
                old_take_profit = existing_pos.take_profit if existing_pos else None
                
                entry_price = float(pos.get("entry_price", 0) or pos.get("avgPx", 0) or 0)
                side = (pos.get("side") or "").lower()
                if side not in {"long", "short"}:
                    raw_side = str(pos.get("posSide_raw", "") or pos.get("posSide", "")).lower()
                    if raw_side in {"long", "short"}:
                        side = raw_side
                    else:
                        side = "long" if size >= 0 else "short"
                
                if old_stop_loss is None and entry_price > 0:
                    if side == "long":
                        old_stop_loss = entry_price * DEFAULT_STOP_LOSS_LONG_RATIO
                    else:
                        old_stop_loss = entry_price * DEFAULT_STOP_LOSS_SHORT_RATIO
                    logger.info(f"📊 {symbol} 自动设置止损: {old_stop_loss:.4f}")
                
                if old_take_profit is None and entry_price > 0:
                    if side == "long":
                        old_take_profit = entry_price * DEFAULT_TAKE_PROFIT_LONG_RATIO
                    else:
                        old_take_profit = entry_price * DEFAULT_TAKE_PROFIT_SHORT_RATIO
                    logger.info(f"📊 {symbol} 自动设置止盈: {old_take_profit:.4f}")
                
                self.positions[symbol] = Position(
                    symbol=symbol,
                    side=side,
                    entry_price=entry_price,
                    quantity=abs(size),
                    current_price=float(
                        pos.get("mark_price", 0)
                        or pos.get("mark_px", 0)
                        or pos.get("markPx", 0)
                        or pos.get("current_price", 0)
                        or 0
                    ),
                    unrealized_pnl=float(pos.get("unrealized_pnl", 0) or 0),
                    unrealized_pnl_percent=float(
                        pos.get("pnl_ratio", 0)
                        or pos.get("uplRatio", 0)
                        or pos.get("unrealized_pnl_percent", 0)
                        or 0
                    ),
                    stop_loss=old_stop_loss,
                    take_profit=old_take_profit
                )

            if valid_rows == 0 and existing_symbols:
                self._empty_position_reads += 1
                if self._empty_position_reads < 3:
                    logger.warning(
                        "持仓同步返回空结果（第 %d 次），保留现有持仓避免误清空",
                        self._empty_position_reads,
                    )
                    return
            else:
                self._empty_position_reads = 0

            closed_symbols = existing_symbols - new_symbols
            for symbol in closed_symbols:
                logger.info(f"📊 {symbol} 已平仓，从监控列表移除")
                del self.positions[symbol]
            
            if self.positions:
                logger.info(f"📊 当前监控 {len(self.positions)} 个持仓")
                for sym, pos in self.positions.items():
                    logger.info(f"   - {sym}: {pos.side} {pos.quantity} | 止损={pos.stop_loss:.4f} | 止盈={pos.take_profit:.4f}")
            await self._sync_wallet_snapshot()
            await self._ensure_sltp_binding_for_positions()
            
        except Exception as e:
            logger.error(f"更新持仓失败: {e}")

    async def _sync_wallet_snapshot(self) -> None:
        """实时同步钱包数据，供风控与重启接管使用。"""
        if not self.exchange:
            return
        try:
            balance = await self.exchange.get_balance()
            if isinstance(balance, dict):
                self._wallet_snapshot = {
                    "timestamp": datetime.now().isoformat(),
                    "balance": balance,
                }
                if self.main_controller is not None:
                    setattr(self.main_controller, "_latest_account_state", {
                        "balance": balance,
                        "positions": [
                            {
                                "symbol": p.symbol,
                                "side": p.side,
                                "quantity": p.quantity,
                                "entry_price": p.entry_price,
                                "mark_price": p.current_price,
                                "unrealized_pnl": p.unrealized_pnl,
                            }
                            for p in self.positions.values()
                        ],
                        "timestamp": datetime.now().isoformat(),
                    })
        except Exception as e:
            logger.debug(f"钱包同步失败: {e}")

    async def _bootstrap_live_state_takeover(self) -> None:
        """启动后立即接管交易所真实持仓/钱包，防止重启后丢失状态。"""
        for i in range(3):
            await self._update_positions()
            await self._sync_wallet_snapshot()
            if self.positions:
                logger.info("✅ 启动接管成功：已同步到 %d 个实时持仓", len(self.positions))
                return
            await asyncio.sleep(2)
        logger.warning("启动接管未发现持仓（可能确实空仓或交易所短时无返回）")

    async def _ensure_sltp_binding_for_positions(self) -> None:
        """确保接管到的持仓都挂上止盈止损跟踪（重启后尤其关键）。"""
        if not self.main_controller:
            return
        stop_loss_manager = self.main_controller.get_stop_loss_manager()
        if not stop_loss_manager:
            return
        for symbol, pos in list(self.positions.items()):
            key = f"{symbol}|{pos.side}"
            if key in self._sltp_bound_keys:
                continue
            if not pos.stop_loss or not pos.take_profit:
                continue
            try:
                from .stop_loss_take_profit import StopLossConfig, TakeProfitConfig, StopType, TakeProfitType

                sl_config = StopLossConfig(
                    stop_type=StopType.FIXED,
                    stop_value=pos.stop_loss,
                    enable_breakeven=True,
                    breakeven_trigger=0.02,
                )
                tp_config = TakeProfitConfig(
                    tp_type=TakeProfitType.FIXED,
                    tp_value=pos.take_profit,
                )
                await stop_loss_manager.create_order(
                    symbol=symbol,
                    side=pos.side,
                    entry_price=pos.entry_price,
                    quantity=pos.quantity,
                    stop_loss_config=sl_config,
                    take_profit_config=tp_config,
                    metadata={"source": "position_takeover"},
                )
                self._sltp_bound_keys.add(key)
            except Exception as e:
                logger.debug(f"补挂SLTP失败 {symbol}: {e}")
    
    async def _monitoring_loop(self) -> None:
        """监控循环 - 持仓跟踪和止损止盈检查"""
        while self._running:
            try:
                self.state = TradingState.MONITORING
                
                # 1. 先更新持仓信息（从交易所实时获取）
                await self._update_positions()
                
                # 2. 监控每个持仓
                for symbol, position in list(self.positions.items()):
                    try:
                        if isinstance(position, dict):
                            logger.warning(f"⚠️ {symbol} 持仓数据格式错误（字典），跳过监控")
                            continue
                        
                        ticker = await self.exchange.get_ticker(symbol.replace("/SWAP", ""))
                        if ticker:
                            position.current_price = ticker.get('last', position.current_price)
                    except Exception as e:
                        logger.debug(f"更新{symbol}实时价格失败，沿用上次价格: {e}")
                    
                    stop_loss = position.stop_loss
                    take_profit = position.take_profit
                    current_price = position.current_price
                    side = position.side
                    
                    stop_loss_triggered = False
                    take_profit_triggered = False
                    
                    if side == "long":
                        if stop_loss and current_price <= stop_loss:
                            stop_loss_triggered = True
                        if take_profit and current_price >= take_profit:
                            take_profit_triggered = True
                    else:
                        if stop_loss and current_price >= stop_loss:
                            stop_loss_triggered = True
                        if take_profit and current_price <= take_profit:
                            take_profit_triggered = True
                    
                    if stop_loss_triggered:
                        logger.warning(f"🚨 {symbol} 触发止损! {side}单 当前价={current_price:.4f} 止损价={stop_loss:.4f}")
                        await self._execute_decision(AIDecision(
                            action=TradeAction.CLOSE_LONG if side == "long" else TradeAction.CLOSE_SHORT,
                            symbol=symbol,
                            price=current_price,
                            quantity=position.quantity,
                            confidence=1.0,
                            reasoning="止损触发",
                            risk_level="high"
                        ))
                    
                    elif take_profit_triggered:
                        logger.info(f"🎯 {symbol} 触发止盈! {side}单 当前价={current_price:.4f} 止盈价={take_profit:.4f}")
                        await self._execute_decision(AIDecision(
                            action=TradeAction.CLOSE_LONG if side == "long" else TradeAction.CLOSE_SHORT,
                            symbol=symbol,
                            price=current_price,
                            quantity=position.quantity,
                            confidence=1.0,
                            reasoning="止盈触发",
                            risk_level="low"
                        ))
                    
                    # 检查持仓风险（无止损止盈时）
                    else:
                        pnl_percent = position.unrealized_pnl_percent
                        if pnl_percent < -5:  # 亏损超过5%
                            logger.warning(f"⚠️ {symbol} 浮亏 {pnl_percent:.2f}%，建议关注")
                        elif pnl_percent > 10:  # 盈利超过10%
                            logger.info(f"📈 {symbol} 浮盈 {pnl_percent:.2f}%，可考虑止盈")
                
                # 每30秒检查一次
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"监控循环错误: {e}")
                await asyncio.sleep(30)
    
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
        route_info = {}
        fallback_symbols = []
        for sym, route in self._last_market_route.items():
            if not isinstance(route, dict):
                continue
            route_info[sym] = {
                "route_channel": route.get("route_channel"),
                "route_fallback": bool(route.get("route_fallback", False)),
                "quality_score": route.get("quality_score"),
                "latency_ms": route.get("latency_ms"),
                "ts": route.get("ts"),
            }
            if bool(route.get("route_fallback", False)):
                fallback_symbols.append(sym)

        status = {
            "state": self.state.value,
            "running": self._running,
            "positions": len(self.positions),
            "trade_count": len(self.trade_history),
            "symbols": self.symbols,
            "ai_config": self.ai_config,
            "market_route_status": {
                "tracked_symbols": len(route_info),
                "fallback_symbols": fallback_symbols,
                "routes": route_info,
            },
            "execution_observability": self._execution_observability,
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
                    
                    if self.ai_config.get("critical_risk_auto_close", False):
                        risk_cfg = {}
                        if self.risk_monitor and hasattr(self.risk_monitor, "risk_config"):
                            risk_cfg = getattr(self.risk_monitor, "risk_config", {}) or {}
                        liq_dist = float(getattr(pos_risk, "distance_to_liquidation", 0) or 0)
                        loss_pct = abs(min(float(getattr(pos_risk, "unrealized_pnl_percent", 0) or 0), 0.0))

                        liq_critical = float(risk_cfg.get("liquidation_distance_critical", 0.08) or 0.08)
                        liq_auto_close_max = float(
                            self.ai_config.get(
                                "critical_risk_auto_close_max_liq_distance",
                                min(liq_critical, 0.04),
                            ) or min(liq_critical, 0.04)
                        )
                        near_liq = liq_dist > 0 and liq_dist <= liq_auto_close_max

                        margin_critical = float(risk_cfg.get("margin_ratio_critical", 0.9) or 0.9)
                        margin_emergency = margin_critical > 0 and float(getattr(account_risk, "margin_ratio", 0) or 0) >= margin_critical

                        liq_only = bool(self.ai_config.get("critical_risk_auto_close_liq_only", True))
                        min_loss_pct = float(self.ai_config.get("critical_risk_auto_close_min_loss_pct", 25.0) or 25.0)
                        severe_loss = loss_pct >= min_loss_pct

                        should_auto_close = margin_emergency or (near_liq if liq_only else (near_liq or severe_loss))
                        if should_auto_close:
                            logger.critical(
                                "🤖 自动风险处理: 平仓 %s (liq_dist=%.3f, loss=%.1f%%, margin=%.3f)",
                                pos_risk.symbol,
                                liq_dist,
                                loss_pct,
                                float(getattr(account_risk, "margin_ratio", 0) or 0),
                            )
                            await self._auto_close_position(pos_risk.symbol)
                        else:
                            logger.warning(
                                "🛡️ 跳过自动强平 %s：未命中强平闸门 (liq_dist=%.3f > %.3f, loss=%.1f%%, liq_only=%s)",
                                pos_risk.symbol,
                                liq_dist,
                                liq_auto_close_max,
                                loss_pct,
                                liq_only,
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
    
    async def _auto_close_position(self, symbol: str) -> bool:
        """账户风控强平：经 ExecutionGateway、source=account_risk_monitor（与 SLTP 分源，避免策略混写）。"""
        try:
            import time

            current_time = time.time()
            if symbol in self._auto_close_attempts:
                last_attempt_time = self._auto_close_attempts[symbol]
                if current_time - last_attempt_time < self._auto_close_cooldown:
                    logger.warning(
                        "⏸️ %s 自动平仓在冷却期内，跳过（距上次 %.1f 秒）",
                        symbol,
                        current_time - last_attempt_time,
                    )
                    return False

            position = self.positions.get(symbol)
            if not position:
                logger.warning("⚠️ 未找到持仓 %s", symbol)
                return False

            if isinstance(position, dict):
                logger.error("❌ 持仓数据格式错误: %s", symbol)
                return False

            self._auto_close_attempts[symbol] = current_time
            logger.critical(
                "🚨 执行自动平仓(风控): %s %s %s",
                symbol,
                position.side,
                position.quantity,
            )

            mc = self.main_controller
            gw = getattr(mc, "execution_gateway", None) if mc else None
            if gw:
                res = await gw.close_swap(
                    symbol,
                    position.side,
                    None,
                    "account_risk_monitor",
                    "critical_risk_auto_close",
                    context={
                        "reasoning": "critical_risk_auto_close",
                        "position_side": position.side,
                        "position_qty": position.quantity,
                    },
                )
                ok = bool(isinstance(res, dict) and res.get("success"))
            else:
                decision = AIDecision(
                    action=(
                        TradeAction.CLOSE_LONG
                        if position.side == "long"
                        else TradeAction.CLOSE_SHORT
                    ),
                    symbol=symbol,
                    price=position.current_price,
                    quantity=position.quantity,
                    confidence=1.0,
                    reasoning="风险控制自动平仓",
                    risk_level="high",
                    metadata={"auto_close": True, "reason": "critical_risk"},
                )
                ok = await self._execute_decision(decision)

            if ok:
                logger.critical("✅ 自动平仓成功: %s", symbol)
                if symbol in self.positions:
                    del self.positions[symbol]
            else:
                logger.error("❌ 自动平仓失败: %s", symbol)

            return ok

        except Exception as e:
            logger.error("自动平仓失败: %s", e)
            return False
    
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
            
            level = "warning" if "warning" in str(event_type).lower() else "critical"
            await memory.add_memory(
                memory_type="risk_event",
                content=f"风险事件[{level}]: {symbol} {event_type} - {description} | 处置: {action_taken} | 影响: {impact}",
                summary=f"⚠️ 风险事件 {symbol} {event_type}",
                metadata=base_metadata(
                    source_module="ai_trading_engine",
                    kind="risk_event",
                    symbol=symbol,
                    extra={
                        "event_type": event_type,
                        "description": description,
                        "action_taken": action_taken,
                        "impact": impact,
                        "level": level,
                    },
                ),
                importance=0.85 if level == "warning" else 0.95,
                source_module="ai_trading_engine",
                tags=tags(kind_tag("risk"), kind_tag(level), symbol_tag(symbol), extra=[f"event:{event_type}"]),
            )
            
            logger.info(f"⚠️ 风险事件已保存到记忆库: {event_key}")
            
        except Exception as e:
            logger.error(f"保存风险事件失败: {e}")


    async def cleanup(self):
        """清理资源"""
        pass
