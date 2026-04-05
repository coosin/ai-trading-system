"""
基于机器学习的异常检测和预警模块

功能：
1. 收集和分析历史监控数据
2. 训练机器学习模型来检测异常
3. 实时监控并预测异常
4. 生成智能告警
5. 自适应学习和模型更新
"""

import asyncio
import logging
import time
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split

logger = logging.getLogger(__name__)


@dataclass
class AnomalyDetectionConfig:
    """异常检测配置"""
    # 模型配置
    contamination: float = 0.03  # 异常比例（降低以减少误报）
    n_estimators: int = 100  # 树的数量
    max_samples: float = 0.8  # 采样比例
    
    # 监控配置
    monitoring_interval: int = 5  # 监控间隔（秒）
    window_size: int = 30  # 滑动窗口大小
    min_history: int = 100  # 最小历史数据量
    
    # 告警配置
    alert_threshold: float = 0.9  # 告警阈值（提高以减少误报）
    alert_cooldown: int = 300  # 告警冷却时间（秒）- 增加到5分钟
    
    # 学习配置
    retrain_interval: int = 3600  # 重训练间隔（秒）
    max_history_size: int = 10000  # 最大历史数据量
    
    # 异常分数阈值
    critical_threshold: float = 0.95  # 严重异常阈值
    high_threshold: float = 0.85  # 高风险阈值
    medium_threshold: float = 0.75  # 中等风险阈值


@dataclass
class AnomalyEvent:
    """异常事件"""
    event_id: str
    timestamp: float
    severity: str  # low, medium, high, critical
    event_type: str
    message: str
    confidence: float
    details: Dict[str, Any]
    resolved: bool = False


@dataclass
class AnomalyScore:
    """异常评分"""
    timestamp: float
    score: float  # 异常分数，越接近1越异常
    is_anomaly: bool
    features: Dict[str, float]
    anomaly_details: Dict[str, Any]


class AnomalyDetector:
    """基于机器学习的异常检测器"""
    
    def __init__(self, config: AnomalyDetectionConfig):
        """初始化异常检测器"""
        self.config = config
        self.enabled = False
        
        # 数据存储
        self.history_data = []
        self.anomaly_events = []
        
        # 模型相关
        self.model = None
        self.scaler = None
        self.pipeline = None
        self.model_trained = False
        self.last_retrain_time = 0
        
        # 告警冷却
        self.last_alert_time = {}
        
        # 特征列
        self.feature_columns = [
            'cpu_usage', 'memory_usage', 'disk_usage', 'network_latency',
            'price_change_24h', 'volume_change_24h', 'volatility_24h',
            'order_pending_time', 'fill_rate', 'pnl_change'
        ]
    
    async def initialize(self) -> bool:
        """初始化异常检测器"""
        try:
            # 初始化模型
            self._init_model()
            
            # 启动监控循环
            asyncio.create_task(self._monitoring_loop())
            
            # 启动重训练循环
            asyncio.create_task(self._retraining_loop())
            
            self.enabled = True
            logger.info("AnomalyDetector initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize AnomalyDetector: {e}")
            return False
    
    async def shutdown(self) -> bool:
        """关闭异常检测器"""
        try:
            self.enabled = False
            self.history_data.clear()
            self.anomaly_events.clear()
            logger.info("AnomalyDetector shutdown successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to shutdown AnomalyDetector: {e}")
            return False
    
    def _init_model(self):
        """初始化模型"""
        # 创建预处理管道
        self.scaler = StandardScaler()
        self.model = IsolationForest(
            contamination=self.config.contamination,
            n_estimators=self.config.n_estimators,
            max_samples=self.config.max_samples,
            random_state=42
        )
        self.pipeline = Pipeline([
            ('scaler', self.scaler),
            ('model', self.model)
        ])
    
    def add_data_point(self, data: Dict[str, float]):
        """添加数据点"""
        # 添加时间戳
        data['timestamp'] = time.time()
        
        # 添加到历史数据
        self.history_data.append(data)
        
        # 限制历史数据大小
        if len(self.history_data) > self.config.max_history_size:
            self.history_data = self.history_data[-self.config.max_history_size:]
    
    def _prepare_features(self, data: Dict[str, float]) -> np.ndarray:
        """准备特征"""
        features = []
        for col in self.feature_columns:
            features.append(data.get(col, 0.0))
        return np.array(features).reshape(1, -1)
    
    def detect_anomaly(self, data: Dict[str, float]) -> AnomalyScore:
        """检测异常"""
        # 准备特征
        features = self._prepare_features(data)
        
        # 检查是否有足够的历史数据和已训练的模型
        if len(self.history_data) < self.config.min_history or not self.pipeline or not self.model_trained:
            return AnomalyScore(
                timestamp=time.time(),
                score=0.0,
                is_anomaly=False,
                features=data,
                anomaly_details={}
            )
        
        try:
            # 预测异常分数
            score = self.pipeline.score_samples(features)[0]
            # Isolation Forest的分数是负的，越接近0越异常
            normalized_score = 1 - (score / np.abs(np.min(self.model.score_samples(self._get_history_features()))))
            
            # 判断是否异常
            is_anomaly = normalized_score > self.config.alert_threshold
            
            # 分析异常详情
            anomaly_details = self._analyze_anomaly(data, normalized_score)
            
            return AnomalyScore(
                timestamp=time.time(),
                score=normalized_score,
                is_anomaly=is_anomaly,
                features=data,
                anomaly_details=anomaly_details
            )
        except Exception as e:
            logger.error(f"Error detecting anomaly: {e}")
            return AnomalyScore(
                timestamp=time.time(),
                score=0.0,
                is_anomaly=False,
                features=data,
                anomaly_details={}
            )
    
    def _get_history_features(self) -> np.ndarray:
        """获取历史特征"""
        features = []
        for data in self.history_data:
            feature_row = []
            for col in self.feature_columns:
                feature_row.append(data.get(col, 0.0))
            features.append(feature_row)
        return np.array(features)
    
    def _analyze_anomaly(self, data: Dict[str, float], score: float) -> Dict[str, Any]:
        """分析异常详情"""
        details = {}
        
        # 分析各个特征的异常程度
        for col in self.feature_columns:
            value = data.get(col, 0.0)
            # 计算历史均值和标准差
            historical_values = [d.get(col, 0.0) for d in self.history_data]
            if historical_values:
                mean = np.mean(historical_values)
                std = np.std(historical_values)
                if std > 0:
                    z_score = abs(value - mean) / std
                    details[f"{col}_z_score"] = z_score
                    if z_score > 3:
                        details[f"{col}_anomaly"] = True
        
        # 确定主要异常原因
        if details:
            max_z_score = 0
            main_cause = None
            for key, value in details.items():
                if "_z_score" in key and value > max_z_score:
                    max_z_score = value
                    main_cause = key.replace("_z_score", "")
            if main_cause:
                details["main_cause"] = main_cause
        
        return details
    
    async def _generate_alert(self, score: AnomalyScore):
        """生成告警"""
        # 检查告警冷却
        alert_key = score.anomaly_details.get("main_cause", "general")
        current_time = time.time()
        
        if alert_key in self.last_alert_time:
            if current_time - self.last_alert_time[alert_key] < self.config.alert_cooldown:
                logger.debug(f"告警 {alert_key} 在冷却期内，跳过")
                return
        
        # 更严格的告警过滤 - 只有在确实异常时才发送
        if score.score < self.config.alert_threshold:
            logger.debug(f"异常分数 {score.score:.2f} 低于阈值 {self.config.alert_threshold}，跳过告警")
            return
        
        # 根据异常分数确定严重程度
        if score.score >= self.config.critical_threshold:
            severity = "critical"
        elif score.score >= self.config.high_threshold:
            severity = "high"
        elif score.score >= self.config.medium_threshold:
            severity = "medium"
        else:
            severity = "low"
        
        # 只有高严重级别的才发送告警
        if severity in ["low", "medium"]:
            logger.debug(f"异常严重程度 {severity}，仅记录不告警")
            return
        
        # 生成事件ID
        event_id = f"anomaly_{int(current_time)}_{score.anomaly_details.get('main_cause', 'general')}"
        
        # 构建告警消息
        main_cause = score.anomaly_details.get("main_cause", "unknown")
        message = f"Anomaly detected: {main_cause} with score {score.score:.2f}"
        
        # 创建异常事件
        event = AnomalyEvent(
            event_id=event_id,
            timestamp=current_time,
            severity=severity,
            event_type="anomaly",
            message=message,
            confidence=score.score,
            details=score.anomaly_details
        )
        
        # 添加到事件列表
        self.anomaly_events.append(event)
        
        # 更新最后告警时间
        self.last_alert_time[alert_key] = current_time
        
        # 记录日志
        logger.warning(f"Anomaly Alert [{severity}]: {message}")
    
    async def _monitoring_loop(self):
        """监控循环"""
        while self.enabled:
            try:
                # 这里应该从监控系统获取最新数据
                # 暂时使用模拟数据
                data = self._get_mock_data()
                
                # 添加数据点
                self.add_data_point(data)
                
                # 检测异常
                score = self.detect_anomaly(data)
                
                # 如果检测到异常，生成告警
                if score.is_anomaly:
                    await self._generate_alert(score)
                
            except Exception as e:
                logger.error(f"Error in anomaly monitoring loop: {e}")
            
            await asyncio.sleep(self.config.monitoring_interval)
    
    async def _retraining_loop(self):
        """重训练循环"""
        while self.enabled:
            try:
                # 检查是否需要重训练
                current_time = time.time()
                if current_time - self.last_retrain_time > self.config.retrain_interval:
                    await self.retrain_model()
                    self.last_retrain_time = current_time
            except Exception as e:
                logger.error(f"Error in retraining loop: {e}")
            
            await asyncio.sleep(self.config.retrain_interval)
    
    async def retrain_model(self):
        """重训练模型"""
        try:
            # 检查是否有足够的历史数据
            if len(self.history_data) < self.config.min_history:
                logger.info("Not enough data to retrain model")
                return
            
            logger.info(f"Retraining anomaly detection model with {len(self.history_data)} data points")
            
            # 准备训练数据
            features = self._get_history_features()
            
            # 训练模型
            self.pipeline.fit(features)
            self.model_trained = True
            
            logger.info("Model retrained successfully")
        except Exception as e:
            logger.error(f"Error retraining model: {e}")
    
    def _get_mock_data(self) -> Dict[str, float]:
        """获取模拟数据"""
        # 生成模拟数据
        data = {
            'cpu_usage': np.random.normal(50, 10),
            'memory_usage': np.random.normal(60, 15),
            'disk_usage': np.random.normal(40, 10),
            'network_latency': np.random.normal(100, 50),
            'price_change_24h': np.random.normal(0, 2),
            'volume_change_24h': np.random.normal(0, 10),
            'volatility_24h': np.random.normal(1, 0.5),
            'order_pending_time': np.random.normal(10, 5),
            'fill_rate': np.random.normal(0.9, 0.05),
            'pnl_change': np.random.normal(0, 100)
        }
        
        # 偶尔添加异常数据
        if np.random.random() < 0.05:
            # 随机选择一个特征设置为异常值
            anomaly_feature = np.random.choice(self.feature_columns)
            data[anomaly_feature] = data[anomaly_feature] * 3
        
        return data
    
    def get_anomaly_events(self, limit: int = 50) -> List[AnomalyEvent]:
        """获取异常事件"""
        return self.anomaly_events[-limit:]
    
    def get_active_anomalies(self) -> List[AnomalyEvent]:
        """获取活跃异常"""
        return [event for event in self.anomaly_events if not event.resolved]
    
    def resolve_anomaly(self, event_id: str):
        """解决异常"""
        for event in self.anomaly_events:
            if event.event_id == event_id:
                event.resolved = True
                break
    
    def get_model_performance(self) -> Dict[str, Any]:
        """获取模型性能"""
        if not self.model or len(self.history_data) < self.config.min_history:
            return {"status": "not_trained"}
        
        try:
            # 计算模型性能指标
            features = self._get_history_features()
            scores = self.model.score_samples(features)
            
            # 计算异常检测率
            anomaly_count = sum(1 for score in scores if score > np.percentile(scores, 95))
            anomaly_rate = anomaly_count / len(scores)
            
            return {
                "status": "trained",
                "history_size": len(self.history_data),
                "anomaly_rate": anomaly_rate,
                "last_retrain": self.last_retrain_time
            }
        except Exception as e:
            logger.error(f"Error getting model performance: {e}")
            return {"status": "error", "message": str(e)}
