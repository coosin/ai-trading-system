#!/usr/bin/env python3
"""
Prometheus指标导出器
将交易系统指标暴露给Prometheus监控
"""

import asyncio
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# Prometheus客户端
try:
    from prometheus_client import (
        REGISTRY,
        Counter,
        Gauge,
        Histogram,
        Summary,
        generate_latest,
        start_http_server,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


@dataclass
class TradingMetric:
    """交易指标"""

    name: str
    value: float
    labels: Dict[str, str]
    metric_type: str  # gauge, counter, histogram
    timestamp: datetime


class PrometheusExporter:
    """Prometheus指标导出器"""

    def __init__(self, config_manager=None, port: int = 9091):
        self.config_manager = config_manager
        self.port = port

        if not PROMETHEUS_AVAILABLE:
            print("⚠️ Prometheus客户端不可用，监控功能受限")
            self.metrics = {}
            return

        # 初始化指标
        self.metrics = self._initialize_metrics()

        # 指标存储
        self.metric_history: Dict[str, List[TradingMetric]] = defaultdict(list)

        # 导出任务
        self.export_task = None
        self.is_running = False

        # 线程池
        self.thread_pool = ThreadPoolExecutor(max_workers=2)

        # HTTP服务器线程
        self.http_server_thread = None

    def _initialize_metrics(self) -> Dict[str, Any]:
        """初始化Prometheus指标"""

        metrics = {}

        # === 系统指标 ===

        # CPU使用率
        metrics["system_cpu_usage"] = Gauge(
            "trading_system_cpu_usage_percent", "系统CPU使用率百分比", ["component"]
        )

        # 内存使用
        metrics["system_memory_usage"] = Gauge(
            "trading_system_memory_usage_bytes", "系统内存使用量（字节）", ["component"]
        )

        # 线程数
        metrics["system_thread_count"] = Gauge(
            "trading_system_thread_count", "系统线程数", ["component"]
        )

        # === 交易指标 ===

        # 订单相关
        metrics["trading_orders_submitted"] = Counter(
            "trading_orders_submitted_total", "已提交订单总数", ["symbol", "order_type", "side"]
        )

        metrics["trading_orders_executed"] = Counter(
            "trading_orders_executed_total", "已执行订单总数", ["symbol", "order_type", "side"]
        )

        metrics["trading_orders_cancelled"] = Counter(
            "trading_orders_cancelled_total", "已取消订单总数", ["symbol", "order_type", "side"]
        )

        metrics["trading_orders_rejected"] = Counter(
            "trading_orders_rejected_total", "已拒绝订单总数", ["symbol", "reason"]
        )

        # 订单执行延迟
        metrics["trading_order_execution_duration"] = Histogram(
            "trading_order_execution_duration_seconds",
            "订单执行延迟（秒）",
            ["symbol", "order_type"],
            buckets=[0.1, 0.5, 1, 2, 5, 10, 30],
        )

        # === 投资组合指标 ===

        # 投资组合价值
        metrics["portfolio_total_value"] = Gauge(
            "trading_portfolio_total_value_usd", "投资组合总价值（USD）", ["account"]
        )

        # 投资组合收益率
        metrics["portfolio_return"] = Gauge(
            "trading_portfolio_return_percent", "投资组合收益率百分比", ["account", "timeframe"]
        )

        # 投资组合回撤
        metrics["portfolio_drawdown"] = Gauge(
            "trading_portfolio_drawdown_percent", "投资组合回撤百分比", ["account"]
        )

        # 夏普比率
        metrics["portfolio_sharpe_ratio"] = Gauge(
            "trading_portfolio_sharpe_ratio", "投资组合夏普比率", ["account", "timeframe"]
        )

        # === 风险指标 ===

        # 风险价值
        metrics["risk_var"] = Gauge(
            "trading_risk_value_at_risk_usd",
            "风险价值（VaR）（USD）",
            ["account", "confidence_level"],
        )

        # 条件风险价值
        metrics["risk_cvar"] = Gauge(
            "trading_risk_conditional_var_usd",
            "条件风险价值（CVaR）（USD）",
            ["account", "confidence_level"],
        )

        # 最大回撤
        metrics["risk_max_drawdown"] = Gauge(
            "trading_risk_max_drawdown_percent", "最大回撤百分比", ["account"]
        )

        # 波动率
        metrics["risk_volatility"] = Gauge(
            "trading_risk_volatility_percent", "波动率百分比", ["account", "timeframe"]
        )

        # === 市场指标 ===

        # 市场波动性
        metrics["market_volatility"] = Gauge(
            "trading_market_volatility_percent", "市场波动性百分比", ["symbol", "timeframe"]
        )

        # 市场流动性
        metrics["market_liquidity"] = Gauge(
            "trading_market_liquidity_score", "市场流动性评分（0-1）", ["symbol"]
        )

        # 价差
        metrics["market_spread"] = Gauge(
            "trading_market_spread_percent", "市场价差百分比", ["symbol"]
        )

        # === 性能指标 ===

        # 数据处理延迟
        metrics["performance_data_processing"] = Histogram(
            "trading_data_processing_duration_seconds",
            "数据处理延迟（秒）",
            ["data_source"],
            buckets=[0.01, 0.05, 0.1, 0.5, 1, 2, 5],
        )

        # API延迟
        metrics["performance_api_latency"] = Histogram(
            "trading_api_latency_seconds",
            "API延迟（秒）",
            ["endpoint"],
            buckets=[0.1, 0.5, 1, 2, 5, 10],
        )

        # 缓存命中率
        metrics["performance_cache_hit_rate"] = Gauge(
            "trading_cache_hit_rate_percent", "缓存命中率百分比", ["cache_level"]
        )

        # === 错误指标 ===

        # 错误计数
        metrics["errors_total"] = Counter(
            "trading_errors_total", "总错误数", ["component", "error_type"]
        )

        # 连接错误
        metrics["errors_connection"] = Counter(
            "trading_connection_errors_total", "连接错误总数", ["component", "target"]
        )

        # 数据错误
        metrics["errors_data"] = Counter(
            "trading_data_errors_total", "数据错误总数", ["component", "data_source"]
        )

        # === 合规性指标 ===

        # 合规性检查
        metrics["compliance_checks"] = Counter(
            "trading_compliance_checks_total", "合规性检查总数", ["standard", "status"]
        )

        # 合规性违规
        metrics["compliance_violations"] = Counter(
            "trading_compliance_violations_total", "合规性违规总数", ["standard", "violation_type"]
        )

        # === 安全指标 ===

        # 安全事件
        metrics["security_events"] = Counter(
            "trading_security_events_total", "安全事件总数", ["event_type", "severity"]
        )

        # 未授权访问尝试
        metrics["unauthorized_access"] = Counter(
            "trading_unauthorized_access_attempts_total", "未授权访问尝试总数", ["source", "target"]
        )

        # === 预测性指标 ===

        # 预测损失
        metrics["predicted_loss"] = Gauge(
            "trading_predicted_daily_loss_percent", "预测日损失百分比", ["model"]
        )

        # 市场崩盘概率
        metrics["predicted_crash_probability"] = Gauge(
            "trading_market_crash_probability", "市场崩盘概率（0-1）", ["model"]
        )

        # 流动性危机概率
        metrics["predicted_liquidity_crisis"] = Gauge(
            "trading_liquidity_crisis_probability", "流动性危机概率（0-1）", ["model"]
        )

        return metrics

    async def start(self):
        """启动指标导出器"""

        if not PROMETHEUS_AVAILABLE:
            print("❌ Prometheus客户端不可用，无法启动导出器")
            return

        if self.is_running:
            print("指标导出器已启动")
            return

        print(f"🚀 启动Prometheus指标导出器 (端口: {self.port})...")

        # 启动HTTP服务器（在单独的线程中）
        def start_http_server_thread():
            try:
                start_http_server(self.port)
                print(f"✅ Prometheus指标服务器已启动: http://localhost:{self.port}")
            except Exception as e:
                print(f"❌ 启动HTTP服务器失败: {e}")

        self.http_server_thread = threading.Thread(target=start_http_server_thread)
        self.http_server_thread.daemon = True
        self.http_server_thread.start()

        # 启动指标收集任务
        self.is_running = True
        self.export_task = asyncio.create_task(self._metric_collection_task())

        print("✅ Prometheus指标导出器已启动")

    async def stop(self):
        """停止指标导出器"""

        print("🛑 停止Prometheus指标导出器...")
        self.is_running = False

        if self.export_task:
            self.export_task.cancel()
            await asyncio.gather(self.export_task, return_exceptions=True)

        print("✅ Prometheus指标导出器已停止")

    async def _metric_collection_task(self):
        """指标收集任务"""

        print("📊 启动指标收集任务...")

        while self.is_running:
            try:
                # 收集系统指标
                await self._collect_system_metrics()

                # 收集业务指标（这里应该从其他模块获取）
                # 例如：await self._collect_trading_metrics()

                # 清理旧指标历史
                await self._cleanup_old_metrics()

                # 每30秒收集一次
                await asyncio.sleep(30)

            except Exception as e:
                print(f"指标收集任务出错: {e}")
                await asyncio.sleep(60)

    async def _collect_system_metrics(self):
        """收集系统指标"""

        import os

        import psutil

        try:
            # 获取当前进程
            process = psutil.Process()

            # CPU使用率
            cpu_percent = process.cpu_percent()
            self.metrics["system_cpu_usage"].labels(component="trading_engine").set(cpu_percent)

            # 内存使用
            memory_info = process.memory_info()
            self.metrics["system_memory_usage"].labels(component="trading_engine").set(
                memory_info.rss
            )

            # 线程数
            thread_count = process.num_threads()
            self.metrics["system_thread_count"].labels(component="trading_engine").set(thread_count)

            # 记录指标历史
            self._record_metric_history(
                "system_cpu_usage", cpu_percent, {"component": "trading_engine"}
            )

        except Exception as e:
            print(f"收集系统指标失败: {e}")

    async def _cleanup_old_metrics(self):
        """清理旧指标历史"""

        cutoff_time = datetime.now() - timedelta(hours=24)

        for metric_name in list(self.metric_history.keys()):
            self.metric_history[metric_name] = [
                metric
                for metric in self.metric_history[metric_name]
                if metric.timestamp > cutoff_time
            ]

    def _record_metric_history(self, metric_name: str, value: float, labels: Dict[str, str]):
        """记录指标历史"""

        metric = TradingMetric(
            name=metric_name,
            value=value,
            labels=labels,
            metric_type="gauge",
            timestamp=datetime.now(),
        )

        self.metric_history[metric_name].append(metric)

        # 保持历史记录长度
        if len(self.metric_history[metric_name]) > 1000:
            self.metric_history[metric_name] = self.metric_history[metric_name][-1000:]

    # 公共接口 - 指标更新方法

    def record_order_submitted(self, symbol: str, order_type: str, side: str):
        """记录订单提交"""

        if "trading_orders_submitted" in self.metrics:
            self.metrics["trading_orders_submitted"].labels(
                symbol=symbol, order_type=order_type, side=side
            ).inc()

    def record_order_executed(self, symbol: str, order_type: str, side: str, duration: float):
        """记录订单执行"""

        if "trading_orders_executed" in self.metrics:
            self.metrics["trading_orders_executed"].labels(
                symbol=symbol, order_type=order_type, side=side
            ).inc()

        if "trading_order_execution_duration" in self.metrics:
            self.metrics["trading_order_execution_duration"].labels(
                symbol=symbol, order_type=order_type
            ).observe(duration)

    def record_order_cancelled(self, symbol: str, order_type: str, side: str):
        """记录订单取消"""

        if "trading_orders_cancelled" in self.metrics:
            self.metrics["trading_orders_cancelled"].labels(
                symbol=symbol, order_type=order_type, side=side
            ).inc()

    def record_portfolio_value(self, account: str, value: float):
        """记录投资组合价值"""

        if "portfolio_total_value" in self.metrics:
            self.metrics["portfolio_total_value"].labels(account=account).set(value)

    def record_portfolio_return(self, account: str, timeframe: str, return_percent: float):
        """记录投资组合收益率"""

        if "portfolio_return" in self.metrics:
            self.metrics["portfolio_return"].labels(account=account, timeframe=timeframe).set(
                return_percent
            )

    def record_portfolio_drawdown(self, account: str, drawdown_percent: float):
        """记录投资组合回撤"""

        if "portfolio_drawdown" in self.metrics:
            self.metrics["portfolio_drawdown"].labels(account=account).set(drawdown_percent)

        if "risk_max_drawdown" in self.metrics:
            self.metrics["risk_max_drawdown"].labels(account=account).set(drawdown_percent)

    def record_market_volatility(self, symbol: str, timeframe: str, volatility_percent: float):
        """记录市场波动性"""

        if "market_volatility" in self.metrics:
            self.metrics["market_volatility"].labels(symbol=symbol, timeframe=timeframe).set(
                volatility_percent
            )

    def record_market_liquidity(self, symbol: str, liquidity_score: float):
        """记录市场流动性"""

        if "market_liquidity" in self.metrics:
            self.metrics["market_liquidity"].labels(symbol=symbol).set(liquidity_score)

    def record_error(self, component: str, error_type: str):
        """记录错误"""

        if "errors_total" in self.metrics:
            self.metrics["errors_total"].labels(component=component, error_type=error_type).inc()

    def record_compliance_check(self, standard: str, status: str):
        """记录合规性检查"""

        if "compliance_checks" in self.metrics:
            self.metrics["compliance_checks"].labels(standard=standard, status=status).inc()

    def record_compliance_violation(self, standard: str, violation_type: str):
        """记录合规性违规"""

        if "compliance_violations" in self.metrics:
            self.metrics["compliance_violations"].labels(
                standard=standard, violation_type=violation_type
            ).inc()

    def record_security_event(self, event_type: str, severity: str):
        """记录安全事件"""

        if "security_events" in self.metrics:
            self.metrics["security_events"].labels(event_type=event_type, severity=severity).inc()

    def record_unauthorized_access(self, source: str, target: str):
        """记录未授权访问"""

        if "unauthorized_access" in self.metrics:
            self.metrics["unauthorized_access"].labels(source=source, target=target).inc()

    def record_predicted_loss(self, model: str, loss_percent: float):
        """记录预测损失"""

        if "predicted_loss" in self.metrics:
            self.metrics["predicted_loss"].labels(model=model).set(loss_percent)

    def record_predicted_crash_probability(self, model: str, probability: float):
        """记录预测市场崩盘概率"""

        if "predicted_crash_probability" in self.metrics:
            self.metrics["predicted_crash_probability"].labels(model=model).set(probability)

    def get_metric_history(self, metric_name: str, limit: int = 100) -> List[TradingMetric]:
        """获取指标历史"""

        return self.metric_history.get(metric_name, [])[-limit:]

    def get_current_metrics(self) -> Dict[str, Dict[str, Any]]:
        """获取当前指标值"""

        current_metrics = {}

        for metric_name, metric_obj in self.metrics.items():
            try:
                # 获取指标当前值（简化实现）
                current_metrics[metric_name] = {
                    "name": metric_name,
                    "type": metric_obj.__class__.__name__,
                    "samples": [],  # 这里应该获取实际样本
                }
            except Exception as e:
                print(f"获取指标 {metric_name} 失败: {e}")

        return current_metrics

    def export_metrics(self) -> str:
        """导出指标为Prometheus格式"""

        if not PROMETHEUS_AVAILABLE:
            return "# Prometheus客户端不可用\n"

        try:
            return generate_latest(REGISTRY).decode("utf-8")
        except Exception as e:
            return f"# 导出指标失败: {e}\n"


# 单例实例
_prometheus_exporter = None


def get_prometheus_exporter(config_manager=None, port: int = 9091) -> PrometheusExporter:
    """获取Prometheus导出器单例"""
    global _prometheus_exporter
    if _prometheus_exporter is None:
        _prometheus_exporter = PrometheusExporter(config_manager, port)
    return _prometheus_exporter


async def test_prometheus_exporter():
    """测试Prometheus导出器"""

    if not PROMETHEUS_AVAILABLE:
        print("⚠️ 跳过测试：Prometheus客户端不可用")
        return

    exporter = get_prometheus_exporter()
    await exporter.start()

    try:
        print("等待指标服务器启动...")
        await asyncio.sleep(2)

        # 模拟一些指标
        exporter.record_order_submitted("BTCUSDT", "LIMIT", "BUY")
        exporter.record_order_executed("BTCUSDT", "LIMIT", "BUY", 0.5)
        exporter.record_portfolio_value("main", 100000.0)
        exporter.record_portfolio_drawdown("main", 2.5)
        exporter.record_market_volatility("BTCUSDT", "1h", 3.2)
        exporter.record_error("trading_engine", "connection_timeout")

        print("✅ 测试指标已记录")
        print(f"📊 指标端点: http://localhost:{exporter.port}")

        # 导出指标
        metrics = exporter.export_metrics()
        print(f"\n指标示例（前500字符）:\n{metrics[:500]}...")

        # 保持运行
        await asyncio.sleep(30)

    finally:
        await exporter.stop()


if __name__ == "__main__":
    asyncio.run(test_prometheus_exporter())
