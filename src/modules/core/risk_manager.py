"""
风险管理模块 - 全智能量化交易系统的安全核心

功能：
1. 仓位限制（单笔、单日、总仓位）
2. 风险指标（VaR、最大回撤、夏普比率）
3. 止损止盈（动态止损止盈策略）
4. 风险监控（实时风险监控和报警）
5. 合规检查（交易规则和合规性检查）
"""

import asyncio
import logging
import math
import statistics
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """风险等级"""

    LOW = "low"  # 低风险
    MEDIUM = "medium"  # 中等风险
    HIGH = "high"  # 高风险
    CRITICAL = "critical"  # 临界风险


class RiskRuleType(Enum):
    """风险规则类型"""

    POSITION_LIMIT = "position_limit"  # 仓位限制
    LOSS_LIMIT = "loss_limit"  # 亏损限制
    CONCENTRATION = "concentration"  # 集中度限制
    VOLATILITY = "volatility"  # 波动率限制
    CUSTOM = "custom"  # 自定义规则


class AlertSeverity(Enum):
    """警报严重程度"""

    INFO = "info"  # 信息
    WARNING = "warning"  # 警告
    ERROR = "error"  # 错误
    CRITICAL = "critical"  # 严重


@dataclass
class RiskRule:
    """风险规则"""

    id: str
    rule_type: RiskRuleType
    name: str
    description: str
    condition: Callable[[Dict[str, Any]], bool]
    action: Callable[[Dict[str, Any]], Awaitable[None]]
    enabled: bool = True
    priority: int = 0  # 0=最低，10=最高
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PositionLimit:
    """仓位限制"""

    max_position_size: float = 0.1  # 单仓位最大比例（10%）
    max_total_position: float = 0.5  # 总仓位最大比例（50%）
    max_daily_trades: int = 50  # 单日最大交易次数
    max_order_value: float = 10000.0  # 单笔订单最大价值
    min_order_value: float = 10.0  # 单笔订单最小价值


@dataclass
class LossLimit:
    """亏损限制"""

    max_daily_loss: float = 0.02  # 单日最大亏损（2%）
    max_total_loss: float = 0.1  # 总最大亏损（10%）
    stop_loss_percent: float = 0.05  # 止损比例（5%）
    take_profit_percent: float = 0.1  # 止盈比例（10%）
    trailing_stop_percent: float = 0.03  # 移动止损比例（3%）


@dataclass
class RiskMetrics:
    """风险指标"""

    var_95: float = 0.0  # 95%置信度VaR
    var_99: float = 0.0  # 99%置信度VaR
    max_drawdown: float = 0.0  # 最大回撤
    sharpe_ratio: float = 0.0  # 夏普比率
    sortino_ratio: float = 0.0  # 索提诺比率
    volatility: float = 0.0  # 波动率
    beta: float = 0.0  # Beta系数
    alpha: float = 0.0  # Alpha值
    win_rate: float = 0.0  # 胜率
    profit_factor: float = 0.0  # 盈利因子
    calmar_ratio: float = 0.0  # 卡尔玛比率
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class RiskAlert:
    """风险警报"""

    id: str
    severity: AlertSeverity
    rule_id: str
    message: str
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    acknowledged: bool = False
    resolved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "severity": self.severity.value,
            "rule_id": self.rule_id,
            "message": self.message,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "acknowledged": self.acknowledged,
            "resolved": self.resolved,
        }


class RiskManager:
    """
    风险管理器

    核心功能：
    1. 仓位限制管理
    2. 风险指标计算
    3. 止损止盈策略
    4. 风险监控和报警
    5. 合规性检查
    """

    def __init__(self, config_manager=None):
        """
        初始化风险管理器

        Args:
            config_manager: 配置管理器实例
        """
        self.config_manager = config_manager

        # 风险规则
        self.rules: Dict[str, RiskRule] = {}

        # 限制配置
        self.position_limits = PositionLimit()
        self.loss_limits = LossLimit()

        # 风险指标
        self.metrics = RiskMetrics()
        self.metrics_history: List[RiskMetrics] = []

        # 警报管理
        self.alerts: Dict[str, RiskAlert] = {}
        self.alert_history: List[RiskAlert] = []

        # 交易数据
        self.trade_history: List[Dict[str, Any]] = []
        self.position_history: List[Dict[str, Any]] = []
        self.pnl_history: List[Dict[str, Any]] = []

        # 统计
        self.stats = {
            "total_checks": 0,
            "total_violations": 0,
            "total_alerts": 0,
            "active_alerts": 0,
            "last_check_time": None,
        }

        # 任务和锁
        self._tasks: List[asyncio.Task] = []
        self._lock = asyncio.Lock()
        self._initialized = False
        self._running = False

        logger.info("风险管理器初始化完成")

    async def initialize(self) -> None:
        """
        初始化风险管理器

        加载配置，设置默认规则
        """
        if self._initialized:
            return

        logger.info("初始化风险管理器...")

        try:
            # 加载配置
            await self._load_config()

            # 设置默认风险规则
            await self._setup_default_rules()

            # 启动监控任务
            self._tasks.append(asyncio.create_task(self._monitoring_worker()))
            self._tasks.append(asyncio.create_task(self._metrics_calculation_worker()))

            self._initialized = True
            logger.info("风险管理器初始化完成")

        except Exception as e:
            logger.error(f"风险管理器初始化失败: {e}")
            traceback.print_exc()

    async def cleanup(self) -> None:
        """
        清理风险管理器

        保存状态，清理资源
        """
        logger.info("清理风险管理器...")

        self._running = False

        # 取消所有任务
        for task in self._tasks:
            if not task.done():
                task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()

        # 保存状态
        await self._save_state()

        self._initialized = False
        logger.info("风险管理器清理完成")

    async def check_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        检查订单风险

        Args:
            order_data: 订单数据

        Returns:
            检查结果
        """
        async with self._lock:
            self.stats["total_checks"] += 1

            violations = []
            warnings = []
            passed = True

            # 检查仓位限制
            position_check = await self._check_position_limits(order_data)
            if not position_check["passed"]:
                violations.append(position_check["message"])
                passed = False
            elif position_check.get("warning"):
                warnings.append(position_check["warning"])

            # 检查亏损限制
            loss_check = await self._check_loss_limits(order_data)
            if not loss_check["passed"]:
                violations.append(loss_check["message"])
                passed = False
            elif loss_check.get("warning"):
                warnings.append(loss_check["warning"])

            # 检查波动率限制
            volatility_check = await self._check_volatility(order_data)
            if not volatility_check["passed"]:
                violations.append(volatility_check["message"])
                passed = False
            elif volatility_check.get("warning"):
                warnings.append(volatility_check["warning"])

            # 执行自定义规则检查
            rule_results = await self._execute_rules(order_data)
            for rule_result in rule_results:
                if not rule_result["passed"]:
                    violations.append(rule_result["message"])
                    passed = False
                elif rule_result.get("warning"):
                    warnings.append(rule_result["warning"])

            # 更新统计
            if not passed:
                self.stats["total_violations"] += 1

            result = {
                "passed": passed,
                "violations": violations,
                "warnings": warnings,
                "timestamp": datetime.now().isoformat(),
                "order_id": order_data.get("id"),
                "symbol": order_data.get("symbol"),
            }

            logger.debug(f"订单风险检查: {order_data.get('id')} -> {'通过' if passed else '拒绝'}")

            return result

    async def add_trade(self, trade_data: Dict[str, Any]) -> None:
        """
        添加交易记录

        Args:
            trade_data: 交易数据
        """
        async with self._lock:
            self.trade_history.append({**trade_data, "timestamp": datetime.now().isoformat()})

            # 限制历史记录长度
            if len(self.trade_history) > 10000:
                self.trade_history = self.trade_history[-10000:]

    async def add_position(self, position_data: Dict[str, Any]) -> None:
        """
        添加仓位记录

        Args:
            position_data: 仓位数据
        """
        async with self._lock:
            self.position_history.append({**position_data, "timestamp": datetime.now().isoformat()})

            # 限制历史记录长度
            if len(self.position_history) > 1000:
                self.position_history = self.position_history[-1000:]

    async def add_pnl(self, pnl_data: Dict[str, Any]) -> None:
        """
        添加盈亏记录

        Args:
            pnl_data: 盈亏数据
        """
        async with self._lock:
            self.pnl_history.append({**pnl_data, "timestamp": datetime.now().isoformat()})

            # 限制历史记录长度
            if len(self.pnl_history) > 1000:
                self.pnl_history = self.pnl_history[-1000:]

    async def register_rule(self, rule: RiskRule) -> bool:
        """
        注册风险规则

        Args:
            rule: 风险规则

        Returns:
            是否注册成功
        """
        async with self._lock:
            if rule.id in self.rules:
                logger.warning(f"风险规则已存在: {rule.id}")
                return False

            self.rules[rule.id] = rule
            logger.info(f"注册风险规则: {rule.name} ({rule.rule_type.value})")
            return True

    async def remove_rule(self, rule_id: str) -> bool:
        """
        移除风险规则

        Args:
            rule_id: 规则ID

        Returns:
            是否移除成功
        """
        async with self._lock:
            if rule_id not in self.rules:
                logger.warning(f"风险规则不存在: {rule_id}")
                return False

            del self.rules[rule_id]
            logger.info(f"移除风险规则: {rule_id}")
            return True

    async def enable_rule(self, rule_id: str) -> bool:
        """
        启用风险规则

        Args:
            rule_id: 规则ID

        Returns:
            是否启用成功
        """
        async with self._lock:
            if rule_id not in self.rules:
                logger.warning(f"风险规则不存在: {rule_id}")
                return False

            self.rules[rule_id].enabled = True
            logger.info(f"启用风险规则: {rule_id}")
            return True

    async def disable_rule(self, rule_id: str) -> bool:
        """
        禁用风险规则

        Args:
            rule_id: 规则ID

        Returns:
            是否禁用成功
        """
        async with self._lock:
            if rule_id not in self.rules:
                logger.warning(f"风险规则不存在: {rule_id}")
                return False

            self.rules[rule_id].enabled = False
            logger.info(f"禁用风险规则: {rule_id}")
            return True

    async def get_risk_metrics(self) -> RiskMetrics:
        """
        获取风险指标

        Returns:
            风险指标
        """
        async with self._lock:
            return self.metrics

    async def get_alerts(
        self, severity: Optional[AlertSeverity] = None, unresolved: bool = True
    ) -> List[RiskAlert]:
        """
        获取警报

        Args:
            severity: 过滤严重程度
            unresolved: 只获取未解决的警报

        Returns:
            警报列表
        """
        async with self._lock:
            alerts = list(self.alerts.values())

            if severity:
                alerts = [a for a in alerts if a.severity == severity]

            if unresolved:
                alerts = [a for a in alerts if not a.resolved]

            return sorted(alerts, key=lambda a: a.timestamp, reverse=True)

    async def acknowledge_alert(self, alert_id: str) -> bool:
        """
        确认警报

        Args:
            alert_id: 警报ID

        Returns:
            是否确认成功
        """
        async with self._lock:
            if alert_id not in self.alerts:
                return False

            self.alerts[alert_id].acknowledged = True
            logger.info(f"确认警报: {alert_id}")
            return True

    async def resolve_alert(self, alert_id: str) -> bool:
        """
        解决警报

        Args:
            alert_id: 警报ID

        Returns:
            是否解决成功
        """
        async with self._lock:
            if alert_id not in self.alerts:
                return False

            self.alerts[alert_id].resolved = True
            self.stats["active_alerts"] = max(0, self.stats["active_alerts"] - 1)
            logger.info(f"解决警报: {alert_id}")
            return True

    async def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            统计信息
        """
        async with self._lock:
            stats = self.stats.copy()
            stats.update(
                {
                    "total_rules": len(self.rules),
                    "enabled_rules": len([r for r in self.rules.values() if r.enabled]),
                    "total_alerts_history": len(self.alert_history),
                    "metrics_timestamp": self.metrics.timestamp.isoformat(),
                    "current_risk_level": await self._calculate_risk_level(),
                }
            )
            return stats

    async def calculate_var(
        self, confidence_level: float = 0.95, lookback_days: int = 252
    ) -> float:
        """
        计算风险价值（VaR）

        Args:
            confidence_level: 置信水平
            lookback_days: 回看天数

        Returns:
            VaR值
        """
        if len(self.pnl_history) < 10:
            return 0.0

        try:
            # 提取盈亏数据
            pnl_values = [p.get("pnl", 0) for p in self.pnl_history[-lookback_days:]]

            if not pnl_values:
                return 0.0

            # 计算历史VaR
            sorted_pnl = sorted(pnl_values)
            var_index = int(len(sorted_pnl) * (1 - confidence_level))

            if var_index >= len(sorted_pnl):
                var_index = len(sorted_pnl) - 1

            var = -sorted_pnl[var_index]  # VaR通常是正数

            return max(0, var)

        except Exception as e:
            logger.error(f"计算VaR失败: {e}")
            return 0.0

    async def calculate_max_drawdown(self) -> float:
        """
        计算最大回撤

        Returns:
            最大回撤比例
        """
        if len(self.pnl_history) < 2:
            return 0.0

        try:
            # 提取累计盈亏
            cumulative_pnl = []
            current = 0

            for pnl_data in self.pnl_history:
                current += pnl_data.get("pnl", 0)
                cumulative_pnl.append(current)

            # 计算最大回撤
            peak = cumulative_pnl[0]
            max_drawdown = 0.0

            for value in cumulative_pnl:
                if value > peak:
                    peak = value

                drawdown = (peak - value) / peak if peak > 0 else 0
                max_drawdown = max(max_drawdown, drawdown)

            return max_drawdown

        except Exception as e:
            logger.error(f"计算最大回撤失败: {e}")
            return 0.0

    async def calculate_sharpe_ratio(self, risk_free_rate: float = 0.02) -> float:
        """
        计算夏普比率

        Args:
            risk_free_rate: 无风险利率

        Returns:
            夏普比率
        """
        if len(self.pnl_history) < 2:
            return 0.0

        try:
            # 提取日收益率
            returns = []
            for i in range(1, len(self.pnl_history)):
                prev_value = self.pnl_history[i - 1].get("portfolio_value", 0)
                curr_value = self.pnl_history[i].get("portfolio_value", 0)

                if prev_value > 0:
                    daily_return = (curr_value - prev_value) / prev_value
                    returns.append(daily_return)

            if not returns:
                return 0.0

            # 计算夏普比率
            avg_return = statistics.mean(returns)
            std_return = statistics.stdev(returns) if len(returns) > 1 else 0

            if std_return > 0:
                # 年化夏普比率
                sharpe = (avg_return - risk_free_rate / 252) / std_return * math.sqrt(252)
                return sharpe
            else:
                return 0.0

        except Exception as e:
            logger.error(f"计算夏普比率失败: {e}")
            return 0.0

    # 私有方法

    async def _load_config(self) -> None:
        """加载风险配置"""
        if self.config_manager:
            risk_config = await self.config_manager.get_config("risk", {})

            # 仓位限制
            position_config = risk_config.get("position_limits", {})
            self.position_limits = PositionLimit(
                max_position_size=position_config.get("max_position_size", 0.1),
                max_total_position=position_config.get("max_total_position", 0.5),
                max_daily_trades=position_config.get("max_daily_trades", 50),
                max_order_value=position_config.get("max_order_value", 10000.0),
                min_order_value=position_config.get("min_order_value", 10.0),
            )

            # 亏损限制
            loss_config = risk_config.get("loss_limits", {})
            self.loss_limits = LossLimit(
                max_daily_loss=loss_config.get("max_daily_loss", 0.02),
                max_total_loss=loss_config.get("max_total_loss", 0.1),
                stop_loss_percent=loss_config.get("stop_loss_percent", 0.05),
                take_profit_percent=loss_config.get("take_profit_percent", 0.1),
                trailing_stop_percent=loss_config.get("trailing_stop_percent", 0.03),
            )

        logger.info(
            f"加载风险配置: 单仓位限制={self.position_limits.max_position_size*100:.1f}%, "
            f"单日亏损限制={self.loss_limits.max_daily_loss*100:.1f}%"
        )

    async def _setup_default_rules(self) -> None:
        """设置默认风险规则"""

        # 规则1: 单仓位限制
        async def position_limit_action(context: Dict[str, Any]) -> None:
            """仓位限制动作"""
            await self._create_alert(
                rule_id="position_limit",
                severity=AlertSeverity.ERROR,
                message=f"超过单仓位限制: {context.get('position_size_percent', 0)*100:.1f}% > {self.position_limits.max_position_size*100:.1f}%",
                data=context,
            )

        position_rule = RiskRule(
            id="position_limit",
            rule_type=RiskRuleType.POSITION_LIMIT,
            name="单仓位限制",
            description="检查单仓位是否超过最大比例",
            condition=lambda ctx: ctx.get("position_size_percent", 0)
            > self.position_limits.max_position_size,
            action=position_limit_action,
            priority=8,
        )
        await self.register_rule(position_rule)

        # 规则2: 单日亏损限制
        async def daily_loss_action(context: Dict[str, Any]) -> None:
            """单日亏损动作"""
            await self._create_alert(
                rule_id="daily_loss_limit",
                severity=AlertSeverity.CRITICAL,
                message=f"超过单日亏损限制: {context.get('daily_loss_percent', 0)*100:.2f}% > {self.loss_limits.max_daily_loss*100:.1f}%",
                data=context,
            )

        daily_loss_rule = RiskRule(
            id="daily_loss_limit",
            rule_type=RiskRuleType.LOSS_LIMIT,
            name="单日亏损限制",
            description="检查单日亏损是否超过限制",
            condition=lambda ctx: ctx.get("daily_loss_percent", 0)
            > self.loss_limits.max_daily_loss,
            action=daily_loss_action,
            priority=9,
        )
        await self.register_rule(daily_loss_rule)

        # 规则3: 集中度风险
        async def concentration_action(context: Dict[str, Any]) -> None:
            """集中度风险动作"""
            await self._create_alert(
                rule_id="concentration_risk",
                severity=AlertSeverity.WARNING,
                message=f"集中度风险: 前3大仓位占比{context.get('top3_concentration', 0)*100:.1f}%",
                data=context,
            )

        concentration_rule = RiskRule(
            id="concentration_risk",
            rule_type=RiskRuleType.CONCENTRATION,
            name="集中度风险",
            description="检查仓位集中度是否过高",
            condition=lambda ctx: ctx.get("top3_concentration", 0) > 0.6,  # 前3大仓位超过60%
            action=concentration_action,
            priority=5,
        )
        await self.register_rule(concentration_rule)

        # 规则4: 波动率风险
        async def volatility_action(context: Dict[str, Any]) -> None:
            """波动率风险动作"""
            await self._create_alert(
                rule_id="volatility_risk",
                severity=AlertSeverity.WARNING,
                message=f"波动率风险: 近期波动率{context.get('volatility', 0)*100:.1f}%",
                data=context,
            )

        volatility_rule = RiskRule(
            id="volatility_risk",
            rule_type=RiskRuleType.VOLATILITY,
            name="波动率风险",
            description="检查市场波动率是否过高",
            condition=lambda ctx: ctx.get("volatility", 0) > 0.05,  # 波动率超过5%
            action=volatility_action,
            priority=6,
        )
        await self.register_rule(volatility_rule)

        logger.info(f"设置 {len(self.rules)} 个默认风险规则")

    async def _check_position_limits(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """检查仓位限制"""
        symbol = order_data.get("symbol", "")
        quantity = order_data.get("quantity", 0)
        price = order_data.get("price", 0)
        portfolio_value = order_data.get("portfolio_value", 0)

        if portfolio_value <= 0:
            return {"passed": True, "message": "投资组合价值无效"}

        # 计算订单价值
        order_value = quantity * price

        # 检查单笔订单最小价值
        if order_value < self.position_limits.min_order_value:
            return {
                "passed": False,
                "message": f"订单价值${order_value:.2f}低于最小限制${self.position_limits.min_order_value:.2f}",
            }

        # 检查单笔订单最大价值
        if order_value > self.position_limits.max_order_value:
            return {
                "passed": False,
                "message": f"订单价值${order_value:.2f}超过最大限制${self.position_limits.max_order_value:.2f}",
            }

        # 计算仓位比例
        position_size_percent = order_value / portfolio_value

        # 检查单仓位比例
        if position_size_percent > self.position_limits.max_position_size:
            return {
                "passed": False,
                "message": f"仓位比例{position_size_percent*100:.1f}%超过限制{self.position_limits.max_position_size*100:.1f}%",
            }

        # 检查总仓位比例（需要当前总仓位数据）
        current_total_position = order_data.get("current_total_position", 0)
        new_total_position = current_total_position + order_value

        if new_total_position / portfolio_value > self.position_limits.max_total_position:
            return {
                "passed": False,
                "message": f"总仓位比例{new_total_position/portfolio_value*100:.1f}%超过限制{self.position_limits.max_total_position*100:.1f}%",
            }

        # 检查单日交易次数（需要当日交易计数）
        daily_trades = order_data.get("daily_trades", 0)
        if daily_trades >= self.position_limits.max_daily_trades:
            return {
                "passed": False,
                "message": f"单日交易次数{daily_trades}超过限制{self.position_limits.max_daily_trades}",
            }

        # 警告：仓位比例较高
        if position_size_percent > self.position_limits.max_position_size * 0.8:
            return {"passed": True, "warning": f"仓位比例较高: {position_size_percent*100:.1f}%"}

        return {"passed": True}

    async def _check_loss_limits(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """检查亏损限制"""
        # 获取当前盈亏数据
        daily_pnl = order_data.get("daily_pnl", 0)
        total_pnl = order_data.get("total_pnl", 0)
        portfolio_value = order_data.get("portfolio_value", 0)

        if portfolio_value <= 0:
            return {"passed": True, "message": "投资组合价值无效"}

        # 计算盈亏比例
        daily_loss_percent = abs(min(daily_pnl, 0)) / portfolio_value
        total_loss_percent = abs(min(total_pnl, 0)) / portfolio_value

        # 检查单日亏损
        if daily_loss_percent > self.loss_limits.max_daily_loss:
            return {
                "passed": False,
                "message": f"单日亏损{daily_loss_percent*100:.2f}%超过限制{self.loss_limits.max_daily_loss*100:.1f}%",
            }

        # 检查总亏损
        if total_loss_percent > self.loss_limits.max_total_loss:
            return {
                "passed": False,
                "message": f"总亏损{total_loss_percent*100:.2f}%超过限制{self.loss_limits.max_total_loss*100:.1f}%",
            }

        # 警告：接近亏损限制
        if daily_loss_percent > self.loss_limits.max_daily_loss * 0.8:
            return {"passed": True, "warning": f"接近单日亏损限制: {daily_loss_percent*100:.2f}%"}

        return {"passed": True}

    async def _check_volatility(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """检查波动率"""
        symbol = order_data.get("symbol", "")
        volatility = order_data.get("volatility", 0)  # 预期从市场数据获取

        # 检查波动率是否过高
        if volatility > 0.1:  # 波动率超过10%
            return {"passed": False, "message": f"波动率过高: {volatility*100:.1f}%"}

        # 警告：波动率较高
        if volatility > 0.05:  # 波动率超过5%
            return {"passed": True, "warning": f"波动率较高: {volatility*100:.1f}%"}

        return {"passed": True}

    async def _execute_rules(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """执行风险规则"""
        results = []

        for rule in self.rules.values():
            if not rule.enabled:
                continue

            try:
                # 检查条件
                condition_passed = not rule.condition(context)

                if not condition_passed:
                    # 条件不满足（违反规则）
                    results.append(
                        {
                            "passed": False,
                            "rule_id": rule.id,
                            "rule_name": rule.name,
                            "message": f"违反规则: {rule.name}",
                        }
                    )

                    # 执行动作
                    await rule.action(context)

                else:
                    # 条件满足（通过规则）
                    results.append({"passed": True, "rule_id": rule.id, "rule_name": rule.name})

            except Exception as e:
                logger.error(f"执行风险规则失败 {rule.id}: {e}")
                results.append(
                    {
                        "passed": False,
                        "rule_id": rule.id,
                        "rule_name": rule.name,
                        "message": f"规则执行错误: {str(e)}",
                    }
                )

        return results

    async def _create_alert(
        self, rule_id: str, severity: AlertSeverity, message: str, data: Dict[str, Any]
    ) -> None:
        """创建警报"""
        alert_id = f"alert_{uuid.uuid4().hex[:8]}"

        alert = RiskAlert(
            id=alert_id, severity=severity, rule_id=rule_id, message=message, data=data
        )

        async with self._lock:
            self.alerts[alert_id] = alert
            self.alert_history.append(alert)
            self.stats["total_alerts"] += 1
            self.stats["active_alerts"] += 1

            # 限制历史记录长度
            if len(self.alert_history) > 1000:
                self.alert_history = self.alert_history[-1000:]

        logger.log(
            (
                logging.ERROR
                if severity == AlertSeverity.CRITICAL
                else (
                    logging.WARNING
                    if severity == AlertSeverity.ERROR
                    else logging.WARNING if severity == AlertSeverity.WARNING else logging.INFO
                )
            ),
            f"风险警报 [{severity.value}]: {message}",
        )

    async def _monitoring_worker(self) -> None:
        """监控工作线程"""
        logger.info("启动风险监控线程")

        while self._initialized:
            try:
                await asyncio.sleep(60)  # 每分钟检查一次

                # 更新风险指标
                await self._update_risk_metrics()

                # 检查系统风险
                await self._check_system_risk()

                # 清理旧警报
                await self._cleanup_old_alerts()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"风险监控线程错误: {e}")
                await asyncio.sleep(60)

        logger.info("风险监控线程停止")

    async def _metrics_calculation_worker(self) -> None:
        """指标计算工作线程"""
        logger.info("启动风险指标计算线程")

        while self._initialized:
            try:
                await asyncio.sleep(300)  # 每5分钟计算一次

                # 计算风险指标
                var_95 = await self.calculate_var(0.95)
                var_99 = await self.calculate_var(0.99)
                max_drawdown = await self.calculate_max_drawdown()
                sharpe_ratio = await self.calculate_sharpe_ratio()

                # 更新指标
                async with self._lock:
                    self.metrics = RiskMetrics(
                        var_95=var_95,
                        var_99=var_99,
                        max_drawdown=max_drawdown,
                        sharpe_ratio=sharpe_ratio,
                        timestamp=datetime.now(),
                    )
                    self.metrics_history.append(self.metrics)

                    # 限制历史记录长度
                    if len(self.metrics_history) > 1000:
                        self.metrics_history = self.metrics_history[-1000:]

                logger.debug(
                    f"风险指标更新: VaR95=${var_95:.2f}, 最大回撤={max_drawdown*100:.1f}%, 夏普比率={sharpe_ratio:.2f}"
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"风险指标计算线程错误: {e}")
                await asyncio.sleep(300)

        logger.info("风险指标计算线程停止")

    async def _update_risk_metrics(self) -> None:
        """更新风险指标"""
        # 这里可以添加实时指标更新逻辑
        pass

    async def _check_system_risk(self) -> None:
        """检查系统风险"""
        # 这里可以添加系统级风险检查
        pass

    async def _cleanup_old_alerts(self) -> None:
        """清理旧警报"""
        current_time = datetime.now()
        old_alerts = []

        async with self._lock:
            for alert_id, alert in list(self.alerts.items()):
                # 清理已解决且超过7天的警报
                if alert.resolved and (current_time - alert.timestamp) > timedelta(days=7):
                    old_alerts.append(alert_id)

            for alert_id in old_alerts:
                del self.alerts[alert_id]
                self.stats["active_alerts"] = max(0, self.stats["active_alerts"] - 1)

        if old_alerts:
            logger.debug(f"清理 {len(old_alerts)} 个旧警报")

    async def _calculate_risk_level(self) -> str:
        """计算风险等级"""
        # 基于多个指标计算总体风险等级
        risk_score = 0

        # VaR指标
        if self.metrics.var_95 > 1000:
            risk_score += 2
        elif self.metrics.var_95 > 500:
            risk_score += 1

        # 最大回撤
        if self.metrics.max_drawdown > 0.1:
            risk_score += 2
        elif self.metrics.max_drawdown > 0.05:
            risk_score += 1

        # 夏普比率
        if self.metrics.sharpe_ratio < 0:
            risk_score += 2
        elif self.metrics.sharpe_ratio < 1:
            risk_score += 1

        # 活跃警报
        active_critical = len(
            [
                a
                for a in self.alerts.values()
                if a.severity == AlertSeverity.CRITICAL and not a.resolved
            ]
        )
        risk_score += active_critical * 2

        # 确定风险等级
        if risk_score >= 5:
            return RiskLevel.CRITICAL.value
        elif risk_score >= 3:
            return RiskLevel.HIGH.value
        elif risk_score >= 1:
            return RiskLevel.MEDIUM.value
        else:
            return RiskLevel.LOW.value

    async def _save_state(self) -> None:
        """保存状态"""
        # 在实际系统中，这里应该保存到数据库
        logger.info("保存风险管理器状态")


# 使用示例
async def example_usage():
    """风险管理器使用示例"""

    # 创建风险管理器
    risk_manager = RiskManager()
    await risk_manager.initialize()

    try:
        # 检查订单风险
        order_data = {
            "id": "order_123",
            "symbol": "BTC/USDT",
            "quantity": 1.0,
            "price": 50000.0,
            "portfolio_value": 100000.0,
            "current_total_position": 20000.0,
            "daily_trades": 10,
            "daily_pnl": -500.0,
            "total_pnl": 2000.0,
            "volatility": 0.03,
        }

        check_result = await risk_manager.check_order(order_data)
        print(f"订单风险检查: {'通过' if check_result['passed'] else '拒绝'}")

        if check_result["violations"]:
            print("违反规则:")
            for violation in check_result["violations"]:
                print(f"  - {violation}")

        if check_result["warnings"]:
            print("警告:")
            for warning in check_result["warnings"]:
                print(f"  - {warning}")

        # 获取风险指标
        metrics = await risk_manager.get_risk_metrics()
        print(f"风险指标: VaR95=${metrics.var_95:.2f}, 最大回撤={metrics.max_drawdown*100:.1f}%")

        # 获取警报
        alerts = await risk_manager.get_alerts()
        print(f"活跃警报: {len(alerts)} 个")

        # 获取统计
        stats = await risk_manager.get_stats()
        print(f"风险统计: {stats}")

    finally:
        await risk_manager.cleanup()


if __name__ == "__main__":
    # 运行示例
    asyncio.run(example_usage())
