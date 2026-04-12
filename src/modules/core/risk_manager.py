"""
风险管理模块 - 全智能量化交易系统的安全核心

功能：
1. 仓位限制（单笔、单日、总仓位）
2. 风险指标（VaR、CVaR、最大回撤、夏普比率、索提诺比率）
3. 止损止盈（动态止损止盈策略）
4. 风险监控（实时风险监控和报警）
5. 合规检查（交易规则和合规性检查）
6. 高级风险评估（投资组合风险、流动性风险、系统性风险）
7. 压力测试和情景分析
8. 实时风险控制措施
"""

from scipy.stats import norm
from sklearn.covariance import LedoitWolf

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
    EXTREME = "extreme"  # 极端风险


class RiskMetricType(Enum):
    """风险指标类型"""
    VAR = "var"  # 风险价值
    CVAR = "cvar"  # 条件风险价值
    MAX_DRAWDOWN = "max_drawdown"  # 最大回撤
    SHARPE_RATIO = "sharpe_ratio"  # 夏普比率
    SORTINO_RATIO = "sortino_ratio"  # 索提诺比率
    BETA = "beta"  # 贝塔系数
    VOLATILITY = "volatility"  # 波动率
    LIQUIDITY_RISK = "liquidity_risk"  # 流动性风险
    SYSTEMIC_RISK = "systemic_risk"  # 系统性风险


@dataclass
class RiskAssessment:
    """风险评估结果"""
    timestamp: float
    risk_score: float
    risk_level: RiskLevel
    metrics: Dict[RiskMetricType, float]
    recommendations: List[str]
    confidence: float


@dataclass
class Position:
    """持仓信息"""
    symbol: str
    amount: float
    price: float
    entry_time: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    leverage: float = 1.0


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
    min_order_value: float = 5.0  # 单笔订单最小价值 (小资金优化)


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
    cvar_95: float = 0.0  # 95%置信度CVaR
    cvar_99: float = 0.0  # 99%置信度CVaR
    max_drawdown: float = 0.0  # 最大回撤
    sharpe_ratio: float = 0.0  # 夏普比率
    sortino_ratio: float = 0.0  # 索提诺比率
    volatility: float = 0.0  # 波动率
    beta: float = 0.0  # Beta系数
    alpha: float = 0.0  # Alpha值
    win_rate: float = 0.0  # 胜率
    profit_factor: float = 0.0  # 盈利因子
    calmar_ratio: float = 0.0  # 卡尔玛比率
    liquidity_risk: float = 0.0  # 流动性风险
    systemic_risk: float = 0.0  # 系统性风险
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

    def __init__(self, config_manager=None, db_manager=None):
        """
        初始化风险管理器

        Args:
            config_manager: 配置管理器实例
            db_manager: 数据库管理器实例（可选）
        """
        self.config_manager = config_manager
        self.db_manager = db_manager

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

        # 高级风险评估
        self.positions: Dict[str, Position] = {}  # 实时持仓
        self.risk_history: List[RiskAssessment] = []  # 风险评估历史
        self.risk_thresholds = {
            "low": 0.2,
            "medium": 0.4,
            "high": 0.7,
            "extreme": 1.0
        }
        self.var_confidence = 0.95
        self.var_horizon = 1  # 1天
        self.max_position_size = 0.1  # 最大仓位比例
        self.max_leverage = 3  # 最大杠杆

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
                await asyncio.sleep(30)  # 每30秒检查一次，提高监控频率

                # 更新风险指标
                await self._update_risk_metrics()

                # 检查系统风险
                await self._check_system_risk()

                # 检查实时风险指标
                await self._check_real_time_risk()

                # 执行高级风险评估
                assessment = await self.assess_overall_risk()
                if assessment:
                    # 检查风险是否超过阈值
                    if assessment.risk_level in [RiskLevel.HIGH, RiskLevel.EXTREME, RiskLevel.CRITICAL]:
                        logger.warning(f"检测到高风险: {assessment.risk_level.value}, 分数: {assessment.risk_score}")
                        # 执行风险控制措施
                        await self._execute_risk_control(assessment)

                # 清理旧警报
                await self._cleanup_old_alerts()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"风险监控线程错误: {e}")
                await asyncio.sleep(30)

        logger.info("风险监控线程停止")

    async def _check_real_time_risk(self) -> None:
        """检查实时风险指标"""
        try:
            # 获取当前风险指标
            metrics = await self.get_risk_metrics()
            
            # 检查VaR
            if metrics.var_95 > 1000:
                await self._create_alert(
                    rule_id="var_risk",
                    severity=AlertSeverity.WARNING,
                    message=f"VaR95值过高: ${metrics.var_95:.2f}",
                    data={"var_95": metrics.var_95}
                )
            
            # 检查最大回撤
            if metrics.max_drawdown > 0.15:
                await self._create_alert(
                    rule_id="drawdown_risk",
                    severity=AlertSeverity.ERROR,
                    message=f"最大回撤过大: {metrics.max_drawdown*100:.1f}%",
                    data={"max_drawdown": metrics.max_drawdown}
                )
            
            # 检查夏普比率
            if metrics.sharpe_ratio < -1.0:
                await self._create_alert(
                    rule_id="sharpe_risk",
                    severity=AlertSeverity.WARNING,
                    message=f"夏普比率为负: {metrics.sharpe_ratio:.2f}",
                    data={"sharpe_ratio": metrics.sharpe_ratio}
                )
            
            # 检查活跃警报数量
            alerts = await self.get_alerts()
            if len(alerts) > 5:
                await self._create_alert(
                    rule_id="alert_flood",
                    severity=AlertSeverity.CRITICAL,
                    message=f"警报数量过多: {len(alerts)} 个活跃警报",
                    data={"active_alerts": len(alerts)}
                )
                
        except Exception as e:
            logger.error(f"检查实时风险失败: {e}")

    async def _metrics_calculation_worker(self) -> None:
        """指标计算工作线程"""
        logger.info("启动风险指标计算线程")

        while self._initialized:
            try:
                await asyncio.sleep(300)  # 每5分钟计算一次

                # 计算风险指标
                var_95 = await self.calculate_var(0.95)
                var_99 = await self.calculate_var(0.99)
                
                # 计算CVaR（条件风险价值）
                cvar_95 = var_95 * 1.2  # 简化计算，实际应该使用更复杂的方法
                cvar_99 = var_99 * 1.3  # 简化计算
                
                max_drawdown = await self.calculate_max_drawdown()
                sharpe_ratio = await self.calculate_sharpe_ratio()
                sortino_ratio = await self._calculate_sortino_ratio()
                
                # 计算流动性风险和系统性风险（模拟）
                liquidity_risk = np.random.normal(0.1, 0.05)
                systemic_risk = np.random.normal(0.15, 0.05)

                # 更新指标
                async with self._lock:
                    self.metrics = RiskMetrics(
                        var_95=var_95,
                        var_99=var_99,
                        cvar_95=cvar_95,
                        cvar_99=cvar_99,
                        max_drawdown=max_drawdown,
                        sharpe_ratio=sharpe_ratio,
                        sortino_ratio=sortino_ratio,
                        liquidity_risk=liquidity_risk,
                        systemic_risk=systemic_risk,
                        timestamp=datetime.now(),
                    )
                    self.metrics_history.append(self.metrics)

                    # 限制历史记录长度
                    if len(self.metrics_history) > 1000:
                        self.metrics_history = self.metrics_history[-1000:]

                logger.debug(
                    f"风险指标更新: VaR95=${var_95:.2f}, CVaR95=${cvar_95:.2f}, "
                    f"最大回撤={max_drawdown*100:.1f}%, 夏普比率={sharpe_ratio:.2f}, "
                    f"索提诺比率={sortino_ratio:.2f}"
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

    async def run_stress_test(self, scenario: str = "market_crash") -> Dict[str, Any]:
        """
        运行压力测试

        Args:
            scenario: 压力测试场景 (market_crash, high_volatility, flash_crash)

        Returns:
            压力测试结果
        """
        logger.info(f"开始压力测试: {scenario}")

        try:
            # 定义不同的压力测试场景
            scenarios = {
                "market_crash": {
                    "name": "市场崩溃",
                    "description": "模拟市场大幅下跌的情景",
                    "price_change": -0.3,  # 30%下跌
                    "volatility_increase": 2.0,  # 波动率增加2倍
                    "duration_days": 3
                },
                "high_volatility": {
                    "name": "高波动率",
                    "description": "模拟市场高波动的情景",
                    "price_change": 0.0,  # 价格不变
                    "volatility_increase": 3.0,  # 波动率增加3倍
                    "duration_days": 7
                },
                "flash_crash": {
                    "name": "闪电崩盘",
                    "description": "模拟快速大幅下跌后反弹的情景",
                    "price_change": -0.2,  # 20%下跌
                    "volatility_increase": 5.0,  # 波动率增加5倍
                    "duration_days": 1
                }
            }

            if scenario not in scenarios:
                return {
                    "error": "未知的压力测试场景",
                    "scenarios": list(scenarios.keys())
                }

            scenario_config = scenarios[scenario]
            
            # 模拟压力测试
            test_results = {
                "scenario": scenario,
                "scenario_name": scenario_config["name"],
                "description": scenario_config["description"],
                "price_impact": scenario_config["price_change"],
                "volatility_impact": scenario_config["volatility_increase"],
                "estimated_max_drawdown": abs(scenario_config["price_change"]) * 1.5,
                "estimated_loss": abs(scenario_config["price_change"]) * 0.8,
                "recovery_time_days": scenario_config["duration_days"] * 2,
                "risk_level": "HIGH" if abs(scenario_config["price_change"]) > 0.2 else "MEDIUM",
                "timestamp": datetime.now().isoformat()
            }

            # 生成警报
            await self._create_alert(
                rule_id="stress_test",
                severity=AlertSeverity.WARNING,
                message=f"压力测试完成: {scenario_config['name']} - 预计最大回撤: {test_results['estimated_max_drawdown']*100:.1f}%",
                data=test_results
            )

            logger.info(f"压力测试完成: {scenario}")
            return test_results

        except Exception as e:
            logger.error(f"压力测试失败: {e}")
            return {
                "error": str(e)
            }

    async def run_scenario_analysis(self, scenarios: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        运行情景分析

        Args:
            scenarios: 自定义情景列表

        Returns:
            情景分析结果列表
        """
        results = []

        for i, scenario in enumerate(scenarios):
            try:
                scenario_name = scenario.get("name", f"Scenario_{i}")
                price_change = scenario.get("price_change", 0.0)
                volatility_change = scenario.get("volatility_change", 1.0)
                duration_days = scenario.get("duration_days", 1)

                # 分析情景影响
                impact_analysis = {
                    "scenario_name": scenario_name,
                    "price_change": price_change,
                    "volatility_change": volatility_change,
                    "duration_days": duration_days,
                    "estimated_impact": {
                        "pnl_impact": price_change * 0.9,  # 预计盈亏影响
                        "max_drawdown": abs(price_change) * 1.2,  # 预计最大回撤
                        "margin_call_risk": "HIGH" if abs(price_change) > 0.25 else "MEDIUM" if abs(price_change) > 0.15 else "LOW",
                        "liquidity_impact": "HIGH" if volatility_change > 3.0 else "MEDIUM" if volatility_change > 1.5 else "LOW"
                    },
                    "recommended_actions": [],
                    "timestamp": datetime.now().isoformat()
                }

                # 生成建议操作
                if price_change < -0.2:
                    impact_analysis["recommended_actions"].append("增加止损位")
                    impact_analysis["recommended_actions"].append("减少仓位")
                elif price_change > 0.2:
                    impact_analysis["recommended_actions"].append("考虑部分获利了结")
                    impact_analysis["recommended_actions"].append("设置止盈")

                if volatility_change > 2.0:
                    impact_analysis["recommended_actions"].append("减少交易频率")
                    impact_analysis["recommended_actions"].append("增加订单价差")

                results.append(impact_analysis)

                # 生成警报
                if abs(price_change) > 0.2 or volatility_change > 3.0:
                    await self._create_alert(
                        rule_id="scenario_analysis",
                        severity=AlertSeverity.WARNING,
                        message=f"情景分析: {scenario_name} - 高风险情景",
                        data=impact_analysis
                    )

            except Exception as e:
                logger.error(f"情景分析失败 {scenario.get('name', 'Unknown')}: {e}")
                results.append({
                    "scenario_name": scenario.get("name", "Unknown"),
                    "error": str(e)
                })

        return results

    # 高级风险评估方法

    async def assess_overall_risk(self) -> Optional[RiskAssessment]:
        """
        评估整体风险

        Returns:
            Optional[RiskAssessment]: 风险评估结果
        """
        try:
            if not self._initialized:
                logger.warning("风险管理器未初始化")
                return None

            import time
            timestamp = time.time()
            metrics = {}
            recommendations = []

            # 计算各项风险指标
            if self.positions:
                # 计算投资组合风险
                portfolio_risk = await self._calculate_portfolio_risk()
                metrics.update(portfolio_risk)
                
                # 计算最大回撤
                max_drawdown = await self.calculate_max_drawdown()
                metrics[RiskMetricType.MAX_DRAWDOWN] = max_drawdown
                
                # 计算夏普比率
                sharpe_ratio = await self.calculate_sharpe_ratio()
                metrics[RiskMetricType.SHARPE_RATIO] = sharpe_ratio
                
                # 计算索提诺比率
                sortino_ratio = await self._calculate_sortino_ratio()
                metrics[RiskMetricType.SORTINO_RATIO] = sortino_ratio
            else:
                # 无持仓时的默认风险
                metrics = {
                    RiskMetricType.VAR: 0.0,
                    RiskMetricType.CVAR: 0.0,
                    RiskMetricType.MAX_DRAWDOWN: 0.0,
                    RiskMetricType.SHARPE_RATIO: 0.0,
                    RiskMetricType.SORTINO_RATIO: 0.0,
                    RiskMetricType.VOLATILITY: 0.0,
                    RiskMetricType.LIQUIDITY_RISK: 0.0,
                    RiskMetricType.SYSTEMIC_RISK: 0.0
                }

            # 计算综合风险分数
            risk_score = await self._calculate_risk_score(metrics)
            risk_level = self._get_risk_level(risk_score)

            # 生成风险建议
            recommendations = await self._generate_recommendations(metrics, risk_level)

            # 计算置信度
            confidence = await self._calculate_confidence(metrics)

            assessment = RiskAssessment(
                timestamp=timestamp,
                risk_score=risk_score,
                risk_level=risk_level,
                metrics=metrics,
                recommendations=recommendations,
                confidence=confidence
            )

            # 保存风险评估历史
            self.risk_history.append(assessment)
            if len(self.risk_history) > 1000:
                self.risk_history = self.risk_history[-1000:]

            return assessment
        except Exception as e:
            logger.error(f"评估整体风险失败: {e}")
            return None

    async def assess_position_risk(self, position: Position) -> Dict[str, Any]:
        """
        评估单个持仓风险

        Args:
            position: 持仓信息

        Returns:
            Dict[str, Any]: 风险评估结果
        """
        try:
            risk_metrics = {}

            # 计算价格波动率（模拟数据）
            volatility = np.random.normal(0.02, 0.01)  # 假设2%的日波动率
            risk_metrics["volatility"] = volatility

            # 计算风险价值(VaR)
            var = position.price * volatility * np.sqrt(self.var_horizon) * norm.ppf(self.var_confidence)
            risk_metrics["var"] = var

            # 计算条件风险价值(CVaR)
            cvar = position.price * volatility * np.sqrt(self.var_horizon) * norm.pdf(norm.ppf(self.var_confidence)) / (1 - self.var_confidence)
            risk_metrics["cvar"] = cvar

            # 计算杠杆风险
            leverage_risk = position.leverage * var / position.price
            risk_metrics["leverage_risk"] = leverage_risk

            # 计算流动性风险
            liquidity_risk = await self._calculate_liquidity_risk(position.symbol)
            risk_metrics["liquidity_risk"] = liquidity_risk

            # 计算综合风险分数
            risk_score = (var / position.price) * position.leverage + liquidity_risk
            risk_metrics["risk_score"] = risk_score

            # 确定风险等级
            risk_level = self._get_risk_level(risk_score)
            risk_metrics["risk_level"] = risk_level.value

            return risk_metrics
        except Exception as e:
            logger.error(f"评估持仓风险失败: {e}")
            return {}

    async def _calculate_portfolio_risk(self) -> Dict[RiskMetricType, float]:
        """
        计算投资组合风险

        Returns:
            Dict[RiskMetricType, float]: 风险指标
        """
        try:
            # 模拟投资组合数据
            symbols = list(self.positions.keys())
            if not symbols:
                return {}

            # 模拟收益率数据
            returns = np.random.normal(0, 0.02, (252, len(symbols)))  # 一年的日收益率
            
            # 计算协方差矩阵
            cov_matrix = LedoitWolf().fit(returns).covariance_
            
            # 模拟持仓权重
            weights = np.array([self.positions[symbol].amount * self.positions[symbol].price for symbol in symbols])
            weights = weights / np.sum(weights) if np.sum(weights) > 0 else np.ones(len(symbols)) / len(symbols)
            
            # 计算投资组合波动率
            portfolio_volatility = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
            
            # 计算VaR
            var = portfolio_volatility * np.sqrt(self.var_horizon) * norm.ppf(self.var_confidence)
            
            # 计算CVaR
            cvar = portfolio_volatility * np.sqrt(self.var_horizon) * norm.pdf(norm.ppf(self.var_confidence)) / (1 - self.var_confidence)
            
            # 计算贝塔系数（模拟）
            beta = np.random.normal(1, 0.3)
            
            # 计算流动性风险（模拟）
            liquidity_risk = np.random.normal(0.1, 0.05)
            
            # 计算系统性风险（模拟）
            systemic_risk = np.random.normal(0.15, 0.05)
            
            return {
                RiskMetricType.VAR: var,
                RiskMetricType.CVAR: cvar,
                RiskMetricType.VOLATILITY: portfolio_volatility,
                RiskMetricType.BETA: beta,
                RiskMetricType.LIQUIDITY_RISK: liquidity_risk,
                RiskMetricType.SYSTEMIC_RISK: systemic_risk
            }
        except Exception as e:
            logger.error(f"计算投资组合风险失败: {e}")
            return {}

    async def _calculate_sortino_ratio(self) -> float:
        """
        计算索提诺比率

        Returns:
            float: 索提诺比率
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

            # 计算索提诺比率
            risk_free_rate = 0.02  # 无风险利率
            excess_returns = [r - risk_free_rate / 252 for r in returns]
            downside_returns = [r for r in excess_returns if r < 0]
            downside_std = np.std(downside_returns) if downside_returns else 1.0
            sortino_ratio = np.mean(excess_returns) / downside_std * math.sqrt(252)  # 年化

            return sortino_ratio

        except Exception as e:
            logger.error(f"计算索提诺比率失败: {e}")
            return 0.0

    async def _calculate_liquidity_risk(self, symbol: str) -> float:
        """
        计算流动性风险

        Args:
            symbol: 交易对

        Returns:
            float: 流动性风险分数
        """
        try:
            # 模拟流动性风险
            # 实际应该基于交易量、买卖价差等计算
            return np.random.normal(0.1, 0.05)
        except Exception as e:
            logger.error(f"计算流动性风险失败: {e}")
            return 0.5

    async def _calculate_risk_score(self, metrics: Dict[RiskMetricType, float]) -> float:
        """
        计算综合风险分数

        Args:
            metrics: 风险指标

        Returns:
            float: 风险分数
        """
        try:
            if not metrics:
                return 0.0

            # 权重
            weights = {
                RiskMetricType.VAR: 0.2,
                RiskMetricType.CVAR: 0.2,
                RiskMetricType.MAX_DRAWDOWN: 0.15,
                RiskMetricType.VOLATILITY: 0.15,
                RiskMetricType.LIQUIDITY_RISK: 0.1,
                RiskMetricType.SYSTEMIC_RISK: 0.1,
                RiskMetricType.SHARPE_RATIO: -0.05,  # 负权重，夏普比率越高风险越低
                RiskMetricType.SORTINO_RATIO: -0.05  # 负权重，索提诺比率越高风险越低
            }

            # 计算加权风险分数
            risk_score = 0.0
            total_weight = 0.0

            for metric, value in metrics.items():
                if metric in weights:
                    # 标准化值
                    if metric in [RiskMetricType.SHARPE_RATIO, RiskMetricType.SORTINO_RATIO]:
                        # 对于比率指标，进行标准化
                        normalized_value = min(1.0, max(-1.0, value / 5))
                    else:
                        # 对于风险指标，进行标准化
                        normalized_value = min(1.0, value)
                    
                    risk_score += normalized_value * weights[metric]
                    total_weight += abs(weights[metric])

            if total_weight > 0:
                risk_score = risk_score / total_weight
            
            # 确保风险分数在0-1之间
            return max(0.0, min(1.0, risk_score))
        except Exception as e:
            logger.error(f"计算风险分数失败: {e}")
            return 0.5

    def _get_risk_level(self, risk_score: float) -> RiskLevel:
        """
        根据风险分数确定风险等级

        Args:
            risk_score: 风险分数

        Returns:
            RiskLevel: 风险等级
        """
        if risk_score >= self.risk_thresholds["extreme"]:
            return RiskLevel.EXTREME
        elif risk_score >= self.risk_thresholds["high"]:
            return RiskLevel.HIGH
        elif risk_score >= self.risk_thresholds["medium"]:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

    async def _generate_recommendations(self, metrics: Dict[RiskMetricType, float], risk_level: RiskLevel) -> List[str]:
        """
        生成风险建议

        Args:
            metrics: 风险指标
            risk_level: 风险等级

        Returns:
            List[str]: 建议列表
        """
        recommendations = []

        if risk_level in [RiskLevel.HIGH, RiskLevel.EXTREME, RiskLevel.CRITICAL]:
            recommendations.append("降低仓位以控制风险")
            recommendations.append("增加止损位以限制潜在损失")
            recommendations.append("减少杠杆使用")
            
            if RiskMetricType.VOLATILITY in metrics and metrics[RiskMetricType.VOLATILITY] > 0.03:
                recommendations.append("考虑对冲策略以降低波动率")
            
            if RiskMetricType.LIQUIDITY_RISK in metrics and metrics[RiskMetricType.LIQUIDITY_RISK] > 0.3:
                recommendations.append("减少流动性差的资产持仓")
        elif risk_level == RiskLevel.MEDIUM:
            recommendations.append("保持当前仓位，但密切监控风险")
            recommendations.append("确保止损位设置合理")
        else:
            recommendations.append("风险水平可接受，可以考虑适当增加仓位")

        # 基于夏普比率的建议
        if RiskMetricType.SHARPE_RATIO in metrics:
            sharpe = metrics[RiskMetricType.SHARPE_RATIO]
            if sharpe > 1.5:
                recommendations.append("夏普比率良好，可以考虑增加风险敞口")
            elif sharpe < 0.5:
                recommendations.append("夏普比率较低，建议调整投资组合")

        return recommendations

    async def _calculate_confidence(self, metrics: Dict[RiskMetricType, float]) -> float:
        """
        计算风险评估的置信度

        Args:
            metrics: 风险指标

        Returns:
            float: 置信度
        """
        try:
            # 基于指标数量和数据质量计算置信度
            if not metrics:
                return 0.3
            
            # 指标数量越多，置信度越高
            metric_count = len(metrics)
            base_confidence = min(1.0, metric_count / 8)  # 假设最多8个指标
            
            # 对于关键指标的存在给予额外置信度
            key_metrics = [RiskMetricType.VAR, RiskMetricType.MAX_DRAWDOWN, RiskMetricType.SHARPE_RATIO]
            key_metric_count = sum(1 for metric in key_metrics if metric in metrics)
            confidence_boost = key_metric_count * 0.1
            
            total_confidence = min(1.0, base_confidence + confidence_boost)
            return total_confidence
        except Exception as e:
            logger.error(f"计算置信度失败: {e}")
            return 0.5

    async def _execute_risk_control(self, assessment: RiskAssessment):
        """
        执行风险控制措施

        Args:
            assessment: 风险评估结果
        """
        try:
            # 基于风险等级执行不同的控制措施
            if assessment.risk_level == RiskLevel.EXTREME:
                # 极端风险：平仓部分高风险仓位
                await self._reduce_position_sizes(0.5)  # 减少50%仓位
                await self._set_stricter_stop_losses()
            elif assessment.risk_level == RiskLevel.HIGH or assessment.risk_level == RiskLevel.CRITICAL:
                # 高风险：减少仓位和调整止损
                await self._reduce_position_sizes(0.3)  # 减少30%仓位
                await self._set_stricter_stop_losses()
        except Exception as e:
            logger.error(f"执行风险控制失败: {e}")

    async def _reduce_position_sizes(self, reduction_factor: float):
        """
        减少仓位大小

        Args:
            reduction_factor: 减少比例
        """
        try:
            for symbol, position in list(self.positions.items()):
                # 减少仓位
                new_amount = position.amount * (1 - reduction_factor)
                if new_amount > 0:
                    position.amount = new_amount
                    logger.info(f"减少 {symbol} 仓位 {reduction_factor * 100}%")
                else:
                    # 平仓
                    del self.positions[symbol]
                    logger.info(f"因风险控制平仓 {symbol}")
        except Exception as e:
            logger.error(f"减少仓位失败: {e}")

    async def _set_stricter_stop_losses(self):
        """
        设置更严格的止损位"""
        try:
            for symbol, position in self.positions.items():
                # 设置更严格的止损位（例如，从5%调整到3%）
                if position.stop_loss is None:
                    # 如果没有设置止损，设置一个
                    position.stop_loss = position.price * 0.97  # 3%止损
                else:
                    # 调整现有止损位
                    current_stop_loss = position.stop_loss
                    new_stop_loss = position.price * 0.97  # 3%止损
                    if new_stop_loss > current_stop_loss:  # 更严格的止损
                        position.stop_loss = new_stop_loss
                logger.info(f"为 {symbol} 设置更严格的止损位: {position.stop_loss}")
        except Exception as e:
            logger.error(f"设置止损位失败: {e}")

    async def open_position(self, symbol: str, amount: float, price: float, leverage: float = 1.0, stop_loss: Optional[float] = None, take_profit: Optional[float] = None) -> bool:
        """
        开仓（用于风险控制）

        Args:
            symbol: 交易对
            amount: 数量
            price: 价格
            leverage: 杠杆
            stop_loss: 止损价格
            take_profit: 止盈价格

        Returns:
            bool: 是否添加成功
        """
        try:
            # 检查杠杆是否超过限制
            if leverage > self.max_leverage:
                logger.warning(f"杠杆 {leverage} 超过最大允许值 {self.max_leverage}")
                return False

            # 检查仓位大小是否超过限制
            position_value = amount * price
            total_value = sum(p.amount * p.price for p in self.positions.values()) + position_value
            if position_value / total_value > self.max_position_size:
                logger.warning(f"仓位大小超过最大允许值 {self.max_position_size}")
                return False

            # 创建持仓
            import time
            position = Position(
                symbol=symbol,
                amount=amount,
                price=price,
                entry_time=time.time(),
                stop_loss=stop_loss,
                take_profit=take_profit,
                leverage=leverage
            )

            # 评估持仓风险
            risk_metrics = await self.assess_position_risk(position)
            risk_score = risk_metrics.get("risk_score", 0.0)
            risk_level = self._get_risk_level(risk_score)

            if risk_level in [RiskLevel.HIGH, RiskLevel.EXTREME, RiskLevel.CRITICAL]:
                logger.warning(f"持仓风险过高: {risk_level.value}, 分数: {risk_score}")
                return False

            # 添加持仓
            self.positions[symbol] = position
            logger.info(f"添加持仓 {symbol}: {amount} @ {price}")
            return True
        except Exception as e:
            logger.error(f"添加持仓失败: {e}")
            return False

    async def remove_position(self, symbol: str) -> bool:
        """
        移除持仓

        Args:
            symbol: 交易对

        Returns:
            bool: 是否移除成功
        """
        try:
            if symbol in self.positions:
                del self.positions[symbol]
                logger.info(f"移除持仓 {symbol}")
                return True
            else:
                logger.warning(f"持仓 {symbol} 不存在")
                return False
        except Exception as e:
            logger.error(f"移除持仓失败: {e}")
            return False

    def get_positions(self) -> Dict[str, Position]:
        """
        获取所有持仓

        Returns:
            Dict[str, Position]: 持仓字典
        """
        return self.positions

    def get_risk_history(self, limit: int = 100) -> List[RiskAssessment]:
        """
        获取风险历史

        Args:
            limit: 返回的历史记录数量

        Returns:
            List[RiskAssessment]: 风险评估历史
        """
        return self.risk_history[-limit:]


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
        logger.info(f"订单风险检查: {'通过' if check_result['passed'] else '拒绝'}")

        if check_result["violations"]:
            logger.info("违反规则:")
            for violation in check_result["violations"]:
                logger.info(f"  - {violation}")

        if check_result["warnings"]:
            logger.info("警告:")
            for warning in check_result["warnings"]:
                logger.info(f"  - {warning}")

        # 获取风险指标
        metrics = await risk_manager.get_risk_metrics()
        logger.info(f"风险指标: VaR95=${metrics.var_95:.2f}, 最大回撤={metrics.max_drawdown*100:.1f}%")

        # 获取警报
        alerts = await risk_manager.get_alerts()
        logger.info(f"活跃警报: {len(alerts)} 个")

        # 获取统计
        stats = await risk_manager.get_stats()
        logger.info(f"风险统计: {stats}")

    finally:
        await risk_manager.cleanup()


if __name__ == "__main__":
    # 运行示例
    asyncio.run(example_usage())
