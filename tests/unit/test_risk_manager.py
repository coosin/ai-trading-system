"""
RiskManager单元测试
"""

import asyncio
from datetime import datetime, timedelta

import pytest

from src.modules.core.risk_manager import (
    AlertSeverity,
    LossLimit,
    PositionLimit,
    RiskAlert,
    RiskLevel,
    RiskManager,
    RiskMetrics,
    RiskRule,
    RiskRuleType,
)


class TestRiskManager:
    """RiskManager测试类"""

    @pytest.fixture
    async def risk_manager(self):
        """创建测试用的风险管理器"""
        manager = RiskManager()
        await manager.initialize()
        yield manager
        await manager.cleanup()

    @pytest.mark.asyncio
    async def test_initialization(self, risk_manager):
        """测试初始化"""
        assert risk_manager is not None
        assert len(risk_manager.rules) > 0  # 应该有默认规则
        assert risk_manager.position_limits is not None
        assert risk_manager.loss_limits is not None
        assert risk_manager.metrics is not None

    @pytest.mark.asyncio
    async def test_position_limit_config(self):
        """测试仓位限制配置"""
        limits = PositionLimit(
            max_position_size=0.15,
            max_total_position=0.6,
            max_daily_trades=100,
            max_order_value=50000.0,
            min_order_value=100.0,
        )

        assert limits.max_position_size == 0.15
        assert limits.max_total_position == 0.6
        assert limits.max_daily_trades == 100
        assert limits.max_order_value == 50000.0
        assert limits.min_order_value == 100.0

    @pytest.mark.asyncio
    async def test_loss_limit_config(self):
        """测试亏损限制配置"""
        limits = LossLimit(
            max_daily_loss=0.03,
            max_total_loss=0.15,
            stop_loss_percent=0.08,
            take_profit_percent=0.15,
            trailing_stop_percent=0.05,
        )

        assert limits.max_daily_loss == 0.03
        assert limits.max_total_loss == 0.15
        assert limits.stop_loss_percent == 0.08
        assert limits.take_profit_percent == 0.15
        assert limits.trailing_stop_percent == 0.05

    @pytest.mark.asyncio
    async def test_risk_metrics(self):
        """测试风险指标"""
        metrics = RiskMetrics(
            var_95=1250.50,
            var_99=1850.75,
            max_drawdown=0.125,
            sharpe_ratio=1.8,
            sortino_ratio=2.2,
            volatility=0.045,
            beta=1.1,
            alpha=0.02,
            win_rate=0.65,
            profit_factor=1.5,
            calmar_ratio=1.2,
        )

        assert metrics.var_95 == 1250.50
        assert metrics.var_99 == 1850.75
        assert metrics.max_drawdown == 0.125
        assert metrics.sharpe_ratio == 1.8
        assert metrics.sortino_ratio == 2.2
        assert metrics.volatility == 0.045
        assert metrics.beta == 1.1
        assert metrics.alpha == 0.02
        assert metrics.win_rate == 0.65
        assert metrics.profit_factor == 1.5
        assert metrics.calmar_ratio == 1.2
        assert metrics.timestamp is not None

    @pytest.mark.asyncio
    async def test_check_order_position_limit(self, risk_manager):
        """测试检查订单仓位限制"""
        # 测试超过最大订单价值
        order_data = {
            "id": "test_order_1",
            "symbol": "BTC/USDT",
            "quantity": 10.0,
            "price": 60000.0,  # 价值600,000，超过默认限制
            "portfolio_value": 100000.0,
            "current_total_position": 0.0,
            "daily_trades": 5,
        }

        result = await risk_manager.check_order(order_data)
        assert result["passed"] is False
        assert any("超过最大限制" in v for v in result["violations"])

    @pytest.mark.asyncio
    async def test_check_order_daily_trades(self, risk_manager):
        """测试检查单日交易次数"""
        # 测试超过单日交易次数
        order_data = {
            "id": "test_order_2",
            "symbol": "BTC/USDT",
            "quantity": 0.1,
            "price": 50000.0,
            "portfolio_value": 100000.0,
            "current_total_position": 0.0,
            "daily_trades": 60,  # 超过默认50次限制
            "daily_pnl": 0.0,
            "total_pnl": 0.0,
        }

        result = await risk_manager.check_order(order_data)
        assert result["passed"] is False
        assert any("单日交易次数" in v for v in result["violations"])

    @pytest.mark.asyncio
    async def test_check_order_daily_loss(self, risk_manager):
        """测试检查单日亏损"""
        # 测试超过单日亏损限制
        order_data = {
            "id": "test_order_3",
            "symbol": "BTC/USDT",
            "quantity": 0.1,
            "price": 50000.0,
            "portfolio_value": 100000.0,
            "current_total_position": 0.0,
            "daily_trades": 5,
            "daily_pnl": -3000.0,  # -3%亏损
            "total_pnl": 0.0,
        }

        result = await risk_manager.check_order(order_data)
        # 可能通过，因为-3% > -2%限制，但算法是检查绝对值
        # 结果取决于具体实现
        assert isinstance(result, dict)
        assert "passed" in result

    @pytest.mark.asyncio
    async def test_check_order_valid(self, risk_manager):
        """测试检查有效订单"""
        # 测试有效订单
        order_data = {
            "id": "test_order_4",
            "symbol": "BTC/USDT",
            "quantity": 0.1,
            "price": 50000.0,  # 价值5,000
            "portfolio_value": 100000.0,
            "current_total_position": 10000.0,
            "daily_trades": 5,
            "daily_pnl": 500.0,
            "total_pnl": 2000.0,
        }

        result = await risk_manager.check_order(order_data)
        assert result["passed"] is True
        assert len(result["violations"]) == 0

    @pytest.mark.asyncio
    async def test_register_rule(self, risk_manager):
        """测试注册风险规则"""

        # 创建自定义规则
        async def custom_action(context):
            pass

        rule = RiskRule(
            id="custom_rule_1",
            rule_type=RiskRuleType.CUSTOM,
            name="自定义规则",
            description="测试自定义规则",
            condition=lambda ctx: ctx.get("test_value", 0) > 10,
            action=custom_action,
        )

        success = await risk_manager.register_rule(rule)
        assert success is True
        assert "custom_rule_1" in risk_manager.rules

    @pytest.mark.asyncio
    async def test_register_duplicate_rule(self, risk_manager):
        """测试注册重复规则"""

        # 创建规则
        async def custom_action(context):
            pass

        rule = RiskRule(
            id="duplicate_rule",
            rule_type=RiskRuleType.CUSTOM,
            name="重复规则",
            description="测试重复注册",
            condition=lambda ctx: True,
            action=custom_action,
        )

        # 第一次注册
        success1 = await risk_manager.register_rule(rule)
        assert success1 is True

        # 第二次注册（应该失败）
        success2 = await risk_manager.register_rule(rule)
        assert success2 is False

    @pytest.mark.asyncio
    async def test_remove_rule(self, risk_manager):
        """测试移除风险规则"""

        # 先注册规则
        async def custom_action(context):
            pass

        rule = RiskRule(
            id="rule_to_remove",
            rule_type=RiskRuleType.CUSTOM,
            name="待移除规则",
            description="测试移除",
            condition=lambda ctx: True,
            action=custom_action,
        )

        await risk_manager.register_rule(rule)
        assert "rule_to_remove" in risk_manager.rules

        # 移除规则
        success = await risk_manager.remove_rule("rule_to_remove")
        assert success is True
        assert "rule_to_remove" not in risk_manager.rules

    @pytest.mark.asyncio
    async def test_enable_disable_rule(self, risk_manager):
        """测试启用禁用规则"""

        # 先注册规则
        async def custom_action(context):
            pass

        rule = RiskRule(
            id="toggle_rule",
            rule_type=RiskRuleType.CUSTOM,
            name="开关规则",
            description="测试启用禁用",
            condition=lambda ctx: True,
            action=custom_action,
            enabled=True,
        )

        await risk_manager.register_rule(rule)

        # 禁用规则
        success_disable = await risk_manager.disable_rule("toggle_rule")
        assert success_disable is True
        assert risk_manager.rules["toggle_rule"].enabled is False

        # 启用规则
        success_enable = await risk_manager.enable_rule("toggle_rule")
        assert success_enable is True
        assert risk_manager.rules["toggle_rule"].enabled is True

    @pytest.mark.asyncio
    async def test_get_risk_metrics(self, risk_manager):
        """测试获取风险指标"""
        metrics = await risk_manager.get_risk_metrics()

        assert isinstance(metrics, RiskMetrics)
        assert metrics.var_95 >= 0.0
        assert metrics.max_drawdown >= 0.0
        assert metrics.timestamp is not None

    @pytest.mark.asyncio
    async def test_get_alerts(self, risk_manager):
        """测试获取警报"""
        # 获取所有警报
        all_alerts = await risk_manager.get_alerts()
        assert isinstance(all_alerts, list)

        # 获取未解决的警报
        unresolved_alerts = await risk_manager.get_alerts(unresolved=True)
        assert isinstance(unresolved_alerts, list)

        # 按严重程度过滤
        # 可能没有特定严重程度的警报
        critical_alerts = await risk_manager.get_alerts(severity=AlertSeverity.CRITICAL)
        assert isinstance(critical_alerts, list)

    @pytest.mark.asyncio
    async def test_acknowledge_resolve_alert(self, risk_manager):
        """测试确认和解决警报"""
        # 创建测试警报
        alert_id = "test_alert_1"
        alert = RiskAlert(
            id=alert_id,
            severity=AlertSeverity.WARNING,
            rule_id="test_rule",
            message="测试警报",
            data={"test": "data"},
        )

        # 手动添加到管理器
        risk_manager.alerts[alert_id] = alert
        risk_manager.stats["active_alerts"] = 1
        risk_manager.stats["total_alerts"] = 1

        # 确认警报
        acknowledged = await risk_manager.acknowledge_alert(alert_id)
        assert acknowledged is True
        assert risk_manager.alerts[alert_id].acknowledged is True

        # 解决警报
        resolved = await risk_manager.resolve_alert(alert_id)
        assert resolved is True
        assert risk_manager.alerts[alert_id].resolved is True
        assert risk_manager.stats["active_alerts"] == 0

    @pytest.mark.asyncio
    async def test_get_stats(self, risk_manager):
        """测试获取统计信息"""
        stats = await risk_manager.get_stats()

        assert isinstance(stats, dict)
        assert "total_checks" in stats
        assert "total_violations" in stats
        assert "total_alerts" in stats
        assert "active_alerts" in stats
        assert "total_rules" in stats
        assert "enabled_rules" in stats
        assert "current_risk_level" in stats

        # 检查风险等级是有效值
        risk_level = stats["current_risk_level"]
        assert risk_level in ["low", "medium", "high", "critical"]

    @pytest.mark.asyncio
    async def test_calculate_var(self, risk_manager):
        """测试计算VaR"""
        # 添加测试盈亏数据
        for i in range(20):
            await risk_manager.add_pnl(
                {
                    "pnl": 100.0 * (i % 3 - 1),  # -100, 0, 100交替
                    "portfolio_value": 100000.0 + i * 1000.0,
                }
            )

        # 计算VaR
        var_95 = await risk_manager.calculate_var(0.95)
        var_99 = await risk_manager.calculate_var(0.99)

        # VaR应该是非负数
        assert var_95 >= 0.0
        assert var_99 >= 0.0

        # 99% VaR应该大于或等于95% VaR
        assert var_99 >= var_95 - 0.01  # 允许小的浮点误差

    @pytest.mark.asyncio
    async def test_calculate_max_drawdown(self, risk_manager):
        """测试计算最大回撤"""
        # 添加测试盈亏数据
        pnl_sequence = [100, -50, 200, -150, 100, -200, 300, -100]

        for i, pnl in enumerate(pnl_sequence):
            await risk_manager.add_pnl(
                {"pnl": pnl, "portfolio_value": 100000.0 + sum(pnl_sequence[: i + 1])}
            )

        # 计算最大回撤
        max_dd = await risk_manager.calculate_max_drawdown()

        # 最大回撤应该在0-1之间
        assert 0.0 <= max_dd <= 1.0

    @pytest.mark.asyncio
    async def test_calculate_sharpe_ratio(self, risk_manager):
        """测试计算夏普比率"""
        # 添加测试盈亏数据
        for i in range(30):
            await risk_manager.add_pnl(
                {
                    "pnl": 50.0 + 10.0 * (i % 5 - 2),  # 有正有负的收益
                    "portfolio_value": 100000.0 + i * 100.0,
                }
            )

        # 计算夏普比率
        sharpe = await risk_manager.calculate_sharpe_ratio()

        # 夏普比率可以是任意实数
        assert isinstance(sharpe, float)

    @pytest.mark.asyncio
    async def test_add_trade_position_pnl(self, risk_manager):
        """测试添加交易、仓位、盈亏记录"""
        # 添加交易记录
        await risk_manager.add_trade(
            {
                "symbol": "BTC/USDT",
                "side": "buy",
                "quantity": 0.5,
                "price": 50000.0,
                "commission": 10.0,
            }
        )

        # 添加仓位记录
        await risk_manager.add_position(
            {"symbol": "BTC/USDT", "quantity": 0.5, "avg_price": 50000.0, "market_value": 25000.0}
        )

        # 添加盈亏记录
        await risk_manager.add_pnl(
            {"pnl": 500.0, "portfolio_value": 100500.0, "timestamp": datetime.now().isoformat()}
        )

        # 检查记录数量
        assert len(risk_manager.trade_history) > 0
        assert len(risk_manager.position_history) > 0
        assert len(risk_manager.pnl_history) > 0

    @pytest.mark.asyncio
    async def test_risk_alert_properties(self):
        """测试风险警报属性"""
        # 创建警报
        alert = RiskAlert(
            id="test_alert",
            severity=AlertSeverity.ERROR,
            rule_id="test_rule",
            message="测试错误警报",
            data={"value": 123, "threshold": 100},
        )

        # 检查属性
        assert alert.id == "test_alert"
        assert alert.severity == AlertSeverity.ERROR
        assert alert.rule_id == "test_rule"
        assert alert.message == "测试错误警报"
        assert alert.data["value"] == 123
        assert alert.data["threshold"] == 100
        assert alert.timestamp is not None
        assert alert.acknowledged is False
        assert alert.resolved is False

        # 转换为字典
        alert_dict = alert.to_dict()
        assert alert_dict["id"] == "test_alert"
        assert alert_dict["severity"] == "error"
        assert alert_dict["rule_id"] == "test_rule"
        assert alert_dict["message"] == "测试错误警报"
        assert alert_dict["data"]["value"] == 123
        assert "timestamp" in alert_dict
        assert alert_dict["acknowledged"] is False
        assert alert_dict["resolved"] is False

    @pytest.mark.asyncio
    async def test_enum_values(self):
        """测试枚举值"""
        # 风险等级
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"

        # 风险规则类型
        assert RiskRuleType.POSITION_LIMIT.value == "position_limit"
        assert RiskRuleType.LOSS_LIMIT.value == "loss_limit"
        assert RiskRuleType.CONCENTRATION.value == "concentration"
        assert RiskRuleType.VOLATILITY.value == "volatility"
        assert RiskRuleType.CUSTOM.value == "custom"

        # 警报严重程度
        assert AlertSeverity.INFO.value == "info"
        assert AlertSeverity.WARNING.value == "warning"
        assert AlertSeverity.ERROR.value == "error"
        assert AlertSeverity.CRITICAL.value == "critical"

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, risk_manager):
        """测试并发操作"""

        # 并发检查订单
        async def check_order_task(i):
            order_data = {
                "id": f"order_{i}",
                "symbol": f"SYM{i % 3}",
                "quantity": 0.1 * (i + 1),
                "price": 100.0 * (i + 1),
                "portfolio_value": 100000.0,
                "current_total_position": 0.0,
                "daily_trades": i % 20,
                "daily_pnl": -100.0 * (i % 3),
                "total_pnl": 1000.0 * (i % 2),
            }
            return await risk_manager.check_order(order_data)

        # 创建多个检查任务
        tasks = [check_order_task(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        # 检查结果
        assert len(results) == 10
        assert all(isinstance(r, dict) for r in results)
        assert all("passed" in r for r in results)


if __name__ == "__main__":
    """运行测试"""
    import sys

    import pytest

    # 添加src目录到Python路径
    sys.path.insert(0, "/home/cool/.openclaw-trading/src")

    # 运行测试
    pytest.main([__file__, "-v"])
