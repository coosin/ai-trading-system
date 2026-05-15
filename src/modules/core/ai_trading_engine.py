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
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd

from .technical_indicators import TechnicalIndicatorCalculator, TechnicalIndicators
from .historical_data_storage import HistoricalDataStorage, TradeRecord, IndicatorRecord, get_historical_storage
from .account_risk_monitor import AccountRiskMonitor, AccountRisk, PositionRisk, RiskLevel
from .strategy_optimizer import StrategyOptimizer, StrategyType, StrategyPerformance
from .trading_limits import resolve_position_limits
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
    metadata: Dict[str, Any] = field(default_factory=dict)
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
            "leverage_min": 20,
            "leverage_max": 100,
            "default_leverage": 30,
            "max_positions": DEFAULT_MAX_POSITIONS,
            "min_positions": 1,
            "margin_mode": "cross",
            "grid_trading": True,
            "grid_levels": 5,
            "grid_spacing": 0.02,
        }
        
        self.ai_config = {
            "enabled": True,
            "model_id": "gemini-2.5-flash",
            "analysis_interval": DEFAULT_ANALYSIS_INTERVAL_SECONDS,
            "min_confidence": 0.75,
            "max_positions": DEFAULT_MAX_POSITIONS,
            "max_same_direction_positions": 5,
            "max_hedged_positions": 8,
            "risk_per_trade": 0.01,
            "max_symbol_position_ratio": 0.2,
            # 单笔名义价值硬上限（占账户权益比例）
            "max_position_value_ratio": 0.05,
            "max_total_exposure_ratio": 0.8,
            # 硬限制总持仓数，避免对冲放宽导致持仓数失控
            "hard_max_positions": 5,
            # 仅在趋势明确(bullish/bearish)时允许新开仓
            "require_trend_for_open": True,
            "trade_mode": "real",
            "auto_risk_management": True,
            # False：关闭自动平仓，由主逻辑判断是否平仓
            "critical_risk_auto_close": False,
            # 与 AccountRiskMonitor.liquidation_distance_critical 对齐的「贴近强平」阈值（比例，如 0.08=8%）
            "critical_risk_auto_close_max_liq_distance": 0.08,
            # 保留字段：曾错误地屏蔽「仅浮亏达极端」的自动平仓，逻辑上已不再参与闸门判定（见 _on_risk_warning）。
            "critical_risk_auto_close_liq_only": True,
            "critical_risk_auto_close_min_loss_pct": 25.0,
            "max_loss_per_position": 0.05,
            "daily_loss_limit": 0.10,
            "max_drawdown_limit": 0.15,
            "min_data_quality_for_open": 0.38,
            "low_quality_confidence_penalty": 0.08,
            "fallback_open_min_quality": 0.55,
            "fallback_open_block_seconds": 45,
            # Microstructure hard gates for open actions.
            "enable_microstructure_open_gates": True,
            "microstructure_max_spread_bps": 12.0,
            "microstructure_max_abs_depth_imbalance": 0.92,
            "microstructure_max_abs_funding_rate": 0.0012,
            "microstructure_min_open_interest": None,
            "stop_loss_penalty_step_hits": 3,
            "stop_loss_penalty_step_confidence": 0.05,
            "stop_loss_penalty_max_confidence": 0.15,
        }
        
        # 运行状态
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._lock = asyncio.Lock()
        
        # 风险事件去重 - 记录最近一次风险事件时间
        self._last_risk_events: Dict[str, float] = {}
        self._risk_event_cooldown = 300  # 相同风险事件冷却时间（秒）
        
        self._empty_position_reads = 0
        self._wallet_snapshot: Dict[str, Any] = {}
        self._sltp_bound_keys: set[str] = set()
        # 开仓风控前的持仓对账闸门：避免本地持仓缓存短时为 0 导致硬限制失效
        self._position_gate_sync_cooldown_sec: float = 3.0
        self._last_position_gate_sync_ts: float = 0.0
        self._position_gate_sync_lock = asyncio.Lock()
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
        # 止损复盘统计：连续止损达到阈值后，对该信号提高开仓门槛
        self._signal_stop_loss_stats: Dict[str, Dict[str, Any]] = {}
        # 止损复盘事件去重：避免 close 重试/重复触发导致 hits 爆炸、信号被永久“惩罚封杀”
        self._stop_loss_feedback_seen: Dict[str, float] = {}
        self._stop_loss_feedback_seen_ttl_sec: float = 6 * 3600
        # Track successful same-symbol same-side opens for staged scale-in confidence gates.
        self._symbol_side_open_legs: Dict[str, int] = {}
        
        logger.info("全智能AI交易引擎初始化完成")

    async def initialize(self) -> None:
        """初始化AI交易引擎"""
        logger.info("初始化全智能AI交易引擎...")
        
        # 连接LLM集成
        if self.main_controller and hasattr(self.main_controller, 'llm_integration'):
            self.llm_integration = self.main_controller.llm_integration
            logger.info("✅ LLM集成已连接")
        
        # 连接交易所：simulation 模式优先复用主控制器注入的模拟交易所
        try:
            import os

            okx_config: Dict[str, Any] = {}
            trading_mode = ""
            sim_cfg = {}
            system_cfg = {}
            api_key = ""
            api_secret = ""
            api_passphrase = ""

            if self.main_controller and self.main_controller.config_manager:
                trading_cfg = await self.main_controller.config_manager.get_config("trading", {})
                system_cfg = await self.main_controller.config_manager.get_config("system", {})
                top_mode = await self.main_controller.config_manager.get_config("mode", "")
                sim_cfg = dict(trading_cfg.get("simulation", {}) or {})
                mode_candidates = [
                    trading_cfg.get("mode", ""),
                    system_cfg.get("mode", ""),
                    top_mode,
                ]
                trading_mode = next(
                    (str(m).strip().lower() for m in mode_candidates if str(m).strip()),
                    "",
                )

            use_real_market_data = bool(
                sim_cfg.get("use_real_market_data", False)
                or system_cfg.get("use_real_market_data", False)
            )

            if (
                trading_mode == "simulation"
                and (not use_real_market_data)
                and getattr(self.main_controller, "simulation_exchange", None)
            ):
                self.exchange = self.main_controller.simulation_exchange
                logger.info("✅ SimulationExchange 已连接（来自 MainController）")
            else:
                exchanges_config: Dict[str, Any] = {}
                if self.main_controller and self.main_controller.config_manager:
                    exchanges_config = await self.main_controller.config_manager.get_config("exchanges", {}) or {}
                okx_yaml = dict(exchanges_config.get("okx", {}) or {})
                okx_enabled = bool(okx_yaml.get("enabled", True))

                def _env_lookup(env_key: Any) -> str:
                    if not env_key:
                        return ""
                    return str(os.getenv(str(env_key).strip(), "") or "").strip()

                api_key = (
                    str(okx_yaml.get("api_key") or "").strip()
                    or _env_lookup(okx_yaml.get("api_key_env"))
                    or str(os.getenv("OKX_API_KEY", "") or "").strip()
                )
                api_secret = (
                    str(okx_yaml.get("api_secret") or okx_yaml.get("secret") or "").strip()
                    or _env_lookup(okx_yaml.get("secret_env"))
                    or str(os.getenv("OKX_SECRET", "") or "").strip()
                )
                api_passphrase = (
                    str(okx_yaml.get("api_passphrase") or okx_yaml.get("passphrase") or "").strip()
                    or _env_lookup(okx_yaml.get("passphrase_env"))
                    or str(os.getenv("OKX_PASSPHRASE", "") or "").strip()
                )

                testnet_flag = bool(okx_yaml.get("testnet", False))
                env_testnet_raw = str(os.getenv("OKX_TESTNET", "") or "").strip().lower()
                if env_testnet_raw in ("1", "true", "yes", "on"):
                    testnet_flag = True
                elif env_testnet_raw in ("0", "false", "no", "off"):
                    # 显式环境变量应覆盖 YAML，避免误连 simulated-trading 账户。
                    testnet_flag = False

                if (not okx_enabled):
                    logger.info("OKX disabled by exchanges.okx.enabled=false; skip OKXExchange init")
                elif api_key and api_secret and api_passphrase:
                    okx_config = {
                        "api_key": api_key,
                        "api_secret": api_secret,
                        "api_passphrase": api_passphrase,
                        "testnet": testnet_flag,
                    }
                    if "simulated_order_only" in okx_yaml:
                        okx_config["simulated_order_only"] = bool(okx_yaml.get("simulated_order_only"))
                    logger.info("OKX credentials resolved (YAML / api_key_env / OKX_* env)")

            if okx_config and str(os.getenv("OKX_TESTNET", "") or "").strip().lower() in ("1", "true", "yes"):
                okx_config = dict(okx_config or {})
                okx_config["testnet"] = True
            
            if not self.exchange and okx_config and okx_config.get('api_key'):
                from src.modules.exchanges.okx import OKXExchange
                self.exchange = OKXExchange(okx_config)
                # 传递config_manager给OKXExchange
                if self.main_controller and self.main_controller.config_manager:
                    self.exchange._config_manager = self.main_controller.config_manager
                await self.exchange.initialize()
                logger.info("✅ OKX交易所已连接")
            elif not self.exchange:
                logger.warning("⚠️ OKX配置不完整，使用模拟数据")
                logger.warning("   API Key: %s", "已设置" if bool(api_key) else "未设置")
                logger.warning("   Secret: %s", "已设置" if bool(api_secret) else "未设置")
                logger.warning("   Passphrase: %s", "已设置" if bool(api_passphrase) else "未设置")
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
                data_integration=None,
                llm_integration=self.llm_integration,
            )
            
            from src.modules.core.network_env_from_config import proxy_url_for_data_sources

            cm = getattr(self.main_controller, "config_manager", None)
            proxy_url = proxy_url_for_data_sources(cm)
            
            binance_source = BinanceDataSource(proxy_url=proxy_url)
            coingecko_source = CoinGeckoDataSource(proxy_url=proxy_url)
            
            # register_data_source is synchronous; awaiting it causes NoneType await errors.
            self.data_fusion.register_data_source("binance", binance_source)
            self.data_fusion.register_data_source("coingecko", coingecko_source)
            # Local runtime exchange fallback: when public HTTP sources timeout,
            # still allow fusion layer to use the already-connected exchange feed.
            if self.exchange and hasattr(self.exchange, "get_market_data"):
                self.data_fusion.register_data_source("runtime_exchange", self.exchange, "exchange")
            
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
        
        # 增强风险控制器已退役（保留主风险链路: risk_manager + account_risk_monitor）
        self.enhanced_risk = None
        
        # 加载配置
        if self.main_controller and self.main_controller.config_manager:
            config = await self.main_controller.config_manager.get_config("ai_trading", {})
            if isinstance(config, dict):
                symbols = config.get("symbols")
                if isinstance(symbols, list) and symbols:
                    self.symbols = [str(s) for s in symbols if s]
                else:
                    trading_cfg = await self.main_controller.config_manager.get_config(
                        "trading", {}
                    )
                    if isinstance(trading_cfg, dict):
                        ts = trading_cfg.get("symbols")
                        if isinstance(ts, list) and ts:
                            self.symbols = [str(s) for s in ts if s]
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
            trading_full = await self.main_controller.config_manager.get_config("trading", {})
            from src.modules.core.trading_contract_settings import (
                apply_trading_contract_unified,
            )

            apply_trading_contract_unified(
                trading_full if isinstance(trading_full, dict) else {},
                contract_config=self.contract_config,
                ai_config=self.ai_config,
                ai_core_config=None,
            )
            learning_feedback_cfg = await self.main_controller.config_manager.get_config(
                "learning_feedback", {}
            )
            if isinstance(learning_feedback_cfg, dict):
                for k in (
                    "stop_loss_penalty_step_hits",
                    "stop_loss_penalty_step_confidence",
                    "stop_loss_penalty_max_confidence",
                ):
                    if learning_feedback_cfg.get(k) is not None:
                        self.ai_config[k] = learning_feedback_cfg.get(k)
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
        # stop() 会将 _running 置为 False；start() 必须显式恢复，避免重启后循环不再运行。
        self._running = True
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
            if not symbols:
                # Selector may temporarily degrade under upstream jitter; keep the engine tradable.
                fallback_symbols = list(self.symbols or [])
                if not fallback_symbols:
                    fallback_symbols = [
                        "BTC/USDT",
                        "ETH/USDT",
                        "SOL/USDT",
                        "BNB/USDT",
                    ]
                symbols = [str(s) for s in fallback_symbols if s]
                logger.warning("动态交易对为空，回退使用默认/当前交易对: %s", symbols[:8])
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
            
            # 风险评估（增强版）已退役，避免双风险链路造成重复判断
            
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

            # 趋势门控：只在趋势明确时开仓，减少噪音期无效交易
            if action in [TradeAction.OPEN_LONG, TradeAction.OPEN_SHORT]:
                if bool(self.ai_config.get("require_trend_for_open", True)):
                    if context.trend not in ("bullish", "bearish"):
                        return AIDecision(
                            action=TradeAction.HOLD,
                            symbol=symbol,
                            price=context.price,
                            quantity=0.0,
                            confidence=confidence,
                            reasoning=f"趋势不明确({context.trend})，跳过开仓",
                            risk_level=ai_decision.get("risk_level", "medium"),
                            metadata={"ai_analysis": ai_decision, "market_context": context.__dict__},
                        )

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

            # 信号惩罚门控：同类信号连续止损>=3后，自动提高该信号的最小置信度
            if action in [TradeAction.OPEN_LONG, TradeAction.OPEN_SHORT]:
                signal_key = self._build_signal_key(symbol, action, context)
                stat = self._signal_stop_loss_stats.get(signal_key, {})
                stop_loss_hits = int(stat.get("stop_loss_hits", 0) or 0)
                step_hits = max(
                    1,
                    int(self.ai_config.get("stop_loss_penalty_step_hits", 3) or 3),
                )
                step_conf = float(
                    self.ai_config.get("stop_loss_penalty_step_confidence", 0.05)
                    or 0.05
                )
                max_conf = float(
                    self.ai_config.get("stop_loss_penalty_max_confidence", 0.15)
                    or 0.15
                )
                penalty_steps = stop_loss_hits // step_hits
                if penalty_steps > 0:
                    extra_threshold = min(max_conf, step_conf * penalty_steps)
                    threshold = float(self.ai_config["min_confidence"]) + extra_threshold
                    if float(confidence) < threshold:
                        return AIDecision(
                            action=TradeAction.HOLD,
                            symbol=symbol,
                            price=context.price,
                            quantity=0.0,
                            confidence=confidence,
                            reasoning=(
                                f"信号 {signal_key} 近期止损{stop_loss_hits}次，"
                                f"门槛提升至{threshold:.2f}，当前{float(confidence):.2f}，跳过开仓"
                            ),
                            risk_level=ai_decision.get("risk_level", "high"),
                            metadata={"ai_analysis": ai_decision, "market_context": context.__dict__},
                        )

            # 微结构硬门控：当盘口/资金费率/持仓量风险过高时，直接跳过开仓。
            if action in [TradeAction.OPEN_LONG, TradeAction.OPEN_SHORT]:
                if bool(self.ai_config.get("enable_microstructure_open_gates", True)):
                    mi_raw: Dict[str, Any] = {}
                    if mi_view is not None and hasattr(mi_view, "to_dict"):
                        try:
                            mi_raw = mi_view.to_dict() or {}
                        except Exception:
                            mi_raw = {}
                    if not isinstance(mi_raw, dict) or not mi_raw:
                        md = context.metadata if isinstance(context.metadata, dict) else {}
                        x = md.get("market_intelligence") if isinstance(md, dict) else {}
                        mi_raw = x if isinstance(x, dict) else {}

                    spread = mi_raw.get("spread_bps")
                    depth_imb = (
                        mi_raw.get("depth_imbalance")
                        if mi_raw.get("depth_imbalance") is not None
                        else mi_raw.get("depth_imbalance_top5")
                    )
                    funding = mi_raw.get("funding_rate")
                    open_interest = mi_raw.get("open_interest")

                    # Fallback to unified snapshot payload when MI view does not expose these fields.
                    try:
                        snap_a = (snap.get("渠道A_交易所实时执行数据") or {}) if isinstance(snap, dict) else {}
                        if funding is None:
                            funding = snap_a.get("funding_rate")
                        if open_interest is None:
                            oi_raw = snap_a.get("open_interest")
                            if isinstance(oi_raw, dict):
                                open_interest = oi_raw.get("open_interest")
                            else:
                                open_interest = oi_raw
                    except Exception:
                        pass

                    violations: List[str] = []
                    try:
                        sp_v = float(spread) if spread is not None else None
                    except Exception:
                        sp_v = None
                    try:
                        di_v = float(depth_imb) if depth_imb is not None else None
                    except Exception:
                        di_v = None
                    try:
                        fr_v = float(funding) if funding is not None else None
                    except Exception:
                        fr_v = None
                    try:
                        oi_v = float(open_interest) if open_interest is not None else None
                    except Exception:
                        oi_v = None

                    max_sp = float(self.ai_config.get("microstructure_max_spread_bps", 12.0) or 12.0)
                    max_di = float(self.ai_config.get("microstructure_max_abs_depth_imbalance", 0.92) or 0.92)
                    max_fr = float(self.ai_config.get("microstructure_max_abs_funding_rate", 0.0012) or 0.0012)
                    min_oi_cfg = self.ai_config.get("microstructure_min_open_interest")
                    try:
                        min_oi = float(min_oi_cfg) if min_oi_cfg not in (None, "", "null") else None
                    except Exception:
                        min_oi = None

                    if sp_v is not None and sp_v > max_sp:
                        violations.append(f"spread_bps={sp_v:.4f}>{max_sp:.4f}")
                    if di_v is not None and abs(di_v) > max_di:
                        violations.append(f"depth_imbalance={di_v:.4f}>{max_di:.4f}")
                    if fr_v is not None and abs(fr_v) > max_fr:
                        violations.append(f"funding_rate={fr_v:.6f}>{max_fr:.6f}")
                    if min_oi is not None and oi_v is not None and oi_v < min_oi:
                        violations.append(f"open_interest={oi_v:.2f}<{min_oi:.2f}")

                    if violations:
                        return AIDecision(
                            action=TradeAction.HOLD,
                            symbol=symbol,
                            price=context.price,
                            quantity=0.0,
                            confidence=confidence,
                            reasoning=(
                                f"微结构开仓门控触发: {'; '.join(violations)}，跳过开仓"
                            ),
                            risk_level="high",
                            metadata={
                                "ai_analysis": ai_decision,
                                "market_context": context.__dict__,
                                "microstructure_gate": {
                                    "spread_bps": sp_v,
                                    "depth_imbalance": di_v,
                                    "funding_rate": fr_v,
                                    "open_interest": oi_v,
                                    "thresholds": {
                                        "max_spread_bps": max_sp,
                                        "max_abs_depth_imbalance": max_di,
                                        "max_abs_funding_rate": max_fr,
                                        "min_open_interest": min_oi,
                                    },
                                    "violations": violations,
                                },
                            },
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
            
            # 计算仓位大小（按总资金 5%~10% 的保证金预算，自适应波动与置信度）
            quantity = await self._calculate_position_size(symbol, context, action, confidence=float(confidence))
            
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
    
    async def _calculate_position_size(
        self,
        symbol: str,
        context: MarketContext,
        action: TradeAction,
        confidence: Optional[float] = None,
    ) -> float:
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
            
            # 单笔保证金预算：总资金 5%~10%（用户要求）
            # 以 equity 为基准，结合波动率与置信度做自适应微调。
            min_pct = float(self.ai_config.get("position_margin_pct_min", 0.03) or 0.05)
            max_pct = float(self.ai_config.get("position_margin_pct_max", 0.05) or 0.10)
            base_pct = float(self.ai_config.get("position_margin_pct_default", 0.04) or 0.07)
            min_pct = max(0.01, min(min_pct, 0.50))
            max_pct = max(min_pct, min(max_pct, 0.90))
            base_pct = max(min_pct, min(base_pct, max_pct))

            c = None
            try:
                c = float(confidence) if confidence is not None else None
            except Exception:
                c = None
            if c is not None:
                # 置信度越高，越接近上限；低于 0.65 则更保守（但通常已被门控拦截）
                if c >= 0.85:
                    base_pct = max(base_pct, max_pct)
                elif c <= 0.65:
                    base_pct = min(base_pct, min_pct)
                else:
                    # 0.65..0.85 线性插值到 0.05..0.10
                    t = (c - 0.65) / max(1e-9, 0.20)
                    base_pct = min_pct + (max_pct - min_pct) * max(0.0, min(1.0, t))

            # 波动率越高，保证金预算越低（最多降到 60%）
            vol = float(context.volatility or 0.0)
            vol = max(0.0, min(vol, 0.50))
            vol_factor = 1.0 - 0.8 * vol  # 0..0.5 => 1..0.6
            margin_value = equity * base_pct * vol_factor

            # 杠杆：20~100，自适应（配置驱动分段曲线）
            lev_min = int(self.contract_config.get("leverage_min", 1) or 20)
            lev_max = int(self.contract_config.get("leverage_max", 2) or 100)
            lev0 = int(self.contract_config.get("default_leverage", 1) or 30)
            # context.volatility 通常是 0..0.5，映射为 ATR 口径近似值 0..0.05
            atr_proxy = max(0.001, min(0.15, float(vol) * 0.1))
            lev = self._adaptive_leverage_from_atr(
                atr_pct_1h=atr_proxy,
                leverage_min=lev_min,
                leverage_max=lev_max,
                default_leverage=lev0,
                leverage_curve=self.contract_config.get("leverage_curve"),
            )
            if c is not None and c >= 0.80 and vol <= 0.10:
                lev = min(lev_max, max(lev, int(round(lev0 * 1.15))))
            lev = max(lev_min, min(lev, lev_max))

            position_value = margin_value * float(lev)
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
                await self._refresh_positions_for_risk_gate()
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

                limits = await resolve_position_limits(
                    config_manager=(self.main_controller.config_manager if self.main_controller else None),
                    trading_config=((self.config or {}).get("trading") if isinstance(self.config, dict) else None),
                    ai_config=(self.ai_config if isinstance(self.ai_config, dict) else None),
                )
                max_same = int(limits.max_same_direction_positions)
                max_hedged = int(limits.max_positions_hedge)
                max_positions = int(limits.max_positions_oneway)
                long_cnt, short_cnt = self._count_open_directions()
                opening_long = decision.action == TradeAction.OPEN_LONG
                opening_short = decision.action == TradeAction.OPEN_SHORT
                existing = self.positions.get(decision.symbol)
                total_positions = len(self.positions)
                total_dir = max(1, long_cnt + short_cnt)
                same_dir_count = long_cnt if opening_long else short_cnt
                same_dir_ratio = float(same_dir_count) / float(total_dir)

                if opening_long and long_cnt >= max_same and decision.symbol not in self.positions:
                    logger.info(f"📊 同向多仓已达上限({max_same})，拒绝新开多: {decision.symbol}")
                    return False
                if opening_short and short_cnt >= max_same and decision.symbol not in self.positions:
                    logger.info(f"📊 同向空仓已达上限({max_same})，拒绝新开空: {decision.symbol}")
                    return False

                # 仅单方向时使用基础上限；双方向对冲并存时可放宽到 max_hedged
                has_both_directions = long_cnt > 0 and short_cnt > 0
                total_cap = max_hedged if has_both_directions else max_positions
                hard_max_positions = int(limits.hard_max_positions)
                if len(self.positions) >= hard_max_positions and decision.symbol not in self.positions:
                    logger.info(f"📊 硬限制持仓数已达上限({hard_max_positions})，拒绝新开仓: {decision.symbol}")
                    return False
                if len(self.positions) >= total_cap and decision.symbol not in self.positions:
                    logger.info(f"📊 持仓数已达上限({total_cap})，拒绝新开仓: {decision.symbol}")
                    return False

                # Staged scale-in confidence gates for 2nd/3rd/4th+ same-side opens.
                decision_side = "long" if opening_long else "short"
                leg_key = f"{str(decision.symbol).upper()}|{decision_side}"
                current_legs = int(self._symbol_side_open_legs.get(leg_key, 0) or 0)
                existing_same_side = bool(existing and getattr(existing, "side", "") == decision_side)
                next_leg = (current_legs + 1) if current_legs > 0 else (2 if existing_same_side else 1)
                if next_leg >= 2:
                    if next_leg == 2:
                        need_conf = float(limits.scale_in_min_confidence_2)
                    elif next_leg == 3:
                        need_conf = float(limits.scale_in_min_confidence_3)
                    else:
                        need_conf = float(limits.scale_in_min_confidence_4)
                    got_conf = float(decision.confidence or 0.0)
                    if got_conf < need_conf:
                        logger.info(
                            "📊 加仓置信度不足，拒绝开仓: symbol=%s leg=%s conf=%.3f required=%.3f",
                            decision.symbol,
                            next_leg,
                            got_conf,
                            need_conf,
                        )
                        return False

                # 资金链保护：检查本次开仓后是否超总敞口
                # 注意：OKX SWAP 的 quantity 是“张”，不能直接 quantity*price 当作名义价值。
                qty = float(decision.quantity or 0.0)
                px = float(getattr(decision, "price", 0.0) or 0.0)
                if px <= 0:
                    try:
                        md = decision.metadata if isinstance(decision.metadata, dict) else {}
                        mctx = md.get("market_context", {}) if isinstance(md, dict) else {}
                        px = float((mctx or {}).get("price", 0.0) or 0.0)
                    except Exception:
                        px = 0.0
                ct_val = 0.0
                ct_is_base = False
                try:
                    if self.exchange and hasattr(self.exchange, "get_swap_symbol_info"):
                        info = await self.exchange.get_swap_symbol_info(decision.symbol)
                        ct_val = float((info or {}).get("ctVal") or 0.0)
                        ccy = str((info or {}).get("ctValCcy") or "").upper()
                        base = str(decision.symbol or "").split("/")[0].upper()
                        ct_is_base = bool(ct_val > 0 and ccy and base and ccy == base)
                except Exception:
                    pass
                if ct_val > 0 and qty > 0 and px > 0:
                    projected_value = qty * ct_val * px if ct_is_base else qty * ct_val
                else:
                    projected_value = qty * max(0.0, px)
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

                    # Canonical per-symbol margin cap (available * symbol_max_margin_ratio).
                    # We approximate required margin as notional/leverage; if leverage is missing,
                    # fall back to contract_config.default_leverage (or 1).
                    try:
                        lev = None
                        md = decision.metadata if isinstance(decision.metadata, dict) else {}
                        lev = md.get("leverage") if isinstance(md, dict) else None
                        if lev is None:
                            lev = self.contract_config.get("default_leverage") if isinstance(self.contract_config, dict) else None
                        lev_f = float(lev or 1.0)
                        lev_f = max(1.0, min(200.0, lev_f))
                        required_margin = projected_value / lev_f
                        symbol_margin_cap = float(limits.symbol_max_margin_ratio) * float(available)
                        if required_margin > symbol_margin_cap:
                            logger.info(
                                "📊 单币种保证金占用超限，拒绝开仓: symbol=%s req_margin=%.2f cap=%.2f available=%.2f lev=%.1f",
                                decision.symbol,
                                required_margin,
                                symbol_margin_cap,
                                available,
                                lev_f,
                            )
                            return False
                    except Exception:
                        pass
                    max_position_value_ratio = float(self.ai_config.get("max_position_value_ratio", 0.05) or 0.05)
                    if projected_value > equity * max_position_value_ratio:
                        logger.info(
                            "📊 单笔仓位超限，拒绝开仓: symbol=%s projected=%.2f equity=%.2f limit=%.2f%%",
                            decision.symbol,
                            projected_value,
                            equity,
                            max_position_value_ratio * 100.0,
                        )
                        return False
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
                try:
                    if hasattr(self.risk_manager, "check_order"):
                        res = await self.risk_manager.check_order(decision.__dict__)
                        if isinstance(res, dict) and not bool(res.get("passed", True)):
                            logger.warning(
                                "📊 风险管理器拒绝该订单: symbol=%s violations=%s",
                                decision.symbol,
                                res.get("violations") or [],
                            )
                            return False
                    elif hasattr(self.risk_manager, "check_trade"):
                        risk_ok = await self.risk_manager.check_trade(decision.__dict__)
                        if not risk_ok:
                            logger.warning("📊 风险管理器拒绝该订单: symbol=%s", decision.symbol)
                            return False
                except Exception as e:
                    logger.error("风险管理器检查异常（fail-closed）: %s", e)
                    return False
            
            logger.info(f"✅ AI自主决策通过: {decision.action.value} {decision.symbol}")
            return True
            
        except Exception as e:
            logger.error(f"风险检查失败: {e}")
            return False

    async def _refresh_positions_for_risk_gate(self) -> None:
        """开仓前短冷却刷新持仓，确保硬限制基于交易所权威数据。"""
        if not self.exchange:
            return
        now_ts = time.time()
        if now_ts - float(self._last_position_gate_sync_ts or 0.0) < float(self._position_gate_sync_cooldown_sec or 0.0):
            return
        async with self._position_gate_sync_lock:
            now_ts = time.time()
            if now_ts - float(self._last_position_gate_sync_ts or 0.0) < float(self._position_gate_sync_cooldown_sec or 0.0):
                return
            before_cnt = len(self.positions)
            await self._update_positions()
            self._last_position_gate_sync_ts = time.time()
            after_cnt = len(self.positions)
            if before_cnt == 0 and after_cnt > 0:
                logger.info(
                    "🧭 开仓前持仓对账已纠偏: local_before=%d -> exchange_now=%d",
                    before_cnt,
                    after_cnt,
                )

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

    def _build_signal_key(self, symbol: str, action: TradeAction, context: MarketContext) -> str:
        side = "long" if action == TradeAction.OPEN_LONG else "short" if action == TradeAction.OPEN_SHORT else "hold"
        trend = str(getattr(context, "trend", "unknown") or "unknown")
        return f"{symbol}:{side}:{trend}"

    async def _record_stop_loss_feedback(
        self,
        symbol: str,
        side: str,
        current_price: float,
        stop_loss: float,
        event_id: Optional[str] = None,
    ) -> None:
        # best-effort dedupe: if the same SL event is emitted repeatedly (e.g. close retry),
        # do not accumulate penalties that effectively disable trading.
        try:
            if event_id:
                now_ts = time.time()
                # purge old seen ids (bounded memory)
                if self._stop_loss_feedback_seen and (len(self._stop_loss_feedback_seen) > 2000):
                    cutoff = now_ts - float(self._stop_loss_feedback_seen_ttl_sec or 21600)
                    self._stop_loss_feedback_seen = {
                        k: v for k, v in self._stop_loss_feedback_seen.items() if float(v or 0.0) >= cutoff
                    }
                prev = float(self._stop_loss_feedback_seen.get(str(event_id), 0.0) or 0.0)
                if prev and (now_ts - prev) < float(self._stop_loss_feedback_seen_ttl_sec or 21600):
                    return
                self._stop_loss_feedback_seen[str(event_id)] = now_ts
        except Exception:
            pass
        signal_key = f"{symbol}:{side}:{'bullish' if side == 'long' else 'bearish'}"
        stat = self._signal_stop_loss_stats.setdefault(signal_key, {"stop_loss_hits": 0, "last_at": None})
        stat["stop_loss_hits"] = int(stat.get("stop_loss_hits", 0) or 0) + 1
        stat["last_at"] = datetime.now().isoformat()
        logger.warning(
            "📘 止损复盘记录: key=%s hits=%s price=%.4f stop_loss=%.4f",
            signal_key,
            stat["stop_loss_hits"],
            current_price,
            stop_loss,
        )

        if self.llm_integration and hasattr(self.llm_integration, "enhanced_memory"):
            memory = self.llm_integration.enhanced_memory
            if memory:
                try:
                    await memory.add_memory(
                        memory_type="trade_record",
                        content=f"止损复盘: {symbol} {side} price={current_price} stop={stop_loss} key={signal_key}",
                        summary=f"🧾 止损复盘 {symbol} {side}",
                        metadata=base_metadata(
                            source_module="ai_trading_engine",
                            kind="stop_loss_postmortem",
                            symbol=symbol,
                            extra={
                                "signal_key": signal_key,
                                "side": side,
                                "current_price": current_price,
                                "stop_loss": stop_loss,
                                "stop_loss_hits": stat["stop_loss_hits"],
                                "occurred_at": stat["last_at"],
                            },
                        ),
                        importance=0.88,
                        source_module="ai_trading_engine",
                        tags=tags(kind_tag("trade"), kind_tag("stop_loss"), symbol_tag(symbol)),
                    )
                except Exception:
                    pass

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
                    if swo == "ai_core" and not enable_secondary:
                        logger.warning(
                            "AITradingEngine: 跳过执行（single_write_owner=ai_core，辅引擎不直连交易所；"
                            "若需双控请设置 ai_brain.enable_secondary_controller=true）"
                        )
                        return False
                except Exception:
                    pass
            
            logger.info(f"🚀 执行交易: {decision.action.value} {decision.symbol} "
                       f"@ {decision.price}, 数量={decision.quantity}")
            
            # 确定仓位方向（OKX posSide：开/平哪一侧仓位；勿将 CLOSE_SHORT 与 OPEN_LONG 混为 long）
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
            lev = int(self.contract_config.get("default_leverage", 1))
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
                        _st = (
                            decision.metadata.get("strategy_used")
                            or decision.metadata.get("strategy_id")
                            or decision.metadata.get("strategy")
                            or "AI智能决策"
                        )
                        await self.trade_history_service.record_trade_dict({
                            "order_id": result.get("order_id", ""),
                            "symbol": decision.symbol,
                            "side": side,
                            "order_type": "market",
                            "quantity": decision.quantity,
                            "price": decision.price,
                            "cost": decision.quantity * decision.price,
                            "reasoning": decision.reasoning,
                            "strategy": str(_st),
                            "stop_loss": decision.stop_loss,
                            "take_profit": decision.take_profit,
                            "leverage": self.contract_config.get("default_leverage", 1),
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
                if is_open:
                    try:
                        open_side = "long" if decision.action == TradeAction.OPEN_LONG else "short"
                        leg_key = f"{str(decision.symbol).upper()}|{open_side}"
                        self._symbol_side_open_legs[leg_key] = int(self._symbol_side_open_legs.get(leg_key, 0) or 0) + 1
                    except Exception:
                        pass
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
            side = (
                "long"
                if decision.action in [TradeAction.OPEN_LONG, TradeAction.CLOSE_LONG]
                else "short"
                if decision.action in [TradeAction.OPEN_SHORT, TradeAction.CLOSE_SHORT]
                else "long"
            )
            
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

                strat_name = (getattr(decision, "metadata", {}) or {}).get("strategy", "ai_trading_engine")
                
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
                            "is_profitable": pnl > 0,
                            "strategy": strat_name,
                            "reason": decision.reasoning,
                            "result": result,
                        },
                    ),
                    importance=0.9,
                    source_module="ai_trading_engine",
                    tags=tags(kind_tag("trade"), kind_tag("close"), symbol_tag(decision.symbol)),
                )
                
                logger.info(f"💾 交易记录已保存到记忆库")

                mc = self.main_controller
                le = getattr(mc, "ai_learning_engine", None) if mc else None
                if le is not None and hasattr(le, "record_trade_result"):
                    try:
                        await le.record_trade_result(
                            {
                                "symbol": decision.symbol,
                                "side": side,
                                "entry_price": open_price,
                                "exit_price": decision.price,
                                "pnl": pnl,
                                "pnl_percent": pnl_percent,
                                "strategy": strat_name,
                                "reason": decision.reasoning,
                                "timestamp": datetime.now().isoformat(),
                            }
                        )
                    except Exception as ex:
                        logger.debug(f"AILearningEngine.record_trade_result 跳过: {ex}")
                
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
            
            side = (
                "long"
                if decision.action in [TradeAction.OPEN_LONG, TradeAction.CLOSE_LONG]
                else "short"
                if decision.action in [TradeAction.OPEN_SHORT, TradeAction.CLOSE_SHORT]
                else "long"
            )
            
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
            _sl = order.stop_loss_price
            _tp = order.take_profit_price
            logger.info(
                "   止损价: %s",
                f"{float(_sl):.4f}" if _sl is not None else "N/A",
            )
            logger.info(
                "   止盈价: %s",
                f"{float(_tp):.4f}" if _tp is not None else "N/A",
            )
            
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
        confidence: Optional[float] = None,
        *,
        source: str = "manual",
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        手动/兼容开仓入口。
        自动开仓主链必须走 ai_core，避免绕过统一意图记录、门控与轨迹审计。
        """
        mc = self.main_controller
        gw = getattr(mc, "execution_gateway", None) if mc else None
        if not gw or not self.exchange:
            logger.warning("execute_trade: 无 ExecutionGateway 或交易所，跳过")
            return None
        src = str(source or "manual").strip().lower()
        if src not in {"manual", "system"}:
            logger.warning(
                "execute_trade: 非手动来源(%s)已拒绝，请改走 ai_core 主决策链 symbol=%s",
                src,
                symbol,
            )
            return {
                "success": False,
                "error": f"legacy_open_path_blocked source={src}; route through ai_core",
            }
        s = str(side or "long").strip().lower()
        if s in ("buy", "b"):
            s = "long"
        if s in ("sell", "s"):
            s = "short"
        # 自适应杠杆（20-100）
        lev_min = int(self.contract_config.get("leverage_min", 1) or 20)
        lev_max = int(self.contract_config.get("leverage_max", 2) or 100)
        lev0 = int(self.contract_config.get("default_leverage", 1) or 30)
        lev = max(lev_min, min(lev0, lev_max))
        try:
            mc = self.main_controller
            mi = getattr(mc, "market_intelligence", None) if mc else None
            if mi and hasattr(mi, "get_symbol_view"):
                view = await asyncio.wait_for(mi.get_symbol_view(symbol, include_snapshot=False), timeout=1.2)
                vd = view.to_dict() if hasattr(view, "to_dict") else {}
                atrp = vd.get("atr_pct_1h")
                if atrp is not None:
                    atr = float(atrp)
                    lev = self._adaptive_leverage_from_atr(
                        atr_pct_1h=atr,
                        leverage_min=lev_min,
                        leverage_max=lev_max,
                        default_leverage=lev0,
                        leverage_curve=self.contract_config.get("leverage_curve"),
                    )
        except Exception:
            pass
        try:
            c = float(confidence) if confidence is not None else None
            if c is not None and c >= 0.85:
                lev = min(lev_max, max(lev, int(round(lev0 * 1.25))))
            if c is not None and c <= 0.65:
                lev = max(lev_min, min(lev, lev0))
        except Exception:
            pass

        default_qty = float(self.contract_config.get("default_quantity", 0.01) or 0.01)
        qty = float(quantity if quantity is not None else default_qty)
        # 若未指定 quantity，则按“单笔保证金=总资金 5%~10%”计算（近似用 USDT 可用余额）
        if quantity is None:
            try:
                bal = await self.exchange.get_balance()
                usdt = bal.get("USDT", {}) if isinstance(bal, dict) else {}
                if isinstance(usdt, dict):
                    available = float(usdt.get("free", usdt.get("available", 0)) or 0)
                else:
                    available = float(usdt or 0)
                # margin fraction 5%..10%
                min_pct = float(self.ai_config.get("position_margin_pct_min", 0.03) or 0.05)
                max_pct = float(self.ai_config.get("position_margin_pct_max", 0.05) or 0.10)
                base_pct = float(self.ai_config.get("position_margin_pct_default", 0.04) or 0.07)
                base_pct = max(min_pct, min(base_pct, max_pct))
                if confidence is not None:
                    c = float(confidence)
                    if c >= 0.85:
                        base_pct = max_pct
                    elif c <= 0.65:
                        base_pct = min_pct
                margin = max(0.0, available * base_pct)
                t = await self.exchange.get_ticker(symbol if "/" in str(symbol) else str(symbol).replace("-", "/"))
                px = float((t or {}).get("last") or (t or {}).get("price") or 0)
                if px > 0 and margin > 0:
                    notional = margin * float(lev)
                    qty = max(default_qty, float(notional / px))
            except Exception:
                pass
        res = await gw.open_swap(
            symbol,
            s,
            qty,
            lev,
            src,
            reasoning or "execute_trade",
            margin_mode="cross",
            price=None,
            context={
                "requested_stop_loss": stop_loss,
                "requested_take_profit": take_profit,
                "reasoning": reasoning,
                "confidence": confidence,
                "origin": "ai_trading_engine.execute_trade",
                **(dict(context) if isinstance(context, dict) else {}),
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

    @staticmethod
    def _adaptive_leverage_from_atr(
        *,
        atr_pct_1h: float,
        leverage_min: int,
        leverage_max: int,
        default_leverage: int,
        leverage_curve: Optional[Any] = None,
    ) -> int:
        """
        Piecewise leverage curve:
        - high volatility => lower leverage
        - low volatility => higher leverage
        - default_leverage acts as middle anchor when ATR is unavailable/noisy
        """
        try:
            atr = float(atr_pct_1h)
        except Exception:
            return int(max(leverage_min, min(leverage_max, default_leverage)))

        atr = max(0.001, min(0.15, atr))
        target = None

        # Config-driven piecewise curve from trading.contract.leverage_curve:
        # - atr_gte: threshold (descending)
        # - leverage: target leverage
        if isinstance(leverage_curve, list):
            parsed = []
            for row in leverage_curve:
                if not isinstance(row, dict):
                    continue
                try:
                    thr = float(row.get("atr_gte"))
                    lev = int(row.get("leverage"))
                    parsed.append((thr, lev))
                except Exception:
                    continue
            parsed.sort(key=lambda x: x[0], reverse=True)
            for thr, lev in parsed:
                if atr >= thr:
                    target = lev
                    break

        if target is None:
            if atr >= 0.06:
                target = 20
            elif atr >= 0.04:
                target = 24
            elif atr >= 0.03:
                target = 28
            elif atr >= 0.02:
                target = 32
            elif atr >= 0.015:
                target = 36
            elif atr >= 0.010:
                target = 45
            elif atr >= 0.006:
                target = 60
            else:
                target = 75

        # Keep curve centered around configured default.
        if default_leverage > 0:
            target = int(round((target * 0.7) + (float(default_leverage) * 0.3)))
        return int(max(leverage_min, min(leverage_max, target)))
    
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
                    pos.get("instId")
                    or pos.get("symbol")
                    or pos.get("instrument_id")
                    or pos.get("inst_id")
                )
                if not symbol:
                    continue
                raw_symbol = str(symbol)
                symbol = raw_symbol.replace("-", "/")
                # Normalize common OKX swap suffix so positions map keys match decision symbols.
                # Example: BTC-USDT-SWAP -> BTC/USDT (keep raw instId in metadata).
                if symbol.endswith("/SWAP"):
                    symbol = symbol[: -len("/SWAP")]
                # Some adapters may produce BTC/USDT/SWAP after naive replace.
                if symbol.endswith("/USDT/SWAP"):
                    symbol = symbol.replace("/USDT/SWAP", "/USDT")
                
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
                    take_profit=old_take_profit,
                )
                # Preserve raw instrument id for audit/debug without breaking symbol keying.
                try:
                    self.positions[symbol].metadata["instId"] = raw_symbol
                except Exception:
                    pass

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
                try:
                    sym_u = str(symbol).upper()
                    self._symbol_side_open_legs.pop(f"{sym_u}|long", None)
                    self._symbol_side_open_legs.pop(f"{sym_u}|short", None)
                except Exception:
                    pass
            
            if self.positions:
                logger.info(f"📊 当前监控 {len(self.positions)} 个持仓")
                for sym, pos in self.positions.items():
                    _psl = pos.stop_loss
                    _ptp = pos.take_profit
                    logger.info(
                        "   - %s: %s %s | 止损=%s | 止盈=%s",
                        sym,
                        pos.side,
                        pos.quantity,
                        f"{float(_psl):.4f}" if _psl is not None else "N/A",
                        f"{float(_ptp):.4f}" if _ptp is not None else "N/A",
                    )
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
                        await self._record_stop_loss_feedback(
                            symbol=symbol,
                            side=side,
                            current_price=float(current_price),
                            stop_loss=float(stop_loss),
                        )
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
    
    async def _trade_rows_for_optimization(self) -> List[Dict[str, Any]]:
        """
        合并引擎内存 trade_history 与 TradeHistoryService 持久化记录。
        主链路若走 ai_core/ExecutionGateway，内存列表常为 0，但 JSONL/SQLite 仍有成交。
        """
        merged: List[Dict[str, Any]] = list(self.trade_history)
        seen_oid: set = set()
        for t in merged:
            try:
                orr = t.get("order_result") if isinstance(t.get("order_result"), dict) else {}
                oid = str(orr.get("order_id") or orr.get("orderId") or "").strip()
                if oid:
                    seen_oid.add(oid)
            except Exception:
                pass
        svc = getattr(self, "trade_history_service", None)
        if svc:
            try:
                for tr in await svc.get_recent_trades(limit=800):
                    if not isinstance(tr, dict):
                        continue
                    oid = str(tr.get("order_id") or "").strip()
                    if oid and oid in seen_oid:
                        continue
                    pnl = float(tr.get("pnl") or 0.0)
                    wrapped = {
                        "decision": {
                            "pnl": pnl,
                            "symbol": tr.get("symbol", ""),
                            "action": str((tr.get("metadata") or {}).get("action", "") or ""),
                        },
                        "order_result": {"order_id": tr.get("order_id", "")},
                    }
                    merged.append(wrapped)
                    if oid:
                        seen_oid.add(oid)
            except Exception as e:
                logger.debug("合并 TradeHistoryService 到优化样本失败: %s", e)
        return merged

    async def _optimization_loop(self) -> None:
        """优化循环 - 策略自我优化"""
        while self._running:
            try:
                # 每小时优化一次
                await asyncio.sleep(3600)
                
                logger.info("🔄 开始策略自我优化...")
                
                # 分析交易历史
                opt_rows = await self._trade_rows_for_optimization()
                n_hist = len(opt_rows)
                n_mem = len(self.trade_history)
                if n_hist >= 10:
                    await self._optimize_strategy(opt_rows)
                else:
                    logger.info(
                        "⏭️ 跳过本周期策略优化：合并样本不足 10 条（合并=%s 内存=%s）；"
                        " 学习引擎与记忆平仓另计。",
                        n_hist,
                        n_mem,
                    )
                
            except Exception as e:
                logger.error(f"优化循环错误: {e}")
    
    async def _optimize_strategy(self, trade_rows: Optional[List[Dict[str, Any]]] = None) -> None:
        """策略优化"""
        try:
            rows = trade_rows if trade_rows is not None else list(self.trade_history)
            # 兼容壳 StrategyOptimizer 无实质分析；若走该分支会提前 return，导致下方胜率统计永不执行
            opt = self.strategy_optimizer
            if opt and not getattr(opt, "is_compat_shim", False):
                logger.info("📊 使用策略优化器分析交易表现...")
                performances = await opt._analyze_all_strategies()
                new_proposals = await opt._discover_new_patterns()
                if new_proposals:
                    logger.info(f"💡 发现 {len(new_proposals)} 个新策略提案")
                await opt._process_new_strategy_proposals()
                await opt._save_optimization_results()
                logger.info("✅ 策略优化完成")
                return

            if opt and getattr(opt, "is_compat_shim", False):
                logger.info(
                    "📌 策略优化器为兼容 shim（无全量分析）；本周期使用 trade_history 内置统计。"
                    " 生产级参数收敛见 StrategyManager / apply_trade_feedback 与 API optimize-now。"
                )

            # 备用：原有的简单优化逻辑（胜率 → min_confidence 微调 + 记忆落库）
            profitable_trades = sum(1 for t in rows if t.get("decision", {}).get("pnl", 0) > 0)
            total_trades = len(rows)
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
                        raw_max = self.ai_config.get("critical_risk_auto_close_max_liq_distance")
                        liq_auto_close_max = float(raw_max) if raw_max is not None else liq_critical
                        if liq_auto_close_max <= 0:
                            liq_auto_close_max = liq_critical
                        near_liq = liq_dist > 0 and liq_dist <= liq_auto_close_max

                        margin_critical = float(risk_cfg.get("margin_ratio_critical", 0.9) or 0.9)
                        margin_emergency = margin_critical > 0 and float(getattr(account_risk, "margin_ratio", 0) or 0) >= margin_critical

                        min_loss_pct = float(self.ai_config.get("critical_risk_auto_close_min_loss_pct", 25.0) or 25.0)
                        severe_loss = loss_pct >= min_loss_pct

                        should_recommend = margin_emergency or near_liq or severe_loss
                        if should_recommend:
                            logger.critical(
                                "🤖 临界风险（建议主链路平仓，不自动下单）: %s "
                                "(liq_dist=%.3f, max_liq=%.3f, loss=%.1f%%, margin=%.3f)",
                                pos_risk.symbol,
                                liq_dist,
                                liq_auto_close_max,
                                loss_pct,
                                float(getattr(account_risk, "margin_ratio", 0) or 0),
                            )
                            await self._recommend_close_to_main_lane(
                                symbol=pos_risk.symbol,
                                reason="critical_risk_recommendation",
                                liq_dist=liq_dist,
                                loss_pct=loss_pct,
                                margin_ratio=float(getattr(account_risk, "margin_ratio", 0) or 0),
                            )
                        else:
                            logger.warning(
                                "🛡️ 未达建议平仓闸门 %s (liq_dist=%.3f, need<=%.3f, loss=%.1f%%, need>=%.1f%%)",
                                pos_risk.symbol,
                                liq_dist,
                                liq_auto_close_max,
                                loss_pct,
                                min_loss_pct,
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
    
    async def _recommend_close_to_main_lane(
        self,
        *,
        symbol: str,
        reason: str,
        liq_dist: float = 0.0,
        loss_pct: float = 0.0,
        margin_ratio: float = 0.0,
    ) -> None:
        """临界风险不向交易所强制平仓，仅通知主链路与事件总线。"""
        position = self.positions.get(symbol)
        side = getattr(position, "side", None) if position and not isinstance(position, dict) else None
        qty = getattr(position, "quantity", None) if position and not isinstance(position, dict) else None
        text = (
            f"建议尽快处理持仓 {symbol}（reason={reason}）\n"
            f"侧向={side} 数量={qty}\n"
            f"距强平比例≈{liq_dist:.4f} 浮亏幅度≈{loss_pct:.1f}% 保证金占用≈{margin_ratio:.3f}\n"
            "实际平仓仅由：主 AI 决策、止盈止损模块、或用户 API/显式指令。"
        )
        mc = self.main_controller
        try:
            if mc and hasattr(mc, "_send_notification_handler"):
                await mc._send_notification_handler("风险：建议平仓（未自动下单）", text, priority="high")
        except Exception as e:
            logger.debug("recommend_close notify: %s", e)

        # Also mirror directly to TradeEventHub (bypass messaging.instant off / filters).
        try:
            hub = getattr(mc, "trade_event_hub", None) if mc else None
            if hub and hasattr(hub, "publish_system_alert"):
                await hub.publish_system_alert(
                    source="ai_trading_engine",
                    title="风险：建议平仓（未自动下单）",
                    message=text,
                    priority="high",
                    kind="risk.close_recommendation",
                    data={
                        "symbol": str(symbol or ""),
                        "reason": str(reason or ""),
                        "liq_dist": float(liq_dist or 0.0),
                        "loss_pct": float(loss_pct or 0.0),
                        "margin_ratio": float(margin_ratio or 0.0),
                    },
                )
        except Exception as e:
            logger.debug("recommend_close trade_event_hub: %s", e)
        try:
            from src.modules.core.event_system import EventPriority, EventType

            es = getattr(mc, "event_system", None) if mc else None
            if es and hasattr(es, "emit"):
                await es.emit(
                    EventType.RISK_ALERT,
                    "aitrading_engine",
                    {
                        "kind": "close_recommendation",
                        "symbol": symbol,
                        "reason": reason,
                        "liq_dist": liq_dist,
                        "loss_pct": loss_pct,
                        "margin_ratio": margin_ratio,
                        "side": side,
                    },
                    priority=EventPriority.HIGH,
                )
        except Exception as e:
            logger.debug("recommend_close event: %s", e)
        await self._save_risk_event_to_memory(
            event_type="close_recommendation",
            symbol=symbol,
            description=text[:500],
            action_taken="已通知主链路/用户（无自动平仓）",
            impact=f"symbol={symbol}",
        )

    async def _save_risk_event_to_memory(self, event_type: str, symbol: str,
                                         description: str, action_taken: str,
                                         impact: str) -> None:
        """保存风险事件到记忆库（带去重）"""
        try:
            import time
            
            event_key = f"{event_type}_{symbol}"
            current_time = time.time()

            # For close recommendations, we want repeated visibility in memory/UI.
            # Keep global cooldown for noisy risk events, but bypass it for close_recommendation.
            effective_cooldown = float(self._risk_event_cooldown or 0)
            if str(event_type or "") == "close_recommendation":
                effective_cooldown = 0.0
            
            if event_key in self._last_risk_events:
                last_time = self._last_risk_events[event_key]
                if effective_cooldown > 0 and (current_time - last_time) < effective_cooldown:
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
