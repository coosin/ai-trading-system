#!/usr/bin/env python3
"""
性能监控模块
实时监控系统性能，识别瓶颈，优化资源使用
"""

import asyncio
import time
import psutil
import threading
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import defaultdict, deque
import statistics
import json

@dataclass
class PerformanceMetric:
    """性能指标"""
    timestamp: datetime
    metric_type: str
    value: float
    tags: Dict[str, str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = {}

@dataclass
class PerformanceAlert:
    """性能告警"""
    timestamp: datetime
    alert_type: str
    severity: str  # INFO, WARNING, CRITICAL
    message: str
    metric_value: float
    threshold: float
    suggestion: str = ""

@dataclass
class BottleneckAnalysis:
    """瓶颈分析"""
    timestamp: datetime
    component: str
    metric_type: str
    current_value: float
    average_value: float
    max_value: float
    percentile_95: float
    is_bottleneck: bool
    severity: str
    recommendations: List[str]

class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        
        # 指标存储
        self.metrics: Dict[str, List[PerformanceMetric]] = defaultdict(list)
        self.metric_windows: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        
        # 告警存储
        self.alerts: List[PerformanceAlert] = []
        
        # 性能阈值配置
        self.thresholds = self._load_thresholds()
        
        # 监控任务
        self.monitoring_tasks = []
        self.is_running = False
        
        # 回调函数
        self.alert_callbacks: List[Callable] = []
        
        # 性能分析
        self.bottleneck_history: List[BottleneckAnalysis] = []
        
    def _load_thresholds(self) -> Dict[str, Dict]:
        """加载性能阈值"""
        
        thresholds = {
            'cpu': {
                'warning': 70.0,   # CPU使用率警告阈值
                'critical': 90.0,  # CPU使用率严重阈值
                'duration': 60      # 持续时间(秒)
            },
            'memory': {
                'warning': 75.0,   # 内存使用率警告阈值
                'critical': 90.0,  # 内存使用率严重阈值
                'duration': 60
            },
            'disk': {
                'warning': 80.0,   # 磁盘使用率警告阈值
                'critical': 95.0,  # 磁盘使用率严重阈值
                'duration': 300
            },
            'network': {
                'warning': 10000000,  # 网络IO警告阈值 (bytes/s)
                'critical': 50000000, # 网络IO严重阈值
                'duration': 30
            },
            'latency': {
                'warning': 1.0,     # 延迟警告阈值 (秒)
                'critical': 3.0,    # 延迟严重阈值
                'duration': 30
            },
            'error_rate': {
                'warning': 1.0,     # 错误率警告阈值 (%)
                'critical': 5.0,    # 错误率严重阈值
                'duration': 300
            },
            'queue_size': {
                'warning': 100,     # 队列大小警告阈值
                'critical': 500,    # 队列大小严重阈值
                'duration': 60
            }
        }
        
        return thresholds
    
    async def start(self):
        """启动性能监控"""
        
        if self.is_running:
            print("性能监控已启动")
            return
        
        print("🚀 启动性能监控系统...")
        self.is_running = True
        
        # 启动监控任务
        self.monitoring_tasks = [
            asyncio.create_task(self._monitor_system_resources()),
            asyncio.create_task(self._monitor_application_metrics()),
            asyncio.create_task(self._monitor_bottlenecks()),
            asyncio.create_task(self._cleanup_old_metrics())
        ]
        
        print("✅ 性能监控系统已启动")
    
    async def stop(self):
        """停止性能监控"""
        
        print("🛑 停止性能监控系统...")
        self.is_running = False
        
        # 取消所有任务
        for task in self.monitoring_tasks:
            task.cancel()
        
        # 等待任务完成
        await asyncio.gather(*self.monitoring_tasks, return_exceptions=True)
        
        print("✅ 性能监控系统已停止")
    
    async def _monitor_system_resources(self):
        """监控系统资源"""
        
        print("📊 开始监控系统资源...")
        
        while self.is_running:
            try:
                # CPU使用率
                cpu_percent = psutil.cpu_percent(interval=1)
                await self.record_metric('cpu', 'usage_percent', cpu_percent, {'type': 'system'})
                
                # 内存使用
                memory = psutil.virtual_memory()
                await self.record_metric('memory', 'usage_percent', memory.percent, {'type': 'system'})
                await self.record_metric('memory', 'used_mb', memory.used / 1024 / 1024, {'type': 'system'})
                await self.record_metric('memory', 'available_mb', memory.available / 1024 / 1024, {'type': 'system'})
                
                # 磁盘使用
                disk = psutil.disk_usage('/')
                await self.record_metric('disk', 'usage_percent', disk.percent, {'type': 'system'})
                await self.record_metric('disk', 'free_gb', disk.free / 1024 / 1024 / 1024, {'type': 'system'})
                
                # 网络IO
                net_io = psutil.net_io_counters()
                await self.record_metric('network', 'bytes_sent', net_io.bytes_sent, {'type': 'system'})
                await self.record_metric('network', 'bytes_recv', net_io.bytes_recv, {'type': 'system'})
                
                # 检查阈值
                await self._check_thresholds()
                
                # 每5秒监控一次
                await asyncio.sleep(5)
                
            except Exception as e:
                print(f"系统资源监控出错: {e}")
                await asyncio.sleep(10)
    
    async def _monitor_application_metrics(self):
        """监控应用程序指标"""
        
        print("📈 开始监控应用程序指标...")
        
        while self.is_running:
            try:
                # 这里可以添加应用程序特定的监控
                # 例如：交易频率、数据处理延迟、API调用成功率等
                
                # 监控Python进程
                process = psutil.Process()
                
                # 进程内存
                process_memory = process.memory_info()
                await self.record_metric('process', 'rss_mb', process_memory.rss / 1024 / 1024, {'type': 'application'})
                await self.record_metric('process', 'vms_mb', process_memory.vms / 1024 / 1024, {'type': 'application'})
                
                # 进程CPU
                process_cpu = process.cpu_percent()
                await self.record_metric('process', 'cpu_percent', process_cpu, {'type': 'application'})
                
                # 线程数
                thread_count = process.num_threads()
                await self.record_metric('process', 'thread_count', thread_count, {'type': 'application'})
                
                # 每10秒监控一次
                await asyncio.sleep(10)
                
            except Exception as e:
                print(f"应用程序监控出错: {e}")
                await asyncio.sleep(15)
    
    async def _monitor_bottlenecks(self):
        """监控性能瓶颈"""
        
        print("🔍 开始监控性能瓶颈...")
        
        while self.is_running:
            try:
                # 分析各个组件的性能
                bottlenecks = await self._analyze_bottlenecks()
                
                for bottleneck in bottlenecks:
                    if bottleneck.is_bottleneck:
                        print(f"⚠️ 发现性能瓶颈: {bottleneck.component} - {bottleneck.metric_type}")
                        
                        # 记录瓶颈分析
                        self.bottleneck_history.append(bottleneck)
                        
                        # 保持历史记录长度
                        if len(self.bottleneck_history) > 100:
                            self.bottleneck_history = self.bottleneck_history[-100:]
                
                # 每30秒分析一次
                await asyncio.sleep(30)
                
            except Exception as e:
                print(f"瓶颈监控出错: {e}")
                await asyncio.sleep(60)
    
    async def _cleanup_old_metrics(self):
        """清理旧指标"""
        
        print("🧹 开始清理旧指标...")
        
        while self.is_running:
            try:
                cutoff_time = datetime.now() - timedelta(hours=24)
                
                for metric_type in list(self.metrics.keys()):
                    # 过滤出24小时内的指标
                    self.metrics[metric_type] = [
                        metric for metric in self.metrics[metric_type]
                        if metric.timestamp > cutoff_time
                    ]
                
                # 清理旧告警
                cutoff_time = datetime.now() - timedelta(hours=6)
                self.alerts = [
                    alert for alert in self.alerts
                    if alert.timestamp > cutoff_time
                ]
                
                # 每小时清理一次
                await asyncio.sleep(3600)
                
            except Exception as e:
                print(f"清理指标出错: {e}")
                await asyncio.sleep(1800)
    
    async def record_metric(self, category: str, metric_name: str, value: float, tags: Dict[str, str] = None):
        """记录性能指标"""
        
        try:
            metric = PerformanceMetric(
                timestamp=datetime.now(),
                metric_type=f"{category}.{metric_name}",
                value=value,
                tags=tags or {}
            )
            
            # 存储指标
            self.metrics[metric.metric_type].append(metric)
            
            # 更新滑动窗口
            self.metric_windows[metric.metric_type].append(metric)
            
            # 检查是否超过阈值
            await self._check_metric_threshold(metric)
            
        except Exception as e:
            print(f"记录指标出错: {e}")
    
    async def _check_metric_threshold(self, metric: PerformanceMetric):
        """检查指标是否超过阈值"""
        
        metric_type = metric.metric_type
        value = metric.value
        
        # 确定指标类别
        category = None
        if 'cpu' in metric_type:
            category = 'cpu'
        elif 'memory' in metric_type:
            category = 'memory'
        elif 'disk' in metric_type:
            category = 'disk'
        elif 'network' in metric_type:
            category = 'network'
        elif 'latency' in metric_type:
            category = 'latency'
        elif 'error' in metric_type or 'failure' in metric_type:
            category = 'error_rate'
        elif 'queue' in metric_type:
            category = 'queue_size'
        
        if not category or category not in self.thresholds:
            return
        
        thresholds = self.thresholds[category]
        
        # 检查是否超过阈值
        if 'critical' in thresholds and value >= thresholds['critical']:
            await self._create_alert(
                alert_type=f"{category}_critical",
                severity="CRITICAL",
                message=f"{metric_type} 达到严重阈值: {value:.2f} >= {thresholds['critical']}",
                metric_value=value,
                threshold=thresholds['critical'],
                suggestion=self._get_threshold_suggestion(category, 'critical')
            )
        
        elif 'warning' in thresholds and value >= thresholds['warning']:
            await self._create_alert(
                alert_type=f"{category}_warning",
                severity="WARNING",
                message=f"{metric_type} 达到警告阈值: {value:.2f} >= {thresholds['warning']}",
                metric_value=value,
                threshold=thresholds['warning'],
                suggestion=self._get_threshold_suggestion(category, 'warning')
            )
    
    async def _check_thresholds(self):
        """检查所有阈值"""
        
        # 这里可以添加更复杂的阈值检查逻辑
        # 例如：持续超过阈值、多个指标同时超阈值等
        
        pass
    
    async def _create_alert(self, alert_type: str, severity: str, message: str, 
                          metric_value: float, threshold: float, suggestion: str = ""):
        """创建告警"""
        
        alert = PerformanceAlert(
            timestamp=datetime.now(),
            alert_type=alert_type,
            severity=severity,
            message=message,
            metric_value=metric_value,
            threshold=threshold,
            suggestion=suggestion
        )
        
        self.alerts.append(alert)
        
        # 触发告警回调
        await self._trigger_alert_callbacks(alert)
        
        # 打印告警
        print(f"🚨 {severity}: {message}")
    
    async def _trigger_alert_callbacks(self, alert: PerformanceAlert):
        """触发告警回调"""
        
        for callback in self.alert_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(alert)
                else:
                    callback(alert)
            except Exception as e:
                print(f"告警回调执行失败: {e}")
    
    def _get_threshold_suggestion(self, category: str, level: str) -> str:
        """获取阈值建议"""
        
        suggestions = {
            'cpu': {
                'warning': "考虑优化CPU密集型操作，或增加监控间隔",
                'critical': "立即检查CPU使用情况，可能需要扩容或优化代码"
            },
            'memory': {
                'warning': "检查内存泄漏，考虑优化内存使用",
                'critical': "内存使用过高，可能发生OOM，立即处理"
            },
            'disk': {
                'warning': "磁盘空间不足，考虑清理或扩容",
                'critical': "磁盘空间严重不足，立即处理"
            },
            'network': {
                'warning': "网络流量较高，检查是否正常",
                'critical': "网络流量异常，可能遭受攻击或配置错误"
            },
            'latency': {
                'warning': "延迟较高，检查网络或服务状态",
                'critical': "延迟严重，可能影响交易执行"
            },
            'error_rate': {
                'warning': "错误率升高，检查系统稳定性",
                'critical': "错误率严重，系统可能不稳定"
            },
            'queue_size': {
                'warning': "队列积压，处理能力不足",
                'critical': "队列严重积压，可能丢失数据"
            }
        }
        
        return suggestions.get(category, {}).get(level, "请检查系统状态")
    
    async def _analyze_bottlenecks(self) -> List[BottleneckAnalysis]:
        """分析性能瓶颈"""
        
        bottlenecks = []
        
        # 分析各个指标
        for metric_type, metrics in self.metric_windows.items():
            if len(metrics) < 10:  # 数据不足
                continue
            
            values = [m.value for m in metrics]
            
            # 计算统计信息
            current_value = values[-1] if values else 0
            avg_value = statistics.mean(values) if values else 0
            max_value = max(values) if values else 0
            
            # 计算95百分位
            if len(values) >= 5:
                sorted_values = sorted(values)
                percentile_95 = sorted_values[int(len(sorted_values) * 0.95)]
            else:
                percentile_95 = current_value
            
            # 判断是否为瓶颈
            is_bottleneck = False
            severity = "NORMAL"
            
            # 根据指标类型判断瓶颈
            if 'cpu' in metric_type or 'memory' in metric_type:
                if current_value > 80:
                    is_bottleneck = True
                    severity = "HIGH"
                elif current_value > 60 and current_value > avg_value * 1.5:
                    is_bottleneck = True
                    severity = "MEDIUM"
            
            elif 'latency' in metric_type:
                if current_value > 2.0:  # 2秒
                    is_bottleneck = True
                    severity = "HIGH"
                elif current_value > 1.0 and current_value > avg_value * 2:
                    is_bottleneck = True
                    severity = "MEDIUM"
            
            elif 'error' in metric_type or 'failure' in metric_type:
                if current_value > 5.0:  # 5%
                    is_bottleneck = True
                    severity = "HIGH"
                elif current_value > 1.0:
                    is_bottleneck = True
                    severity = "MEDIUM"
            
            if is_bottleneck:
                # 生成建议
                recommendations = self._generate_recommendations(metric_type, current_value, avg_value)
                
                bottleneck = BottleneckAnalysis(
                    timestamp=datetime.now(),
                    component=self._get_component_from_metric(metric_type),
                    metric_type=metric_type,
                    current_value=current_value,
                    average_value=avg_value,
                    max_value=max_value,
                    percentile_95=percentile_95,
                    is_bottleneck=is_bottleneck,
                    severity=severity,
                    recommendations=recommendations
                )
                
                bottlenecks.append(bottleneck)
        
        return bottlenecks
    
    def _get_component_from_metric(self, metric_type: str) -> str:
        """从指标类型获取组件名称"""
        
        if 'system' in metric_type:
            return 'system'
        elif 'process' in metric_type:
            return 'application'
        elif 'trading' in metric_type:
            return 'trading_engine'
        elif 'data' in metric_type:
            return 'data_pipeline'
        elif 'ai' in metric_type or 'model' in metric_type:
            return 'ai_engine'
        elif 'network' in metric_type:
            return 'network'
        elif 'disk' in metric_type:
            return 'storage'
        else:
            return 'unknown'
    
    def _generate_recommendations(self, metric_type: str, current_value: float, avg_value: float) -> List[str]:
        """生成优化建议"""
        
        recommendations = []
        
        if 'cpu' in metric_type:
            if current_value > 80:
                recommendations.append("优化CPU密集型操作")
                recommendations.append("考虑使用异步编程")
                recommendations.append("检查是否有无限循环")
            elif current_value > avg_value * 1.5:
                recommendations.append("检查最近的代码变更")
                recommendations.append("考虑增加监控频率")
        
        elif 'memory' in metric_type:
            if current_value > 80:
                recommendations.append("检查内存泄漏")
                recommendations.append("优化数据结构")
                recommendations.append("考虑使用内存缓存")
            elif current_value > avg_value * 1.5:
                recommendations.append("检查是否有大对象创建")
                recommendations.append("考虑使用生成器")
        
        elif 'latency' in metric_type:
            if current_value > 2.0:
                recommendations.append("优化网络请求")
                recommendations.append("检查外部API响应时间")
                recommendations.append("考虑使用缓存")
            elif current_value > avg_value * 2:
                recommendations.append("检查网络连接")
                recommendations.append("优化数据库查询")
        
        elif 'disk' in metric_type:
            if current_value > 80:
                recommendations.append("清理磁盘空间")
                recommendations.append("考虑使用云存储")
                recommendations.append("优化日志轮转")
        
        elif 'error' in metric_type or 'failure' in metric_type:
            if current_value > 5.0:
                recommendations.append("检查错误日志")
                recommendations.append("增加错误处理")
                recommendations.append("考虑熔断机制")
        
        # 如果没有特定建议，添加通用建议
        if not recommendations:
            recommendations.append("增加监控频率")
            recommendations.append("检查相关日志")
            recommendations.append("考虑性能优化")
        
        return recommendations
    
    # 公共接口
    
    def register_alert_callback(self, callback: Callable):
        """注册告警回调"""
        self.alert_callbacks.append(callback)
    
    def get_metrics(self, metric_type: str = None, limit: int = 100) -> List[PerformanceMetric]:
        """获取性能指标"""
        
        if metric_type:
            metrics = self.metrics.get(metric_type, [])
        else:
            # 返回所有指标
            metrics = []
            for mt in self.metrics.values():
                metrics.extend(mt)
        
        # 按时间排序
        metrics.sort(key=lambda x: x.timestamp, reverse=True)
        
        return metrics[:limit]
    
    def get_alerts(self, severity: str = None, limit: int = 50) -> List[PerformanceAlert]:
        """获取告警"""
        
        if severity:
            filtered = [alert for alert in self.alerts if alert.severity == severity]
        else:
            filtered = self.alerts
        
        # 按时间排序
        filtered.sort(key=lambda x: x.timestamp, reverse=True)
        
        return filtered[:limit]
    
    def get_bottlenecks(self, severity: str = None, limit: int = 20) -> List[BottleneckAnalysis]:
        """获取瓶颈分析"""
        
        if severity:
            filtered = [b for b in self.bottleneck_history if b.severity == severity]
        else:
            filtered = self.bottleneck_history
        
        # 按时间排序
        filtered.sort(key=lambda x: x.timestamp, reverse=True)
        
        return filtered[:limit]
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """获取性能摘要"""
        
        summary = {
            'timestamp': datetime.now().isoformat(),
            'system': {},
            'application': {},
            'alerts': {},
            'bottlenecks': {}
        }
        
        # 系统资源
        try:
            cpu_percent = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            summary['system'] = {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_used_mb': memory.used / 1024 / 1024,
                'memory_available_mb': memory.available / 1024 / 1024,
                'disk_percent': disk.percent,
                'disk_free_gb': disk.free / 1024 / 1024 / 1024
            }
        except Exception as e:
            summary['system']['error'] = str(e)
        
        # 应用程序
        try:
            process = psutil.Process()
            process_memory = process.memory_info()
            
            summary['application'] = {
                'process_cpu_percent': process.cpu_percent(),
                'process_rss_mb': process_memory.rss / 1024 / 1024,
                'process_threads': process.num_threads(),
                'process_uptime_seconds': time.time() - process.create_time()
            }
        except Exception as e:
            summary['application']['error'] = str(e)
        
        # 告警统计
        alert_counts = defaultdict(int)
        for alert in self.alerts[-100:]:  # 最近100条告警
            alert_counts[alert.severity] += 1
        
        summary['alerts'] = dict(alert_counts)
        
        # 瓶颈统计
        bottleneck_counts = defaultdict(int)
        for bottleneck in self.bottleneck_history[-50:]:  # 最近50个瓶颈
            if bottleneck.is_bottleneck:
                bottleneck_counts[bottleneck.severity] += 1
        
        summary['bottlenecks'] = dict(bottleneck_counts)
        
        return summary
    
    def export_metrics(self, format: str = 'json') -> str:
        """导出性能指标"""
        
        data = {
            'summary': self.get_performance_summary(),
            'recent_alerts': [asdict(alert) for alert in self.get_alerts(limit=20)],
            'recent_bottlenecks': [asdict(bottleneck) for bottleneck in self.get_bottlenecks(limit=10)]
        }
        
        if format == 'json':
            return json.dumps(data, indent=2, default=str)
        else:
            raise ValueError(f"不支持的格式: {format}")
    
    async def profile_function(self, func_name: str, func: Callable, *args, **kwargs) -> Any:
        """性能剖析装饰器"""
        
        start_time = time.perf_counter()
        
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            latency = time.perf_counter() - start_time
            
            # 记录延迟指标
            await self.record_metric(
                'latency', 
                func_name, 
                latency,
                {'function': func_name}
            )
            
            return result
            
        except Exception as e:
            # 记录错误
            await self.record_metric(
                'error',
                f"{func_name}_error",
                1.0,
                {'function': func_name, 'error': str(e)}
            )
            raise e

# 单例实例
_performance_monitor = None

def get_performance_monitor(config_manager=None) -> PerformanceMonitor:
    """获取性能监控器单例"""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor(config_manager)
    return _performance_monitor

async def test_performance_monitor():
    """测试性能监控"""
    
    monitor = get_performance_monitor()
    await monitor.start()
    
    try:
        # 注册告警回调
        def alert_callback(alert: PerformanceAlert):
            print(f"收到告警: {alert.severity} - {alert.message}")
        
        monitor.register_alert_callback(alert_callback)
        
        # 模拟一些指标
        for i in range(10):
            await monitor.record_metric('test', 'latency', i * 0.1)
            await monitor.record_metric('test', 'cpu', 50 + i * 5)
            await asyncio.sleep(1)
        
        # 获取性能摘要
        summary = monitor.get_performance_summary()
        print(f"性能摘要: {json.dumps(summary, indent=2, default=str)}")
        
        # 保持运行
        await asyncio.sleep(10)
        
    finally:
        await monitor.stop()

if __name__ == "__main__":
    asyncio.run(test_performance_monitor())