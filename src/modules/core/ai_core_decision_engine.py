"""
AI 核心决策引擎 - 完整控制权版本
AI拥有策略生成、回测、优化、交易执行的100%控制权

架构：
1. AI生成策略 → 2. AI回测验证 → 3. AI优化参数 → 4. AI决定交易 → 5. AI执行交易 → 6. AI报告用户
"""

import asyncio
import logging
import json
import re
import math
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

from src.modules.memory.memory_schema import base_metadata, kind_tag, symbol_tag, tags

from src.modules.core.timing_constants import (
    SLEEP_1S,
    SLEEP_2S,
    SLEEP_5S,
    SLEEP_30S,
    SLEEP_5MIN,
    SLEEP_1H,
)


@dataclass
class TradeDecision:
    """AI交易决策"""
    symbol: str
    action: str  # buy, sell, hold, close
    side: str    # long, short
    quantity: int
    leverage: int
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence: float
    reasoning: str
    strategy_used: str
    risk_level: str


@dataclass
class StrategyProposal:
    """AI策略提案"""
    name: str
    strategy_type: str
    parameters: Dict[str, Any]
    symbols: List[str]
    timeframe: str
    reasoning: str
    expected_return: float
    risk_level: str


class AICoreDecisionEngine:
    """
    AI核心决策引擎 - 完整控制权版本
    
    AI拥有完整的决策权和控制权：
    1. 策略生成权 - AI自主创建、修改、删除策略
    2. 回测执行权 - AI自主进行策略回测验证
    3. 参数优化权 - AI自主优化策略参数
    4. 交易决策权 - AI全权决定开仓、平仓、止损止盈
    5. 风险控制权 - AI自主评估和控制风险
    6. 资金管理权 - AI自主分配资金和仓位

    实盘开平仓（S1，与 config ai_brain / ExecutionGateway 一致）：
    - 主路径：execute_command(write_source=ai_core) → ExecutionVerifier → ExecutionGateway
    - 回退：ExecutionGateway(open_swap/close_swap, source=ai_core)
    - 仅当无 ExecutionGateway 时允许交易所直连兜底
    - 用户指令平仓：manual；账户级临界风险由监控告警主链路，不经辅环强平
    """
    
    def __init__(self, main_controller=None):
        self.main_controller = main_controller
        
        # 核心模块引用
        self.llm = None
        self.exchange = None
        self.memory = None
        self.strategy_manager = None
        self.risk_monitor = None
        self.telegram_bot = None
        self.backtester = None
        self.parameter_optimizer = None
        self.plugin_manager = None
        
        # 用户规则
        self.blacklist = set()  # 空黑名单，允许所有交易对
        self.authorization = {
            "full_authorization": True,
            "auto_trading": True,
            "auto_strategy": True,
            "auto_backtest": True,
            "auto_optimize": True,
        }
        
        self.config = {
            "leverage_min": 10,
            "leverage_max": 100,
            "default_leverage": 20,
            "max_positions": 5,
            # 中频档：在不激进放宽风控的前提下，适度提升开单频率
            "min_trade_interval": 80,
            "strategy_check_interval": 300,
            "backtest_lookback_days": 30,
            "aggressive_mode": False,
            "auto_create_strategy": True,
            "min_confidence_to_trade": 0.72,
            # Explicit open gate: avoid low-confidence churn
            "ai_core_min_confidence_to_open": 0.78,
            "min_data_quality_to_trade": 0.55,
            "min_rr_to_trade": 1.15,
            "max_spread_bps_to_trade": 40.0,
            "max_abs_depth_imbalance_to_trade": 0.92,
            "degraded_data_quantity_factor": 0.68,
            "low_balance_usdt_threshold": 25.0,
            "default_max_margin_fraction": 0.30,
            "low_balance_margin_fraction": 0.55,
            "boost_on_low_risk": True,
            "low_risk_rr_multiplier": 0.96,
            "low_risk_spread_multiplier": 1.08,
            "high_risk_rr_multiplier": 1.08,
            "high_risk_spread_multiplier": 0.90,
            "auto_frequency_profile_switch": True,
            "frequency_profile_switch_telegram_notify": True,
            "frequency_profile_cooldown_seconds": 1800,
            "frequency_profile_lookback_trades": 20,
            "frequency_profile_max_drawdown_guard": 0.12,
            "auto_adaptive_guards": True,
            "auto_tune_guards": True,
            "auto_tune_by_symbol_group": True,
            "auto_tune_by_session": True,
            "auto_tune_step_rr": 0.05,
            "auto_tune_step_spread_bps": 2.0,
            "auto_tune_global_enabled": True,
            "auto_tune_global_cooldown_seconds": 86400,
            "auto_tune_global_step_rr": 0.02,
            "auto_tune_global_step_spread_bps": 1.0,
            "auto_tune_group_step_rr": None,
            "auto_tune_group_step_spread_bps": None,
            "auto_tune_cooldown_seconds": 10800,
            "auto_tune_min_rr_delta": 0.01,
            "auto_tune_min_spread_delta_bps": 0.5,
            "auto_tune_rr_bounds": [1.0, 2.0],
            "auto_tune_spread_bounds": [12.0, 80.0],
            "auto_tune_sltp_params": True,
            "auto_tune_sltp_cooldown_seconds": 21600,
            "auto_tune_sltp_step_tighten": 0.02,
            "auto_tune_sltp_step_extend": 0.02,
            "auto_tune_sltp_tighten_bounds": [0.08, 0.30],
            "auto_tune_sltp_extend_bounds": [0.02, 0.25],
            "max_loss_per_position": 0.05,
            "daily_loss_limit": 0.10,
            "max_drawdown_limit": 0.15,
            "risk_check_interval": 30,
            "auto_reduce_on_high_risk": True,
            "emergency_close_on_critical": True,
            # AI 主观平仓防抖（仅作用于主决策循环里的 LLM close；SLTP/用户指令平仓不走此逻辑）
            "ai_core_discretionary_close_enabled": True,
            "ai_core_discretionary_close_cooldown_sec": 2700,
            "ai_core_min_confidence_to_close": 0.84,
            "ai_core_discretionary_close_confirmations": 2,
            "ai_core_discretionary_close_confirm_window_sec": 1200,
            "ai_core_min_position_age_sec_before_discretionary_close": 600,
            # 决策理由若包含以下子串，禁止主观平仓（模型常一边写「多周期矛盾」一边给 100% confidence close）
            "ai_core_close_reason_veto_substrings": [
                "多周期矛盾",
                "multi-timeframe contradiction",
                "timeframes contradict",
            ],
            # 策略研究任务限流（避免挤占交易/API主路径）；手动 API 不受持仓/冷却限制
            "research_enabled": True,
            "research_cooldown_seconds": 7200,
            "research_max_symbols": 4,
            "research_lookback_days": 28,
            "research_timeout_seconds": 420,
            # hold_avoidance_override hardening (reduce churn in choppy markets)
            "hold_avoidance_override_enabled": True,
            "hold_avoidance_override_cooldown_sec": 1200,
            "hold_avoidance_override_min_abs_sentiment": 0.06,
            "hold_avoidance_override_min_mi_quality_score": 0.62,
            "hold_avoidance_override_require_mi_trend_alignment": True,
        }

        # 开仓 RR 门控与主配置 stop_loss_take_profit（移动止损）对齐
        self._sltp_open_snapshot: Dict[str, Any] = {}
        
        # 状态
        self._running = False
        self._last_decision_time: Dict[str, datetime] = {}
        self._last_hold_override_at: Dict[str, datetime] = {}
        self._last_strategy_check: Optional[datetime] = None
        self._pending_decisions: List[TradeDecision] = []
        # 与 StrategyManager 中已启用策略同步的镜像；用于状态与提示词排序
        self._active_strategies: Dict[str, Any] = {}
        # 简化回测打分后的优先策略 ID（决策提示词优先推荐）
        self._preferred_strategy_id: Optional[str] = None
        self._strategy_performance: Dict[str, Dict] = {}
        self._execution_guards_stats: Dict[str, int] = {
            "data_quality_guard_hold": 0,
            "degraded_quantity_reduced": 0,
            "rr_rejected": 0,
            "spread_rejected": 0,
            "depth_imbalance_rejected": 0,
            "discretionary_close_suppressed": 0,
        }
        self._adaptive_guard_profile: Dict[str, Any] = {
            "profile": "normal",
            "symbol_group": "DEFAULT",
            "atr_pct_1h": 0.0,
            "effective_min_rr": self.config.get("min_rr_to_trade", 1.2),
            "effective_max_spread_bps": self.config.get("max_spread_bps_to_trade", 35.0),
            "effective_max_abs_depth_imbalance": self.config.get("max_abs_depth_imbalance_to_trade", 0.92),
        }
        self._symbol_group_guard_overrides: Dict[str, Dict[str, float]] = {}
        self._last_group_tune_at: Dict[str, datetime] = {}
        self._last_global_tune_at: Optional[datetime] = None
        self._sltp_group_adaptive: Dict[str, Dict[str, float]] = {}
        self._last_sltp_tune_at: Dict[str, datetime] = {}
        self._last_research_at: Optional[datetime] = None
        self._frequency_profile: str = "balanced"
        self._last_frequency_profile_switch_at: Optional[datetime] = None
        # (symbol_base, side) -> 最近一次由主循环执行的「主观平仓」成功时间
        self._last_ai_discretionary_close_at: Dict[str, datetime] = {}
        # key -> (consecutive_close_signals, first_signal_at)
        self._discretionary_close_streak: Dict[str, tuple] = {}
        # 主动性扫描器推送的机会（默认不自动开仓，仅进入本引擎决策上下文）
        self._scanner_hints: Dict[str, Dict[str, Any]] = {}
        self._scanner_hint_ttl_sec: float = 5400.0

        logger.info("🧠 AI核心决策引擎初始化（完整控制权版本）")
    
    async def initialize(self) -> None:
        """初始化 - 获取所有模块引用"""
        logger.info("初始化AI核心决策引擎...")
        
        if not self.main_controller:
            logger.error("主控制器未设置")
            return
        
        # 获取LLM
        if hasattr(self.main_controller, 'llm_integration'):
            self.llm = self.main_controller.llm_integration
            logger.info("✅ LLM已连接")
        
        # 获取交易所
        if hasattr(self.main_controller, 'okx_exchange'):
            self.exchange = self.main_controller.okx_exchange
            logger.info("✅ 交易所已连接")
        elif hasattr(self.main_controller, 'exchange'):
            self.exchange = self.main_controller.exchange
            logger.info("✅ 交易所已连接")
        
        # 获取策略管理器
        if hasattr(self.main_controller, 'strategy_manager'):
            self.strategy_manager = self.main_controller.strategy_manager
            logger.info("✅ 策略管理器已连接")
        
        # 获取风险监控
        if hasattr(self.main_controller, 'risk_monitor'):
            self.risk_monitor = self.main_controller.risk_monitor
            logger.info("✅ 风险监控已连接")
        
        # 获取Telegram机器人
        if hasattr(self.main_controller, 'telegram_bot'):
            self.telegram_bot = self.main_controller.telegram_bot
            logger.info("✅ Telegram已连接")
        
        # 获取回测系统
        if hasattr(self.main_controller, 'enhanced_backtester'):
            self.backtester = self.main_controller.enhanced_backtester
            logger.info("✅ 回测系统已连接")
        
        # 获取参数优化器
        if hasattr(self.main_controller, 'parameter_optimizer'):
            self.parameter_optimizer = self.main_controller.parameter_optimizer
            logger.info("✅ 参数优化器已连接")
        
        # 获取插件管理器（第三方数据）
        if hasattr(self.main_controller, 'plugin_manager'):
            self.plugin_manager = self.main_controller.plugin_manager
            logger.info("✅ 插件管理器已连接")
        
        # 获取记忆系统（优先复用主控制器核心记忆）
        self.memory = getattr(self.main_controller, "ai_memory_manager", None)
        if self.memory:
            logger.info("✅ 记忆系统已连接（主控制器核心记忆）")
        else:
            # 单一真源：不再 fallback 到并行记忆实现
            logger.warning("⚠️ MemoryGateway 未就绪：AI核心决策引擎将以无记忆模式运行")
        
        # 加载用户规则
        await self._load_user_rules()

        if self.main_controller.config_manager:
            try:
                tr = await self.main_controller.config_manager.get_config("trading", {}) or {}
                from src.modules.core.trading_contract_settings import (
                    apply_trading_contract_unified,
                )

                _cc: Dict[str, Any] = {}
                _ai: Dict[str, Any] = {}
                apply_trading_contract_unified(
                    tr if isinstance(tr, dict) else {},
                    contract_config=_cc,
                    ai_config=_ai,
                    ai_core_config=self.config,
                )
                sltp = (
                    await self.main_controller.config_manager.get_config(
                        "stop_loss_take_profit", {}
                    )
                    or {}
                )
                self._sltp_open_snapshot = dict(sltp) if isinstance(sltp, dict) else {}
            except Exception as e:
                logger.warning("AI核心加载 trading.contract / SLTP 快照失败: %s", e)
        
        logger.info("✅ AI核心决策引擎初始化完成 - AI拥有完整控制权")

    def _scanner_hint_key(self, symbol: str) -> str:
        return str(symbol or "").replace(" ", "").upper()

    def _prune_scanner_hints(self) -> None:
        if not self._scanner_hints:
            return
        now = datetime.now()
        ttl = float(self._scanner_hint_ttl_sec or 5400.0)
        stale = []
        for k, p in self._scanner_hints.items():
            try:
                raw = str(p.get("received_at", "") or "").replace("Z", "+00:00")
                ts = datetime.fromisoformat(raw)
                if ts.tzinfo is not None:
                    ts = ts.replace(tzinfo=None)
                if (now - ts).total_seconds() > ttl:
                    stale.append(k)
            except Exception:
                continue
        for k in stale:
            self._scanner_hints.pop(k, None)

    def ingest_scanner_opportunity(self, payload: Dict[str, Any]) -> None:
        """
        接收 ProactiveMarketScanner 的「机会提示」。
        仅供 _build_decision_prompt 与币种优先级参考，不是已执行订单，也不代替风控。
        """
        try:
            sym = str(payload.get("symbol") or "").strip()
            if not sym:
                return
            key = self._scanner_hint_key(sym)
            row = dict(payload)
            row["received_at"] = datetime.now().isoformat()
            self._scanner_hints[key] = row
            logger.info("📥 ai_core 已接收扫描机会提示: %s %s", key, row.get("opportunity_type"))
        except Exception as e:
            logger.debug("ingest_scanner_opportunity failed: %s", e)

    def _scanner_hint_payload_for_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        self._prune_scanner_hints()
        key = self._scanner_hint_key(symbol)
        if key in self._scanner_hints:
            return self._scanner_hints[key]
        base = symbol.split("/")[0].upper() if "/" in symbol else ""
        if not base:
            return None
        for hk, pv in self._scanner_hints.items():
            if hk.startswith(base + "/"):
                return pv
        return None

    def _format_scanner_hint_block(self, symbol: str) -> str:
        p = self._scanner_hint_payload_for_symbol(symbol)
        if not p:
            return ""
        ds = p.get("data_sources") or []
        ds_s = ", ".join(str(x) for x in ds) if isinstance(ds, list) else str(ds)
        conf = float(p.get("confidence") or 0)
        gm = p.get("gate_metrics") if isinstance(p.get("gate_metrics"), dict) else {}
        gr = p.get("gate_pass_reason") or ""
        gate_extra = ""
        if gm:
            gate_extra = (
                f"\n- 实时数据预检: {gr or 'ok'} | spread_bps={gm.get('spread_bps')} | "
                f"atr_pct_1h={gm.get('atr_pct_1h')} | risk_reward={gm.get('risk_reward')} | "
                f"vol/均量={gm.get('volume_vs_avg_ratio')} | 24h涨跌={gm.get('change_24h')}\n"
            )
        return f"""
【主动性扫描发现（仅供参考：不是已成交订单，也不是绕过风控的指令）】
- 机会类型: {p.get('opportunity_type')}
- 建议方向: {p.get('direction')}
- 扫描置信度: {conf:.0%}
- 参考 入场/止损/止盈: {p.get('entry_price')} / {p.get('stop_loss')} / {p.get('take_profit')}
- 扫描理由: {p.get('reasoning')}
- 数据来源: {ds_s}
- 提示接收时间: {p.get('received_at')}{gate_extra}
你必须用技术指标、多源融合、风险与持仓情况独立复核；与上述方向矛盾或证据不足时 action 必须为 hold。
禁止仅因本段文字下单或放宽系统最小置信度要求；若开仓须在 reasoning 中说明如何与扫描结论一致或为何不采纳。
"""

    def _merge_scanner_priority_symbols(self, symbols: List[str], *, limit: int = 8) -> List[str]:
        """将仍有未过期扫描提示的交易对优先排在前面，便于 ai_core 尽快研判。"""
        self._prune_scanner_hints()
        prioritized = list(self._scanner_hints.keys())
        out: List[str] = []
        seen = set()
        for s in prioritized + (symbols or []):
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out[:limit]

    async def _load_user_rules(self) -> None:
        """从记忆加载用户规则"""
        if not self.memory:
            return
        
        try:
            blacklist_mems = await self.memory.retrieve_memories(
                query="黑名单 禁区 不要",
                min_importance=0.8,
                limit=5
            )
            for mem in blacklist_mems:
                # 不再自动将ETH加入黑名单
                if "ETH" in mem.content or "以太坊" in mem.content:
                    logger.info(f"ℹ️ 忽略ETH黑名单记忆: 已移除ETH限制")
            
            auth_mems = await self.memory.retrieve_memories(
                query="全权 负责 授权",
                min_importance=0.8,
                limit=3
            )
            for mem in auth_mems:
                if "全权负责" in mem.content or "整个交易流程" in mem.content:
                    self.authorization["full_authorization"] = True
                    self.authorization["auto_trading"] = True
                    self.authorization["auto_strategy"] = True
                    self.authorization["auto_backtest"] = True
                    self.authorization["auto_optimize"] = True
            
            logger.info(f"📋 用户规则已加载: 黑名单={self.blacklist}, 授权={self.authorization}")
            
        except Exception as e:
            logger.error(f"加载用户规则失败: {e}")
    
    async def start(self) -> None:
        """启动AI决策循环"""
        logger.info("🚀 启动AI核心决策引擎...")
        self._running = True
        
        # 等待交易所连接完成
        logger.info("⏳ 等待交易所连接...")
        for i in range(10):
            if self.exchange:
                try:
                    # 测试交易所连接
                    await self.exchange.get_balance()
                    logger.info("✅ 交易所连接就绪")
                    break
                except Exception as e:
                    logger.debug(f"交易所未就绪，等待... ({i+1}/10): {e}")
                    await asyncio.sleep(SLEEP_1S)
            else:
                logger.debug(f"交易所未连接，等待... ({i+1}/10)")
                await asyncio.sleep(SLEEP_1S)
        
        # 启动时同步持仓和交易上下文
        await self._sync_positions_on_startup()
        
        asyncio.create_task(self._main_decision_loop())
        asyncio.create_task(self._strategy_management_loop())
        asyncio.create_task(self._risk_monitoring_loop())
        asyncio.create_task(self._startup_strategy_sync_and_backtest())

        logger.info("✅ AI核心决策引擎已启动 - AI拥有完整控制权")
    
    async def _sync_positions_on_startup(self) -> None:
        """启动时同步持仓 - 从交易所获取当前持仓状态"""
        logger.info("🔄 同步持仓状态...")
        
        if not self.exchange:
            logger.warning("交易所未连接，无法同步持仓")
            return
        
        try:
            # 获取当前持仓
            positions = await self.exchange.get_positions()
            logger.debug(f"获取到 {len(positions) if positions else 0} 个持仓记录")
            
            if not positions:
                logger.info("📊 交易所返回无持仓数据")
                return
            
            # 打印原始数据用于调试
            for p in positions[:3]:
                logger.debug(f"持仓原始数据: symbol={p.get('symbol')}, size={p.get('size')}, side={p.get('side')}")
            
            # 注意：OKX的get_positions返回格式是 {symbol, side, size, entry_price, unrealized_pnl}
            # 而不是 {instId, posSide, pos}
            active_positions = [p for p in positions if float(p.get('size', 0) or 0) != 0]
            
            if active_positions:
                logger.info(f"📊 同步到 {len(active_positions)} 个活跃持仓:")
                for pos in active_positions:
                    symbol = pos.get('symbol', '')
                    side = pos.get('side', '')
                    size = pos.get('size', 0)
                    pnl = float(pos.get('unrealized_pnl', 0) or 0)
                    entry_price = float(pos.get('entry_price', 0) or 0)
                    logger.info(f"   - {symbol}: {side} {size} | 入场价: {entry_price:.4f} | 盈亏: ${pnl:+.2f}")
                
                # 保存到记忆系统
                if self.memory:
                    position_summary = {
                        "timestamp": datetime.now().isoformat(),
                        "total_positions": len(active_positions),
                        "positions": [
                            {
                                "symbol": p.get('symbol', ''),
                                "side": p.get('side', ''),
                                "size": p.get('size', 0),
                                "entry_price": float(p.get('entry_price', 0) or 0),
                                "pnl": float(p.get('unrealized_pnl', 0) or 0)
                            }
                            for p in active_positions
                        ]
                    }
                    
                    # 保存持仓快照到记忆
                    try:
                        await self.memory.add_memory(
                            content=f"系统启动时持仓同步: {json.dumps(position_summary, ensure_ascii=False)}",
                            memory_type="episodic",
                            importance=0.9
                        )
                        logger.info("✅ 持仓状态已保存到记忆系统")
                    except Exception as e:
                        logger.warning(f"保存持仓到记忆失败: {e}")
            else:
                logger.info("📊 当前无活跃持仓")
            
            # 获取账户余额
            try:
                balance = await self.exchange.get_balance()
                usdt = balance.get('USDT', {})
                if isinstance(usdt, dict):
                    available = usdt.get('free', 0)
                    total = usdt.get('total', 0)
                else:
                    available = usdt
                    total = usdt
                logger.info(f"💰 账户余额: 可用 {available:.2f} USDT, 总计 {total:.2f} USDT")
            except Exception as e:
                logger.warning(f"获取余额失败: {e}")
            
        except Exception as e:
            logger.error(f"同步持仓失败: {e}")
    
    async def stop(self) -> None:
        """停止"""
        self._running = False
        logger.info("🛑 AI核心决策引擎已停止")
    
    async def _main_decision_loop(self) -> None:
        """AI主决策循环 - 24小时不间断主动交易，自主选择币种"""
        while self._running:
            try:
                logger.info("🔄 AI开始主动扫描市场机会...")
                
                # AI自主选择交易币种 - 根据市场波动和机会
                symbols = await self._auto_select_trading_symbols()
                
                for symbol in symbols:
                    if symbol in self._last_decision_time:
                        elapsed = (datetime.now() - self._last_decision_time[symbol]).total_seconds()
                        if elapsed < self.config["min_trade_interval"]:
                            continue
                    
                    decision = await self._ai_analyze_and_decide(symbol)
                    
                    if decision:
                        if decision.action != "hold":
                            logger.info(f"🎯 AI发现交易机会: {symbol} {decision.action} {decision.side}")
                            success = await self._execute_decision(decision)
                            if success:
                                await self._report_decision(decision)
                        else:
                            logger.info(f"📊 {symbol} 暂无机会，继续监控")
                    
                    await asyncio.sleep(SLEEP_2S)
                
                await asyncio.sleep(SLEEP_30S)
                
            except Exception as e:
                logger.error(f"AI决策循环错误: {e}")
                await asyncio.sleep(SLEEP_5S)
    
    async def _auto_select_trading_symbols(self) -> List[str]:
        """AI自主选择交易币种 - 根据市场波动和机会，自由选择"""
        # 尝试从交易所获取所有可用的USDT交易对
        all_symbols = []
        
        if self.exchange:
            try:
                if hasattr(self.exchange, 'get_symbols'):
                    exchange_symbols = await self.exchange.get_symbols()
                    # 过滤USDT交易对
                    all_symbols = [s for s in exchange_symbols if '/USDT' in s or '-USDT' in s]
                    # 标准化格式
                    all_symbols = [s.replace('-USDT', '/USDT').replace('-SWAP', '') for s in all_symbols]
                    # 去重
                    all_symbols = list(set(all_symbols))
            except Exception as e:
                logger.debug(f"获取交易所交易对失败，回退默认列表: {e}")
        
        # 如果无法获取交易所交易对，使用主流币种
        if not all_symbols:
            all_symbols = [
                "BTC/USDT", "SOL/USDT", "BNB/USDT", 
                "XRP/USDT", "DOGE/USDT", "ADA/USDT",
                "AVAX/USDT", "DOT/USDT", "MATIC/USDT", "LINK/USDT",
                "ATOM/USDT", "LTC/USDT", "TRX/USDT", "BCH/USDT"
            ]
        
        # 黑名单已清空，不过滤任何交易对
        available_symbols = all_symbols
        
        if not self.exchange:
            return self._merge_scanner_priority_symbols(available_symbols[:5], limit=8)
        
        try:
            # 获取市场数据，选择波动大的币种
            symbol_volatility = {}
            
            for symbol in available_symbols[:30]:  # 最多检查30个币种
                try:
                    ticker = await self.exchange.get_ticker(symbol.replace('/', '-'))
                    if ticker:
                        change_24h = abs(float(ticker.get('change24h', 0) or ticker.get('change', 0)))
                        volume = float(ticker.get('volume', 0) or 0)
                        # 综合评分：波动性 + 成交量
                        score = change_24h * 100 + (volume / 1000000 if volume > 0 else 0)
                        symbol_volatility[symbol] = score
                except Exception as e:
                    logger.debug(f"获取币种行情失败 {symbol}: {e}")
            
            # 选择评分最高的5个币种
            sorted_symbols = sorted(symbol_volatility.items(), key=lambda x: x[1], reverse=True)
            selected = [s[0] for s in sorted_symbols[:5]]
            
            if selected:
                merged = self._merge_scanner_priority_symbols(selected, limit=8)
                logger.info(f"📊 AI自主选择交易币种: {merged}")
                return merged
            
        except Exception as e:
            logger.error(f"AI选择币种失败: {e}")
        
        return self._merge_scanner_priority_symbols(available_symbols[:5], limit=8)

    async def _sync_active_strategies_from_manager(self) -> None:
        """将 StrategyManager 中已启用策略同步到 _active_strategies（与「仅 AI 自建」脱钩）。"""
        if not self.strategy_manager:
            return
        configs = getattr(self.strategy_manager, "strategy_configs", None) or {}
        n = 0
        for sid, cfg in configs.items():
            if hasattr(cfg, "enabled") and not getattr(cfg, "enabled", True):
                continue
            st = getattr(cfg, "strategy_type", "unknown")
            stv = st.value if hasattr(st, "value") else str(st)
            self._active_strategies[sid] = {
                "strategy_id": sid,
                "name": getattr(cfg, "name", sid),
                "description": getattr(cfg, "description", ""),
                "strategy_type": stv,
                "parameters": dict(getattr(cfg, "parameters", {}) or {}),
                "symbols": list(getattr(cfg, "symbols", []) or []),
                "timeframe": getattr(cfg, "timeframe", "1h"),
                "initial_capital": float(getattr(cfg, "initial_capital", 10000.0) or 10000.0),
                "enabled": True,
            }
            n += 1
        logger.info("✅ 已从策略管理器同步 %s 个启用策略到 AI 核心", n)

    @staticmethod
    def _score_backtest_perf(perf: Dict[str, Any]) -> float:
        """综合打分：夏普、回撤惩罚、收益、成交次数（用于择优）。"""
        if not perf:
            return -1e9
        try:
            sh = float(perf.get("sharpe_ratio", 0) or 0)
            dd = float(perf.get("max_drawdown", 0.5) or 0)
            tr = float(perf.get("total_return", 0) or 0)
            tc = int(perf.get("trade_count", 0) or 0)
            if tc < 2:
                return -1e8 + tr
            dd_pen = max(0.0, min(abs(dd), 0.99))
            return sh * (1.0 - dd_pen * 0.5) + 0.25 * tr + 0.01 * float(tc)
        except Exception:
            return -1e9

    async def _rank_strategies_after_backtest(self) -> None:
        """根据 _strategy_performance 中的简化回测结果选出优先策略。"""
        best_id: Optional[str] = None
        best_score = -1e18
        for sid, perf in (self._strategy_performance or {}).items():
            if not isinstance(perf, dict):
                continue
            sc = self._score_backtest_perf(perf)
            if sc > best_score:
                best_score = sc
                best_id = sid
        if best_id:
            self._preferred_strategy_id = best_id
            logger.info("📌 回测择优：优先策略 %s (score=%.4f)", best_id, best_score)
        else:
            self._preferred_strategy_id = None

    async def _startup_strategy_sync_and_backtest(self) -> None:
        """启动后异步：同步策略池 → 自动回测 → 自动优化 → 择优（全权模式无需用户点「激活」）。"""
        try:
            await asyncio.sleep(5)
            await self._sync_active_strategies_from_manager()
            if self.authorization.get("auto_backtest"):
                await self._auto_backtest_strategies()
            if self.authorization.get("auto_optimize"):
                await self._auto_optimize_strategies()
            await self._rank_strategies_after_backtest()
        except Exception as e:
            logger.warning("启动时策略同步/回测/择优失败: %s", e)
    
    async def _strategy_management_loop(self) -> None:
        """AI策略管理循环 - 等待交易事件触发"""
        while self._running:
            try:
                # 不再定时执行，改为交易后触发
                await asyncio.sleep(SLEEP_1H)  # 每小时检查一次是否有需要优化的策略
                
                logger.info("🔄 AI进行定期策略检查...")
                
                # 从记忆系统获取历史经验
                await self._learn_from_memory()
                
                # 检查是否有表现不佳的策略需要优化
                await self._check_and_optimize_underperforming_strategies()

                # 自动研究并发布候选策略（walk-forward 门控）
                await self._run_research_pipeline()

                # 根据近期交易表现自动微调执行门控阈值（小步、带边界）
                await self._auto_tune_guard_thresholds()

                # 自动切换频率档位（稳健/中频/积极），带冷却防抖
                await self._auto_switch_frequency_profile()
                
            except Exception as e:
                logger.error(f"策略管理循环错误: {e}")
                await asyncio.sleep(SLEEP_5MIN)

    async def _auto_tune_guard_thresholds(self) -> None:
        """基于近期交易结果自动微调 RR 与最大价差阈值。"""
        if not bool(self.config.get("auto_tune_guards", True)):
            return
        try:
            records: List[Dict[str, Any]] = []
            wins = 0
            losses = 0
            pnls: List[float] = []

            # 优先使用交易历史（若可用）
            for rec in list(getattr(self, "_trade_history", []) or [])[-40:]:
                d = rec.get("decision", {}) if isinstance(rec, dict) else {}
                pnl = d.get("pnl")
                sym = str(d.get("symbol", "") or rec.get("symbol", "") if isinstance(rec, dict) else "")
                try:
                    pnl_f = float(pnl)
                    ts = d.get("timestamp") or (rec.get("timestamp") if isinstance(rec, dict) else None)
                    records.append({"symbol": sym, "pnl": pnl_f, "timestamp": ts})
                    pnls.append(pnl_f)
                    if pnl_f > 0:
                        wins += 1
                    elif pnl_f < 0:
                        losses += 1
                except Exception:
                    continue

            # 回退使用策略表现里的交易复盘
            if len(pnls) < 8:
                for perf in (self._strategy_performance or {}).values():
                    for tr in list(perf.get("trades", []) or [])[-40:]:
                        res = tr.get("result", {}) if isinstance(tr, dict) else {}
                        pnl = None
                        sym = str(tr.get("symbol", "") if isinstance(tr, dict) else "")
                        if isinstance(res, dict):
                            pnl = res.get("pnl")
                        if pnl is None and isinstance(tr, dict):
                            pnl = tr.get("pnl")
                        try:
                            pnl_f = float(pnl)
                            ts = tr.get("timestamp") if isinstance(tr, dict) else None
                            records.append({"symbol": sym, "pnl": pnl_f, "timestamp": ts})
                            pnls.append(pnl_f)
                            if pnl_f > 0:
                                wins += 1
                            elif pnl_f < 0:
                                losses += 1
                        except Exception:
                            continue

            total = wins + losses
            if total < 8:
                return

            win_rate = wins / total if total > 0 else 0.0
            avg_pnl = (sum(pnls) / len(pnls)) if pnls else 0.0

            rr_min, rr_max = self.config.get("auto_tune_rr_bounds", [1.0, 2.0])
            sp_min, sp_max = self.config.get("auto_tune_spread_bounds", [12.0, 80.0])
            min_rr_delta = float(self.config.get("auto_tune_min_rr_delta", 0.01) or 0.01)
            min_sp_delta = float(self.config.get("auto_tune_min_spread_delta_bps", 0.5) or 0.5)

            # ---------- 全局基准：慢速漂移（可与分组解耦；冷却更长、步长更小） ----------
            if bool(self.config.get("auto_tune_global_enabled", True)):
                g_rr_step = float(self.config.get("auto_tune_global_step_rr", 0.02) or 0.02)
                g_sp_step = float(self.config.get("auto_tune_global_step_spread_bps", 1.0) or 1.0)
                gcool = int(self.config.get("auto_tune_global_cooldown_seconds", 86400) or 86400)
                now_utc = datetime.utcnow()
                can_global = True
                if self._last_global_tune_at and gcool > 0:
                    if (now_utc - self._last_global_tune_at).total_seconds() < gcool:
                        can_global = False

                if can_global:
                    rr = float(self.config.get("min_rr_to_trade", 1.2) or 1.2)
                    spread = float(self.config.get("max_spread_bps_to_trade", 35.0) or 35.0)
                    old_rr = rr
                    old_sp = spread
                    changed = False
                    if win_rate < 0.45 or avg_pnl < 0:
                        rr = min(float(rr_max), rr + g_rr_step)
                        spread = max(float(sp_min), spread - g_sp_step)
                        changed = True
                    elif win_rate > 0.60 and avg_pnl > 0:
                        rr = max(float(rr_min), rr - g_rr_step)
                        spread = min(float(sp_max), spread + g_sp_step)
                        changed = True
                    if changed:
                        if abs(rr - old_rr) >= min_rr_delta or abs(spread - old_sp) >= min_sp_delta:
                            self.config["min_rr_to_trade"] = float(rr)
                            self.config["max_spread_bps_to_trade"] = float(spread)
                            self._last_global_tune_at = now_utc
                            logger.info(
                                "🛠️ 自动调参(全局基准): win_rate=%.2f avg_pnl=%.4f RR %.2f->%.2f spread %.1f->%.1f",
                                win_rate, avg_pnl, old_rr, rr, old_sp, spread,
                            )

            # ---------- 分组/时段：较快响应（独立步长与冷却） ----------
            # 可选：按交易对分组独立学习，避免不同币种波动相互污染
            if bool(self.config.get("auto_tune_by_symbol_group", True)):
                rr_step = self.config.get("auto_tune_group_step_rr")
                sp_step = self.config.get("auto_tune_group_step_spread_bps")
                if rr_step is None:
                    rr_step = float(self.config.get("auto_tune_step_rr", 0.05) or 0.05)
                else:
                    rr_step = float(rr_step or 0.05)
                if sp_step is None:
                    sp_step = float(self.config.get("auto_tune_step_spread_bps", 2.0) or 2.0)
                else:
                    sp_step = float(sp_step or 2.0)
                grouped: Dict[str, List[float]] = {}
                tune_by_session = bool(self.config.get("auto_tune_by_session", True))
                for r in records:
                    g = self._symbol_group_key(r.get("symbol", ""))
                    if tune_by_session:
                        g = f"{g}@{self._market_session_key(r.get('timestamp'))}"
                    grouped.setdefault(g, []).append(float(r.get("pnl", 0.0)))
                for g, gpnl in grouped.items():
                    if len(gpnl) < 6:
                        continue
                    cooldown_seconds = int(self.config.get("auto_tune_cooldown_seconds", 10800) or 10800)
                    last_tune = self._last_group_tune_at.get(g)
                    if last_tune and cooldown_seconds > 0:
                        if (datetime.utcnow() - last_tune).total_seconds() < cooldown_seconds:
                            continue
                    gw = sum(1 for x in gpnl if x > 0)
                    gl = sum(1 for x in gpnl if x < 0)
                    gtotal = gw + gl
                    if gtotal < 6:
                        continue
                    gwr = gw / gtotal
                    gavg = sum(gpnl) / len(gpnl)
                    cur = self._symbol_group_guard_overrides.get(g, {})
                    g_rr = float(cur.get("min_rr_to_trade", self.config.get("min_rr_to_trade", 1.2)) or 1.2)
                    g_sp = float(cur.get("max_spread_bps_to_trade", self.config.get("max_spread_bps_to_trade", 35.0)) or 35.0)
                    old_g_rr, old_g_sp = g_rr, g_sp
                    if gwr < 0.45 or gavg < 0:
                        g_rr = min(float(rr_max), g_rr + rr_step)
                        g_sp = max(float(sp_min), g_sp - sp_step)
                    elif gwr > 0.60 and gavg > 0:
                        g_rr = max(float(rr_min), g_rr - rr_step)
                        g_sp = min(float(sp_max), g_sp + sp_step)
                    else:
                        continue
                    # 防抖：变动太小则不更新，避免阈值来回抖动
                    if abs(g_rr - old_g_rr) < min_rr_delta and abs(g_sp - old_g_sp) < min_sp_delta:
                        continue
                    self._symbol_group_guard_overrides[g] = {
                        "min_rr_to_trade": float(g_rr),
                        "max_spread_bps_to_trade": float(g_sp),
                        "sample_size": float(len(gpnl)),
                    }
                    self._last_group_tune_at[g] = datetime.utcnow()
                    logger.info(
                        "🧩 分组调参[%s]: win_rate=%.2f avg_pnl=%.4f RR %.2f->%.2f spread %.1f->%.1f",
                        g, gwr, gavg, old_g_rr, g_rr, old_g_sp, g_sp
                    )

                    # 同步学习动态 SL/TP 参数（按同一分组/时段）
                    if bool(self.config.get("auto_tune_sltp_params", True)):
                        sltp_cooldown = int(self.config.get("auto_tune_sltp_cooldown_seconds", 21600) or 21600)
                        last_sltp = self._last_sltp_tune_at.get(g)
                        if (not last_sltp) or sltp_cooldown <= 0 or (datetime.utcnow() - last_sltp).total_seconds() >= sltp_cooldown:
                            stp = float(self.config.get("auto_tune_sltp_step_tighten", 0.02) or 0.02)
                            sep = float(self.config.get("auto_tune_sltp_step_extend", 0.02) or 0.02)
                            tmin, tmax = self.config.get("auto_tune_sltp_tighten_bounds", [0.08, 0.30])
                            emin, emax = self.config.get("auto_tune_sltp_extend_bounds", [0.02, 0.25])
                            curp = self._sltp_group_adaptive.get(g, {})
                            cur_tighten = float(curp.get("dynamic_tighten_ratio", 0.15) or 0.15)
                            cur_extend = float(curp.get("dynamic_tp_extend_ratio", 0.10) or 0.10)
                            old_tighten, old_extend = cur_tighten, cur_extend
                            # 低胜率或负收益：更保守（更快锁盈，减少延展）
                            if gwr < 0.45 or gavg < 0:
                                cur_tighten = min(float(tmax), cur_tighten + stp)
                                cur_extend = max(float(emin), cur_extend - sep)
                            # 高胜率且正收益：更进攻（略放缓锁盈，增加延展）
                            elif gwr > 0.60 and gavg > 0:
                                cur_tighten = max(float(tmin), cur_tighten - stp)
                                cur_extend = min(float(emax), cur_extend + sep)
                            if abs(cur_tighten - old_tighten) >= 0.005 or abs(cur_extend - old_extend) >= 0.005:
                                self._sltp_group_adaptive[g] = {
                                    "dynamic_tighten_ratio": float(cur_tighten),
                                    "dynamic_tp_extend_ratio": float(cur_extend),
                                    "sample_size": float(len(gpnl)),
                                }
                                self._last_sltp_tune_at[g] = datetime.utcnow()
                                logger.info(
                                    "🧠 分组SLTP调参[%s]: tighten %.3f->%.3f extend %.3f->%.3f",
                                    g, old_tighten, cur_tighten, old_extend, cur_extend
                                )
        except Exception as e:
            logger.debug(f"自动调参(执行门控)失败: {e}")

    def _get_frequency_profiles(self) -> Dict[str, Dict[str, Any]]:
        return {
            "conservative": {
                "min_trade_interval": 110,
                "min_confidence_to_trade": 0.75,
                "min_rr_to_trade": 1.20,
                "max_spread_bps_to_trade": 35.0,
                "degraded_data_quantity_factor": 0.60,
                "boost_on_low_risk": True,
                "low_risk_rr_multiplier": 0.98,
                "low_risk_spread_multiplier": 1.05,
                "high_risk_rr_multiplier": 1.10,
                "high_risk_spread_multiplier": 0.88,
            },
            "balanced": {
                "min_trade_interval": 80,
                "min_confidence_to_trade": 0.72,
                "min_rr_to_trade": 1.15,
                "max_spread_bps_to_trade": 40.0,
                "degraded_data_quantity_factor": 0.68,
                "boost_on_low_risk": True,
                "low_risk_rr_multiplier": 0.96,
                "low_risk_spread_multiplier": 1.08,
                "high_risk_rr_multiplier": 1.08,
                "high_risk_spread_multiplier": 0.90,
            },
            "aggressive": {
                "min_trade_interval": 65,
                "min_confidence_to_trade": 0.68,
                "min_rr_to_trade": 1.10,
                "max_spread_bps_to_trade": 48.0,
                "degraded_data_quantity_factor": 0.75,
                "boost_on_low_risk": True,
                "low_risk_rr_multiplier": 0.94,
                "low_risk_spread_multiplier": 1.12,
                "high_risk_rr_multiplier": 1.10,
                "high_risk_spread_multiplier": 0.88,
            },
        }

    def _apply_frequency_profile(self, profile: str) -> Dict[str, Any]:
        profiles = self._get_frequency_profiles()
        p = str(profile or "").strip().lower()
        if p not in profiles:
            p = "balanced"
        applied = {}
        for k, v in profiles[p].items():
            self.config[k] = v
            applied[k] = v
        self._frequency_profile = p
        self._last_frequency_profile_switch_at = datetime.utcnow()
        return applied

    async def _auto_switch_frequency_profile(self) -> None:
        if not bool(self.config.get("auto_frequency_profile_switch", True)):
            return
        try:
            lookback = max(8, int(self.config.get("frequency_profile_lookback_trades", 20) or 20))
            cooldown = max(300, int(self.config.get("frequency_profile_cooldown_seconds", 1800) or 1800))
            if self._last_frequency_profile_switch_at:
                elapsed = (datetime.utcnow() - self._last_frequency_profile_switch_at).total_seconds()
                if elapsed < cooldown:
                    return

            pnls: List[float] = []
            losses_streak = 0
            max_losses_streak = 0
            for rec in list(getattr(self, "_trade_history", []) or [])[-lookback:]:
                d = rec.get("decision", {}) if isinstance(rec, dict) else {}
                pnl = d.get("pnl")
                try:
                    p = float(pnl)
                except Exception:
                    continue
                pnls.append(p)
                if p < 0:
                    losses_streak += 1
                    max_losses_streak = max(max_losses_streak, losses_streak)
                else:
                    losses_streak = 0

            if len(pnls) < 8:
                return

            wins = len([x for x in pnls if x > 0])
            losses = len([x for x in pnls if x < 0])
            total = max(1, wins + losses)
            win_rate = wins / total
            avg_pnl = sum(pnls) / len(pnls)

            eq = 1.0
            peak = 1.0
            dd = 0.0
            for p in pnls:
                eq *= (1.0 + p)
                peak = max(peak, eq)
                if peak > 0:
                    dd = max(dd, (peak - eq) / peak)

            dd_guard = float(self.config.get("frequency_profile_max_drawdown_guard", 0.12) or 0.12)
            target = self._frequency_profile or "balanced"
            if dd >= dd_guard or max_losses_streak >= 3 or win_rate < 0.42:
                target = "conservative"
            elif win_rate >= 0.62 and avg_pnl > 0 and dd < dd_guard * 0.7 and max_losses_streak <= 1:
                target = "aggressive"
            else:
                target = "balanced"

            old_profile = self._frequency_profile or "balanced"
            if target != old_profile:
                self._apply_frequency_profile(target)
                logger.info(
                    "🎛️ 自动切档: %s -> %s (win_rate=%.2f avg_pnl=%.4f max_dd=%.3f max_loss_streak=%s sample=%s)",
                    old_profile,
                    target,
                    win_rate,
                    avg_pnl,
                    dd,
                    max_losses_streak,
                    len(pnls),
                )
                if bool(self.config.get("frequency_profile_switch_telegram_notify", True)):
                    try:
                        if self.telegram_bot and hasattr(self.telegram_bot, "send_message") and self.telegram_bot.chat_ids:
                            await self.telegram_bot.send_message(
                                chat_id=self.telegram_bot.chat_ids[0],
                                text=(
                                    "🎛️ 自动频率切档\n"
                                    f"档位: {old_profile} -> {target}\n"
                                    f"胜率: {win_rate:.2%}\n"
                                    f"平均PnL: {avg_pnl:.4f}\n"
                                    f"最大回撤: {dd:.3f}\n"
                                    f"最大连亏: {max_losses_streak}\n"
                                    f"样本数: {len(pnls)}"
                                ),
                            )
                    except Exception as e:
                        logger.debug(f"发送自动切档Telegram通知失败: {e}")
        except Exception as e:
            logger.debug(f"自动切档失败: {e}")

    @staticmethod
    def _symbol_group_key(symbol: str) -> str:
        s = str(symbol or "").upper()
        if "BTC" in s:
            return "BTC"
        if "ETH" in s:
            return "ETH"
        if "SOL" in s:
            return "SOL"
        if "BNB" in s:
            return "BNB"
        return "ALT"

    @staticmethod
    def _market_session_key(ts: Any = None) -> str:
        """将时间映射到交易时段（按 UTC 小时简化分桶）。"""
        try:
            if isinstance(ts, datetime):
                hour = int(ts.hour)
            else:
                s = str(ts or "").strip()
                if s.endswith("Z"):
                    s = s.replace("Z", "+00:00")
                dt = datetime.fromisoformat(s) if s else datetime.utcnow()
                hour = int(dt.hour)
        except Exception:
            hour = int(datetime.utcnow().hour)

        if 0 <= hour < 8:
            return "ASIA"
        if 8 <= hour < 16:
            return "EU"
        return "US"

    async def _run_research_pipeline(self) -> None:
        pipeline = None
        if self.main_controller and hasattr(self.main_controller, "strategy_research_pipeline"):
            pipeline = self.main_controller.strategy_research_pipeline
        if not pipeline or not self.authorization.get("auto_strategy"):
            return
        if not bool(self.config.get("research_enabled", True)):
            return
        try:
            now = datetime.utcnow()
            cooldown = int(self.config.get("research_cooldown_seconds", 21600) or 21600)
            if self._last_research_at and cooldown > 0:
                elapsed = (now - self._last_research_at).total_seconds()
                if elapsed < cooldown:
                    logger.debug("跳过策略研究：冷却中（剩余 %.0fs）", cooldown - elapsed)
                    return

            symbols = self.config.get("symbols", ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"])
            max_symbols = max(1, int(self.config.get("research_max_symbols", 2) or 2))
            lookback_days = max(7, int(self.config.get("research_lookback_days", 20) or 20))
            timeout_sec = max(60, int(self.config.get("research_timeout_seconds", 240) or 240))

            # 优先在非繁忙状态运行自动研究；有持仓时跳过（请用手动 /modules/strategy/research-run）
            busy = len(getattr(self, "_active_positions", {}) or {}) > 0
            if busy:
                logger.info("跳过自动策略研究：当前有活动持仓（可用手动 research-run 接口）")
                return

            result = await asyncio.wait_for(
                pipeline.run_cycle(
                    symbols=symbols[:max_symbols],
                    timeframe="1h",
                    lookback_days=lookback_days,
                ),
                timeout=timeout_sec,
            )
            self._last_research_at = now
            if result.get("published"):
                logger.info(f"✅ 策略研究发布 {len(result['published'])} 个策略")
        except asyncio.TimeoutError:
            logger.warning("策略研究流水线超时，已跳过本轮以保障主服务稳定")
        except Exception as e:
            logger.warning(f"策略研究流水线执行失败: {e}")
    
    async def _analyze_trade_and_update_strategy(self, decision: TradeDecision, result: Dict) -> None:
        """交易后分析并更新策略 - 每次交易后调用"""
        logger.info(f"📊 AI开始交易后分析: {decision.symbol}")
        
        try:
            # 1. 分析交易结果
            trade_analysis = {
                "symbol": decision.symbol,
                "action": decision.action,
                "side": decision.side,
                "entry_price": decision.entry_price,
                "quantity": decision.quantity,
                "leverage": decision.leverage,
                "reasoning": decision.reasoning,
                "strategy_used": decision.strategy_used,
                "result": result,
                "timestamp": datetime.now().isoformat(),
            }
            
            # 2. 保存交易分析到记忆
            if self.memory:
                try:
                    await self.memory.add_memory(
                        memory_type="decision",
                        content=f"交易分析: {decision.symbol} {decision.action} {decision.side} - {decision.reasoning}",
                        summary=f"📊 交易复盘: {decision.symbol} {decision.side}",
                        metadata=base_metadata(
                            source_module="ai_core_decision_engine",
                            kind="trade_post_analysis",
                            symbol=trade_analysis.get("symbol"),
                            extra=trade_analysis,
                        ),
                        importance=0.85,
                        source_module="ai_core_decision_engine",
                        tags=tags(
                            kind_tag("trade_analysis"),
                            kind_tag("post_trade"),
                            symbol_tag(trade_analysis.get("symbol")),
                            extra=["module:ai_core_decision_engine"],
                        ),
                    )
                    logger.info("💾 交易分析已保存到记忆库")
                except Exception as e:
                    logger.error(f"保存交易分析失败: {e}")
            
            # 3. 如果使用了策略，更新策略表现
            if decision.strategy_used and self.strategy_manager:
                await self._update_strategy_performance(decision.strategy_used, trade_analysis)
            
            # 4. 学习并优化
            await self._learn_from_trade(trade_analysis)
            
            logger.info(f"✅ 交易后分析完成: {decision.symbol}")
            
        except Exception as e:
            logger.error(f"交易后分析失败: {e}")
    
    async def _update_strategy_performance(self, strategy_id: str, trade_analysis: Dict) -> None:
        """更新策略表现记录"""
        if strategy_id not in self._strategy_performance:
            self._strategy_performance[strategy_id] = {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "total_pnl": 0,
                "trades": []
            }
        
        perf = self._strategy_performance[strategy_id]
        perf.setdefault("total_trades", 0)
        perf.setdefault("wins", 0)
        perf.setdefault("losses", 0)
        perf.setdefault("total_pnl", 0.0)
        perf.setdefault("trades", [])
        perf["total_trades"] += 1
        perf["trades"].append(trade_analysis)
        res = trade_analysis.get("result") if isinstance(trade_analysis, dict) else None
        if isinstance(res, dict) and res.get("pnl") is not None:
            try:
                pnl_f = float(res["pnl"])
                if pnl_f > 0:
                    perf["wins"] += 1
                elif pnl_f < 0:
                    perf["losses"] += 1
                perf["total_pnl"] = float(perf.get("total_pnl", 0) or 0) + pnl_f
            except (TypeError, ValueError):
                pass
        
        # 只保留最近50笔交易
        if len(perf["trades"]) > 50:
            perf["trades"] = perf["trades"][-50:]
        
        logger.info(f"📊 更新策略表现: {strategy_id} (总交易: {perf['total_trades']})")
    
    async def _learn_from_trade(self, trade_analysis: Dict) -> None:
        """从交易中学习"""
        if not self.llm:
            return
        
        try:
            # 构建学习prompt
            prompt = f"""分析以下交易，总结经验教训：

交易详情:
- 交易对: {trade_analysis['symbol']}
- 操作: {trade_analysis['action']} {trade_analysis['side']}
- 价格: {trade_analysis['entry_price']}
- 数量: {trade_analysis['quantity']}张
- 杠杆: {trade_analysis['leverage']}x
- 理由: {trade_analysis['reasoning']}
- 使用策略: {trade_analysis['strategy_used']}

请总结:
1. 这次交易的决策是否合理？
2. 有什么可以改进的地方？
3. 对未来类似情况有什么建议？

用简洁的中文回答，不超过100字。"""

            response = await self.llm.generate(prompt, is_user_input=False)
            
            if response and self.memory:
                await self.memory.add_memory(
                    memory_type="decision",
                    content=f"交易经验: {trade_analysis['symbol']} - {response.content[:200]}",
                    summary=f"💡 交易经验总结: {trade_analysis['symbol']}",
                    metadata=trade_analysis,
                    importance=0.75,
                    source_module="ai_core_decision_engine",
                    tags=["trade_experience", "learning"]
                )
                logger.info("📚 AI从交易中学习并保存经验")
                
        except Exception as e:
            logger.error(f"学习失败: {e}")
    
    async def _check_and_optimize_underperforming_strategies(self) -> None:
        """检查并优化表现不佳的策略"""
        for strategy_id, perf in self._strategy_performance.items():
            if not isinstance(perf, dict):
                continue
            total = int(perf.get("total_trades", perf.get("trade_count", 0)) or 0)
            if total < 5:
                continue
            wr = perf.get("win_rate")
            if wr is not None:
                try:
                    win_rate = float(wr)
                except (TypeError, ValueError):
                    win_rate = 0.0
            else:
                wins = int(perf.get("wins", 0) or 0)
                win_rate = wins / total if total > 0 else 0.0
            if win_rate < 0.4:
                logger.info(f"🔧 策略 {strategy_id} 胜率过低 ({win_rate:.1%})，需要优化")
                await self._optimize_strategy(strategy_id)
    
    async def _learn_from_memory(self) -> None:
        """从记忆系统学习历史经验"""
        if not self.memory:
            return
        
        try:
            from src.modules.memory.memory_context_policy import get_effective_context_policy

            cfg_mgr = (
                getattr(self.main_controller, "config_manager", None)
                if self.main_controller
                else None
            )
            der = get_effective_context_policy(cfg_mgr).get("decision_engine_recall") or {}
            te_limit = int(der.get("trade_experience_limit", 12))
            sp_limit = int(der.get("strategy_performance_limit", 6))
            lq = str(der.get("lesson_query", "经验教训 止损 止盈 滑点"))
            ll = int(der.get("lesson_limit", 8))

            # 获取交易经验
            trade_experiences = await self.memory.retrieve_memories(
                query="交易 经验 教训 开平仓 止损 止盈 滑点",
                min_importance=0.65,
                limit=te_limit,
            )

            lesson_pack = await self.memory.retrieve_memories(
                query=lq,
                min_importance=0.55,
                limit=ll,
            )
            
            if trade_experiences:
                logger.info(f"📚 AI从记忆中学习到 {len(trade_experiences)} 条经验")
                
                # 分析经验，提取有效策略
                for exp in trade_experiences[:3]:
                    logger.info(f"   - 经验: {exp.content[:100]}...")
            if lesson_pack:
                logger.info(f"📒 定向经验教训召回 {len(lesson_pack)} 条（决策引擎）")

            # 获取策略表现
            strategy_performance = await self.memory.retrieve_memories(
                query="策略 回测 表现 收益",
                min_importance=0.6,
                limit=sp_limit,
            )
            
            if strategy_performance:
                logger.info(f"📊 AI获取到 {len(strategy_performance)} 条策略表现记录")
                
        except Exception as e:
            logger.error(f"从记忆学习失败: {e}")
    
    async def _risk_monitoring_loop(self) -> None:
        """AI风险监控循环 - 忽略黑名单币种风险"""
        while self._running:
            try:
                await asyncio.sleep(SLEEP_30S)
                
                if not self.risk_monitor:
                    continue
                
                risk_data = await self.risk_monitor.check_account_risk()
                
                if hasattr(risk_data, 'risk_level') and risk_data.risk_level.value in ['high', 'critical']:
                    # 获取所有持仓，检查风险是否来自黑名单币种
                    if self.exchange:
                        try:
                            positions = await self.exchange.get_positions()
                            non_blacklist_risk = False
                            
                            for pos in positions:
                                symbol = pos.get('instId', '')
                                pnl_ratio = float(pos.get('uplRatio', 0))
                                
                                logger.info(f"📊 检查持仓风险: {symbol}, 盈亏比例: {pnl_ratio:.2%}")
                                
                                # 检查是否在黑名单中
                                in_blacklist = False
                                for bl in self.blacklist:
                                    if bl in symbol or symbol in bl:
                                        in_blacklist = True
                                        break
                                
                                logger.debug(f"📋 {symbol} 黑名单状态: {in_blacklist}, 黑名单: {list(self.blacklist)}")
                                
                                # 如果是非黑名单币种且亏损严重，才处理
                                if not in_blacklist and pnl_ratio < -0.1:
                                    non_blacklist_risk = True
                                    logger.warning(f"🚨 非黑名单币种风险: {symbol} 亏损 {pnl_ratio:.2%}")
                            
                            logger.info(f"📊 风险检查结果: non_blacklist_risk={non_blacklist_risk}, 持仓数={len(positions)}")
                            
                            # 只有非黑名单币种有风险才处理
                            if non_blacklist_risk:
                                await self._handle_high_risk(risk_data)
                            else:
                                if self.blacklist:
                                    logger.info("📋 当前未发现非黑名单高风险持仓，维持监控")
                                else:
                                    logger.info("📋 当前未发现高风险持仓，维持监控")
                                
                        except Exception as e:
                            logger.error(f"检查持仓风险失败: {e}")
                
            except Exception as e:
                logger.error(f"风险监控循环错误: {e}")
                await asyncio.sleep(SLEEP_30S)
    
    async def _s1_close_swap(
        self,
        symbol: str,
        side: str,
        size: Optional[float],
        source: str,
        reason: str,
    ) -> Dict[str, Any]:
        """
        S1 平仓：优先 ExecutionGateway（尊重 single_write_owner / 辅助来源规则），
        无 Gateway 时再走交易所 close_swap_position / close_position。
        """
        mc = getattr(self, "main_controller", None)
        gw = getattr(mc, "execution_gateway", None) if mc else None
        if gw:
            return await gw.close_swap(symbol, side, size, source, reason)
        if not self.exchange:
            return {"success": False, "error": "no_exchange"}
        try:
            close_fn = getattr(self.exchange, "close_swap_position", None) or getattr(
                self.exchange, "close_position", None
            )
            if callable(close_fn):
                res = await close_fn(symbol, side, size)
                if isinstance(res, dict):
                    return res
                return {"success": bool(res), "raw": res}
        except Exception as e:
            logger.exception("S1 直连平仓异常: %s", e)
            return {"success": False, "error": str(e)}
        return {"success": False, "error": "no_close_method"}
    
    async def _handle_high_risk(self, risk_data) -> None:
        """高风险扫描：仅告警与建议，不直接平仓（平仓入口限于主决策/SLTP/用户）。"""
        logger.warning(f"🚨 AI检测到高风险: {risk_data.risk_level.value}")
        
        if not self.exchange:
            logger.warning("交易所未连接，无法处理高风险")
            return
        
        try:
            positions = await self.exchange.get_positions()
            logger.info(f"📋 AI检查 {len(positions)} 个持仓")
            
            for pos in positions:
                symbol = pos.get('instId', '')
                pnl_ratio = float(pos.get('uplRatio', 0))
                pos_side = pos.get('posSide', 'long')
                
                if pnl_ratio < -0.1:
                    logger.warning(
                        "🚨 高风险持仓建议关注 %s 亏损 %s（未自动平仓，请主链路或用户处理）",
                        symbol,
                        f"{pnl_ratio:.2%}",
                    )
                    msg = (
                        f"高风险持仓建议: {symbol} {pos_side} 未实现盈亏比例 {pnl_ratio:.2%}。"
                        "未执行平仓；请主 AI 决策、止盈止损或用户 API。"
                    )
                    mc = self.main_controller
                    try:
                        if mc and hasattr(mc, "_send_notification_handler"):
                            await mc._send_notification_handler(
                                "高风险持仓（建议）", msg, priority="high"
                            )
                    except Exception as e:
                        logger.debug("high risk notify: %s", e)
                    if self.telegram_bot and self.telegram_bot.chat_ids:
                        try:
                            await self.telegram_bot.send_message(
                                chat_id=self.telegram_bot.chat_ids[0],
                                text=f"⚠️ {msg}",
                            )
                        except Exception as e:
                            logger.debug("telegram high risk: %s", e)
                        
        except Exception as e:
            logger.error(f"AI风险处理失败: {e}")
    
    async def _auto_generate_strategies(self) -> None:
        """AI自动生成策略 - 根据市场情况动态生成"""
        if not self.llm or not self.strategy_manager:
            return
        
        try:
            strategies = getattr(self.strategy_manager, 'strategy_configs', {})
            
            # AI根据市场情况决定是否需要生成新策略
            market_overview = await self._get_market_overview()
            
            # 获取当前市场状态
            should_generate = await self._should_generate_new_strategy(market_overview, strategies)
            
            if should_generate:
                logger.info("📊 AI开始生成新策略...")
                
                proposal = await self._ai_generate_strategy_proposal(market_overview)
                
                if proposal:
                    # 过滤黑名单交易对
                    proposal.symbols = [s for s in proposal.symbols if s not in self.blacklist]
                    
                    if proposal.symbols:  # 确保有可交易的币对
                        success = await self._create_strategy_from_proposal(proposal)
                        if success:
                            logger.info(f"✅ AI成功创建策略: {proposal.name}")
                            
                            if self.telegram_bot and self.telegram_bot.chat_ids:
                                await self.telegram_bot.send_message(
                                    chat_id=self.telegram_bot.chat_ids[0],
                                    text=f"📊 AI自主创建策略\n\n名称: {proposal.name}\n类型: {proposal.strategy_type}\n交易对: {', '.join(proposal.symbols)}\n\n理由: {proposal.reasoning}"
                                )
            
            # 检查是否需要组合策略
            if len(strategies) >= 2:
                await self._try_combine_strategies(strategies, market_overview)
                
        except Exception as e:
            logger.error(f"AI策略生成失败: {e}")
    
    async def _should_generate_new_strategy(self, market_overview: Dict, existing_strategies: Dict) -> bool:
        """判断是否需要生成新策略"""
        # 如果没有策略，需要生成
        if not existing_strategies:
            return True
        
        # 如果市场有重大变化，需要生成新策略
        for symbol, data in market_overview.items():
            change_24h = abs(data.get('change_24h', 0))
            if change_24h > 0.05:  # 24小时涨跌超过5%
                return True
        
        # 定期生成新策略（保持策略多样性）
        import random
        return random.random() < 0.1  # 10%概率生成新策略
    
    async def _try_combine_strategies(self, strategies: Dict, market_overview: Dict) -> None:
        """尝试组合策略"""
        try:
            # 检查是否有互补的策略可以组合
            strategy_types = set()
            for sid, config in strategies.items():
                strategy_type = getattr(config, 'strategy_type', None)
                if strategy_type:
                    strategy_types.add(strategy_type.value if hasattr(strategy_type, 'value') else str(strategy_type))
            
            # 如果有多种不同类型的策略，考虑组合
            if len(strategy_types) >= 2:
                # 检查是否已有组合策略
                has_combined = any('combined' in sid or 'combination' in sid for sid in strategies.keys())
                
                if not has_combined and hasattr(self.strategy_manager, 'combine_strategies'):
                    strategy_ids = list(strategies.keys())[:3]  # 最多组合3个策略
                    combined_id = await self.strategy_manager.combine_strategies(strategy_ids)
                    if combined_id:
                        logger.info(f"✅ AI组合策略成功: {combined_id}")
                        
        except Exception as e:
            logger.debug(f"策略组合检查失败: {e}")
    
    async def _get_market_overview(self) -> Dict:
        """获取市场概览 - AI自由选择交易币对"""
        overview = {}
        
        if not self.exchange:
            return overview
        
        try:
            # 获取交易所支持的所有交易对
            all_symbols = []
            if hasattr(self.exchange, 'get_symbols'):
                try:
                    all_symbols = await self.exchange.get_symbols()
                except Exception as e:
                    logger.debug(f"获取交易对列表失败，使用默认交易对: {e}")
            
            # 如果无法获取所有交易对，使用主流交易对
            if not all_symbols:
                all_symbols = [
                    "BTC/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
                    "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "DOT/USDT",
                    "MATIC/USDT", "LINK/USDT", "ATOM/USDT", "LTC/USDT"
                ]
            
            # 过滤掉黑名单中的交易对
            tradeable_symbols = [s for s in all_symbols if s not in self.blacklist and '/USDT' in s]
            
            # 获取这些交易对的行情数据
            for symbol in tradeable_symbols[:20]:  # 最多获取20个交易对
                try:
                    ticker = await self.exchange.get_ticker(symbol.replace('/', '-'))
                    if ticker:
                        overview[symbol] = {
                            "price": ticker.get('last', 0),
                            "change_24h": ticker.get('change', 0),
                            "volume": ticker.get('volume', 0),
                        }
                except Exception as e:
                    logger.debug(f"获取市场概览行情失败 {symbol}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"获取市场概览失败: {e}")
        
        return overview
    
    async def _ai_generate_strategy_proposal(self, market_overview: Dict) -> Optional[StrategyProposal]:
        """AI生成策略提案"""
        if not self.llm:
            return None
        
        try:
            prompt = f"""你是一个专业的量化交易策略设计师。根据当前市场情况，设计一个新的交易策略。

【当前市场情况】
{json.dumps(market_overview, indent=2, ensure_ascii=False)}

【已有策略】
{len(getattr(self.strategy_manager, 'strategy_configs', {}))}个

【用户规则】
- 黑名单: {list(self.blacklist)}
- 杠杆范围: {self.config['leverage_min']}-{self.config['leverage_max']}x

请设计一个策略，返回JSON格式：
{{
    "name": "策略名称",
    "strategy_type": "trend_following/mean_reversion/grid_trading/ml_based",
    "parameters": {{
        "entry_conditions": "入场条件描述",
        "exit_conditions": "出场条件描述",
        "stop_loss_pct": 止损百分比,
        "take_profit_pct": 止盈百分比,
        "leverage": 杠杆倍数
    }},
    "symbols": ["BTC/USDT"],
    "timeframe": "1h/4h/1d",
    "reasoning": "设计理由",
    "expected_return": 预期年化收益率,
    "risk_level": "low/medium/high"
}}

只返回JSON。"""

            response = await self.llm.generate(prompt, is_user_input=False)
            
            if not response:
                return None
            
            json_match = None
            json_pattern = r'\{[^{}]*\}'
            matches = re.findall(json_pattern, response.content, re.DOTALL)
            if matches:
                json_match = matches[-1]
            
            if not json_match:
                return None
            
            data = json.loads(json_match)
            
            return StrategyProposal(
                name=data.get('name', 'AI Generated Strategy'),
                strategy_type=data.get('strategy_type', 'trend_following'),
                parameters=data.get('parameters', {}),
                symbols=data.get('symbols', ['BTC/USDT']),
                timeframe=data.get('timeframe', '1h'),
                reasoning=data.get('reasoning', ''),
                expected_return=data.get('expected_return', 0.2),
                risk_level=data.get('risk_level', 'medium')
            )
            
        except Exception as e:
            logger.error(f"AI生成策略提案失败: {e}")
            return None
    
    async def _create_strategy_from_proposal(self, proposal: StrategyProposal) -> bool:
        """从提案创建策略"""
        if not self.strategy_manager:
            return False
        
        try:
            strategy_config = {
                "strategy_id": f"ai_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "name": proposal.name,
                "description": f"AI自主生成 - {proposal.reasoning}",
                "strategy_type": proposal.strategy_type,
                "parameters": proposal.parameters,
                "symbols": [s for s in proposal.symbols if s not in self.blacklist],
                "timeframe": proposal.timeframe,
                "initial_capital": 10000.0,
                "enabled": True,
            }
            
            if hasattr(self.strategy_manager, 'load_strategy_config'):
                await self.strategy_manager.load_strategy_config(strategy_config)
            
            self._active_strategies[strategy_config['strategy_id']] = strategy_config
            
            await self._save_strategy_to_memory(strategy_config, proposal)
            
            return True
            
        except Exception as e:
            logger.error(f"创建策略失败: {e}")
            return False
    
    async def _save_strategy_to_memory(self, config: Dict, proposal: StrategyProposal) -> None:
        """保存策略到记忆"""
        if not self.memory:
            return
        
        try:
            await self.memory.add_memory(
                memory_type="decision",
                content=f"AI生成策略: {config['name']} - {proposal.reasoning}",
                summary=f"📊 AI策略: {config['name']} ({config['strategy_type']})",
                metadata={
                    "strategy_id": config['strategy_id'],
                    "name": config['name'],
                    "type": config['strategy_type'],
                    "symbols": config['symbols'],
                    "parameters": config['parameters'],
                },
                importance=0.9,
                source_module="ai_core_decision_engine",
                tags=["ai_strategy", "auto_generated"]
            )
        except Exception as e:
            logger.error(f"保存策略到记忆失败: {e}")
    
    async def _auto_backtest_strategies(self) -> None:
        """AI自动回测策略"""
        if not self.backtester or not self.authorization.get("auto_backtest"):
            return
        
        try:
            strategies = getattr(self.strategy_manager, 'strategy_configs', {})
            
            for strategy_id, config in strategies.items():
                if strategy_id not in self._strategy_performance:
                    logger.info(f"📈 AI开始回测策略: {getattr(config, 'name', strategy_id)}")
                    
                    result = await self._run_backtest(strategy_id)
                    
                    if result:
                        # 回测结果含 trade_count 等字段；与实盘统计字典并存，避免缺少 total_trades/trades 导致 KeyError
                        self._strategy_performance[strategy_id] = {
                            "total_trades": 0,
                            "wins": 0,
                            "losses": 0,
                            "total_pnl": 0.0,
                            "trades": [],
                            **result,
                        }
                        logger.info(f"✅ 回测完成: {result.get('total_return', 0):.2%} 收益")
        
        except Exception as e:
            logger.error(f"AI回测策略失败: {e}")
    
    async def _run_backtest(self, strategy_id: str) -> Optional[Dict]:
        """运行回测"""
        if not self.backtester or not self.exchange:
            return None
        
        try:
            strategies = getattr(self.strategy_manager, 'strategy_configs', {})
            config = strategies.get(strategy_id)
            
            if not config:
                return None
            
            symbols = getattr(config, 'symbols', [])
            if not symbols:
                return None
            
            symbol = symbols[0].replace('/', '-')
            
            klines = await self.exchange.get_klines(symbol, '1H', limit=720)
            
            if not klines:
                return None

            closes = self._extract_close_prices(klines)
            if len(closes) < 80:
                logger.warning(f"回测样本不足: {strategy_id} close_count={len(closes)}")
                return None

            params = self._resolve_strategy_ma_params(config)
            metrics = self._simulate_ma_backtest(closes, params["fast"], params["slow"])

            return {
                "strategy_id": strategy_id,
                "symbol": symbol,
                "timeframe": "1H",
                "samples": len(closes),
                "total_return": metrics["total_return"],
                "max_drawdown": metrics["max_drawdown"],
                "win_rate": metrics["win_rate"],
                "sharpe_ratio": metrics["sharpe_ratio"],
                "trade_count": metrics["trade_count"],
                "parameters": params,
                "backtest_date": datetime.now().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"回测失败: {e}")
            return None
    
    async def _auto_optimize_strategies(self) -> None:
        """AI自动优化策略"""
        if not self.parameter_optimizer or not self.authorization.get("auto_optimize"):
            return
        
        try:
            for strategy_id, performance in self._strategy_performance.items():
                if performance.get('sharpe_ratio', 0) < 1.0:
                    logger.info(f"🔧 AI开始优化策略: {strategy_id}")
                    
                    result = await self._optimize_strategy(strategy_id)
                    
                    if result:
                        logger.info(f"✅ 策略优化完成: {result}")
        
        except Exception as e:
            logger.error(f"AI优化策略失败: {e}")
    
    async def _optimize_strategy(self, strategy_id: str) -> Optional[Dict]:
        """优化策略参数"""
        if not self.parameter_optimizer:
            return None
        
        try:
            if not self.exchange or not self.strategy_manager:
                return None

            strategies = getattr(self.strategy_manager, 'strategy_configs', {})
            config = strategies.get(strategy_id)
            if not config:
                return None

            symbols = getattr(config, 'symbols', [])
            if not symbols:
                return None

            symbol = symbols[0].replace('/', '-')
            klines = await self.exchange.get_klines(symbol, '1H', limit=720)
            closes = self._extract_close_prices(klines or [])
            if len(closes) < 120:
                logger.warning(f"策略优化样本不足: {strategy_id} close_count={len(closes)}")
                return None

            base_params = self._resolve_strategy_ma_params(config)
            base_metrics = self._simulate_ma_backtest(closes, base_params["fast"], base_params["slow"])

            fast_candidates = [6, 8, 10, 12, 16, 20, 24]
            slow_candidates = [30, 40, 50, 60, 72, 84, 100]
            drawdown_limit = float(self.config.get("max_drawdown_limit", 0.15))

            best = None
            for fast in fast_candidates:
                for slow in slow_candidates:
                    if fast >= slow:
                        continue
                    metrics = self._simulate_ma_backtest(closes, fast, slow)
                    # Score balances risk-adjusted return and drawdown.
                    score = (
                        metrics["sharpe_ratio"] * 1.2
                        + metrics["total_return"] * 0.8
                        - metrics["max_drawdown"] * 1.0
                    )
                    if metrics["trade_count"] < 4:
                        score -= 0.2
                    candidate = {
                        "fast": fast,
                        "slow": slow,
                        "metrics": metrics,
                        "score": score,
                    }
                    if metrics["max_drawdown"] <= drawdown_limit:
                        if best is None or candidate["score"] > best["score"]:
                            best = candidate

            # If no candidate satisfies drawdown limit, fallback to global best score.
            if best is None:
                for fast in fast_candidates:
                    for slow in slow_candidates:
                        if fast >= slow:
                            continue
                        metrics = self._simulate_ma_backtest(closes, fast, slow)
                        score = (
                            metrics["sharpe_ratio"] * 1.2
                            + metrics["total_return"] * 0.8
                            - metrics["max_drawdown"] * 1.0
                        )
                        if metrics["trade_count"] < 4:
                            score -= 0.2
                        candidate = {"fast": fast, "slow": slow, "metrics": metrics, "score": score}
                        if best is None or candidate["score"] > best["score"]:
                            best = candidate

            if not best:
                return None

            new_params = self._build_updated_strategy_params(config, best["fast"], best["slow"])
            if hasattr(config, "parameters") and isinstance(config.parameters, dict):
                config.parameters.update(new_params)
                config.updated_at = datetime.now()
                # bump strategy version for audit/versioning linkage
                if hasattr(config, "version"):
                    try:
                        from src.modules.strategies.strategy_dsl import bump_version as _bump

                        config.version = _bump(getattr(config, "version", "1.0.0"))
                    except Exception:
                        pass

                # link optimization to audit + memory
                if self.main_controller and hasattr(self.main_controller, "log_audit_event"):
                    try:
                        from src.modules.core.audit_logger import AuditEventType, AuditSeverity

                        await self.main_controller.log_audit_event(
                            event_type=AuditEventType.CONFIG_CHANGE,
                            severity=AuditSeverity.INFO,
                            action="strategy_optimize",
                            details={
                                "strategy_id": strategy_id,
                                "version": getattr(config, "version", None),
                                "old_params": base_params,
                                "new_params": new_params,
                            },
                            source="ai_core_decision_engine",
                        )
                    except Exception:
                        pass
                if self.main_controller and hasattr(self.main_controller, "memory_gateway") and self.main_controller.memory_gateway:
                    try:
                        await self.main_controller.memory_gateway.add_memory(
                            memory_type="strategy",
                            content=f"优化策略 {strategy_id} v{getattr(config,'version',None)}: {base_params} -> {new_params}",
                            metadata={
                                "strategy_id": strategy_id,
                                "version": getattr(config, "version", None),
                                "old": base_params,
                                "new": new_params,
                            },
                            source_module="ai_core_decision_engine",
                            importance=0.8,
                            tags=["strategy", "optimize", "versioning"],
                        )
                    except Exception:
                        pass

            return {
                "strategy_id": strategy_id,
                "symbol": symbol,
                "old": {"parameters": base_params, "metrics": base_metrics},
                "new": {"parameters": new_params, "metrics": best["metrics"]},
                "improvement": {
                    "delta_sharpe": best["metrics"]["sharpe_ratio"] - base_metrics["sharpe_ratio"],
                    "delta_return": best["metrics"]["total_return"] - base_metrics["total_return"],
                    "delta_drawdown": best["metrics"]["max_drawdown"] - base_metrics["max_drawdown"],
                },
                "optimized_at": datetime.now().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"策略优化失败: {e}")
            return None

    def _extract_close_prices(self, klines: List[Any]) -> List[float]:
        """Normalize exchange kline payload to close-price list."""
        closes: List[float] = []
        for k in klines:
            close_val = None
            if isinstance(k, dict):
                close_val = k.get("close") or k.get("c")
            elif isinstance(k, (list, tuple)) and len(k) >= 5:
                close_val = k[4]
            try:
                if close_val is not None:
                    closes.append(float(close_val))
            except (TypeError, ValueError):
                continue
        return closes

    def _resolve_strategy_ma_params(self, strategy_config: Any) -> Dict[str, int]:
        """Read MA-like parameters from strategy config with sane defaults."""
        params = {}
        if hasattr(strategy_config, "parameters") and isinstance(strategy_config.parameters, dict):
            params = strategy_config.parameters
        elif isinstance(strategy_config, dict):
            params = strategy_config.get("parameters", {})
        fast = int(
            params.get("ma_fast")
            or params.get("short_window")
            or params.get("fast_period")
            or 12
        )
        slow = int(
            params.get("ma_slow")
            or params.get("long_window")
            or params.get("slow_period")
            or 48
        )
        if fast >= slow:
            fast = max(6, slow // 4)
            slow = max(fast + 4, slow)
        return {"fast": fast, "slow": slow}

    def _build_updated_strategy_params(self, strategy_config: Any, fast: int, slow: int) -> Dict[str, Any]:
        """Write optimized MA params back using existing key style."""
        params = {}
        if hasattr(strategy_config, "parameters") and isinstance(strategy_config.parameters, dict):
            params = strategy_config.parameters
        elif isinstance(strategy_config, dict):
            params = strategy_config.get("parameters", {})

        updated: Dict[str, Any] = {}
        if "short_window" in params or "long_window" in params:
            updated["short_window"] = fast
            updated["long_window"] = slow
        if "fast_period" in params or "slow_period" in params:
            updated["fast_period"] = fast
            updated["slow_period"] = slow
        if "ma_fast" in params or "ma_slow" in params:
            updated["ma_fast"] = fast
            updated["ma_slow"] = slow

        if not updated:
            updated["short_window"] = fast
            updated["long_window"] = slow
        return updated

    def _simulate_ma_backtest(self, closes: List[float], fast: int, slow: int) -> Dict[str, float]:
        """Simple deterministic MA crossover simulation on close prices."""
        if len(closes) <= slow + 2:
            return {
                "total_return": 0.0,
                "max_drawdown": 1.0,
                "win_rate": 0.0,
                "sharpe_ratio": -1.0,
                "trade_count": 0,
            }

        equity = 1.0
        peak = 1.0
        max_drawdown = 0.0
        period_returns: List[float] = []
        trade_returns: List[float] = []
        last_signal = 0
        current_trade_ret = 0.0

        for i in range(slow, len(closes)):
            fast_ma = sum(closes[i - fast + 1 : i + 1]) / fast
            slow_ma = sum(closes[i - slow + 1 : i + 1]) / slow
            signal = 1 if fast_ma > slow_ma else -1

            prev_close = closes[i - 1]
            cur_close = closes[i]
            if prev_close <= 0:
                continue
            raw_ret = (cur_close - prev_close) / prev_close
            strat_ret = raw_ret * signal
            period_returns.append(strat_ret)
            equity *= (1.0 + strat_ret)
            peak = max(peak, equity)
            if peak > 0:
                max_drawdown = max(max_drawdown, (peak - equity) / peak)

            if last_signal == 0:
                last_signal = signal
                current_trade_ret = 0.0
            elif signal != last_signal:
                trade_returns.append(current_trade_ret)
                current_trade_ret = 0.0
                last_signal = signal
            current_trade_ret += strat_ret

        if current_trade_ret != 0.0:
            trade_returns.append(current_trade_ret)

        total_return = equity - 1.0
        trade_count = len(trade_returns)
        win_count = len([r for r in trade_returns if r > 0])
        win_rate = (win_count / trade_count) if trade_count > 0 else 0.0

        if len(period_returns) > 1:
            mean_r = sum(period_returns) / len(period_returns)
            var = sum((r - mean_r) ** 2 for r in period_returns) / max(1, len(period_returns) - 1)
            std_r = math.sqrt(var)
            if std_r > 1e-12:
                sharpe_ratio = (mean_r / std_r) * math.sqrt(24 * 365)
            else:
                sharpe_ratio = 0.0
        else:
            sharpe_ratio = 0.0

        return {
            "total_return": float(total_return),
            "max_drawdown": float(max_drawdown),
            "win_rate": float(win_rate),
            "sharpe_ratio": float(sharpe_ratio),
            "trade_count": int(trade_count),
        }
    
    async def _ai_analyze_and_decide(self, symbol: str) -> Optional[TradeDecision]:
        """AI分析市场并做出决策 - 使用所有模块数据，全部实时获取"""
        logger.info(f"🧠 AI分析 {symbol}...")
        
        if not self.llm:
            logger.warning("LLM未连接，无法进行AI决策")
            return None
        
        try:
            await self._refresh_runtime_guard_config()
            # 1. 获取市场数据 - 实时
            market_data = await self._get_market_data(symbol)
            logger.info(f"   ✅ 市场数据: 价格={market_data.get('price', 0)}")
            
            # 2. 获取技术指标 - 多周期K线，实时
            technical = await self._get_technical_indicators(symbol)
            logger.info(f"   ✅ 技术指标: RSI(1H)={technical.get('rsi_1h', 0):.1f}, 趋势(1H)={technical.get('trend_1h', 'unknown')}, 趋势(4H)={technical.get('trend_4h', 'unknown')}, 趋势(1D)={technical.get('trend_1d', 'unknown')}")
            
            # 3. 获取策略建议
            strategy_advice = await self._get_strategy_advice(symbol)
            logger.info(f"   ✅ 策略建议: {strategy_advice.get('count', 0)}个策略可用")
            
            # 4. 获取风险评估 - 实时
            risk_assessment = await self._get_risk_assessment(symbol)
            logger.info(f"   ✅ 风险评估: 等级={risk_assessment.get('level', 'unknown')}")
            
            # 5. 获取当前持仓 - 实时
            current_positions = await self._get_current_positions()
            self._current_positions = {p.get('symbol'): p for p in current_positions if p.get('symbol')}
            logger.info(f"   ✅ 当前持仓: {len(current_positions)}个")
            
            # 6. 获取账户余额 - 实时
            account_balance = await self._get_account_balance()
            logger.info(f"   ✅ 账户余额: 可用={account_balance.get('available', 0):.2f} USDT")
            
            # 7. 获取第三方数据 - 实时
            third_party_data = await self._get_third_party_data(symbol)
            logger.info(f"   ✅ 第三方数据: 可用={third_party_data.get('available', False)}, 情绪={third_party_data.get('sentiment', 'neutral')}")
            
            # 8. 获取历史经验
            historical_experience = await self._get_historical_experience(symbol)
            
            # 9. 获取多源数据融合结果 - 实时
            multi_source_analysis = await self._get_multi_source_analysis(symbol)
            logger.info(f"   ✅ 多源数据融合: {multi_source_analysis.get('status', 'unknown')}")

            # 9.5 统一行情情报（只读）：供 prompt 与门控参考
            mi_view = None
            try:
                mi = getattr(self.main_controller, "market_intelligence", None) if self.main_controller else None
                if mi and hasattr(mi, "get_symbol_view"):
                    mi_view = await mi.get_symbol_view(symbol, include_snapshot=False)
            except Exception:
                mi_view = None
            
            # 10. 获取AI交易引擎分析 - 实时
            ai_engine_analysis = await self._get_ai_engine_analysis(symbol)
            logger.info(f"   ✅ AI引擎分析: {ai_engine_analysis.get('trend', 'unknown')}")

            # 10.5 数据质量门控：当多源数据明显退化且第三方不可用时，避免做出激进决策。
            quality_score = float(multi_source_analysis.get("quality_score", 0) or 0)
            degraded_count = int(multi_source_analysis.get("degraded_count", 0) or 0)
            third_party_available = bool(third_party_data.get("available", False))
            min_quality = float(self.config.get("min_data_quality_to_trade", 0.55) or 0.55)
            if quality_score < min_quality and (degraded_count > 0 or not third_party_available):
                self._execution_guards_stats["data_quality_guard_hold"] += 1
                logger.warning(
                    "⚠️ 数据质量门控触发: symbol=%s quality=%.2f degraded=%s third_party=%s",
                    symbol,
                    quality_score,
                    degraded_count,
                    third_party_available,
                )
                return TradeDecision(
                    symbol=symbol,
                    action="hold",
                    side="long",
                    quantity=0,
                    leverage=int(self.config.get("default_leverage", 1) or 1),
                    entry_price=float(market_data.get("price", 0) or 0),
                    stop_loss=0.0,
                    take_profit=0.0,
                    confidence=0.0,
                    reasoning=f"data_quality_guard: quality={quality_score:.2f} degraded={degraded_count} third_party={third_party_available}",
                    strategy_used="data_quality_guard",
                    risk_level=risk_assessment.get("level", "high"),
                )
            
            # 构建完整的决策prompt
            prompt = self._build_decision_prompt(
                symbol=symbol,
                market_data=market_data,
                technical=technical,
                strategy_advice=strategy_advice,
                risk_assessment=risk_assessment,
                current_positions=current_positions,
                account_balance=account_balance,
                third_party_data=third_party_data,
                historical_experience=historical_experience,
                multi_source_analysis=multi_source_analysis,
                ai_engine_analysis=ai_engine_analysis,
                market_intelligence=(mi_view.to_dict() if mi_view else None),
            )
            
            response = await self.llm.generate(prompt, is_user_input=False)
            
            if not response:
                logger.warning(f"AI未返回决策: {symbol}")
                return None
            
            decision = self._parse_ai_decision(response.content, symbol)

            # 兜底：LLM 可能过度保守长期返回 hold。
            # 在多源融合置信度高且技术趋势一致时，把 hold 变更为可执行的 buy/sell，
            # 交由后续 ExecutionGateway 统一走 S1 单写入所有权。
            if decision and decision.action == "hold" and bool(self.config.get("hold_avoidance_override_enabled", True)):
                try:
                    fusion_conf = float(multi_source_analysis.get("confidence", 0) or 0)
                    fusion_sent = multi_source_analysis.get("sentiment", 0)
                    strat_count = int(strategy_advice.get("count", 0) or 0)
                    risk_level = risk_assessment.get("level", "unknown")
                    tech_trend_1h = technical.get("trend_1h", "unknown")
                    min_conf = float(self.config.get("min_confidence_to_trade", 0.6))
                    min_abs_sent = float(self.config.get("hold_avoidance_override_min_abs_sentiment", 0.06) or 0.06)
                    mi_q_min = float(self.config.get("hold_avoidance_override_min_mi_quality_score", 0.62) or 0.62)
                    require_mi_align = bool(self.config.get("hold_avoidance_override_require_mi_trend_alignment", True))
                    cooldown = float(self.config.get("hold_avoidance_override_cooldown_sec", 1200) or 1200)

                    mi_trend = getattr(mi_view, "trend", None) if mi_view else None
                    mi_q = getattr(mi_view, "quality_score", None) if mi_view else None
                    mi_conf = getattr(mi_view, "confidence", None) if mi_view else None
                    try:
                        mi_qf = float(mi_q) if mi_q is not None else 0.0
                    except Exception:
                        mi_qf = 0.0

                    now = datetime.now()

                    if (
                        self.authorization.get("full_authorization")
                        and risk_level in ("low", "medium")
                        and strat_count > 0
                        and fusion_conf >= min_conf
                        and isinstance(fusion_sent, (int, float))
                        and abs(float(fusion_sent)) >= min_abs_sent
                        and mi_qf >= mi_q_min
                    ):
                        # rate limit per symbol-side
                        key = f"{symbol}:{'long' if float(fusion_sent) > 0 else 'short'}"
                        last = self._last_hold_override_at.get(key)
                        if last and (now - last).total_seconds() < cooldown:
                            raise RuntimeError("hold_avoidance_override cooldown")

                        if tech_trend_1h == "bearish" and fusion_sent < -0.05:
                            if require_mi_align and str(mi_trend or "").lower() not in ("bearish", "down", "short"):
                                raise RuntimeError("hold_avoidance_override mi trend mismatch")
                            decision.action = "sell"
                            decision.side = "short"
                            decision.quantity = max(1, int(decision.quantity or 1))
                            decision.leverage = int(self.config.get("default_leverage", 1) or 1)
                            decision.confidence = float(max(decision.confidence or 0, min(1.0, fusion_conf)))
                            decision.reasoning = (
                                f"hold_avoidance_override: fusion_conf={fusion_conf:.2f}, fusion_sent={fusion_sent:.3f}, "
                                f"tech_trend_1h=bearish"
                            )
                            decision.strategy_used = decision.strategy_used or "s1_fusion_override"
                            self._last_hold_override_at[key] = now
                        elif tech_trend_1h == "bullish" and fusion_sent > 0.05:
                            if require_mi_align and str(mi_trend or "").lower() not in ("bullish", "up", "long"):
                                raise RuntimeError("hold_avoidance_override mi trend mismatch")
                            decision.action = "buy"
                            decision.side = "long"
                            decision.quantity = max(1, int(decision.quantity or 1))
                            decision.leverage = int(self.config.get("default_leverage", 1) or 1)
                            decision.confidence = float(max(decision.confidence or 0, min(1.0, fusion_conf)))
                            decision.reasoning = (
                                f"hold_avoidance_override: fusion_conf={fusion_conf:.2f}, fusion_sent={fusion_sent:.3f}, "
                                f"tech_trend_1h=bullish"
                            )
                            decision.strategy_used = decision.strategy_used or "s1_fusion_override"
                            self._last_hold_override_at[key] = now
                except Exception as e:
                    logger.debug(f"hold override skipped: {e}")
            
            if decision:
                self._last_decision_time[symbol] = datetime.now()
                logger.info(f"✅ AI决策完成: {symbol} {decision.action} {decision.side}")
            
            return decision
            
        except Exception as e:
            logger.error(f"AI分析决策失败: {symbol} - {e}")
            return None
    
    async def _get_multi_source_analysis(self, symbol: str) -> Dict:
        """获取多源数据融合分析结果"""
        result = {"status": "unavailable"}
        
        if not self.main_controller:
            return result
        
        try:
            # 检查AI交易引擎中的多源数据融合
            if hasattr(self.main_controller, 'ai_trading_engine') and self.main_controller.ai_trading_engine:
                engine = self.main_controller.ai_trading_engine
                fusion = None
                # ai_trading_engine 里实际挂载的是 self.data_fusion（历史命名不一致）
                if hasattr(engine, 'multi_source_fusion') and engine.multi_source_fusion:
                    fusion = engine.multi_source_fusion
                elif hasattr(engine, 'data_fusion') and engine.data_fusion:
                    fusion = engine.data_fusion
                elif hasattr(engine, 'multi_source_data_fusion') and engine.multi_source_data_fusion:
                    fusion = engine.multi_source_data_fusion

                if fusion and hasattr(fusion, 'analyze_market'):
                    analysis = await fusion.analyze_market(symbol)
                    if analysis:
                        # fusion.analyze_market 目前返回 dict（而非对象属性）
                        if isinstance(analysis, dict):
                            sentiment = analysis.get("sentiment")
                            if sentiment is None:
                                sentiment = analysis.get("overall_sentiment", "neutral")
                            signal_strength = (
                                analysis.get("signal_strength")
                                if analysis.get("signal_strength") is not None
                                else analysis.get("confidence", 0)
                            )
                            result = {
                                "status": "available",
                                "sentiment": sentiment,
                                "signal_strength": signal_strength,
                                "recommendation": analysis.get("recommendation", "neutral"),
                                "confidence": analysis.get("confidence", 0),
                                "trend": analysis.get("trend", "unknown"),
                                "quality_score": analysis.get("quality_score", 0),
                                "degraded_sources": analysis.get("degraded_sources", []),
                                "degraded_count": len(analysis.get("degraded_sources", []) or []),
                            }
                        else:
                            result = {
                                "status": "available",
                                "sentiment": getattr(analysis, 'overall_sentiment', 'neutral'),
                                "signal_strength": getattr(analysis, 'signal_strength', 0),
                                "recommendation": getattr(analysis, 'recommendation', 'neutral'),
                                "confidence": getattr(analysis, 'confidence', 0),
                                "trend": getattr(analysis, 'trend', 'unknown'),
                            }
                        logger.info(f"📊 多源数据融合: {symbol} 情绪={result['sentiment']}, 信号强度={result['signal_strength']}")
                        return result
            
            # 备用：检查主控制器直接属性
            if hasattr(self.main_controller, 'multi_source_data_fusion') and self.main_controller.multi_source_data_fusion:
                fusion = self.main_controller.multi_source_data_fusion
                analysis = await fusion.analyze_market(symbol)
                if analysis:
                    if isinstance(analysis, dict):
                        sentiment = analysis.get("sentiment")
                        if sentiment is None:
                            sentiment = analysis.get("overall_sentiment", "neutral")
                        signal_strength = (
                            analysis.get("signal_strength")
                            if analysis.get("signal_strength") is not None
                            else analysis.get("confidence", 0)
                        )
                        result = {
                            "status": "available",
                            "sentiment": sentiment,
                            "signal_strength": signal_strength,
                            "recommendation": analysis.get("recommendation", "neutral"),
                            "confidence": analysis.get("confidence", 0),
                            "trend": analysis.get("trend", "unknown"),
                            "quality_score": analysis.get("quality_score", 0),
                            "degraded_sources": analysis.get("degraded_sources", []),
                            "degraded_count": len(analysis.get("degraded_sources", []) or []),
                        }
                    else:
                        result = {
                            "status": "available",
                            "sentiment": getattr(analysis, 'overall_sentiment', 'neutral'),
                            "signal_strength": getattr(analysis, 'signal_strength', 0),
                            "recommendation": getattr(analysis, 'recommendation', 'neutral'),
                            "confidence": getattr(analysis, 'confidence', 0),
                            "trend": getattr(analysis, 'trend', 'unknown'),
                        }
                    logger.info(f"📊 多源数据融合: {symbol} 情绪={result['sentiment']}")
                    
        except Exception as e:
            logger.error(f"获取多源数据融合失败: {e}")
        
        return result
    
    async def _get_ai_engine_analysis(self, symbol: str) -> Dict:
        """获取AI交易引擎分析结果"""
        result = {"trend": "unknown"}
        
        if not self.main_controller:
            return result
        
        try:
            # 检查AI交易引擎
            if hasattr(self.main_controller, 'ai_trading_engine') and self.main_controller.ai_trading_engine:
                engine = self.main_controller.ai_trading_engine
                # 获取引擎的最新分析结果
                if hasattr(engine, 'last_analysis_results'):
                    analysis = engine.last_analysis_results.get(symbol)
                    if analysis:
                        result = {
                            "trend": analysis.get('trend', 'unknown'),
                            "sentiment": analysis.get('sentiment', 'neutral'),
                            "signal_strength": analysis.get('signal_strength', 0),
                            "prediction": analysis.get('prediction', {}),
                        }
                        logger.info(f"🤖 AI引擎分析: {symbol} 趋势={result['trend']}")
                
                # 如果没有缓存结果，尝试获取市场分析
                if result["trend"] == "unknown" and hasattr(engine, 'analyze_market'):
                    analysis = await engine.analyze_market(symbol)
                    if analysis:
                        result = {
                            "trend": getattr(analysis, 'trend', 'unknown'),
                            "sentiment": getattr(analysis, 'sentiment', 'neutral'),
                            "signal_strength": getattr(analysis, 'signal_strength', 0),
                        }
                        logger.info(f"🤖 AI引擎分析: {symbol} 趋势={result['trend']}")
                
                # 兜底：ai_trading_engine 可能没有 analyze_market/last_analysis_results
                # 此时用 data_fusion 情绪映射 bullish/bearish，避免 prompt 缺失 AI 引擎趋势
                if result["trend"] == "unknown":
                    fusion = getattr(engine, "data_fusion", None)
                    if fusion and hasattr(fusion, "analyze_market"):
                        fusion_analysis = await fusion.analyze_market(symbol)
                        if isinstance(fusion_analysis, dict) and fusion_analysis:
                            sentiment = fusion_analysis.get("sentiment", "neutral")
                            signal_strength = (
                                fusion_analysis.get("signal_strength")
                                if fusion_analysis.get("signal_strength") is not None
                                else fusion_analysis.get("confidence", 0)
                            )

                            if isinstance(sentiment, (int, float)):
                                if sentiment > 0.05:
                                    trend = "bullish"
                                elif sentiment < -0.05:
                                    trend = "bearish"
                                else:
                                    trend = "neutral"
                            else:
                                trend = "neutral"
                                sentiment = "neutral"

                            result = {
                                "trend": trend,
                                "sentiment": sentiment,
                                "signal_strength": signal_strength,
                                "prediction": {},
                            }
                            logger.info(f"🤖 AI引擎分析(融合兜底): {symbol} 趋势={result['trend']}")
                        
        except Exception as e:
            logger.error(f"获取AI引擎分析失败: {e}")
        
        return result
    
    async def _get_historical_experience(self, symbol: str) -> str:
        """从记忆系统获取历史经验"""
        if not self.memory:
            return ""
        
        try:
            # 获取该币种的历史交易经验
            experiences = await self.memory.retrieve_memories(
                query=f"{symbol} 交易 盈利 亏损 经验",
                min_importance=0.6,
                limit=5
            )
            
            if experiences:
                exp_text = "\n".join([f"- {exp.content[:200]}" for exp in experiences[:3]])
                logger.info(f"📚 AI获取到 {symbol} 的历史经验")
                return f"\n【历史交易经验】\n{exp_text}"
            
        except Exception as e:
            logger.error(f"获取历史经验失败: {e}")
        
        return ""
    
    async def _get_market_data(self, symbol: str) -> Dict:
        """获取市场数据"""
        if not self.exchange:
            return {}
        
        try:
            ticker = await self.exchange.get_ticker(symbol.replace('/', '-'))
            return {
                "price": ticker.get('last', 0),
                "high": ticker.get('high', 0),
                "low": ticker.get('low', 0),
                "volume": ticker.get('volume', 0),
            }
        except Exception as e:
            logger.error(f"获取市场数据失败: {symbol} - {e}")
            return {}
    
    async def _get_technical_indicators(self, symbol: str) -> Dict:
        """获取技术指标 - 多周期K线数据"""
        if not self.exchange:
            return {}
        
        try:
            # 获取多个周期的K线数据
            klines_1h = await self.exchange.get_klines(symbol.replace('/', '-'), '1H', limit=100)
            klines_4h = await self.exchange.get_klines(symbol.replace('/', '-'), '4H', limit=50)
            klines_1d = await self.exchange.get_klines(symbol.replace('/', '-'), '1D', limit=30)
            
            if not klines_1h:
                return {}
            
            closes_1h = [k.get('close', 0) for k in klines_1h]
            closes_4h = [k.get('close', 0) for k in klines_4h] if klines_4h else closes_1h
            closes_1d = [k.get('close', 0) for k in klines_1d] if klines_1d else closes_1h
            
            def calculate_ma(closes, period):
                return sum(closes[-period:]) / period if len(closes) >= period else 0
            
            def calculate_rsi(closes, period=14):
                gains = []
                losses = []
                for i in range(1, min(period + 1, len(closes))):
                    change = closes[-i] - closes[-i-1]
                    if change > 0:
                        gains.append(change)
                    else:
                        losses.append(abs(change))
                
                if not gains or not losses:
                    return 50
                
                avg_gain = sum(gains) / len(gains)
                avg_loss = sum(losses) / len(losses)
                rs = avg_gain / avg_loss
                return 100 - (100 / (1 + rs))
            
            ma5_1h = calculate_ma(closes_1h, 5)
            ma20_1h = calculate_ma(closes_1h, 20)
            ma5_4h = calculate_ma(closes_4h, 5)
            ma20_4h = calculate_ma(closes_4h, 20)
            ma20_1d = calculate_ma(closes_1d, 20)
            
            rsi_1h = calculate_rsi(closes_1h)
            rsi_4h = calculate_rsi(closes_4h)
            
            # 趋势判断
            trend_1h = "bullish" if ma5_1h > ma20_1h else "bearish"
            trend_4h = "bullish" if ma5_4h > ma20_4h else "bearish"
            trend_1d = "bullish" if closes_1d[-1] > ma20_1d else "bearish" if closes_1d[-1] < ma20_1d else "sideways"
            
            return {
                "ma5_1h": ma5_1h,
                "ma20_1h": ma20_1h,
                "ma5_4h": ma5_4h,
                "ma20_4h": ma20_4h,
                "ma20_1d": ma20_1d,
                "rsi_1h": rsi_1h,
                "rsi_4h": rsi_4h,
                "trend_1h": trend_1h,
                "trend_4h": trend_4h,
                "trend_1d": trend_1d,
                "price": closes_1h[-1] if closes_1h else 0,
                "volume_1h": klines_1h[-1].get('volume', 0) if klines_1h else 0,
            }
        except Exception as e:
            logger.error(f"获取技术指标失败: {symbol} - {e}")
            return {}
    
    async def _get_strategy_advice(self, symbol: str) -> Dict:
        """获取策略建议"""
        if not self.strategy_manager:
            return {"advice": "策略管理器未连接", "strategies": []}
        
        try:
            def _norm_sym(s: str) -> str:
                s = (s or "").strip().upper()
                s = s.replace("-SWAP", "").replace("SWAP", "")
                s = s.replace("-", "").replace("/", "")
                return s

            norm_symbol = _norm_sym(symbol)

            strategies = getattr(self.strategy_manager, 'strategy_configs', {})
            
            advice_list = []
            for sid, config in strategies.items():
                if hasattr(config, "enabled") and not getattr(config, "enabled"):
                    continue
                symbols = getattr(config, 'symbols', []) or []
                norm_symbols = [_norm_sym(x) for x in symbols if x]
                if norm_symbol in norm_symbols or not symbols:
                    strategy_type = getattr(config, "strategy_type", "unknown")
                    # 规避 json 序列化错误：Enum 类型必须转成 value/字符串
                    if hasattr(strategy_type, "value"):
                        strategy_type = strategy_type.value
                    advice_list.append({
                        "id": sid,
                        "name": getattr(config, 'name', 'Unknown'),
                        "type": strategy_type,
                        "performance": self._strategy_performance.get(sid, {}),
                    })

            # 兜底：避免策略建议为 0 导致模型持续 hold
            if not advice_list and strategies:
                for sid, config in strategies.items():
                    if hasattr(config, "enabled") and not getattr(config, "enabled"):
                        continue
                    strategy_type = getattr(config, "strategy_type", "unknown")
                    if hasattr(strategy_type, "value"):
                        strategy_type = strategy_type.value
                    advice_list.append({
                        "id": sid,
                        "name": getattr(config, "name", "Unknown"),
                        "type": strategy_type,
                        "performance": self._strategy_performance.get(sid, {}),
                    })
                    if len(advice_list) >= 3:
                        break

            pref = getattr(self, "_preferred_strategy_id", None)
            if pref and advice_list:
                advice_list.sort(key=lambda x: (0 if x.get("id") == pref else 1, str(x.get("name", ""))))

            return {
                "strategies": advice_list,
                "count": len(advice_list),
                "preferred_strategy_id": pref,
            }
        except Exception as e:
            logger.error(f"获取策略建议失败: {symbol} - {e}")
            return {"advice": f"获取失败: {e}", "strategies": []}
    
    async def _get_risk_assessment(self, symbol: str) -> Dict:
        """获取风险评估"""
        if not self.risk_monitor:
            return {"level": "unknown", "message": "风险监控未连接"}
        
        try:
            risk = await self.risk_monitor.check_account_risk()
            return {
                "level": risk.risk_level.value if hasattr(risk, 'risk_level') else "unknown",
                "margin_ratio": risk.margin_ratio if hasattr(risk, 'margin_ratio') else 0,
            }
        except Exception as e:
            logger.error(f"获取风险评估失败: {symbol} - {e}")
            return {"level": "unknown", "message": str(e)}
    
    async def _get_current_positions(self) -> List[Dict]:
        """获取当前持仓 - 实时从交易所获取"""
        if not self.exchange:
            return []
        
        try:
            positions = await self.exchange.get_positions()
            # OKX返回格式: {symbol, side, size, entry_price, unrealized_pnl}
            active_positions = [p for p in positions if float(p.get('size', 0) or 0) != 0]
            return [
                {
                    "symbol": p.get('symbol', ''),
                    "side": p.get('side', ''),
                    "size": p.get('size', 0),
                    "entry_price": float(p.get('entry_price', 0) or 0),
                    "pnl": float(p.get('unrealized_pnl', 0) or 0),
                    "pnl_ratio": float(p.get('pnl_ratio', 0) or 0),
                }
                for p in active_positions
            ]
        except Exception as e:
            logger.error(f"获取持仓失败: {e}")
            return []
    
    async def _get_account_balance(self) -> Dict:
        """获取账户余额 - 实时从交易所获取"""
        if not self.exchange:
            return {}
        
        try:
            balance = await self.exchange.get_balance()
            usdt = balance.get('USDT', {})
            if isinstance(usdt, dict):
                return {
                    "available": float(usdt.get('free', 0) or 0),
                    "total": float(usdt.get('total', 0) or 0),
                    "locked": float(usdt.get('locked', 0) or 0),
                }
            else:
                return {
                    "available": float(usdt or 0),
                    "total": float(usdt or 0),
                    "locked": 0,
            }
        except Exception as e:
            logger.error(f"获取余额失败: {e}")
            return {}
    
    async def _get_third_party_data(self, symbol: str) -> Dict:
        """获取第三方数据 - 优先使用自主市场分析器"""
        result = {
            "available": False,
            "sentiment": "neutral",
            "news": [],
            "social_sentiment": {},
            "fear_greed_index": None,
            "on_chain_data": {},
            "own_analysis": {},  # 自主分析结果
        }
        
        # 1. 优先使用自主市场分析器
        try:
            from src.modules.data.own_market_analyzer import get_own_market_analyzer
            analyzer = await get_own_market_analyzer(self.exchange)
            if analyzer:
                analysis = await analyzer.analyze_symbol(symbol)
                if analysis:
                    result["own_analysis"] = analysis
                    result["available"] = True
                    
                    # 提取关键数据
                    if "sentiment" in analysis:
                        result["sentiment"] = analysis["sentiment"].get("sentiment", "neutral")
                        result["fear_greed_index"] = analysis["sentiment"].get("fear_greed_index")
                    
                    logger.info(f"📊 自主市场分析完成: {symbol}, 情绪: {result['sentiment']}")
        except Exception as e:
            logger.debug(f"自主市场分析失败: {e}")
        
        # 2. 尝试从插件管理器获取数据
        if self.plugin_manager:
            try:
                plugins_info = self.plugin_manager.get_all_plugin_info()
                result["plugins_count"] = len(plugins_info)
                result["available"] = True
                
                if hasattr(self.plugin_manager, 'get_market_sentiment'):
                    sentiment = await self.plugin_manager.get_market_sentiment(symbol)
                    if sentiment:
                        result["sentiment"] = sentiment.get('sentiment', 'neutral')
                        result["social_sentiment"] = sentiment
                
                if hasattr(self.plugin_manager, 'get_news'):
                    news = await self.plugin_manager.get_news(symbol)
                    if news:
                        result["news"] = news[:5]
                        
            except Exception as e:
                logger.error(f"从插件管理器获取数据失败: {e}")
        
        # 3. 尝试从主控制器获取第三方数据集成器
        if self.main_controller and hasattr(self.main_controller, 'third_party_integrator'):
            try:
                integrator = self.main_controller.third_party_integrator
                if integrator:
                    data = await integrator.get_comprehensive_data(symbol.replace('/', '-'))
                    if data:
                        result["available"] = True
                        result["sentiment"] = data.get('sentiment', result["sentiment"])
                        result["fear_greed_index"] = data.get('fear_greed_index')
                        result["on_chain_data"] = data.get('on_chain', {})
            except Exception as e:
                logger.error(f"从第三方集成器获取数据失败: {e}")
        
        if not result["available"]:
            logger.warning(f"⚠️ 第三方数据暂不可用: {symbol}")
        
        return result
    
    def _build_decision_prompt(
        self,
        symbol: str,
        market_data: Dict,
        technical: Dict,
        strategy_advice: Dict,
        risk_assessment: Dict,
        current_positions: List[Dict],
        account_balance: Dict = None,
        third_party_data: Dict = None,
        historical_experience: str = "",
        multi_source_analysis: Dict = None,
        ai_engine_analysis: Dict = None,
        market_intelligence: Optional[Dict] = None,
    ) -> str:
        """构建AI决策prompt - 融合所有模块数据进行决策，全部实时数据"""
        
        if account_balance is None:
            account_balance = {}
        if third_party_data is None:
            third_party_data = {}
        if multi_source_analysis is None:
            multi_source_analysis = {}
        if ai_engine_analysis is None:
            ai_engine_analysis = {}
        if market_intelligence is None:
            market_intelligence = {}
        
        aggressive_note = ""
        if self.config.get("aggressive_mode"):
            aggressive_note = """
【重要：积极交易模式已启用】
- 你必须主动寻找交易机会，不要只是观望
- 当置信度 >= 60% 时，应该执行交易
- 市场有波动就有机会，不要等待完美时机
- 止盈目标要实际，3-5%即可，不要贪心
- 及时止盈，落袋为安
- 必须综合所有模块数据做出决策
"""
        
        # 构建第三方数据详细描述
        third_party_detail = f"""【第三方数据分析】
- 数据可用: {third_party_data.get('available', False)}
- 市场情绪: {third_party_data.get('sentiment', 'neutral')}
- 恐惧贪婪指数: {third_party_data.get('fear_greed_index', 'N/A')}
- 链上数据: {json.dumps(third_party_data.get('on_chain_data', {}), ensure_ascii=False)[:500] if third_party_data.get('on_chain_data') else '暂无'}
- 社交媒体情绪: {json.dumps(third_party_data.get('social_sentiment', {}), ensure_ascii=False)[:500] if third_party_data.get('social_sentiment') else '暂无'}
"""
        
        # 构建多源数据融合分析
        multi_source_detail = ""
        if multi_source_analysis.get('status') == 'available':
            multi_source_detail = f"""
【多源数据融合分析】
- 综合情绪: {multi_source_analysis.get('sentiment', 'neutral')}
- 信号强度: {multi_source_analysis.get('signal_strength', 0)}
- 系统建议: {multi_source_analysis.get('recommendation', 'neutral')}
- 置信度: {multi_source_analysis.get('confidence', 0):.0%}
"""
        
        # 构建AI引擎分析
        ai_engine_detail = ""
        if ai_engine_analysis.get('trend') != 'unknown':
            ai_engine_detail = f"""
【AI交易引擎分析】
- 趋势判断: {ai_engine_analysis.get('trend', 'unknown')}
- 情绪分析: {ai_engine_analysis.get('sentiment', 'neutral')}
- 信号强度: {ai_engine_analysis.get('signal_strength', 0)}
"""

        # 构建统一行情情报（只读支撑数据）
        mi_detail = ""
        try:
            if isinstance(market_intelligence, dict) and market_intelligence:
                exs = market_intelligence.get("exchange_support") or {}
                rs = market_intelligence.get("risk_support") or {}
                es = market_intelligence.get("execution_support") or {}
                guards = (es.get("guards") or {}) if isinstance(es, dict) else {}
                sltp = (es.get("sltp_suggestions") or {}) if isinstance(es, dict) else {}
                mi_detail = f"""
【统一行情情报汇总（只读支撑数据，不是下单指令）】
- 数据质量: {market_intelligence.get('quality_score')} | provenance={market_intelligence.get('provenance')}
- 盘口: spread_bps={market_intelligence.get('spread_bps')} depth_imbalance={guards.get('depth_imbalance_top5')}
- 波动: atr_pct_1h={market_intelligence.get('atr_pct_1h')} | 24h涨跌={market_intelligence.get('change_24h')}
- 执行门控建议: min_quality>={guards.get('min_quality_score_to_trade')} max_spread_bps<={guards.get('max_spread_bps_to_trade')} min_rr>={guards.get('min_rr_to_trade')}
- SLTP建议: risk_pct={sltp.get('risk_pct')} tp_pct={sltp.get('take_profit_pct')} trailing_offset={sltp.get('trailing_offset')}
- 汇总趋势/倾向(参考): trend={market_intelligence.get('trend')} bias={market_intelligence.get('action_bias')} conf={market_intelligence.get('confidence')}
- 冲突: {market_intelligence.get('conflicts')}
（你必须结合技术指标/多源融合/风险与持仓独立复核；若证据不足或冲突明显，action 必须为 hold）
"""
        except Exception:
            mi_detail = ""
        
        # 构建持仓详情
        positions_detail = "无持仓"
        if current_positions:
            positions_detail = ""
            for pos in current_positions:
                positions_detail += f"  - {pos.get('symbol', '')}: {pos.get('side', '')} {pos.get('size', 0)} | 入场价: {pos.get('entry_price', 0):.4f} | 盈亏: ${pos.get('pnl', 0):+.2f}\n"

        scanner_hint_block = self._format_scanner_hint_block(symbol)
        
        prompt = f"""你是一个拥有完整控制权的量化交易AI，正在24小时不间断运行。

你必须综合以下所有模块的实时数据做出交易决策：
1. 市场数据 - 实时价格、成交量
2. 技术指标 - 多周期K线(1H/4H/1D)、MA、RSI、趋势
3. 策略建议 - 可用策略
4. 风险评估 - 实时账户风险
5. 当前持仓 - 实时仓位情况
6. 账户余额 - 实时可用资金
7. 第三方数据 - 新闻、情绪、链上数据
8. 多源数据融合 - 综合分析结果
9. AI引擎分析 - 趋势预测
10. 历史经验 - 过往交易经验

{aggressive_note}

【交易对】{symbol}
{scanner_hint_block}
【市场数据 - 实时】
- 当前价格: {market_data.get('price', 0)}
- 24h最高: {market_data.get('high', 0)}
- 24h最低: {market_data.get('low', 0)}
- 成交量: {market_data.get('volume', 0)}

【技术指标 - 多周期K线实时分析】
1小时周期:
- MA5: {technical.get('ma5_1h', 0):.4f}
- MA20: {technical.get('ma20_1h', 0):.4f}
- RSI: {technical.get('rsi_1h', 0):.1f}
- 趋势: {technical.get('trend_1h', 'unknown')}

4小时周期:
- MA5: {technical.get('ma5_4h', 0):.4f}
- MA20: {technical.get('ma20_4h', 0):.4f}
- RSI: {technical.get('rsi_4h', 0):.1f}
- 趋势: {technical.get('trend_4h', 'unknown')}

日线周期:
- MA20: {technical.get('ma20_1d', 0):.4f}
- 趋势: {technical.get('trend_1d', 'unknown')}

【可用策略】
- 策略数量: {strategy_advice.get('count', 0)}
- 策略详情: {json.dumps(strategy_advice.get('strategies', [])[:3], indent=2, ensure_ascii=False, default=str)[:2000]}
{historical_experience}
【风险评估 - 实时】
- 风险等级: {risk_assessment.get('level', 'unknown')}
- 保证金比例: {risk_assessment.get('margin_ratio', 0):.2%}

【账户余额 - 实时】
- 可用余额: {account_balance.get('available', 0):.2f} USDT
- 总余额: {account_balance.get('total', 0):.2f} USDT
- 冻结金额: {account_balance.get('locked', 0):.2f} USDT

【当前持仓 - 实时】
{positions_detail}
{third_party_detail}
{multi_source_detail}
{ai_engine_detail}
{mi_detail}
【用户规则】
- 黑名单: {list(self.blacklist)} (绝对不能操作)
- 授权状态: {'已授权全权交易' if self.authorization.get('full_authorization') else '未授权'}

【交易配置】
- 杠杆范围: {self.config['leverage_min']}-{self.config['leverage_max']}x
- 默认杠杆: {self.config['default_leverage']}x
- 最大持仓数: {self.config['max_positions']}
- 最小交易置信度: {self.config.get('min_confidence_to_trade', 0.6)}
- 主观平仓要求: 仅在「多周期趋势已实质反转」或风险不可接受时 action=close；不要因单根K线、短时反弹/回踩或单一指标抖动平仓；若证据不足请 hold。
- 重要: 若在理由中写出「多周期矛盾」「大周期与短周期方向不一致」等，则 **必须 action=hold**，由 SLTP 管理出场；不得同时写矛盾又输出 close，也不得把「可用余额为 0」单独作为平仓主因（平仓不会创造可用保证金逻辑）。

【决策要求】
你必须综合分析以上所有数据，做出交易决策。特别注意：
1. 技术指标 + 多源数据融合 + AI引擎分析 三者趋势是否一致
2. 第三方数据的情绪是否支持你的判断
3. 风险评估等级是否允许开仓
4. 历史经验中是否有类似情况的教训
5. 已有持仓时：优先让交易所侧止盈止损（SLTP）管理价位平仓；除非趋势明确反转，否则避免频繁 close
6. confidence 应反映真实不确定性：存在周期冲突时 confidence 不得超过 0.75，且 action 应为 hold

请做出交易决策，返回JSON格式：

{{
    "action": "buy/sell/hold/close",
    "side": "long/short",
    "quantity": 整数张数,
    "leverage": 杠杆倍数,
    "confidence": 0.0-1.0,
    "reasoning": "决策理由（必须说明如何综合各模块数据）",
    "strategy_used": "使用的策略ID或名称",
    "risk_level": "low/medium/high",
    "stop_loss_pct": 止损百分比,
    "take_profit_pct": 止盈百分比
}}

只返回JSON。"""
        
        return prompt
    
    def _parse_ai_decision(self, response: str, symbol: str) -> Optional[TradeDecision]:
        """解析AI决策"""
        try:
            json_str = response.strip()
            
            if json_str.startswith('```json'):
                json_str = json_str[7:]
            if json_str.startswith('```'):
                json_str = json_str[3:]
            if json_str.endswith('```'):
                json_str = json_str[:-3]
            json_str = json_str.strip()
            
            if json_str.startswith('{') and json_str.endswith('}'):
                pass
            else:
                start = json_str.find('{')
                end = json_str.rfind('}')
                if start != -1 and end != -1:
                    json_str = json_str[start:end+1]
                else:
                    logger.warning(f"AI响应中没有找到JSON: {response[:100]}")
                    return None
            
            data = json.loads(json_str)
            
            action = data.get('action', 'hold')
            if action == 'hold':
                return TradeDecision(
                    symbol=symbol,
                    action='hold',
                    side='',
                    quantity=0,
                    leverage=0,
                    entry_price=0,
                    stop_loss=0,
                    take_profit=0,
                    confidence=0,
                    reasoning=data.get('reasoning', 'AI决定持有'),
                    strategy_used=data.get('strategy_used', ''),
                    risk_level=data.get('risk_level', 'low')
                )
            
            entry_price = 0
            
            return TradeDecision(
                symbol=symbol,
                action=action,
                side=data.get('side', 'long'),
                quantity=max(1, int(data.get('quantity', 1))),
                leverage=data.get('leverage', self.config['default_leverage']),
                entry_price=entry_price,
                stop_loss=0,
                take_profit=0,
                confidence=data.get('confidence', 0.5),
                reasoning=data.get('reasoning', ''),
                strategy_used=data.get('strategy_used', ''),
                risk_level=data.get('risk_level', 'medium')
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"解析AI决策失败: {e}")
            return None
        except Exception as e:
            logger.error(f"处理AI决策失败: {e}")
            return None

    @staticmethod
    def _position_row_age_sec(pos: Dict[str, Any]) -> Optional[float]:
        """OKX 持仓 cTime/timestamp（多为毫秒）-> 已持仓秒数；无法解析则 None。"""
        try:
            raw = pos.get("cTime") or pos.get("timestamp") or pos.get("uTime") or 0
            t = float(raw or 0)
            if t <= 0:
                return None
            if t > 1e15:
                t = t / 1e6
            elif t > 1e12:
                t = t / 1e3
            from time import time as _now

            return max(0.0, float(_now()) - t)
        except Exception:
            return None

    async def _matching_position_age_sec(self, symbol: str, side: str) -> Optional[float]:
        """当前决策品种+方向在交易所的持仓已开时长（秒）。"""
        if not self.exchange or not hasattr(self.exchange, "get_positions"):
            return None
        try:
            rows = await self.exchange.get_positions()
        except Exception:
            return None
        base = (symbol.split("/")[0] if "/" in symbol else symbol).strip().upper()
        want = str(side or "").strip().lower()
        best: Optional[float] = None
        for p in rows or []:
            if not isinstance(p, dict):
                continue
            try:
                sz = float(p.get("size", 0) or 0)
            except (TypeError, ValueError):
                sz = 0.0
            if abs(sz) < 1e-12:
                continue
            iid = str(p.get("instId") or "").upper()
            sym = str(p.get("symbol") or "").upper()
            if base and base not in iid and base not in sym:
                continue
            ps = str(p.get("side") or p.get("posSide") or "").strip().lower()
            if want and ps and want not in ps:
                continue
            age = self._position_row_age_sec(p)
            if age is None:
                continue
            best = age if best is None else max(best, age)
        return best

    async def _discretionary_close_passes(self, decision: TradeDecision) -> tuple[bool, str]:
        """
        主循环中的 LLM 主观平仓防抖：冷却、更高置信度、连续确认、最短持仓时间。
        SLTP / 用户平仓指令不经过此函数。
        """
        if not bool(self.config.get("ai_core_discretionary_close_enabled", True)):
            return False, "discretionary_close_disabled"

        key = f"{decision.symbol}|{str(decision.side or '').lower()}"
        min_age = float(self.config.get("ai_core_min_position_age_sec_before_discretionary_close", 0) or 0)
        if min_age > 0:
            age = await self._matching_position_age_sec(decision.symbol, decision.side)
            if age is not None and age < min_age:
                return False, f"position_too_young_{age:.0f}s_lt_{min_age:.0f}s"

        reason_text = str(decision.reasoning or "")
        vetoes = self.config.get("ai_core_close_reason_veto_substrings")
        if vetoes is None:
            vetoes = ["多周期矛盾"]
        elif isinstance(vetoes, str):
            vetoes = [vetoes]
        for sub in vetoes:
            sub_s = str(sub or "").strip()
            if sub_s and sub_s in reason_text:
                self._discretionary_close_streak.pop(key, None)
                return False, f"close_reason_veto:{sub_s[:40]}"

        min_c = float(self.config.get("ai_core_min_confidence_to_close", 0.84))
        if float(decision.confidence or 0) < min_c:
            self._discretionary_close_streak.pop(key, None)
            return False, f"close_confidence_{float(decision.confidence or 0):.2f}_lt_{min_c}"

        cd = float(self.config.get("ai_core_discretionary_close_cooldown_sec", 2700))
        last = self._last_ai_discretionary_close_at.get(key)
        if last and (datetime.now() - last).total_seconds() < cd:
            self._discretionary_close_streak.pop(key, None)
            return False, f"cooldown_{int(cd)}s"

        need = max(1, int(self.config.get("ai_core_discretionary_close_confirmations", 2)))
        win = float(self.config.get("ai_core_discretionary_close_confirm_window_sec", 1200))
        if need <= 1:
            return True, "ok"

        now = datetime.now()
        st = self._discretionary_close_streak.get(key)
        if st is None:
            self._discretionary_close_streak[key] = (1, now)
            return False, f"need_{need}_close_signals_now_1"
        cnt, t0 = st
        if (now - t0).total_seconds() > win:
            self._discretionary_close_streak[key] = (1, now)
            return False, f"confirm_window_reset_need_1_of_{need}"
        cnt += 1
        self._discretionary_close_streak[key] = (cnt, t0)
        if cnt < need:
            return False, f"need_{need}_close_signals_now_{cnt}"
        self._discretionary_close_streak.pop(key, None)
        return True, "ok"
    
    async def _execute_decision(self, decision: TradeDecision, *, bypass_discretionary_close_gates: bool = False) -> bool:
        """执行AI决策 - 带余额检查"""
        if decision.action == 'hold':
            return True
        
        if decision.symbol in self.blacklist:
            logger.warning(f"⚠️ {decision.symbol} 在黑名单中，不执行交易")
            return False
        
        if not self.exchange:
            logger.error("交易所未连接，无法执行交易")
            return False
        
        try:
            # 1. 检查账户余额
            balance = await self.exchange.get_balance()
            usdt_balance = balance.get('USDT', {})
            available = float(usdt_balance.get('free', 0) if isinstance(usdt_balance, dict) else usdt_balance)
            
            logger.info(f"💰 账户可用余额: {available:.2f} USDT")

            is_close = decision.action == "close"
            is_open = decision.action in ("buy", "sell")

            if is_close and not bypass_discretionary_close_gates:
                ok_dc, why_dc = await self._discretionary_close_passes(decision)
                if not ok_dc:
                    self._execution_guards_stats["discretionary_close_suppressed"] = (
                        int(self._execution_guards_stats.get("discretionary_close_suppressed", 0)) + 1
                    )
                    logger.info("🧷 AI主观平仓暂缓: %s %s — %s", decision.symbol, decision.side, why_dc)
                    return False

            # 开仓：不再做应用层「最小可用 USDT」硬门槛；实际能否成交由交易所 minSz/余额 决定。平仓不因低 USDT 阻塞。

            # 2. 获取当前价格
            ticker = await self.exchange.get_ticker(decision.symbol.replace('/', '-'))
            current_price = ticker.get('last', 0)
            
            if current_price <= 0:
                logger.error(f"无法获取 {decision.symbol} 的价格")
                return False
            
            decision.entry_price = current_price
            
            lev_min = float(self.config.get("leverage_min", 1) or 1)
            lev_max = float(self.config.get("leverage_max", 100) or 100)
            leverage = float(decision.leverage or self.config.get("default_leverage", 20))
            leverage = min(max(leverage, lev_min), lev_max)
            low_thr = float(self.config.get("low_balance_usdt_threshold") or 25.0)
            if is_open:
                # 3. 根据余额动态调整数量：低余额时允许用更高比例的可用作保证金（仍受杠杆上限约束）
                if available < low_thr:
                    margin_frac = float(self.config.get("low_balance_margin_fraction") or 0.55)
                else:
                    margin_frac = float(self.config.get("default_max_margin_fraction") or 0.30)
                margin_frac = max(0.05, min(0.92, margin_frac))
                max_margin = available * margin_frac
                max_position_value = max_margin * leverage
                max_quantity = int(max_position_value / max(current_price, 1e-9))
                logger.info(
                    "📊 资金预算: available=%.2f margin_frac=%.2f margin=%.2f lev=%s max_qty=%s (低余额阈值=%.2f)",
                    available,
                    margin_frac,
                    max_margin,
                    leverage,
                    max_quantity,
                    low_thr,
                )

                if decision.quantity > max_quantity:
                    capped = max(1, max_quantity) if max_quantity > 0 else 1
                    logger.info(f"📊 调整数量: {decision.quantity} -> {capped} (根据余额)")
                    decision.quantity = capped
                decision.quantity = max(1, int(decision.quantity or 1))

            # 3.1 动态仓位/组合风险预算（波动率/相关性/总仓位比例）— 仅开仓
            try:
                if is_open and self.main_controller and hasattr(self.main_controller, "get_dynamic_position_manager"):
                    dpm = self.main_controller.get_dynamic_position_manager()
                else:
                    dpm = None
                if dpm:
                    positions = await self.exchange.get_positions()
                    current_positions = {p.get("symbol"): p for p in (positions or []) if p.get("symbol")}
                    base_value = float(decision.quantity) * float(current_price)
                    adjusted_value, details = await dpm.calculate_dynamic_position_size(
                        symbol=decision.symbol,
                        base_size=base_value,
                        account_balance=float(available or 0),
                        current_positions=current_positions,
                        market_data={"volatility": 0.02},
                    )
                    new_qty = max(1, int(float(adjusted_value) / float(current_price)))
                    if new_qty != decision.quantity:
                        logger.info(f"📊 动态仓位调整数量: {decision.quantity} -> {new_qty}")
                        decision.quantity = new_qty
                    if self.main_controller and hasattr(self.main_controller, "memory_gateway") and self.main_controller.memory_gateway:
                        await self.main_controller.memory_gateway.add_memory(
                            memory_type="risk_setting",
                            content=f"动态仓位调整: {decision.symbol} qty={decision.quantity} details={details}",
                            metadata={"symbol": decision.symbol, "details": details},
                            source_module="ai_core_decision_engine",
                            importance=0.65,
                            tags=["position_sizing", "risk_budget"],
                        )
            except Exception as e:
                logger.debug(f"动态仓位调整失败: {e}")
            
            decision.leverage = int(round(leverage))

            rr = 0.0
            spread_bps = None
            depth_imbalance = None
            min_rr = 0.0

            if is_close:
                # 平仓：不套用开仓盈亏比/盘口门控（避免低余额+止损结构导致无法平仓）
                self._adaptive_guard_profile = {
                    "profile": "close",
                    "symbol_group": self._symbol_group_key(decision.symbol),
                    "session_group": self._market_session_key(datetime.utcnow()),
                    "composite_group": "",
                    "atr_pct_1h": 0.0,
                    "effective_min_rr": 0.0,
                    "effective_max_spread_bps": 0.0,
                    "effective_max_abs_depth_imbalance": 0.0,
                }
                logger.info("🎯 平仓路径：跳过开仓专用 RR/盘口/深度门控")
            else:
                # 4. 开仓门控用风险距离：主路径为移动止损（固定止盈止损关闭），此处仅构造合成 RR
                sltp = self._sltp_open_snapshot or {}
                trailing_only = bool(sltp.get("trailing_only_mode", True))
                if trailing_only:
                    off = float(sltp.get("initial_trailing_offset", 0.01) or 0.01)
                    mult = float(sltp.get("open_rr_synthetic_reward_multiple", 1.5) or 1.5)
                    risk_px = current_price * off
                    reward_px = risk_px * mult
                    if decision.side == "long":
                        decision.stop_loss = current_price - risk_px
                        decision.take_profit = current_price + reward_px
                    else:
                        decision.stop_loss = current_price + risk_px
                        decision.take_profit = current_price - reward_px
                else:
                    atr = current_price * 0.02
                    if decision.side == "long":
                        decision.stop_loss = current_price - 2 * atr
                        decision.take_profit = current_price + 3 * atr
                    else:
                        decision.stop_loss = current_price + 2 * atr
                        decision.take_profit = current_price - 3 * atr
                
                # 3.2 数据退化时自动降仓（避免单点数据故障造成激进下单）
                if "data_quality_guard" in str(decision.reasoning or ""):
                    logger.warning("⚠️ 数据质量保护触发，跳过执行")
                    return True
                if "degraded=" in str(decision.reasoning or ""):
                    try:
                        q_factor = float(self.config.get("degraded_data_quantity_factor", 0.6) or 0.6)
                        new_qty = max(1, int(float(decision.quantity) * q_factor))
                        if new_qty < decision.quantity:
                            self._execution_guards_stats["degraded_quantity_reduced"] += 1
                            logger.info("📉 数据退化降仓: %s -> %s", decision.quantity, new_qty)
                            decision.quantity = new_qty
                    except Exception:
                        pass

                # 3.3 执行前二次确认门：最小盈亏比 + 盘口价差 + 深度失衡
                try:
                    risk = abs(float(decision.entry_price) - float(decision.stop_loss))
                    reward = abs(float(decision.take_profit) - float(decision.entry_price))
                    rr = reward / max(1e-9, risk)
                except Exception:
                    rr = 0.0
                symbol_group = self._symbol_group_key(decision.symbol)
                session_group = self._market_session_key(datetime.utcnow())
                composite_group = f"{symbol_group}@{session_group}"
                gcfg = self._symbol_group_guard_overrides.get(composite_group) or self._symbol_group_guard_overrides.get(symbol_group, {})
                min_rr = float(gcfg.get("min_rr_to_trade", self.config.get("min_rr_to_trade", 1.2)) or 1.2)
                max_spread_bps = float(gcfg.get("max_spread_bps_to_trade", self.config.get("max_spread_bps_to_trade", 35.0)) or 35.0)
                max_abs_imb = float(self.config.get("max_abs_depth_imbalance_to_trade", 0.92) or 0.92)

            # 3.3.1 自适应门控阈值：波动低 -> 收紧；波动高 -> 适度放宽。
            if (not is_close) and bool(self.config.get("auto_adaptive_guards", True)):
                try:
                    tech = await self._get_technical_indicators(decision.symbol)
                    price_ref = float(tech.get("price", decision.entry_price) or decision.entry_price or 0)
                    ma5 = float(tech.get("ma5_1h", 0) or 0)
                    ma20 = float(tech.get("ma20_1h", 0) or 0)
                    atr_proxy = abs(ma5 - ma20)
                    atr_pct = (atr_proxy / max(1e-9, price_ref)) if price_ref > 0 else 0.0
                    profile = "normal"
                    if atr_pct >= 0.02:
                        profile = "high_vol"
                        min_rr = min_rr * 0.90
                        max_spread_bps = max_spread_bps * 1.25
                        max_abs_imb = min(0.98, max_abs_imb * 1.05)
                    elif atr_pct <= 0.005:
                        profile = "low_vol"
                        min_rr = min_rr * 1.10
                        max_spread_bps = max(5.0, max_spread_bps * 0.80)
                        max_abs_imb = max(0.80, max_abs_imb * 0.95)

                    # 在低风险状态下做轻度放宽以提高开单率；高风险时反向收紧。
                    if bool(self.config.get("boost_on_low_risk", True)):
                        risk_level = str(getattr(decision, "risk_level", "") or "").lower()
                        if risk_level == "low":
                            min_rr = min_rr * float(self.config.get("low_risk_rr_multiplier", 0.96) or 0.96)
                            max_spread_bps = max_spread_bps * float(
                                self.config.get("low_risk_spread_multiplier", 1.08) or 1.08
                            )
                        elif risk_level in ("high", "critical"):
                            min_rr = min_rr * float(self.config.get("high_risk_rr_multiplier", 1.08) or 1.08)
                            max_spread_bps = max(
                                5.0,
                                max_spread_bps
                                * float(self.config.get("high_risk_spread_multiplier", 0.90) or 0.90),
                            )

                    min_rr = min(2.5, max(0.9, float(min_rr)))
                    max_spread_bps = min(120.0, max(5.0, float(max_spread_bps)))
                    max_abs_imb = min(0.995, max(0.75, float(max_abs_imb)))
                    self._adaptive_guard_profile = {
                        "profile": profile,
                        "symbol_group": symbol_group,
                        "session_group": session_group,
                        "composite_group": composite_group,
                        "atr_pct_1h": float(atr_pct),
                        "effective_min_rr": float(min_rr),
                        "effective_max_spread_bps": float(max_spread_bps),
                        "effective_max_abs_depth_imbalance": float(max_abs_imb),
                    }
                except Exception as e:
                    logger.debug(f"自适应门控计算失败: {e}")

            if not is_close:
                # Explicit open-confidence gate: prevent low-confidence churn before any exchange interaction.
                try:
                    conf = float(getattr(decision, "confidence", 0) or 0)
                except Exception:
                    conf = 0.0
                min_open_c = float(
                    self.config.get(
                        "ai_core_min_confidence_to_open",
                        self.config.get("min_confidence_to_trade", 0.72),
                    )
                    or 0.72
                )
                if conf < min_open_c:
                    self._execution_guards_stats["confidence_open_rejected"] = int(
                        self._execution_guards_stats.get("confidence_open_rejected", 0)
                    ) + 1
                    logger.warning(
                        "⚠️ 执行门控拒绝: open 置信度过低 conf=%.3f < %.3f symbol=%s",
                        conf,
                        min_open_c,
                        decision.symbol,
                    )
                    return False

                if rr < min_rr:
                    self._execution_guards_stats["rr_rejected"] += 1
                    logger.warning("⚠️ 执行门控拒绝: RR过低 rr=%.2f < %.2f symbol=%s", rr, min_rr, decision.symbol)
                    return False

                try:
                    if hasattr(self.exchange, "get_order_book"):
                        ob = await self.exchange.get_order_book(decision.symbol, depth=10)
                        if ob and getattr(ob, "bids", None) and getattr(ob, "asks", None):
                            best_bid = float(ob.bids[0][0])
                            best_ask = float(ob.asks[0][0])
                            bid_vol = sum(float(x[1]) for x in ob.bids[:5])
                            ask_vol = sum(float(x[1]) for x in ob.asks[:5])
                            spread_bps = ((best_ask - best_bid) / max(1e-9, best_bid)) * 10000.0
                            depth_imbalance = (bid_vol - ask_vol) / max(1e-9, bid_vol + ask_vol)
                except Exception as e:
                    logger.debug(f"执行前订单簿检查失败: {e}")

                if spread_bps is not None and spread_bps > max_spread_bps:
                    self._execution_guards_stats["spread_rejected"] += 1
                    logger.warning(
                        "⚠️ 执行门控拒绝: 盘口价差过大 spread=%.2fbps > %.2f symbol=%s",
                        spread_bps, max_spread_bps, decision.symbol
                    )
                    return False
                if depth_imbalance is not None and abs(depth_imbalance) > max_abs_imb:
                    self._execution_guards_stats["depth_imbalance_rejected"] += 1
                    logger.warning(
                        "⚠️ 执行门控拒绝: 深度失衡过大 imbalance=%.3f > %.3f symbol=%s",
                        abs(depth_imbalance), max_abs_imb, decision.symbol
                    )
                    return False

            logger.info(f"🎯 执行AI决策: {decision.symbol} {decision.action} {decision.side}")
            logger.info(f"   入场价: {decision.entry_price}")
            logger.info(f"   数量: {decision.quantity}张")
            logger.info(f"   杠杆: {decision.leverage}x")
            logger.info(f"   止损: {decision.stop_loss}")
            logger.info(f"   止盈: {decision.take_profit}")
            logger.info(f"   RR: {rr:.2f}")
            logger.info(f"   门控档位: {self._adaptive_guard_profile.get('profile', 'normal')}")
            if spread_bps is not None:
                logger.info(f"   盘口价差: {spread_bps:.2f} bps")
            if depth_imbalance is not None:
                logger.info(f"   深度失衡: {depth_imbalance:.3f}")
            logger.info(f"   理由: {decision.reasoning}")
            logger.info(f"   策略: {decision.strategy_used}")
            
            order = None
            trace_id = str(uuid.uuid4())

            # Trade intent event (best-effort): for frontend/TG + audit correlation
            try:
                hub = getattr(self.main_controller, "trade_event_hub", None) if self.main_controller else None
                if hub and hasattr(hub, "publish_intent"):
                    from src.modules.core.trade_event_hub import TradeIntent

                    await hub.publish_intent(
                        TradeIntent(
                            trace_id=trace_id,
                            source="ai_core",
                            symbol=str(decision.symbol),
                            side=str(decision.side),
                            action="close" if decision.action == "close" else "open",
                            quantity=float(decision.quantity) if decision.action != "close" else None,
                            leverage=int(decision.leverage) if decision.action != "close" else None,
                            reason=str(getattr(decision, "strategy_used", "") or "ai_core_decision"),
                            context={
                                "decision_action": decision.action,
                                "confidence": getattr(decision, "confidence", None),
                                "risk_level": getattr(decision, "risk_level", None),
                                "strategy_used": getattr(decision, "strategy_used", None),
                                "decision_reasoning": getattr(decision, "reasoning", None),
                            },
                        )
                    )
            except Exception:
                pass

            # 优先走主控制器执行验证网关，避免直接裸下单
            if self.main_controller and hasattr(self.main_controller, "execute_command"):
                try:
                    from src.modules.core.execution_verifier import CommandType
                    command_type = CommandType.CLOSE_POSITION if decision.action == "close" else CommandType.OPEN_POSITION
                    action = f"{decision.action}_{decision.side}"
                    exec_result = await self.main_controller.execute_command(
                        command_type=command_type,
                        action=action,
                        symbol=decision.symbol,
                        params={
                            "symbol": decision.symbol,
                            "side": decision.side,
                            "quantity": decision.quantity,
                            "leverage": decision.leverage,
                            "entry_price": decision.entry_price,
                            "stop_loss": decision.stop_loss,
                            "take_profit": decision.take_profit,
                            "write_source": "ai_core",
                            "trace_id": trace_id,
                        },
                    )
                    if exec_result and getattr(exec_result, "status", None) and exec_result.status.value == "success":
                        order = {
                            "success": True,
                            "orderId": exec_result.execution_id,
                            "details": exec_result.details,
                            "trace_id": trace_id,
                        }
                    else:
                        # 关键：execution_verifier 可能因为交易所缺失 create_order 等原因失败，
                        # 这时必须让 order 仍保持为 None，强制走下面 ExecutionGateway（S1 窄出口）回退路径。
                        err = getattr(exec_result, "error_message", None) if exec_result else None
                        status = getattr(getattr(exec_result, "status", None), "value", None) if exec_result else None
                        if err or status:
                            logger.warning(
                                "execute_command failed; fallback to ExecutionGateway. status=%s err=%s",
                                status,
                                err,
                            )
                        order = None
                except Exception as e:
                    logger.warning(f"执行验证网关调用失败，回退交易所直连: {e}")

            # 回退：ExecutionGateway（S1）；无 Gateway 时再直连交易所（避免在有 S1 时绕过策略双写）
            if order is None:
                gw = (
                    getattr(self.main_controller, "execution_gateway", None)
                    if self.main_controller
                    else None
                )
                if gw:
                    try:
                        if decision.action == "close":
                            order = await gw.close_swap(
                                decision.symbol,
                                decision.side,
                                None,
                                "ai_core",
                                "ai_decision_close",
                                context={
                                    "strategy_used": getattr(decision, "strategy_used", None),
                                    "decision_reasoning": getattr(decision, "reasoning", None),
                                    "confidence": getattr(decision, "confidence", None),
                                    "risk_level": getattr(decision, "risk_level", None),
                                    "trace_id": trace_id,
                                },
                            )
                        else:
                            order = await gw.open_swap(
                                decision.symbol,
                                decision.side,
                                float(decision.quantity),
                                int(decision.leverage),
                                "ai_core",
                                "ai_decision_open",
                                margin_mode="cross",
                                price=None,
                                context={
                                    "strategy_used": getattr(decision, "strategy_used", None),
                                    "decision_reasoning": getattr(decision, "reasoning", None),
                                    "confidence": getattr(decision, "confidence", None),
                                    "risk_level": getattr(decision, "risk_level", None),
                                    "rr": rr,
                                    "spread_bps": spread_bps,
                                    "depth_imbalance": depth_imbalance,
                                    "guard_profile": getattr(self, "_adaptive_guard_profile", None),
                                    "trace_id": trace_id,
                                },
                            )
                    except Exception as e:
                        logger.warning(f"ExecutionGateway 执行失败: {e}")
                        order = None

                if order is None and not gw:
                    if decision.action == 'close':
                        order = await self.exchange.close_position(
                            symbol=decision.symbol.replace('/', '-'),
                            side=decision.side
                        )
                    else:
                        await self.exchange.set_leverage(
                            symbol=decision.symbol.replace('/', '-'),
                            leverage=decision.leverage,
                            margin_mode='cross'
                        )
                        order = await self.exchange.open_swap_position(
                            symbol=decision.symbol.replace('/', '-'),
                            side=decision.side,
                            size=decision.quantity,
                            leverage=decision.leverage
                        )
                elif order is None and gw:
                    logger.error(
                        "S1: ExecutionGateway 未成功下单且 Gateway 已启用，已跳过交易所直连兜底 symbol=%s",
                        decision.symbol,
                    )

            if order and isinstance(order, dict):
                order.setdefault("trace_id", trace_id)
            
            if order and order.get('success'):
                logger.info(f"✅ AI决策执行成功: {order.get('orderId')}")

                if decision.action == "close":
                    ck = f"{decision.symbol}|{str(decision.side or '').lower()}"
                    self._last_ai_discretionary_close_at[ck] = datetime.now()
                    self._discretionary_close_streak.pop(ck, None)

                # 开仓成功后，立即同步创建/更新仓位跟踪止盈止损单（使用当前动态门控信息）
                if decision.action != "close":
                    try:
                        await self._sync_dynamic_sltp_after_open(
                            decision=decision,
                            min_rr=min_rr if 'min_rr' in locals() else float(self.config.get("min_rr_to_trade", 1.2) or 1.2),
                            spread_bps=spread_bps if 'spread_bps' in locals() else None,
                            depth_imbalance=depth_imbalance if 'depth_imbalance' in locals() else None,
                            order_result=order if isinstance(order, dict) else None,
                            trace_id=trace_id,
                        )
                    except Exception as e:
                        logger.warning(f"同步止盈止损跟踪失败（不影响开仓成功）: {e}")
                
                await self._save_decision_to_memory(decision, order)
                
                # 交易后分析、总结、优化
                await self._analyze_trade_and_update_strategy(decision, order)
                
                return True
            else:
                error = order.get('error', '未知错误') if order else '返回为空'
                logger.error(f"❌ AI决策执行失败: {error}")
                return False
                
        except Exception as e:
            logger.error(f"执行AI决策失败: {e}")
            return False

    async def _resolve_entry_qty_after_open(
        self,
        decision: TradeDecision,
        order_result: Optional[Dict[str, Any]],
    ) -> tuple[float, float]:
        """优先使用成交/验证详情中的价格，其次 ticker；数量尽量对齐交易所持仓。"""
        entry = float(decision.entry_price or 0)
        qty = float(decision.quantity or 0)
        details: Dict[str, Any] = {}
        if order_result:
            d = order_result.get("details")
            if isinstance(d, dict):
                details = d
            for key in ("price", "average", "avgPx", "fillPx"):
                v = None
                if details:
                    v = details.get(key)
                if v is None:
                    v = order_result.get(key)
                try:
                    if v is not None and float(v) > 0:
                        entry = float(v)
                        break
                except (TypeError, ValueError):
                    continue
        if self.exchange:
            try:
                t = await self.exchange.get_ticker(str(decision.symbol).replace("/", "-"))
                last = float((t or {}).get("last") or 0)
                if last > 0:
                    if entry <= 0:
                        entry = last
                    else:
                        rel = abs(entry - last) / max(last, 1e-9)
                        if rel > 0.025:
                            logger.info(
                                "SLTP entry 校准: 决策/成交=%.6g 与 last=%.6g 偏离 %.2f%%，采用 last",
                                entry,
                                last,
                                rel * 100.0,
                            )
                            entry = last
            except Exception as e:
                logger.debug("SLTP ticker 校准跳过: %s", e)
        if self.exchange and qty > 0:
            try:
                rows = await self.exchange.get_positions()
                want = str(decision.side or "").lower()
                base = decision.symbol.split("/")[0].upper()
                for p in rows or []:
                    if not isinstance(p, dict):
                        continue
                    if str(p.get("side", "")).lower() != want:
                        continue
                    iid = str(p.get("instId", "")).upper()
                    if base and base in iid:
                        sz = abs(float(p.get("size", 0) or 0))
                        if sz > 1e-12:
                            qty = sz
                            break
            except Exception:
                pass
        return entry, qty

    async def _sync_dynamic_sltp_after_open(
        self,
        decision: TradeDecision,
        min_rr: float,
        spread_bps: Optional[float],
        depth_imbalance: Optional[float],
        order_result: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> None:
        """开仓成功后将自适应门控结果应用到仓位跟踪止盈止损。"""
        if not self.main_controller or not hasattr(self.main_controller, "create_stop_loss_order"):
            return
        entry, qty = await self._resolve_entry_qty_after_open(decision, order_result)
        if entry <= 0:
            return
        if qty <= 0:
            qty = float(decision.quantity or 0)

        risk_pct = abs(float(decision.stop_loss or 0) - entry) / max(1e-9, entry)
        tp_pct = abs(float(decision.take_profit or 0) - entry) / max(1e-9, entry)
        # 兜底范围，避免极端值
        risk_pct = min(0.08, max(0.006, risk_pct))
        tp_pct = min(0.20, max(0.010, tp_pct))

        # 若当前 RR 低于目标门槛，按门槛抬高止盈距离，保证与执行门控一致。
        rr_now = tp_pct / max(1e-9, risk_pct)
        if rr_now < float(min_rr):
            tp_pct = min(0.20, risk_pct * float(min_rr))

        trailing_offset = float(self._adaptive_guard_profile.get("effective_max_spread_bps", 35.0) or 35.0) / 10000.0
        trailing_offset = min(0.03, max(0.008, trailing_offset * 2.0))

        # 盘口极端时先更保守：减小 trailing offset（更快锁盈）
        if spread_bps is not None and spread_bps > 45:
            trailing_offset = max(0.006, trailing_offset * 0.8)
        if depth_imbalance is not None:
            if (decision.side == "long" and depth_imbalance < -0.40) or (decision.side == "short" and depth_imbalance > 0.40):
                trailing_offset = max(0.006, trailing_offset * 0.85)

        # 若 MarketIntelligence 提供了更全面的 SLTP 建议参数，则在边界内优先采用（统一真源）
        try:
            mi = getattr(self.main_controller, "market_intelligence", None)
            if mi and hasattr(mi, "get_symbol_view"):
                v = await mi.get_symbol_view(decision.symbol, include_snapshot=False)
                es = getattr(v, "execution_support", None)
                sugg = (es.get("sltp_suggestions") or {}) if isinstance(es, dict) else {}
                r2 = sugg.get("risk_pct")
                t2 = sugg.get("take_profit_pct")
                tr2 = sugg.get("trailing_offset")
                if r2 is not None:
                    r2f = float(r2)
                    if 0.004 <= r2f <= 0.10:
                        risk_pct = min(0.08, max(0.006, r2f))
                if t2 is not None:
                    t2f = float(t2)
                    if 0.006 <= t2f <= 0.30:
                        tp_pct = min(0.20, max(0.010, t2f))
                if tr2 is not None:
                    tr2f = float(tr2)
                    if 0.004 <= tr2f <= 0.05:
                        trailing_offset = min(0.03, max(0.006, tr2f))
        except Exception:
            pass

        idx_key = f"{decision.symbol}|{decision.side}"
        symbol_group = self._symbol_group_key(decision.symbol)
        session_group = self._market_session_key(datetime.utcnow())
        composite_group = f"{symbol_group}@{session_group}"
        sltp_prof = self._sltp_group_adaptive.get(composite_group) or self._sltp_group_adaptive.get(symbol_group) or {}
        dyn_tighten = float(sltp_prof.get("dynamic_tighten_ratio", 0.15) or 0.15)
        dyn_extend = float(sltp_prof.get("dynamic_tp_extend_ratio", 0.10) or 0.10)
        await self.main_controller.create_stop_loss_order(
            symbol=decision.symbol,
            side=decision.side,
            entry_price=entry,
            quantity=float(qty),
            stop_loss_percent=float(risk_pct),
            take_profit_percent=float(tp_pct),
            enable_trailing=True,
            trailing_offset=float(trailing_offset),
            metadata={
                "index_key": idx_key,
                "guard_profile": dict(self._adaptive_guard_profile),
                "effective_min_rr": float(min_rr),
                "spread_bps_on_open": float(spread_bps) if spread_bps is not None else None,
                "depth_imbalance_on_open": float(depth_imbalance) if depth_imbalance is not None else None,
                "dynamic_tighten_ratio": float(dyn_tighten),
                "dynamic_tp_extend_ratio": float(dyn_extend),
                "sltp_adaptive_group": composite_group if composite_group in self._sltp_group_adaptive else symbol_group,
                "trace_id": trace_id,
            },
        )
    
    async def _save_decision_to_memory(self, decision: TradeDecision, order: Dict) -> None:
        """保存AI决策到记忆"""
        if not self.memory:
            return
        
        try:
            await self.memory.add_memory(
                memory_type="trade_record",
                content=f"AI决策: {decision.symbol} {decision.action} {decision.side} @{decision.entry_price} - {decision.reasoning}",
                summary=f"🎯 AI交易决策: {decision.symbol} {decision.side} @{decision.entry_price}",
                metadata={
                    "symbol": decision.symbol,
                    "action": decision.action,
                    "side": decision.side,
                    "price": decision.entry_price,
                    "quantity": decision.quantity,
                    "leverage": decision.leverage,
                    "reasoning": decision.reasoning,
                    "strategy": decision.strategy_used,
                    "order_id": order.get('orderId'),
                },
                importance=0.9,
                source_module="ai_core_decision_engine",
                tags=["ai_decision", "trade", decision.symbol.replace("/", "")]
            )
            
            logger.info("💾 AI决策已保存到记忆库")
            
        except Exception as e:
            logger.error(f"保存AI决策失败: {e}")
    
    async def _report_decision(self, decision: TradeDecision) -> None:
        """向用户报告AI决策"""
        action_zh = {"buy": "买入", "sell": "卖出", "hold": "观望", "close": "平仓"}.get(str(decision.action).lower(), str(decision.action))
        side_zh = {"long": "做多", "short": "做空"}.get(str(decision.side).lower(), str(decision.side))
        risk_zh = {"low": "低", "medium": "中", "high": "高", "critical": "严重"}.get(str(decision.risk_level).lower(), str(decision.risk_level))
        message = f"""
🎯 AI交易决策报告

交易对: {decision.symbol}
操作: {action_zh}
方向: {side_zh}
价格: {decision.entry_price}
数量: {decision.quantity}张
杠杆: {decision.leverage}x
止损: {decision.stop_loss:.2f}
止盈: {decision.take_profit:.2f}

决策理由: {decision.reasoning}
使用策略: {decision.strategy_used}
置信度: {decision.confidence:.0%}
风险等级: {risk_zh}

时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        logger.info(message)
        
        # 即时消息统一由“司令部”转发给用户（避免模块直发 TG）
        if self.main_controller and hasattr(self.main_controller, "_send_notification_handler"):
            try:
                await self.main_controller._send_notification_handler("AI决策", message, priority="medium")
            except Exception:
                pass
    
    def get_status(self) -> Dict:
        """获取状态"""
        sm_enabled = 0
        sm_ids: List[str] = []
        if self.strategy_manager:
            for sid, cfg in (getattr(self.strategy_manager, "strategy_configs", {}) or {}).items():
                if getattr(cfg, "enabled", True):
                    sm_enabled += 1
                    sm_ids.append(sid)
        return {
            "running": self._running,
            "blacklist": list(self.blacklist),
            "authorization": self.authorization,
            "modules": {
                "llm": self.llm is not None,
                "exchange": self.exchange is not None,
                "memory": self.memory is not None,
                "strategy_manager": self.strategy_manager is not None,
                "risk_monitor": self.risk_monitor is not None,
                "telegram": self.telegram_bot is not None,
                "backtester": self.backtester is not None,
                "parameter_optimizer": self.parameter_optimizer is not None,
                "plugin_manager": self.plugin_manager is not None,
            },
            "strategies": {
                "active": sm_enabled,
                "enabled_strategy_ids": sm_ids[:32],
                "ai_core_registered": len(self._active_strategies),
                "preferred_strategy_id": self._preferred_strategy_id,
                "performance_tracked": len(self._strategy_performance),
            },
            "last_decisions": {
                symbol: time.isoformat() 
                for symbol, time in self._last_decision_time.items()
            },
            "last_strategy_check": self._last_strategy_check.isoformat() if self._last_strategy_check else None,
            "active_positions": len(self._current_positions) if hasattr(self, '_current_positions') else 0,
            "positions": self._current_positions if hasattr(self, '_current_positions') else {},
            "total_trades": len(self._trade_history) if hasattr(self, '_trade_history') else 0,
            "execution_guards": {
                "config": {
                    "min_trade_interval": self.config.get("min_trade_interval"),
                    "min_confidence_to_trade": self.config.get("min_confidence_to_trade"),
                    "ai_core_min_confidence_to_open": self.config.get("ai_core_min_confidence_to_open"),
                    "min_data_quality_to_trade": self.config.get("min_data_quality_to_trade"),
                    "min_rr_to_trade": self.config.get("min_rr_to_trade"),
                    "max_spread_bps_to_trade": self.config.get("max_spread_bps_to_trade"),
                    "max_abs_depth_imbalance_to_trade": self.config.get("max_abs_depth_imbalance_to_trade"),
                    "degraded_data_quantity_factor": self.config.get("degraded_data_quantity_factor"),
                    "boost_on_low_risk": self.config.get("boost_on_low_risk"),
                    "low_risk_rr_multiplier": self.config.get("low_risk_rr_multiplier"),
                    "low_risk_spread_multiplier": self.config.get("low_risk_spread_multiplier"),
                    "high_risk_rr_multiplier": self.config.get("high_risk_rr_multiplier"),
                    "high_risk_spread_multiplier": self.config.get("high_risk_spread_multiplier"),
                    "auto_frequency_profile_switch": self.config.get("auto_frequency_profile_switch"),
                    "frequency_profile_switch_telegram_notify": self.config.get("frequency_profile_switch_telegram_notify"),
                    "frequency_profile_cooldown_seconds": self.config.get("frequency_profile_cooldown_seconds"),
                    "frequency_profile_lookback_trades": self.config.get("frequency_profile_lookback_trades"),
                    "frequency_profile_max_drawdown_guard": self.config.get("frequency_profile_max_drawdown_guard"),
                    "auto_adaptive_guards": self.config.get("auto_adaptive_guards"),
                    "auto_tune_guards": self.config.get("auto_tune_guards"),
                    "auto_tune_by_symbol_group": self.config.get("auto_tune_by_symbol_group"),
                    "auto_tune_by_session": self.config.get("auto_tune_by_session"),
                    "auto_tune_global_enabled": self.config.get("auto_tune_global_enabled"),
                    "auto_tune_global_cooldown_seconds": self.config.get("auto_tune_global_cooldown_seconds"),
                    "auto_tune_global_step_rr": self.config.get("auto_tune_global_step_rr"),
                    "auto_tune_global_step_spread_bps": self.config.get("auto_tune_global_step_spread_bps"),
                    "auto_tune_step_rr": self.config.get("auto_tune_step_rr"),
                    "auto_tune_step_spread_bps": self.config.get("auto_tune_step_spread_bps"),
                    "auto_tune_group_step_rr": self.config.get("auto_tune_group_step_rr"),
                    "auto_tune_group_step_spread_bps": self.config.get("auto_tune_group_step_spread_bps"),
                    "auto_tune_cooldown_seconds": self.config.get("auto_tune_cooldown_seconds"),
                    "auto_tune_min_rr_delta": self.config.get("auto_tune_min_rr_delta"),
                    "auto_tune_min_spread_delta_bps": self.config.get("auto_tune_min_spread_delta_bps"),
                    "auto_tune_sltp_params": self.config.get("auto_tune_sltp_params"),
                    "auto_tune_sltp_cooldown_seconds": self.config.get("auto_tune_sltp_cooldown_seconds"),
                    "auto_tune_sltp_step_tighten": self.config.get("auto_tune_sltp_step_tighten"),
                    "auto_tune_sltp_step_extend": self.config.get("auto_tune_sltp_step_extend"),
                    "hold_avoidance_override_enabled": self.config.get("hold_avoidance_override_enabled"),
                    "hold_avoidance_override_cooldown_sec": self.config.get("hold_avoidance_override_cooldown_sec"),
                    "hold_avoidance_override_min_abs_sentiment": self.config.get("hold_avoidance_override_min_abs_sentiment"),
                    "hold_avoidance_override_min_mi_quality_score": self.config.get("hold_avoidance_override_min_mi_quality_score"),
                    "hold_avoidance_override_require_mi_trend_alignment": self.config.get("hold_avoidance_override_require_mi_trend_alignment"),
                },
                "adaptive_profile": dict(self._adaptive_guard_profile),
                "group_overrides": dict(self._symbol_group_guard_overrides),
                "sltp_group_adaptive": dict(self._sltp_group_adaptive),
                "group_last_tuned_at": {
                    k: v.isoformat() for k, v in self._last_group_tune_at.items()
                },
                "sltp_last_tuned_at": {
                    k: v.isoformat() for k, v in self._last_sltp_tune_at.items()
                },
                "global_last_tuned_at": (
                    self._last_global_tune_at.isoformat() if self._last_global_tune_at else None
                ),
                "stats": dict(self._execution_guards_stats),
                "frequency_profile": self._frequency_profile,
                "last_frequency_profile_switch_at": (
                    self._last_frequency_profile_switch_at.isoformat()
                    if self._last_frequency_profile_switch_at
                    else None
                ),
            },
        }

    async def _refresh_runtime_guard_config(self) -> None:
        """支持运行期热更新执行门控阈值（由 ai_managed_config 驱动）。"""
        if not self.main_controller or not hasattr(self.main_controller, "get_ai_managed_config"):
            return
        try:
            overrides = await self.main_controller.get_ai_managed_config("ai_core_runtime", {})
            if not isinstance(overrides, dict) or not overrides:
                return
            keys = (
                "min_trade_interval",
                "min_confidence_to_trade",
                "min_data_quality_to_trade",
                "min_rr_to_trade",
                "max_spread_bps_to_trade",
                "max_abs_depth_imbalance_to_trade",
                "degraded_data_quantity_factor",
                "boost_on_low_risk",
                "low_risk_rr_multiplier",
                "low_risk_spread_multiplier",
                "high_risk_rr_multiplier",
                "high_risk_spread_multiplier",
                "low_balance_usdt_threshold",
                "default_max_margin_fraction",
                "low_balance_margin_fraction",
                "auto_frequency_profile_switch",
                "frequency_profile_switch_telegram_notify",
                "frequency_profile_cooldown_seconds",
                "frequency_profile_lookback_trades",
                "frequency_profile_max_drawdown_guard",
                "auto_adaptive_guards",
                "auto_tune_guards",
                "auto_tune_by_symbol_group",
                "auto_tune_by_session",
                "auto_tune_global_enabled",
                "auto_tune_global_cooldown_seconds",
                "auto_tune_global_step_rr",
                "auto_tune_global_step_spread_bps",
                "auto_tune_step_rr",
                "auto_tune_step_spread_bps",
                "auto_tune_group_step_rr",
                "auto_tune_group_step_spread_bps",
                "auto_tune_cooldown_seconds",
                "auto_tune_min_rr_delta",
                "auto_tune_min_spread_delta_bps",
                "auto_tune_sltp_params",
                "auto_tune_sltp_cooldown_seconds",
                "auto_tune_sltp_step_tighten",
                "auto_tune_sltp_step_extend",
            )
            for k in keys:
                if k in overrides and overrides[k] is not None:
                    if k in (
                        "auto_adaptive_guards",
                        "auto_tune_guards",
                        "auto_tune_by_symbol_group",
                        "auto_tune_by_session",
                        "auto_tune_global_enabled",
                        "auto_tune_sltp_params",
                        "boost_on_low_risk",
                        "auto_frequency_profile_switch",
                        "frequency_profile_switch_telegram_notify",
                    ):
                        self.config[k] = bool(overrides[k])
                    elif k in (
                        "auto_tune_group_step_rr",
                        "auto_tune_group_step_spread_bps",
                        "low_balance_usdt_threshold",
                        "default_max_margin_fraction",
                        "low_balance_margin_fraction",
                    ):
                        v = overrides[k]
                        self.config[k] = None if v == "" or v == "null" else float(v)
                    else:
                        self.config[k] = float(overrides[k])
        except Exception as e:
            logger.debug(f"刷新运行期门控配置失败: {e}")
    
    async def process_user_command(self, command: str) -> Dict[str, Any]:
        """处理用户命令 - 纯自然语言交流，AI直接理解并执行"""
        try:
            # 直接使用LLM理解用户意图并执行
            return await self._handle_general_command(command)
                
        except Exception as e:
            logger.error(f"处理用户命令失败: {e}")
            return {"success": False, "response": f"处理失败: {str(e)}"}
    
    async def _get_detailed_status_report(self) -> str:
        """获取详细状态报告"""
        status = self.get_status()
        
        report = "📊 AI核心系统状态报告\n\n"
        
        report += "【运行状态】\n"
        report += f"运行中: {'✅' if status['running'] else '❌'}\n"
        report += f"最后策略检查: {status.get('last_strategy_check', '未检查')}\n\n"
        
        report += "【授权状态】\n"
        for key, value in status['authorization'].items():
            report += f"  {key}: {'✅' if value else '❌'}\n"
        
        report += "\n【模块连接】\n"
        for name, connected in status['modules'].items():
            report += f"  {name}: {'✅' if connected else '❌'}\n"
        
        report += f"\n【策略管理】\n"
        report += f"  活跃策略: {status['strategies']['active']}个\n"
        report += f"  已回测: {status['strategies']['performance_tracked']}个\n"
        
        report += f"\n【用户规则】\n"
        report += f"  黑名单: {status['blacklist']}\n"
        
        # 添加实时持仓信息
        if self.exchange:
            try:
                positions = await self.exchange.get_positions()
                active_pos = [p for p in positions if float(p.get('size', 0) or 0) != 0]
                if active_pos:
                    report += f"\n【当前持仓】\n"
                    for pos in active_pos[:5]:
                        symbol = pos.get('symbol', '')
                        side = pos.get('side', '')
                        size = pos.get('size', 0)
                        pnl = float(pos.get('unrealized_pnl', 0) or 0)
                        report += f"  {symbol}: {side} {size} | 盈亏: ${pnl:+.2f}\n"
            except Exception as e:
                logger.debug(f"获取实时持仓信息失败: {e}")
        
        return report
    
    async def _handle_position_query(self, command: str) -> Dict[str, Any]:
        """处理持仓查询"""
        if not self.exchange:
            return {"success": False, "response": "交易所未连接"}
        
        try:
            positions = await self.exchange.get_positions()
            
            if not positions:
                return {"success": True, "response": "当前没有持仓"}
            
            response = "📊 当前持仓详情\n\n"
            total_pnl = 0
            
            for pos in positions:
                symbol = pos.get('instId', '')
                side = pos.get('posSide', '')
                size = pos.get('pos', '')
                entry = float(pos.get('avgPx', 0))
                pnl = float(pos.get('upl', 0))
                pnl_ratio = float(pos.get('uplRatio', 0))
                
                total_pnl += pnl
                
                # 检查是否在黑名单
                in_blacklist = any(bl in symbol for bl in self.blacklist)
                blacklist_note = " ⚠️(黑名单)" if in_blacklist else ""
                
                response += f"{'🟢' if side == 'long' else '🔴'} {symbol}: {side} {size}\n"
                response += f"   入场价: {entry:.4f}\n"
                response += f"   盈亏: ${pnl:+.2f} ({pnl_ratio:+.2%}){blacklist_note}\n\n"
            
            response += f"总盈亏: ${total_pnl:+.2f}"
            
            return {"success": True, "response": response}
            
        except Exception as e:
            return {"success": False, "response": f"查询持仓失败: {str(e)}"}
    
    async def _handle_third_party_data_query(self, command: str) -> Dict[str, Any]:
        """处理第三方数据查询"""
        response = "📊 第三方数据系统状态\n\n"
        
        # 1. 检查多源数据融合
        fusion_found = False
        if self.main_controller and hasattr(self.main_controller, 'ai_trading_engine'):
            engine = self.main_controller.ai_trading_engine
            if engine and hasattr(engine, 'multi_source_fusion') and engine.multi_source_fusion:
                response += "✅ 多源数据融合系统\n"
                response += "   功能: 综合分析市场情绪、技术指标、链上数据\n"
                response += "   状态: 运行中\n\n"
                fusion_found = True
        
        if not fusion_found and self.main_controller and hasattr(self.main_controller, 'multi_source_data_fusion'):
            fusion = self.main_controller.multi_source_data_fusion
            if fusion:
                response += "✅ 多源数据融合系统\n"
                response += "   功能: 综合分析市场情绪、技术指标、链上数据\n"
                response += "   状态: 运行中\n\n"
                fusion_found = True
        
        # 2. 检查第三方数据集成器
        if self.main_controller and hasattr(self.main_controller, 'third_party_integrator'):
            integrator = self.main_controller.third_party_integrator
            if integrator:
                response += "✅ 第三方数据集成器\n"
                response += "   功能: 整合新闻、社交媒体、链上数据\n"
                response += "   状态: 运行中\n\n"
        
        # 3. 检查插件管理器
        if self.plugin_manager:
            plugins_info = self.plugin_manager.get_all_plugin_info() if hasattr(self.plugin_manager, 'get_all_plugin_info') else {}
            if plugins_info:
                response += f"✅ 插件管理器\n"
                response += f"   已加载插件: {len(plugins_info)}个\n"
                for name in list(plugins_info.keys())[:3]:
                    response += f"   - {name}\n"
                response += "\n"
        
        # 4. 获取最近的分析结果
        analysis_added = False
        if self.exchange:
            try:
                for symbol in ["BTC/USDT", "SOL/USDT", "DOGE/USDT"]:
                    analysis = await self._get_third_party_data(symbol)
                    if analysis.get('available'):
                        response += f"📈 {symbol} 最新数据分析\n"
                        response += f"   数据可用: ✅\n"
                        response += f"   市场情绪: {analysis.get('sentiment', 'neutral')}\n"
                        if analysis.get('fear_greed_index'):
                            response += f"   恐惧贪婪指数: {analysis.get('fear_greed_index')}\n"
                        response += "\n"
                        analysis_added = True
                        break
            except Exception as e:
                response += f"⚠️ 获取分析数据时出错: {str(e)}\n\n"
        
        if not fusion_found and not analysis_added:
            response += "⚠️ 当前未检测到活跃的第三方数据源\n"
            response += "但AI核心决策引擎仍可正常工作\n"
        
        return {"success": True, "response": response}
    
    async def _handle_strategy_list_query(self, command: str) -> Dict[str, Any]:
        """处理策略列表查询"""
        strategies = getattr(self.strategy_manager, 'strategy_configs', {}) if self.strategy_manager else {}
        
        if not strategies:
            return {"success": True, "response": "目前还没有创建策略。需要我自动创建吗？"}
        
        response = f"📊 策略列表\n\n"
        response += f"已注册策略: {len(strategies)}个\n\n"
        
        for sid, config in list(strategies.items())[:5]:
            name = getattr(config, 'name', 'Unknown') if hasattr(config, 'name') else config.get('name', 'Unknown')
            stype = getattr(config, 'strategy_type', 'unknown') if hasattr(config, 'strategy_type') else config.get('strategy_type', 'unknown')
            response += f"• {name} ({stype})\n"
        
        return {"success": True, "response": response}
    
    async def _handle_trade_history_query(self, command: str) -> Dict[str, Any]:
        """处理交易历史查询"""
        if not self.memory:
            return {"success": False, "response": "记忆系统未连接"}
        
        try:
            memories = await self.memory.retrieve_memories(
                query="交易 决策 开仓 平仓",
                min_importance=0.8,
                limit=10
            )
            
            if not memories:
                return {"success": True, "response": "暂无交易记录"}
            
            response = "📊 最近交易记录\n\n"
            
            for i, mem in enumerate(memories[:10]):
                content = mem.content[:100]
                timestamp = mem.timestamp.strftime('%m-%d %H:%M') if hasattr(mem, 'timestamp') else ''
                response += f"{i+1}. [{timestamp}] {content}...\n"
            
            return {"success": True, "response": response}
            
        except Exception as e:
            return {"success": False, "response": f"查询失败: {str(e)}"}
    
    async def _handle_risk_query(self, command: str) -> Dict[str, Any]:
        """处理风险查询"""
        if not self.risk_monitor:
            return {"success": False, "response": "风险监控未连接"}
        
        try:
            risk_data = await self.risk_monitor.check_account_risk()
            
            response = "📊 风险评估报告\n\n"
            
            if hasattr(risk_data, 'risk_level'):
                level = risk_data.risk_level.value
                level_emoji = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}.get(level, "⚪")
                response += f"风险等级: {level_emoji} {level.upper()}\n"
            
            if hasattr(risk_data, 'margin_ratio'):
                response += f"保证金比例: {risk_data.margin_ratio:.2%}\n"
            
            # 检查持仓风险
            if self.exchange:
                positions = await self.exchange.get_positions()
                for pos in positions:
                    symbol = pos.get('instId', '')
                    pnl_ratio = float(pos.get('uplRatio', 0))
                    
                    # 忽略黑名单币种
                    if any(bl in symbol for bl in self.blacklist):
                        continue
                    
                    if pnl_ratio < -0.05:
                        response += f"\n⚠️ {symbol} 亏损较大: {pnl_ratio:.2%}"
            
            return {"success": True, "response": response}
            
        except Exception as e:
            return {"success": False, "response": f"查询失败: {str(e)}"}
    
    async def _handle_account_query(self, command: str) -> Dict[str, Any]:
        """处理账户查询"""
        if not self.exchange:
            return {"success": False, "response": "交易所未连接"}
        
        try:
            balance = await self.exchange.get_balance()
            
            response = "📊 账户信息\n\n"
            
            total_usdt = 0
            for currency, amount in balance.items():
                if isinstance(amount, dict):
                    free = amount.get('free', 0)
                    locked = amount.get('locked', 0)
                    if free > 0 or locked > 0:
                        response += f"{currency}: {free:.2f} (锁定: {locked:.2f})\n"
                        if currency == 'USDT':
                            total_usdt = free
                elif isinstance(amount, (int, float)) and amount > 0:
                    response += f"{currency}: {amount:.2f}\n"
                    if currency == 'USDT':
                        total_usdt = amount
            
            # 获取持仓数量
            positions = await self.exchange.get_positions()
            active_positions = [p for p in positions if float(p.get('pos', 0)) != 0]
            
            response += f"\n总持仓数: {len(active_positions)}个"
            response += f"\n可用余额: ${total_usdt:.2f} USDT"
            
            return {"success": True, "response": response}
            
        except Exception as e:
            return {"success": False, "response": f"查询失败: {str(e)}"}
    
    async def _handle_create_strategy_command(self, command: str) -> Dict[str, Any]:
        """处理创建策略命令"""
        market_overview = await self._get_market_overview()
        proposal = await self._ai_generate_strategy_proposal(market_overview)
        
        if proposal:
            success = await self._create_strategy_from_proposal(proposal)
            if success:
                return {
                    "success": True,
                    "response": f"✅ AI已创建策略: {proposal.name}\n类型: {proposal.strategy_type}\n交易对: {', '.join(proposal.symbols)}\n理由: {proposal.reasoning}"
                }
        
        return {"success": False, "response": "策略创建失败"}
    
    async def _handle_backtest_command(self, command: str) -> Dict[str, Any]:
        """处理回测命令"""
        strategies = getattr(self.strategy_manager, 'strategy_configs', {})
        
        if not strategies:
            return {"success": False, "response": "没有可回测的策略"}
        
        strategy_id = list(strategies.keys())[0]
        result = await self._run_backtest(strategy_id)
        
        if result:
            return {
                "success": True,
                "response": f"✅ 回测完成\n收益率: {result.get('total_return', 0):.2%}\n最大回撤: {result.get('max_drawdown', 0):.2%}\n夏普比率: {result.get('sharpe_ratio', 0):.2f}"
            }
        
        return {"success": False, "response": "回测失败"}
    
    async def _handle_optimize_command(self, command: str) -> Dict[str, Any]:
        """处理优化命令"""
        strategies = getattr(self.strategy_manager, 'strategy_configs', {})
        
        if not strategies:
            return {"success": False, "response": "没有可优化的策略"}
        
        strategy_id = list(strategies.keys())[0]
        result = await self._optimize_strategy(strategy_id)
        
        if result:
            return {
                "success": True,
                "response": f"✅ 策略优化完成\n{result.get('improvement', '')}"
            }
        
        return {"success": False, "response": "优化失败"}
    
    async def _handle_trade_command(self, command: str) -> Dict[str, Any]:
        """处理交易命令"""
        if not self.authorization.get("auto_trading"):
            return {"success": False, "response": "未授权交易"}
        
        symbol = "BTC/USDT"
        if "SOL" in command:
            symbol = "SOL/USDT"
        elif "BNB" in command:
            symbol = "BNB/USDT"
        
        if symbol in self.blacklist:
            return {"success": True, "response": f"{symbol} 在黑名单中，不执行交易"}
        
        decision = await self._ai_analyze_and_decide(symbol)
        
        if decision and decision.action != "hold":
            success = await self._execute_decision(decision, bypass_discretionary_close_gates=True)
            if success:
                return {
                    "success": True,
                    "response": f"✅ AI执行交易: {decision.symbol} {decision.action} {decision.side}\n价格: {decision.entry_price}\n数量: {decision.quantity}张\n杠杆: {decision.leverage}x"
                }
        
        return {"success": True, "response": "AI决定暂不交易"}
    
    async def _handle_close_command(self, command: str) -> Dict[str, Any]:
        """处理平仓命令"""
        if not self.exchange:
            return {"success": False, "response": "交易所未连接"}
        
        try:
            positions = await self.exchange.get_positions()
            
            closed = []
            for pos in positions:
                symbol = pos.get('instId', '')
                side = pos.get('posSide', 'long')
                res = await self._s1_close_swap(
                    symbol,
                    side,
                    None,
                    "manual",
                    "user_close_all_command",
                )
                if res.get("success"):
                    closed.append(f"{symbol} {side}")
                else:
                    logger.error(
                        "平仓失败 %s %s: %s",
                        symbol,
                        side,
                        res.get("error"),
                    )
            
            if closed:
                return {"success": True, "response": f"✅ AI已平仓: {', '.join(closed)}"}
            
            return {"success": True, "response": "没有持仓需要平仓"}
            
        except Exception as e:
            return {"success": False, "response": f"平仓失败: {str(e)}"}
    
    async def _handle_general_command(self, command: str) -> Dict[str, Any]:
        """处理通用命令 - 纯自然语言，AI理解并执行"""
        if not self.llm:
            return {"success": False, "response": "LLM未连接"}
        
        try:
            # 获取完整的系统上下文
            context = await self._build_conversation_context()
            
            # 构建prompt
            prompt = f"""你是一个拥有完整控制权的量化交易AI助手。用户通过Telegram与你交流。

{context}

【用户消息】
{command}

【你的能力】
你可以执行以下操作：
1. 查询账户余额、持仓、交易历史
2. 分析市场行情、技术指标
3. 执行交易（开仓、平仓）
4. 创建、回测、优化策略
5. 查看风险状态
6. 查看第三方数据分析结果
7. 回答任何问题

【重要规则】
- 黑名单已清空，所有交易对均可操作
- 用自然语言回复，简洁专业
- 如果用户要求执行操作，先确认当前状态再执行
- 保持对话自然流畅

请直接回复用户，不要使用Markdown格式。"""

            response = await self.llm.generate(prompt, is_user_input=False)
            
            if response and response.success and response.content:
                return {"success": True, "response": response.content}
            elif response and not response.success:
                error_msg = response.error_message or "LLM调用失败"
                logger.error(f"LLM响应失败: {error_msg}")
                return {"success": False, "response": f"AI处理失败: {error_msg}"}
            elif response and not response.content:
                return {"success": False, "response": "AI返回了空响应"}
            
            return {"success": False, "response": "无法处理"}
            
        except Exception as e:
            logger.error(f"处理通用命令失败: {e}")
            return {"success": False, "response": f"处理失败: {str(e)}"}
    
    async def _build_conversation_context(self) -> str:
        """构建对话上下文 - 包含所有模块的实时状态"""
        context_parts = []
        
        # 1. 基本状态
        status = self.get_status()
        context_parts.append(f"""【系统状态】
- 运行中: {'是' if status['running'] else '否'}
- 授权状态: {status['authorization']}
- 活跃策略: {status['strategies']['active']}个
- 黑名单: {status['blacklist']}""")
        
        # 2. 模块连接状态
        modules_status = []
        for name, connected in status['modules'].items():
            modules_status.append(f"  {name}: {'已连接' if connected else '未连接'}")
        context_parts.append(f"""【模块连接】
{chr(10).join(modules_status)}""")
        
        # 3. 账户余额
        if self.exchange:
            try:
                balance = await self.exchange.get_balance()
                usdt = balance.get('USDT', {})
                if isinstance(usdt, dict):
                    available = usdt.get('free', 0)
                else:
                    available = usdt
                context_parts.append(f"""【账户余额】
- 可用USDT: {available:.2f}""")
            except Exception as e:
                logger.debug(f"获取余额失败: {e}")
        
        # 4. 当前持仓 - 重要！
        if self.exchange:
            try:
                positions = await self.exchange.get_positions()
                # get_positions 返回的字段: symbol, side, size, entry_price, unrealized_pnl
                active_pos = [p for p in positions if float(p.get('size', 0) or 0) != 0]
                logger.debug(f"对话上下文获取到 {len(active_pos)} 个活跃持仓")
                if active_pos:
                    pos_info = []
                    for p in active_pos[:10]:
                        symbol = p.get('symbol', '')
                        side = p.get('side', '')
                        size = p.get('size', 0)
                        pnl = float(p.get('unrealized_pnl', 0) or 0)
                        entry_price = float(p.get('entry_price', 0) or 0)
                        pos_info.append(f"  {symbol}: {side} {size} | 入场价: {entry_price:.4f} | 盈亏: ${pnl:+.2f}")
                    context_parts.append(f"""【当前持仓】(共{len(active_pos)}个)
{chr(10).join(pos_info)}""")
                else:
                    context_parts.append("""【当前持仓】
- 无持仓""")
            except Exception as e:
                logger.error(f"获取持仓失败: {e}")
                context_parts.append("""【当前持仓】
- 获取失败，请检查交易所连接""")
        
        # 5. 最近市场数据
        if self.exchange:
            try:
                btc_ticker = await self.exchange.get_ticker('BTC-USDT-SWAP')
                if btc_ticker:
                    context_parts.append(f"""【BTC行情】
- 价格: {btc_ticker.get('last', 0)}
- 24h涨跌: {float(btc_ticker.get('change24h', 0) or 0):.2%}""")
            except Exception as e:
                logger.debug(f"获取BTC行情失败: {e}")
        
        # 6. 从记忆获取最近的对话
        if self.memory:
            try:
                recent_memories = await self.memory.retrieve_memories(
                    query="用户 偏好 规则 设置 交易 持仓",
                    min_importance=0.5,
                    limit=5
                )
                if recent_memories:
                    mem_info = [f"  - {m.content[:150]}" for m in recent_memories]
                    context_parts.append(f"""【用户偏好/规则/历史】
{chr(10).join(mem_info)}""")
            except Exception as e:
                logger.debug(f"获取记忆失败: {e}")
        
        return "\n\n".join(context_parts)
    
    def _format_status_report(self) -> str:
        """格式化状态报告"""
        status = self.get_status()
        
        report = "📊 AI核心决策引擎状态报告\n\n"
        
        report += "【运行状态】\n"
        report += f"运行中: {'✅' if status['running'] else '❌'}\n"
        report += f"最后策略检查: {status.get('last_strategy_check', '未检查')}\n\n"
        
        report += "【授权状态】\n"
        for key, value in status['authorization'].items():
            report += f"  {key}: {'✅' if value else '❌'}\n"
        
        report += "\n【模块连接】\n"
        for name, connected in status['modules'].items():
            report += f"  {name}: {'✅' if connected else '❌'}\n"
        
        report += f"\n【策略管理】\n"
        report += f"  活跃策略: {status['strategies']['active']}个\n"
        report += f"  已回测: {status['strategies']['performance_tracked']}个\n"
        
        report += f"\n【用户规则】\n"
        report += f"  黑名单: {status['blacklist']}\n"
        
        return report


    async def cleanup(self):
        """清理资源"""
        pass
