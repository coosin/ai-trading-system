"""
增强的数据质量监控系统

功能：
1. 数据完整性检查 - 检测缺失值、异常值
2. 数据一致性检查 - 跨数据源验证
3. 数据时效性检查 - 监控数据更新频率
4. 数据异常检测 - 统计方法和机器学习
5. 数据质量报告和告警
"""

import asyncio
import logging
import math
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor

logger = logging.getLogger(__name__)


class DataQualityLevel(Enum):
    """数据质量级别"""
    EXCELLENT = "excellent"  # 优秀
    GOOD = "good"          # 良好
    ACCEPTABLE = "acceptable"  # 可接受
    POOR = "poor"          # 差
    CRITICAL = "critical"    # 严重


class DataIssueType(Enum):
    """数据问题类型"""
    MISSING = "missing"      # 缺失值
    OUTLIER = "outlier"      # 异常值
    INCONSISTENT = "inconsistent"  # 不一致
    STALE = "stale"         # 过期
    DUPLICATE = "duplicate"  # 重复
    FORMAT_ERROR = "format_error"  # 格式错误


@dataclass
class DataQualityMetric:
    """数据质量指标"""
    name: str
    value: float
    threshold: float
    level: DataQualityLevel
    timestamp: datetime = field(default_factory=datetime.now)
    description: str = ""


@dataclass
class DataIssue:
    """数据问题"""
    id: str
    data_source: str
    issue_type: DataIssueType
    severity: DataQualityLevel
    description: str
    timestamp: datetime = field(default_factory=datetime.now)
    affected_records: int = 0
    location: str = ""
    resolved: bool = False


class DataQualityChecker:
    """数据质量检查器"""
    
    def __init__(self):
        self.issues: List[DataIssue] = []
        self.metrics: List[DataQualityMetric] = []
        self._anomaly_detectors: Dict[str, Any] = {}
    
    async def check_data_integrity(self, data: pd.DataFrame, 
                                 data_source: str) -> List[DataIssue]:
        """检查数据完整性"""
        issues = []
        
        # 检查缺失值
        missing_cols = data.columns[data.isnull().any()]
        for col in missing_cols:
            missing_count = data[col].isnull().sum()
            missing_ratio = missing_count / len(data)
            
            if missing_ratio > 0.5:
                severity = DataQualityLevel.CRITICAL
            elif missing_ratio > 0.2:
                severity = DataQualityLevel.POOR
            elif missing_ratio > 0.05:
                severity = DataQualityLevel.ACCEPTABLE
            else:
                severity = DataQualityLevel.GOOD
            
            if severity.value in ["critical", "poor"]:
                issue = DataIssue(
                    id=f"{data_source}_missing_{col}",
                    data_source=data_source,
                    issue_type=DataIssueType.MISSING,
                    severity=severity,
                    description=f"Column {col} has {missing_ratio:.2f}% missing values",
                    affected_records=missing_count,
                    location=col
                )
                issues.append(issue)
        
        # 检查重复值
        duplicate_rows = data.duplicated().sum()
        if duplicate_rows > 0:
            duplicate_ratio = duplicate_rows / len(data)
            if duplicate_ratio > 0.1:
                severity = DataQualityLevel.POOR
            else:
                severity = DataQualityLevel.ACCEPTABLE
            
            issue = DataIssue(
                id=f"{data_source}_duplicate",
                data_source=data_source,
                issue_type=DataIssueType.DUPLICATE,
                severity=severity,
                description=f"Dataset has {duplicate_ratio:.2f}% duplicate rows",
                affected_records=duplicate_rows
            )
            issues.append(issue)
        
        return issues
    
    async def check_data_consistency(self, data_sources: Dict[str, pd.DataFrame]) -> List[DataIssue]:
        """检查数据一致性"""
        issues = []
        
        # 获取所有数据源的共同列
        common_cols = set()
        for data in data_sources.values():
            if not common_cols:
                common_cols = set(data.columns)
            else:
                common_cols.intersection_update(data.columns)
        
        # 检查共同列的值一致性
        for col in common_cols:
            # 收集所有数据源的值
            values = []
            sources_with_col = []
            
            for source, data in data_sources.items():
                if col in data.columns:
                    source_values = data[col].dropna().values
                    if len(source_values) > 0:
                        values.append(source_values)
                        sources_with_col.append(source)
            
            if len(values) >= 2:
                # 计算数据源之间的差异
                for i in range(len(values)):
                    for j in range(i + 1, len(values)):
                        # 计算相关性
                        if len(values[i]) > 10 and len(values[j]) > 10:
                            # 取最小值长度
                            min_len = min(len(values[i]), len(values[j]))
                            correlation = np.corrcoef(values[i][:min_len], values[j][:min_len])[0, 1]
                            
                            if correlation < 0.7:
                                issue = DataIssue(
                                    id=f"consistency_{sources_with_col[i]}_{sources_with_col[j]}_{col}",
                                    data_source=f"{sources_with_col[i]} vs {sources_with_col[j]}",
                                    issue_type=DataIssueType.INCONSISTENT,
                                    severity=DataQualityLevel.POOR,
                                    description=f"Correlation for column {col} between {sources_with_col[i]} and {sources_with_col[j]} is {correlation:.2f}",
                                    location=col
                                )
                                issues.append(issue)
        
        return issues
    
    async def check_data_timeliness(self, data: pd.DataFrame, 
                                  data_source: str, 
                                  timestamp_col: str = "timestamp") -> List[DataIssue]:
        """检查数据时效性"""
        issues = []
        
        if timestamp_col in data.columns:
            # 转换为datetime
            try:
                data[timestamp_col] = pd.to_datetime(data[timestamp_col])
                
                # 检查最新数据时间
                latest_timestamp = data[timestamp_col].max()
                time_diff = datetime.now() - latest_timestamp
                
                if time_diff > timedelta(days=1):
                    severity = DataQualityLevel.CRITICAL
                elif time_diff > timedelta(hours=6):
                    severity = DataQualityLevel.POOR
                elif time_diff > timedelta(hours=1):
                    severity = DataQualityLevel.ACCEPTABLE
                else:
                    severity = DataQualityLevel.GOOD
                
                if severity.value in ["critical", "poor"]:
                    issue = DataIssue(
                        id=f"{data_source}_stale",
                        data_source=data_source,
                        issue_type=DataIssueType.STALE,
                        severity=severity,
                        description=f"Latest data is {time_diff.total_seconds()/3600:.1f} hours old",
                        location=timestamp_col
                    )
                    issues.append(issue)
                    
                # 检查数据更新频率
                data_sorted = data.sort_values(timestamp_col)
                time_diffs = data_sorted[timestamp_col].diff().dropna()
                if len(time_diffs) > 0:
                    avg_interval = time_diffs.mean().total_seconds()
                    std_interval = time_diffs.std().total_seconds()
                    
                    # 检查更新频率的稳定性
                    if std_interval / avg_interval > 2:
                        issue = DataIssue(
                            id=f"{data_source}_inconsistent_update",
                            data_source=data_source,
                            issue_type=DataIssueType.INCONSISTENT,
                            severity=DataQualityLevel.ACCEPTABLE,
                            description=f"Data update interval is inconsistent (std/mean = {std_interval/avg_interval:.2f})",
                            location=timestamp_col
                        )
                        issues.append(issue)
                        
            except Exception as e:
                issue = DataIssue(
                    id=f"{data_source}_format_error",
                    data_source=data_source,
                    issue_type=DataIssueType.FORMAT_ERROR,
                    severity=DataQualityLevel.POOR,
                    description=f"Error parsing timestamp column: {e}",
                    location=timestamp_col
                )
                issues.append(issue)
        
        return issues
    
    async def detect_anomalies(self, data: pd.DataFrame, 
                             data_source: str, 
                             method: str = "isolation_forest") -> List[DataIssue]:
        """检测数据异常"""
        issues = []
        
        # 选择数值列
        numeric_cols = data.select_dtypes(include=[np.number]).columns
        
        for col in numeric_cols:
            # 过滤缺失值
            values = data[col].dropna().values
            if len(values) < 10:
                continue
            
            try:
                if method == "isolation_forest":
                    # 使用隔离森林
                    clf = IsolationForest(contamination=0.1, random_state=42)
                    predictions = clf.fit_predict(values.reshape(-1, 1))
                    anomaly_indices = np.where(predictions == -1)[0]
                    
                elif method == "lof":
                    # 使用局部异常因子
                    clf = LocalOutlierFactor(contamination=0.1)
                    predictions = clf.fit_predict(values.reshape(-1, 1))
                    anomaly_indices = np.where(predictions == -1)[0]
                    
                elif method == "zscore":
                    # 使用Z-score
                    z_scores = np.abs(stats.zscore(values))
                    anomaly_indices = np.where(z_scores > 3)[0]
                    
                else:
                    continue
                
                if len(anomaly_indices) > 0:
                    anomaly_ratio = len(anomaly_indices) / len(values)
                    
                    if anomaly_ratio > 0.2:
                        severity = DataQualityLevel.POOR
                    else:
                        severity = DataQualityLevel.ACCEPTABLE
                    
                    issue = DataIssue(
                        id=f"{data_source}_outlier_{col}",
                        data_source=data_source,
                        issue_type=DataIssueType.OUTLIER,
                        severity=severity,
                        description=f"Column {col} has {anomaly_ratio:.2f}% outliers",
                        affected_records=len(anomaly_indices),
                        location=col
                    )
                    issues.append(issue)
                    
            except Exception as e:
                logger.error(f"异常检测错误 {col}: {e}")
        
        return issues
    
    async def calculate_quality_metrics(self, data: pd.DataFrame) -> List[DataQualityMetric]:
        """计算数据质量指标"""
        metrics = []
        
        # 完整性指标
        total_cells = data.size
        missing_cells = data.isnull().sum().sum()
        completeness = 1 - (missing_cells / total_cells)
        
        if completeness >= 0.95:
            level = DataQualityLevel.EXCELLENT
        elif completeness >= 0.9:
            level = DataQualityLevel.GOOD
        elif completeness >= 0.8:
            level = DataQualityLevel.ACCEPTABLE
        elif completeness >= 0.7:
            level = DataQualityLevel.POOR
        else:
            level = DataQualityLevel.CRITICAL
        
        metrics.append(DataQualityMetric(
            name="completeness",
            value=completeness,
            threshold=0.9,
            level=level,
            description="数据完整性比例"
        ))
        
        # 一致性指标（列内标准差）
        numeric_cols = data.select_dtypes(include=[np.number]).columns
        if len(numeric_cols) > 0:
            stds = []
            for col in numeric_cols:
                if data[col].std() > 0:
                    stds.append(data[col].std() / data[col].mean())
            
            if stds:
                avg_cv = statistics.mean(stds)
                if avg_cv < 0.1:
                    level = DataQualityLevel.EXCELLENT
                elif avg_cv < 0.3:
                    level = DataQualityLevel.GOOD
                elif avg_cv < 0.5:
                    level = DataQualityLevel.ACCEPTABLE
                else:
                    level = DataQualityLevel.POOR
                
                metrics.append(DataQualityMetric(
                    name="consistency",
                    value=1 / (1 + avg_cv),  # 转换为0-1范围
                    threshold=0.7,
                    level=level,
                    description="数据一致性指标"
                ))
        
        # 唯一性指标
        duplicate_ratio = data.duplicated().sum() / len(data)
        uniqueness = 1 - duplicate_ratio
        
        if uniqueness >= 0.99:
            level = DataQualityLevel.EXCELLENT
        elif uniqueness >= 0.95:
            level = DataQualityLevel.GOOD
        elif uniqueness >= 0.9:
            level = DataQualityLevel.ACCEPTABLE
        else:
            level = DataQualityLevel.POOR
        
        metrics.append(DataQualityMetric(
            name="uniqueness",
            value=uniqueness,
            threshold=0.95,
            level=level,
            description="数据唯一性比例"
        ))
        
        return metrics
    
    async def generate_quality_report(self, data: pd.DataFrame, 
                                   data_source: str) -> Dict[str, Any]:
        """生成数据质量报告"""
        # 收集所有问题
        issues = []
        
        # 检查完整性
        integrity_issues = await self.check_data_integrity(data, data_source)
        issues.extend(integrity_issues)
        
        # 检查时效性
        timeliness_issues = await self.check_data_timeliness(data, data_source)
        issues.extend(timeliness_issues)
        
        # 检测异常
        anomaly_issues = await self.detect_anomalies(data, data_source)
        issues.extend(anomaly_issues)
        
        # 计算质量指标
        metrics = await self.calculate_quality_metrics(data)
        
        # 计算整体质量分数
        if metrics:
            avg_score = statistics.mean([m.value for m in metrics])
            if avg_score >= 0.95:
                overall_level = DataQualityLevel.EXCELLENT
            elif avg_score >= 0.9:
                overall_level = DataQualityLevel.GOOD
            elif avg_score >= 0.8:
                overall_level = DataQualityLevel.ACCEPTABLE
            elif avg_score >= 0.7:
                overall_level = DataQualityLevel.POOR
            else:
                overall_level = DataQualityLevel.CRITICAL
        else:
            avg_score = 0
            overall_level = DataQualityLevel.CRITICAL
        
        # 按严重程度分组问题
        critical_issues = [i for i in issues if i.severity == DataQualityLevel.CRITICAL]
        poor_issues = [i for i in issues if i.severity == DataQualityLevel.POOR]
        acceptable_issues = [i for i in issues if i.severity == DataQualityLevel.ACCEPTABLE]
        
        return {
            "data_source": data_source,
            "timestamp": datetime.now(),
            "overall_score": avg_score,
            "overall_level": overall_level.value,
            "metrics": [m.__dict__ for m in metrics],
            "issues": {
                "critical": [i.__dict__ for i in critical_issues],
                "poor": [i.__dict__ for i in poor_issues],
                "acceptable": [i.__dict__ for i in acceptable_issues]
            },
            "summary": {
                "total_issues": len(issues),
                "critical_count": len(critical_issues),
                "poor_count": len(poor_issues),
                "acceptable_count": len(acceptable_issues)
            }
        }
    
    def get_issues(self) -> List[DataIssue]:
        """获取所有问题"""
        return self.issues
    
    def get_metrics(self) -> List[DataQualityMetric]:
        """获取所有指标"""
        return self.metrics
    
    def clear_issues(self):
        """清除问题列表"""
        self.issues.clear()
    
    def clear_metrics(self):
        """清除指标列表"""
        self.metrics.clear()


class EnhancedDataQualitySystem:
    """增强的数据质量系统"""
    
    def __init__(self):
        self.checkers: Dict[str, DataQualityChecker] = {}
        self.reports: Dict[str, List[Dict[str, Any]]] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._check_interval = 60  # 秒
    
    async def initialize(self):
        """初始化数据质量系统"""
        self._running = True
        self._task = asyncio.create_task(self._monitoring_loop())
        logger.info("数据质量系统初始化完成")
    
    async def cleanup(self):
        """清理资源"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("数据质量系统清理完成")
    
    def register_data_source(self, name: str):
        """注册数据源"""
        if name not in self.checkers:
            self.checkers[name] = DataQualityChecker()
            self.reports[name] = []
            logger.info(f"注册数据源: {name}")
    
    async def check_data_source(self, name: str, data: pd.DataFrame) -> Dict[str, Any]:
        """检查数据源"""
        if name not in self.checkers:
            self.register_data_source(name)
        
        checker = self.checkers[name]
        report = await checker.generate_quality_report(data, name)
        
        # 保存报告
        self.reports[name].append(report)
        
        # 限制报告数量
        if len(self.reports[name]) > 100:
            self.reports[name] = self.reports[name][-100:]
        
        return report
    
    async def _monitoring_loop(self):
        """监控循环"""
        while self._running:
            try:
                # 这里可以添加定期检查逻辑
                await asyncio.sleep(self._check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"数据质量监控循环错误: {e}")
                await asyncio.sleep(self._check_interval)
    
    def get_report_history(self, name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取报告历史"""
        if name in self.reports:
            return self.reports[name][-limit:]
        return []
    
    def get_latest_report(self, name: str) -> Optional[Dict[str, Any]]:
        """获取最新报告"""
        if name in self.reports and self.reports[name]:
            return self.reports[name][-1]
        return None
    
    def get_all_reports(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取所有报告"""
        return self.reports


# 使用示例
async def example_usage():
    """使用示例"""
    # 创建数据质量系统
    dqs = EnhancedDataQualitySystem()
    await dqs.initialize()
    
    try:
        # 创建测试数据
        np.random.seed(42)
        data = pd.DataFrame({
            "timestamp": pd.date_range("2023-01-01", periods=100, freq="H"),
            "price": np.random.normal(50000, 1000, 100),
            "volume": np.random.normal(1000, 200, 100),
            "open": np.random.normal(50000, 1000, 100),
            "high": np.random.normal(50500, 1000, 100),
            "low": np.random.normal(49500, 1000, 100),
            "close": np.random.normal(50000, 1000, 100)
        })
        
        # 故意添加一些问题
        data.loc[0:5, "price"] = np.nan  # 缺失值
        data.loc[90:99, "volume"] = 10000  # 异常值
        data.loc[50, "timestamp"] = pd.Timestamp("2022-01-01")  # 过期数据
        
        # 检查数据源
        report = await dqs.check_data_source("binance_btc", data)
        print(f"数据质量报告: {report['data_source']}")
        print(f"整体质量: {report['overall_level']} (分数: {report['overall_score']:.2f})")
        print(f"问题统计: {report['summary']}")
        
        # 检查关键问题
        if report['issues']['critical']:
            print("\n关键问题:")
            for issue in report['issues']['critical']:
                print(f"- {issue['description']}")
        
        # 获取报告历史
        history = dqs.get_report_history("binance_btc")
        print(f"\n报告历史数量: {len(history)}")
        
    finally:
        await dqs.cleanup()


if __name__ == "__main__":
    asyncio.run(example_usage())
