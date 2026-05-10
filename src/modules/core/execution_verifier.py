"""
执行验证模块 - 确保AI命令真正执行

核心功能：
1. 命令解析和分类
2. 执行状态追踪
3. 结果验证和反馈
4. 审计日志记录
5. 执行状态查询

使用方式：
- 每个执行操作必须通过此模块
- 返回结构化的执行结果
- 用户可随时查询执行状态
"""

import asyncio
import logging
import json
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)
from src.modules.core.decision_contract import validate_envelope


class CommandType(Enum):
    """命令类型"""
    OPEN_POSITION = "open_position"       # 开仓
    CLOSE_POSITION = "close_position"     # 平仓
    SET_STOP_LOSS = "set_stop_loss"       # 设置止损
    SET_TAKE_PROFIT = "set_take_profit"   # 设置止盈
    MODIFY_ORDER = "modify_order"         # 修改订单
    CANCEL_ORDER = "cancel_order"         # 取消订单
    QUERY_POSITION = "query_position"     # 查询持仓
    QUERY_BALANCE = "query_balance"       # 查询余额
    ANALYZE_MARKET = "analyze_market"     # 分析市场
    OPTIMIZE_STRATEGY = "optimize_strategy"  # 优化策略
    BACKTEST = "backtest"                 # 回测
    OTHER = "other"                       # 其他


class ExecutionStatus(Enum):
    """执行状态"""
    PENDING = "pending"           # 待执行
    EXECUTING = "executing"       # 执行中
    SUCCESS = "success"           # 成功
    FAILED = "failed"             # 失败
    PARTIAL = "partial"           # 部分成功
    CANCELLED = "cancelled"       # 已取消
    TIMEOUT = "timeout"           # 超时


@dataclass
class ExecutionResult:
    """执行结果"""
    execution_id: str
    command_type: CommandType
    action: str
    status: ExecutionStatus
    symbol: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    duration_ms: float = 0.0
    verified: bool = False
    verification_details: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "command_type": self.command_type.value,
            "action": self.action,
            "status": self.status.value,
            "symbol": self.symbol,
            "details": self.details,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "verified": self.verified,
            "verification_details": self.verification_details
        }
    
    def to_user_message(self) -> str:
        """生成用户可读的执行结果消息"""
        status_emoji = {
            ExecutionStatus.SUCCESS: "✅",
            ExecutionStatus.FAILED: "❌",
            ExecutionStatus.PENDING: "⏳",
            ExecutionStatus.EXECUTING: "🔄",
            ExecutionStatus.PARTIAL: "⚠️",
            ExecutionStatus.CANCELLED: "🚫",
            ExecutionStatus.TIMEOUT: "⏰"
        }
        
        emoji = status_emoji.get(self.status, "❓")
        
        if self.status == ExecutionStatus.SUCCESS:
            msg = f"{emoji} 执行成功\n"
            msg += f"操作: {self.action}\n"
            if self.symbol:
                msg += f"交易对: {self.symbol}\n"
            if self.details:
                for key, value in self.details.items():
                    if key not in ["raw_response", "internal_data"]:
                        msg += f"{key}: {value}\n"
            msg += f"执行时间: {self.duration_ms:.0f}ms"
            return msg
        
        elif self.status == ExecutionStatus.FAILED:
            msg = f"{emoji} 执行失败\n"
            msg += f"操作: {self.action}\n"
            if self.error_message:
                msg += f"原因: {self.error_message}"
            return msg
        
        else:
            return f"{emoji} {self.action} - {self.status.value}"


@dataclass
class ExecutionConfig:
    """执行配置"""
    timeout_seconds: int = 30
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    log_dir: str = "logs/executions"
    enable_verification: bool = True
    verification_timeout_seconds: int = 10
    # verifier 开仓探针在同一 symbol 上的最小间隔（秒）；0 表示关闭。压制 execution_verifier_open 风暴。
    verifier_open_symbol_cooldown_sec: float = 900.0


class ExecutionVerifier:
    """
    执行验证器
    
    确保AI命令真正执行，提供可验证的执行结果
    """

    @staticmethod
    def _resolve_writable_log_dir(preferred: Path) -> Path:
        """与 AuditLogger 一致：宿主机挂载权限异常时选用可写目录。"""
        for d in (preferred, Path("data/executions"), Path("/tmp/openclaw_executions")):
            try:
                d.mkdir(parents=True, exist_ok=True)
                probe = d / ".exec_write_probe"
                probe.write_bytes(b"")
                probe.unlink()
                if d.resolve() != preferred.resolve():
                    logger.warning("执行记录目录 %s 不可写，已改用: %s", preferred, d)
                return d
            except OSError:
                continue
        return preferred
    
    def __init__(self, config: Optional[ExecutionConfig] = None):
        self.config = config or ExecutionConfig()
        
        self.execution_history: Dict[str, ExecutionResult] = {}
        self.pending_executions: Dict[str, ExecutionResult] = {}
        
        self._executors: Dict[CommandType, Callable] = {}
        self._verifiers: Dict[CommandType, Callable] = {}
        
        self._log_path = self._resolve_writable_log_dir(Path(self.config.log_dir))
        
        self._stats = {
            "total_executions": 0,
            "successful": 0,
            "failed": 0,
            "pending": 0
        }
        
        self._exchange = None
        self._audit_logger = None
        self._stop_loss_manager = None
        self._main_controller = None
        self._verifier_symbol_last_open: Dict[str, float] = {}

        logger.info(
            "执行验证器初始化完成 verifier_open_symbol_cooldown_sec=%.1f",
            float(getattr(self.config, "verifier_open_symbol_cooldown_sec", 0.0) or 0.0),
        )
    
    def set_main_controller(self, main_controller: Any) -> None:
        """注入主控制器，用于 S1（ExecutionGateway）统一开平仓出口。"""
        self._main_controller = main_controller
    
    def set_exchange(self, exchange):
        """设置交易所实例"""
        self._exchange = exchange
    
    def set_audit_logger(self, audit_logger):
        """设置审计日志记录器"""
        self._audit_logger = audit_logger
    
    def set_stop_loss_manager(self, stop_loss_manager):
        """设置止盈止损管理器"""
        self._stop_loss_manager = stop_loss_manager
    
    def register_executor(self, command_type: CommandType, executor: Callable):
        """注册执行器"""
        self._executors[command_type] = executor
    
    def register_verifier(self, command_type: CommandType, verifier: Callable):
        """注册验证器"""
        self._verifiers[command_type] = verifier

    @staticmethod
    def _symbol_key_for_verifier_cooldown(sym: str) -> str:
        x = str(sym or "").strip().upper().replace("-SWAP", "").replace("/SWAP", "")
        x = x.split(":")[0] if ":" in x else x
        return x or "__unknown__"

    @staticmethod
    def _normalize_swap_side(raw: Any) -> Optional[str]:
        if raw is None:
            return None
        s = str(raw).strip().lower()
        if s in ("long", "buy", "b"):
            return "long"
        if s in ("short", "sell", "s"):
            return "short"
        return None

    def _policy_denied_error(self, err: str) -> bool:
        e = (err or "").lower()
        return "policy_denied" in e or "open_policy_denied" in e

    async def execute(
        self,
        command_type: CommandType,
        action: str,
        symbol: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> ExecutionResult:
        """
        执行命令并返回结果
        
        Args:
            command_type: 命令类型
            action: 操作描述
            symbol: 交易对
            params: 执行参数
        
        Returns:
            执行结果
        """
        execution_id = self._generate_execution_id()
        
        result = ExecutionResult(
            execution_id=execution_id,
            command_type=command_type,
            action=action,
            status=ExecutionStatus.PENDING,
            symbol=symbol
        )
        
        self.execution_history[execution_id] = result
        self._stats["total_executions"] += 1
        self._stats["pending"] += 1
        
        start_time = time.time()
        
        try:
            result.status = ExecutionStatus.EXECUTING
            self.pending_executions[execution_id] = result
            
            executor = self._executors.get(command_type)
            
            if executor:
                execution_params = params or {}
                execution_result = await self._execute_with_timeout(
                    executor, execution_params
                )
                
                if execution_result.get("success", False):
                    result.status = ExecutionStatus.SUCCESS
                    result.details = execution_result.get("details", {})
                    self._stats["successful"] += 1
                else:
                    result.status = ExecutionStatus.FAILED
                    result.error_message = execution_result.get("error", "执行失败")
                    self._stats["failed"] += 1
            else:
                result = await self._default_execute(command_type, action, symbol, params)
            
            if self.config.enable_verification and result.status == ExecutionStatus.SUCCESS:
                verification = await self._verify_execution(result)
                result.verified = verification.get("verified", False)
                result.verification_details = verification.get("details", "")
            
        except asyncio.TimeoutError:
            result.status = ExecutionStatus.TIMEOUT
            result.error_message = f"执行超时（{self.config.timeout_seconds}秒）"
            self._stats["failed"] += 1
            
        except Exception as e:
            result.status = ExecutionStatus.FAILED
            result.error_message = str(e)
            self._stats["failed"] += 1
            logger.error(f"执行失败: {action} - {e}")
        
        finally:
            result.duration_ms = (time.time() - start_time) * 1000
            result.timestamp = datetime.now()
            
            if execution_id in self.pending_executions:
                del self.pending_executions[execution_id]
            self._stats["pending"] -= 1
            
            await self._log_execution(result)
            
            if self._audit_logger:
                await self._audit_log(result)
        
        return result
    
    async def _execute_with_timeout(
        self,
        executor: Callable,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """带超时的执行"""
        try:
            result = await asyncio.wait_for(
                executor(**params),
                timeout=self.config.timeout_seconds
            )
            return result
        except asyncio.TimeoutError:
            raise
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _default_execute(
        self,
        command_type: CommandType,
        action: str,
        symbol: Optional[str],
        params: Optional[Dict[str, Any]]
    ) -> ExecutionResult:
        """默认执行逻辑"""
        result = self.execution_history.get(
            list(self.execution_history.keys())[-1]
        ) if self.execution_history else None
        
        if not result:
            result = ExecutionResult(
                execution_id=self._generate_execution_id(),
                command_type=command_type,
                action=action,
                status=ExecutionStatus.FAILED,
                symbol=symbol,
                error_message="无法创建执行结果"
            )
            return result
        
        params = params or {}
        
        try:
            if command_type == CommandType.OPEN_POSITION:
                return await self._execute_open_position(result, symbol, params)
            
            elif command_type == CommandType.CLOSE_POSITION:
                return await self._execute_close_position(result, symbol, params)
            
            elif command_type == CommandType.SET_STOP_LOSS:
                return await self._execute_set_stop_loss(result, symbol, params)
            
            elif command_type == CommandType.QUERY_POSITION:
                return await self._execute_query_position(result, symbol, params)
            
            elif command_type == CommandType.QUERY_BALANCE:
                return await self._execute_query_balance(result, params)
            
            elif command_type == CommandType.ANALYZE_MARKET:
                return await self._execute_analyze_market(result, symbol, params)
            
            else:
                result.status = ExecutionStatus.SUCCESS
                result.details = {"message": f"命令 {action} 已记录"}
                self._stats["successful"] += 1
                return result
                
        except Exception as e:
            result.status = ExecutionStatus.FAILED
            result.error_message = str(e)
            self._stats["failed"] += 1
            return result
    
    async def _execute_open_position(
        self,
        result: ExecutionResult,
        symbol: Optional[str],
        params: Dict[str, Any]
    ) -> ExecutionResult:
        """执行开仓（强制经 ExecutionGateway / S1；禁止直连交易所回退）。"""
        if not self._exchange:
            result.status = ExecutionStatus.FAILED
            result.error_message = "交易所未连接"
            self._stats["failed"] += 1
            return result

        params = params or {}
        env = params.get("decision_envelope") if isinstance(params.get("decision_envelope"), dict) else None
        if env:
            ok_env, why_env = validate_envelope(env)
            if not ok_env:
                result.status = ExecutionStatus.FAILED
                result.error_message = str(why_env)
                self._stats["failed"] += 1
                return result
            sym = env.get("symbol") or symbol or params.get("symbol")
            side = self._normalize_swap_side(env.get("side") or params.get("side", "long")) or "long"
            quantity = float(env.get("quantity", params.get("quantity", 0)) or 0)
            leverage = int(env.get("leverage", params.get("leverage") or 20) or 20)
        else:
            sym = symbol or params.get("symbol")
            side = self._normalize_swap_side(params.get("side", "long")) or "long"
            quantity = float(params.get("quantity", 0) or 0)
            leverage = int(params.get("leverage") or 20)
        # CRITICAL: 不允许“省略即特权”。write_source 缺失则视为 unknown，交由 S1 policy 决定是否放行。
        write_source = str(params.get("write_source") or params.get("source") or "unknown").strip().lower()
        price = params.get("price")
        order_type = params.get("order_type", "market")

        gw = None
        if self._main_controller is not None:
            gw = getattr(self._main_controller, "execution_gateway", None)

        if not gw or not sym:
            result.status = ExecutionStatus.FAILED
            result.error_message = "execution_gateway_not_ready"
            self._stats["failed"] += 1
            return result

        cd = float(getattr(self.config, "verifier_open_symbol_cooldown_sec", 0.0) or 0.0)
        nk = self._symbol_key_for_verifier_cooldown(sym)
        if cd > 0:
            now = time.time()
            last = float(self._verifier_symbol_last_open.get(nk, 0.0) or 0.0)
            if last > 0 and (now - last) < cd:
                remain = cd - (now - last)
                result.status = ExecutionStatus.FAILED
                result.error_message = (
                    f"execution_verifier_open_symbol_cooldown: {nk} wait {remain:.0f}s (min_interval={cd:.0f}s)"
                )
                self._stats["failed"] += 1
                logger.warning(
                    "VERIFIER_OPEN_COOLDOWN_SKIP symbol=%s remain_sec=%.0f cooldown_sec=%.0f",
                    nk,
                    remain,
                    cd,
                )
                return result

        try:
            gres = await gw.open_swap(
                sym,
                side,
                quantity,
                leverage,
                write_source,
                "execution_verifier_open",
                margin_mode="cross",
                price=price,
                context={
                    "write_source": write_source,
                    "symbol": sym,
                    "side": side,
                    "quantity": quantity,
                    "leverage": leverage,
                    "entry_price": params.get("entry_price"),
                    "stop_loss": params.get("stop_loss"),
                    "take_profit": params.get("take_profit"),
                    "trace_id": params.get("trace_id"),
                    "strategy_used": params.get("strategy_used") or params.get("strategy_id"),
                    "strategy_id": params.get("strategy_id") or params.get("strategy_used"),
                },
            )
        except Exception as e:
            result.status = ExecutionStatus.FAILED
            result.error_message = str(e)
            self._stats["failed"] += 1
            return result

        if gres.get("success"):
            if cd > 0:
                self._verifier_symbol_last_open[nk] = time.time()
            result.status = ExecutionStatus.SUCCESS
            result.details = {
                "order_id": (gres.get("orderId") or gres.get("order_id") or gres.get("id")),
                "symbol": sym,
                "side": side,
                "quantity": quantity,
                "price": gres.get("average", price),
                "status": "filled",
                "gateway": True,
                "trace_id": gres.get("trace_id") or params.get("trace_id"),
            }
            self._stats["successful"] += 1
            # 僅在明確傳入 SL/TP 配置時註冊，避免僅有數字 stop_loss 時誤用默認百分比，
            # 與 ai_core 開倉後 _sync_dynamic_sltp_after_open 重複掛單（雙 index、雙平倉風險）。
            if (
                self._stop_loss_manager
                and params.get("stop_loss_config") is not None
                and params.get("take_profit_config") is not None
            ):
                ep = float(gres.get("average") or params.get("entry_price") or price or 0)
                if ep > 0:
                    await self._stop_loss_manager.create_order(
                        symbol=sym,
                        side=side,
                        entry_price=ep,
                        quantity=quantity,
                        stop_loss_config=params.get("stop_loss_config"),
                        take_profit_config=params.get("take_profit_config"),
                        metadata=params.get("sltp_metadata"),
                    )
            return result

        err = str(gres.get("error") or "")
        result.status = ExecutionStatus.FAILED
        result.error_message = err or "open_failed"
        self._stats["failed"] += 1
        return result
    
    async def _execute_close_position(
        self,
        result: ExecutionResult,
        symbol: Optional[str],
        params: Dict[str, Any]
    ) -> ExecutionResult:
        """执行平仓（优先经 ExecutionGateway / S1）。"""
        if not self._exchange:
            result.status = ExecutionStatus.FAILED
            result.error_message = "交易所未连接"
            self._stats["failed"] += 1
            return result

        params = params or {}
        env = params.get("decision_envelope") if isinstance(params.get("decision_envelope"), dict) else None
        if env:
            ok_env, why_env = validate_envelope(env)
            if not ok_env:
                result.status = ExecutionStatus.FAILED
                result.error_message = str(why_env)
                self._stats["failed"] += 1
                return result
            sym = env.get("symbol") or symbol or params.get("symbol")
            pos_side: Optional[str] = self._normalize_swap_side(env.get("side") or params.get("side"))
        else:
            sym = symbol or params.get("symbol")
            pos_side: Optional[str] = self._normalize_swap_side(params.get("side"))
        # CRITICAL: 不允许“省略即特权”。write_source 缺失则视为 unknown，交由 S1 policy 决定是否放行。
        write_source = str(params.get("write_source") or params.get("source") or "unknown").strip().lower()
        quantity = params.get("quantity")

        gw = None
        if self._main_controller is not None:
            gw = getattr(self._main_controller, "execution_gateway", None)

        if not pos_side and sym:
            try:
                positions = await self._exchange.fetch_positions([sym])
                position = next((p for p in positions if p.get("symbol") == sym), None)
                if position:
                    pos_side = self._normalize_swap_side(
                        position.get("posSide") or position.get("side")
                    )
                    if not pos_side and position.get("contracts") is not None:
                        c = float(position.get("contracts", 0) or 0)
                        pos_side = "long" if c > 0 else "short" if c < 0 else None
            except Exception as e:
                logger.debug("fetch_positions for close: %s", e)

        if not sym or not pos_side:
            result.status = ExecutionStatus.FAILED
            result.error_message = f"无法解析平仓方向或交易对: {sym}"
            self._stats["failed"] += 1
            return result

        if quantity is None and sym:
            try:
                positions = await self._exchange.fetch_positions([sym])
                position = next((p for p in positions if p.get("symbol") == sym), None)
                if position:
                    quantity = abs(float(position.get("contracts", 0)))
            except Exception:
                pass

        if not gw:
            result.status = ExecutionStatus.FAILED
            result.error_message = "execution_gateway_not_ready"
            self._stats["failed"] += 1
            return result

        try:
            gres = await gw.close_swap(
                sym,
                pos_side,
                float(quantity) if quantity is not None else None,
                write_source,
                "execution_verifier_close",
                context={
                    "write_source": write_source,
                    "symbol": sym,
                    "side": pos_side,
                    "quantity": quantity,
                    "pnl": params.get("pnl", 0),
                    "trace_id": params.get("trace_id"),
                    "strategy_used": params.get("strategy_used") or params.get("strategy_id"),
                    "strategy_id": params.get("strategy_id") or params.get("strategy_used"),
                },
            )
        except Exception as e:
            result.status = ExecutionStatus.FAILED
            result.error_message = str(e)
            self._stats["failed"] += 1
            return result

        if gres.get("success"):
            result.status = ExecutionStatus.SUCCESS
            result.details = {
                "order_id": (gres.get("orderId") or gres.get("order_id") or gres.get("id")),
                "symbol": sym,
                "quantity": quantity,
                "price": gres.get("average"),
                "pnl": params.get("pnl", 0),
                "gateway": True,
                "skipped": bool(gres.get("skipped")),
                "trace_id": gres.get("trace_id") or params.get("trace_id"),
            }
            self._stats["successful"] += 1
            if self._stop_loss_manager:
                await self._stop_loss_manager.cancel_order(sym)
            return result

        err = str(gres.get("error") or "")
        result.status = ExecutionStatus.FAILED
        result.error_message = err or "close_failed"
        self._stats["failed"] += 1
        return result
    
    async def _execute_set_stop_loss(
        self,
        result: ExecutionResult,
        symbol: Optional[str],
        params: Dict[str, Any]
    ) -> ExecutionResult:
        """执行设置止损"""
        if not self._stop_loss_manager:
            result.status = ExecutionStatus.FAILED
            result.error_message = "止盈止损管理器未初始化"
            self._stats["failed"] += 1
            return result
        
        try:
            stop_loss = params.get("stop_loss")
            take_profit = params.get("take_profit")
            
            order = await self._stop_loss_manager.modify_order(
                symbol=symbol,
                new_stop_loss=stop_loss,
                new_take_profit=take_profit
            )
            
            if order:
                result.status = ExecutionStatus.SUCCESS
                result.details = {
                    "symbol": symbol,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit
                }
                self._stats["successful"] += 1
            else:
                result.status = ExecutionStatus.FAILED
                result.error_message = "修改止盈止损失败"
                self._stats["failed"] += 1
                
        except Exception as e:
            result.status = ExecutionStatus.FAILED
            result.error_message = str(e)
            self._stats["failed"] += 1
        
        return result
    
    async def _execute_query_position(
        self,
        result: ExecutionResult,
        symbol: Optional[str],
        params: Dict[str, Any]
    ) -> ExecutionResult:
        """执行查询持仓"""
        if not self._exchange:
            result.status = ExecutionStatus.FAILED
            result.error_message = "交易所未连接"
            self._stats["failed"] += 1
            return result
        
        try:
            if symbol:
                positions = await self._exchange.fetch_positions([symbol])
            else:
                positions = await self._exchange.fetch_positions()
            
            result.status = ExecutionStatus.SUCCESS
            result.details = {
                "positions": positions,
                "count": len(positions)
            }
            self._stats["successful"] += 1
            
        except Exception as e:
            result.status = ExecutionStatus.FAILED
            result.error_message = str(e)
            self._stats["failed"] += 1
        
        return result
    
    async def _execute_query_balance(
        self,
        result: ExecutionResult,
        params: Dict[str, Any]
    ) -> ExecutionResult:
        """执行查询余额"""
        if not self._exchange:
            result.status = ExecutionStatus.FAILED
            result.error_message = "交易所未连接"
            self._stats["failed"] += 1
            return result
        
        try:
            balance = await self._exchange.fetch_balance()
            
            result.status = ExecutionStatus.SUCCESS
            result.details = {
                "total": balance.get("total", {}),
                "free": balance.get("free", {}),
                "used": balance.get("used", {})
            }
            self._stats["successful"] += 1
            
        except Exception as e:
            result.status = ExecutionStatus.FAILED
            result.error_message = str(e)
            self._stats["failed"] += 1
        
        return result
    
    async def _execute_analyze_market(
        self,
        result: ExecutionResult,
        symbol: Optional[str],
        params: Dict[str, Any]
    ) -> ExecutionResult:
        """执行市场分析"""
        if not self._exchange:
            result.status = ExecutionStatus.FAILED
            result.error_message = "交易所未连接"
            self._stats["failed"] += 1
            return result
        
        try:
            ticker = await self._exchange.fetch_ticker(symbol)
            ohlcv = await self._exchange.fetch_ohlcv(symbol, "1h", limit=24)
            
            result.status = ExecutionStatus.SUCCESS
            result.details = {
                "symbol": symbol,
                "current_price": ticker.get("last"),
                "24h_change": ticker.get("percentage"),
                "24h_volume": ticker.get("quoteVolume"),
                "analysis": params.get("analysis", "市场数据已获取")
            }
            self._stats["successful"] += 1
            
        except Exception as e:
            result.status = ExecutionStatus.FAILED
            result.error_message = str(e)
            self._stats["failed"] += 1
        
        return result
    
    async def _verify_execution(self, result: ExecutionResult) -> Dict[str, Any]:
        """验证执行结果"""
        verifier = self._verifiers.get(result.command_type)
        
        if verifier:
            try:
                verification = await asyncio.wait_for(
                    verifier(result),
                    timeout=self.config.verification_timeout_seconds
                )
                return verification
            except Exception as e:
                return {"verified": False, "details": str(e)}
        
        if result.command_type in [CommandType.OPEN_POSITION, CommandType.CLOSE_POSITION]:
            if result.details.get("order_id"):
                return {"verified": True, "details": "订单ID已确认"}
        
        return {"verified": True, "details": "自动验证通过"}
    
    async def _log_execution(self, result: ExecutionResult):
        """记录执行日志"""
        try:
            log_file = self._log_path / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
            
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")
                
        except Exception as e:
            logger.error(f"记录执行日志失败: {e}")
    
    async def _audit_log(self, result: ExecutionResult):
        """审计日志"""
        try:
            from .audit_logger import AuditEventType, AuditSeverity
            
            event_type_map = {
                CommandType.OPEN_POSITION: AuditEventType.TRADE_OPEN,
                CommandType.CLOSE_POSITION: AuditEventType.TRADE_CLOSE,
                CommandType.SET_STOP_LOSS: AuditEventType.POSITION_UPDATE,
                CommandType.QUERY_POSITION: AuditEventType.POSITION_QUERY,
            }
            
            event_type = event_type_map.get(
                result.command_type, 
                AuditEventType.SYSTEM_ACTION
            )
            
            severity = AuditSeverity.INFO if result.status == ExecutionStatus.SUCCESS else AuditSeverity.WARNING
            
            await self._audit_logger.log_event(
                event_type=event_type,
                severity=severity,
                action=result.action,
                details=result.to_dict(),
                source="execution_verifier"
            )
        except Exception as e:
            logger.error(f"审计日志记录失败: {e}")
    
    def _generate_execution_id(self) -> str:
        """生成执行ID"""
        return f"exec_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

    async def record_close_audit(
        self,
        *,
        symbol: str,
        side: str,
        size: Optional[float],
        success: bool,
        reason: str,
        source: str = "stop_loss_take_profit",
        details: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """
        供 SLTP / 其他绕过 execute() 的平仓路径写入 logs/executions/*.jsonl（与 open 记录同格式族）。
        """
        execution_id = self._generate_execution_id()
        det = dict(details or {})
        sd = str(side or "").strip().lower()
        action = "close_short" if sd == "short" else "close_long"
        oid = det.get("order_id")
        verified = bool(success) and bool(oid)
        result = ExecutionResult(
            execution_id=execution_id,
            command_type=CommandType.CLOSE_POSITION,
            action=action,
            status=ExecutionStatus.SUCCESS if success else ExecutionStatus.FAILED,
            symbol=str(symbol or "").strip() or None,
            details=det,
            error_message=error_message,
            timestamp=datetime.now(),
            duration_ms=0.0,
            verified=verified,
            verification_details="订单ID已确认" if verified else None,
        )
        self.execution_history[execution_id] = result
        self._stats["total_executions"] += 1
        if success:
            self._stats["successful"] += 1
        else:
            self._stats["failed"] += 1
        await self._log_execution(result)
        try:
            if self._audit_logger:
                await self._audit_log(result)
        except Exception:
            pass
    
    async def get_execution_status(self, execution_id: str) -> Optional[ExecutionResult]:
        """获取执行状态"""
        return self.execution_history.get(execution_id)
    
    async def get_recent_executions(self, limit: int = 10) -> List[ExecutionResult]:
        """获取最近的执行记录"""
        executions = list(self.execution_history.values())
        return executions[-limit:]
    
    async def get_pending_executions(self) -> List[ExecutionResult]:
        """获取待执行的命令"""
        return list(self.pending_executions.values())
    
    async def query_execution(self, query: str) -> Dict[str, Any]:
        """
        查询执行状态（自然语言查询）
        
        Args:
            query: 查询内容
        
        Returns:
            查询结果
        """
        query_lower = query.lower()
        
        if "最近" in query or "最近执行" in query:
            recent = await self.get_recent_executions(5)
            return {
                "type": "recent_executions",
                "executions": [e.to_dict() for e in recent],
                "message": f"最近执行了 {len(recent)} 条命令"
            }
        
        if "持仓" in query or "仓位" in query:
            position_executions = [
                e for e in self.execution_history.values()
                if e.command_type in [CommandType.OPEN_POSITION, CommandType.CLOSE_POSITION, CommandType.QUERY_POSITION]
                and e.status == ExecutionStatus.SUCCESS
            ]
            return {
                "type": "position_executions",
                "executions": [e.to_dict() for e in position_executions[-5:]],
                "message": f"找到 {len(position_executions)} 条持仓相关执行记录"
            }
        
        if "失败" in query or "错误" in query:
            failed = [
                e for e in self.execution_history.values()
                if e.status == ExecutionStatus.FAILED
            ]
            return {
                "type": "failed_executions",
                "executions": [e.to_dict() for e in failed[-5:]],
                "message": f"有 {len(failed)} 条执行失败的命令"
            }
        
        if "统计" in query or "概览" in query:
            return {
                "type": "statistics",
                "stats": self._stats,
                "message": f"总执行: {self._stats['total_executions']}, 成功: {self._stats['successful']}, 失败: {self._stats['failed']}"
            }
        
        recent = await self.get_recent_executions(3)
        return {
            "type": "default",
            "executions": [e.to_dict() for e in recent],
            "message": f"最近执行了 {len(recent)} 条命令"
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "pending_count": len(self.pending_executions),
            "history_count": len(self.execution_history)
        }
    
    async def cleanup(self):
        """清理资源"""
        for execution_id, result in list(self.pending_executions.items()):
            result.status = ExecutionStatus.CANCELLED
            result.error_message = "系统关闭，执行被取消"
        
        self.pending_executions.clear()
        logger.info("执行验证器清理完成")


def create_execution_verifier(config: Optional[ExecutionConfig] = None) -> ExecutionVerifier:
    """创建执行验证器实例"""
    return ExecutionVerifier(config)
