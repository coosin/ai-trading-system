from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple

from src.modules.intelligence.decision_engine.engine import Decision, DecisionType
from src.modules.core.database_manager import DatabaseManager

logger = logging.getLogger(__name__)


class SignalType(Enum):
    """信号类型"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    EXIT = "exit"


class SignalStatus(Enum):
    """信号状态"""
    PENDING = "pending"
    EXECUTED = "executed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class TradingSignal:
    """交易信号"""
    signal_id: str
    signal_type: SignalType
    asset: str
    amount: float
    price: float
    confidence: float
    timestamp: float
    expiry: float
    status: SignalStatus
    metadata: Dict[str, Any]


class SignalGenerator:
    """信号生成器模块"""

    def __init__(self, db_manager: DatabaseManager, config: Dict[str, Any]):
        """初始化信号生成器

        Args:
            db_manager: 数据库管理器
            config: 配置信息
        """
        self.db_manager = db_manager
        self.config = config
        self.signals = {}
        self.risk_rules = config.get("risk_rules", {
            "max_position_size": 0.1,  # 最大仓位比例
            "max_leverage": 3,  # 最大杠杆
            "stop_loss_pct": 0.05,  # 止损比例
            "take_profit_pct": 0.1,  # 止盈比例
            "max_drawdown": 0.2,  # 最大回撤
        })
        self.signal_expiry = config.get("signal_expiry", 300)  # 信号过期时间（秒）
        self.enabled = False

    async def initialize(self) -> bool:
        """初始化信号生成器

        Returns:
            bool: 初始化是否成功
        """
        try:
            # 加载风险规则
            self.risk_rules = self.config.get("risk_rules", self.risk_rules)
            
            # 清理过期信号
            await self._cleanup_expired_signals()
            
            self.enabled = True
            logger.info("SignalGenerator initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize SignalGenerator: {e}")
            return False

    async def shutdown(self) -> bool:
        """关闭信号生成器

        Returns:
            bool: 关闭是否成功
        """
        try:
            self.enabled = False
            self.signals.clear()
            logger.info("SignalGenerator shutdown successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to shutdown SignalGenerator: {e}")
            return False

    async def generate_signal(self, decision: Decision) -> Optional[TradingSignal]:
        """根据决策生成交易信号

        Args:
            decision: 决策结果

        Returns:
            Optional[TradingSignal]: 交易信号
        """
        if not self.enabled:
            logger.warning("SignalGenerator is not enabled")
            return None

        try:
            # 转换决策类型为信号类型
            signal_type = self._decision_to_signal_type(decision.decision_type)
            
            # 应用风险管理
            if not await self._apply_risk_management(decision):
                logger.warning(f"Risk management rejected decision: {decision.decision_type}")
                return None
            
            # 生成信号
            signal = TradingSignal(
                signal_id=f"signal_{int(asyncio.get_event_loop().time() * 1000)}",
                signal_type=signal_type,
                asset=decision.asset,
                amount=decision.amount,
                price=decision.price,
                confidence=decision.confidence,
                timestamp=asyncio.get_event_loop().time(),
                expiry=asyncio.get_event_loop().time() + self.signal_expiry,
                status=SignalStatus.PENDING,
                metadata={
                    "decision_reason": decision.reason,
                    "risk_level": decision.risk_level.value,
                    "decision_metadata": decision.metadata
                }
            )
            
            # 记录信号
            self.signals[signal.signal_id] = signal
            await self._record_signal(signal)
            
            # 发送信号
            await self._send_signal(signal)
            
            return signal
        except Exception as e:
            logger.error(f"Error generating signal: {e}")
            return None

    def _decision_to_signal_type(self, decision_type: DecisionType) -> SignalType:
        """将决策类型转换为信号类型

        Args:
            decision_type: 决策类型

        Returns:
            SignalType: 信号类型
        """
        mapping = {
            DecisionType.BUY: SignalType.BUY,
            DecisionType.SELL: SignalType.SELL,
            DecisionType.HOLD: SignalType.HOLD,
            DecisionType.EXIT: SignalType.EXIT
        }
        return mapping.get(decision_type, SignalType.HOLD)

    async def _apply_risk_management(self, decision: Decision) -> bool:
        """应用风险管理规则

        Args:
            decision: 决策结果

        Returns:
            bool: 是否通过风险检查
        """
        try:
            # 检查仓位大小
            if decision.amount > self.risk_rules.get("max_position_size", 0.1):
                logger.warning(f"Position size {decision.amount} exceeds maximum {self.risk_rules['max_position_size']}")
                return False
            
            # 检查置信度
            if decision.confidence < 0.5:
                logger.warning(f"Confidence {decision.confidence} too low")
                return False
            
            # 这里可以添加更多风险管理逻辑
            # 例如：检查当前持仓、检查账户余额、检查市场流动性等
            
            return True
        except Exception as e:
            logger.error(f"Error applying risk management: {e}")
            return False

    async def _record_signal(self, signal: TradingSignal) -> bool:
        """记录信号

        Args:
            signal: 交易信号

        Returns:
            bool: 记录是否成功
        """
        try:
            # 这里应该将信号记录到数据库
            # 暂时使用日志记录
            logger.info(f"Signal recorded: {signal}")
            return True
        except Exception as e:
            logger.error(f"Failed to record signal: {e}")
            return False

    async def _send_signal(self, signal: TradingSignal) -> bool:
        """发送信号

        Args:
            signal: 交易信号

        Returns:
            bool: 发送是否成功
        """
        try:
            # 这里应该将信号发送到执行系统
            # 暂时使用日志记录
            logger.info(f"Signal sent: {signal}")
            
            # 模拟信号执行
            await asyncio.sleep(0.1)
            signal.status = SignalStatus.EXECUTED
            
            return True
        except Exception as e:
            logger.error(f"Failed to send signal: {e}")
            signal.status = SignalStatus.FAILED
            return False

    async def _cleanup_expired_signals(self) -> int:
        """清理过期信号

        Returns:
            int: 清理的信号数量
        """
        try:
            current_time = asyncio.get_event_loop().time()
            expired_signals = [
                signal_id for signal_id, signal in self.signals.items()
                if signal.expiry < current_time and signal.status == SignalStatus.PENDING
            ]
            
            for signal_id in expired_signals:
                signal = self.signals[signal_id]
                signal.status = SignalStatus.CANCELLED
                del self.signals[signal_id]
                logger.info(f"Expired signal cancelled: {signal_id}")
            
            return len(expired_signals)
        except Exception as e:
            logger.error(f"Error cleaning up expired signals: {e}")
            return 0

    async def get_signal_status(self, signal_id: str) -> Optional[SignalStatus]:
        """获取信号状态

        Args:
            signal_id: 信号ID

        Returns:
            Optional[SignalStatus]: 信号状态
        """
        try:
            signal = self.signals.get(signal_id)
            return signal.status if signal else None
        except Exception as e:
            logger.error(f"Error getting signal status: {e}")
            return None

    async def cancel_signal(self, signal_id: str) -> bool:
        """取消信号

        Args:
            signal_id: 信号ID

        Returns:
            bool: 取消是否成功
        """
        try:
            signal = self.signals.get(signal_id)
            if signal and signal.status == SignalStatus.PENDING:
                signal.status = SignalStatus.CANCELLED
                logger.info(f"Signal cancelled: {signal_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error cancelling signal: {e}")
            return False

    async def get_signal_history(self, limit: int = 100) -> List[TradingSignal]:
        """获取信号历史

        Args:
            limit: 返回的信号数量限制

        Returns:
            List[TradingSignal]: 信号历史列表
        """
        try:
            # 按时间戳排序，返回最新的信号
            sorted_signals = sorted(
                self.signals.values(),
                key=lambda x: x.timestamp,
                reverse=True
            )
            return sorted_signals[:limit]
        except Exception as e:
            logger.error(f"Error getting signal history: {e}")
            return []

    async def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标

        Returns:
            Dict[str, Any]: 性能指标
        """
        try:
            # 计算信号性能指标
            total_signals = len(self.signals)
            executed_signals = sum(1 for s in self.signals.values() if s.status == SignalStatus.EXECUTED)
            failed_signals = sum(1 for s in self.signals.values() if s.status == SignalStatus.FAILED)
            cancelled_signals = sum(1 for s in self.signals.values() if s.status == SignalStatus.CANCELLED)
            
            if total_signals > 0:
                execution_rate = executed_signals / total_signals
                success_rate = (executed_signals) / (executed_signals + failed_signals) if (executed_signals + failed_signals) > 0 else 0
            else:
                execution_rate = 0
                success_rate = 0
            
            return {
                "total_signals": total_signals,
                "executed_signals": executed_signals,
                "failed_signals": failed_signals,
                "cancelled_signals": cancelled_signals,
                "execution_rate": execution_rate,
                "success_rate": success_rate
            }
        except Exception as e:
            logger.error(f"Error getting performance metrics: {e}")
            return {}

    def is_healthy(self) -> bool:
        """检查信号生成器健康状态

        Returns:
            bool: 健康状态
        """
        return self.enabled
