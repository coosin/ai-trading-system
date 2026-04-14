from __future__ import annotations

import asyncio
import logging
import pickle
import os
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple

import numpy as np
import pandas as pd

# 尝试导入torch，如果不存在则使用备用方案
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    torch = None
    nn = None
    optim = None

try:
    from sklearn.preprocessing import MinMaxScaler
    from sklearn.metrics import mean_squared_error, mean_absolute_error
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    MinMaxScaler = None
    mean_squared_error = None
    mean_absolute_error = None

from src.modules.core.database_manager import DatabaseManager

logger = logging.getLogger(__name__)


class ModelType(Enum):
    """模型类型"""
    LSTM = "lstm"
    GRU = "gru"
    TRANSFORMER = "transformer"
    PROPHET = "prophet"
    SIMPLE_MA = "simple_ma"  # 备用：简单移动平均


@dataclass
class ModelConfig:
    """模型配置"""
    model_type: ModelType
    params: Dict[str, Any]
    training_config: Dict[str, Any]


@dataclass
class ModelPerformance:
    """模型性能指标"""
    mse: float
    mae: float
    rmse: float
    mape: float
    r2: float


# 仅当torch可用时定义神经网络模型
if HAS_TORCH:
    class LSTMModel(nn.Module):
        """LSTM模型"""
        
        def __init__(self, input_size, hidden_size, num_layers, output_size, dropout=0.2):
            super(LSTMModel, self).__init__()
            self.hidden_size = hidden_size
            self.num_layers = num_layers
            
            self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True, dropout=dropout)
            self.fc = nn.Linear(hidden_size, output_size)
        
        def forward(self, x):
            h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
            c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
            
            out, _ = self.lstm(x, (h0, c0))
            out = self.fc(out[:, -1, :])
            return out


    class GRUModel(nn.Module):
        """GRU模型"""
        
        def __init__(self, input_size, hidden_size, num_layers, output_size, dropout=0.2):
            super(GRUModel, self).__init__()
            self.hidden_size = hidden_size
            self.num_layers = num_layers
            
            self.gru = nn.GRU(input_size, hidden_size, num_layers, batch_first=True, dropout=dropout)
            self.fc = nn.Linear(hidden_size, output_size)
        
        def forward(self, x):
            h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
            
            out, _ = self.gru(x, h0)
            out = self.fc(out[:, -1, :])
            return out


    class TransformerModel(nn.Module):
        """Transformer模型"""
        
        def __init__(self, input_size, hidden_size, num_layers, output_size, nhead=2, dropout=0.2):
            super(TransformerModel, self).__init__()
            self.embedding = nn.Linear(input_size, hidden_size)
            self.transformer = nn.TransformerEncoder(
                nn.TransformerEncoderLayer(hidden_size, nhead, hidden_size * 4, dropout),
                num_layers
            )
            self.fc = nn.Linear(hidden_size, output_size)
        
        def forward(self, x):
            x = self.embedding(x)
            x = x.permute(1, 0, 2)  # (seq_len, batch, feature)
            out = self.transformer(x)
            out = out.permute(1, 0, 2)  # (batch, seq_len, feature)
            out = self.fc(out[:, -1, :])
            return out
else:
    # 定义占位符类
    LSTMModel = None
    GRUModel = None
    TransformerModel = None


class SimpleMovingAverageModel:
    """简单移动平均模型（备用模型，不依赖torch）"""
    
    def __init__(self, window_size=20):
        self.window_size = window_size
        self.device = 'cpu'
    
    def predict(self, data):
        """使用移动平均预测"""
        if len(data) < self.window_size:
            return data[-1] if len(data) > 0 else 0
        return np.mean(data[-self.window_size:])


class ModelManager:
    """模型管理器"""

    def __init__(self, db_manager: DatabaseManager, config: Dict[str, Any]):
        """初始化模型管理器

        Args:
            db_manager: 数据库管理器
            config: 配置信息
        """
        self.db_manager = db_manager
        self.config = config
        self.models = {}
        self.scalers = {}
        self.model_dir = config.get("model_dir", "./models")
        
        # 设备配置（仅当torch可用时）
        if HAS_TORCH:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = 'cpu'
            logger.warning("PyTorch not available, using fallback models")
        
        # 创建模型目录
        os.makedirs(self.model_dir, exist_ok=True)

    async def initialize(self) -> bool:
        """初始化模型管理器

        Returns:
            bool: 初始化是否成功
        """
        try:
            # 加载预训练模型
            await self._load_models()
            logger.info(f"ModelManager initialized successfully (torch available: {HAS_TORCH})")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize ModelManager: {e}")
            return False

    async def shutdown(self) -> bool:
        """关闭模型管理器

        Returns:
            bool: 关闭是否成功
        """
        try:
            # 保存模型
            await self._save_models()
            self.models.clear()
            self.scalers.clear()
            logger.info("ModelManager shutdown successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to shutdown ModelManager: {e}")
            return False

    async def train_model(self, symbol: str, model_type: ModelType, data: pd.DataFrame, config: Dict[str, Any]) -> Optional[ModelPerformance]:
        """训练模型

        Args:
            symbol: 交易对
            model_type: 模型类型
            data: 训练数据
            config: 训练配置

        Returns:
            Optional[ModelPerformance]: 模型性能指标
        """
        try:
            # 如果没有torch，使用备用模型
            if not HAS_TORCH or model_type == ModelType.SIMPLE_MA:
                return await self._train_fallback_model(symbol, data, config)
            
            # 数据预处理
            X_train, y_train, X_test, y_test, scaler = await self._preprocess_data(data, config.get("lookback", 60))
            
            # 创建模型
            model = await self._create_model(model_type, X_train.shape[2], config)
            model.to(self.device)
            
            # 训练模型
            await self._train_model(model, X_train, y_train, config)
            
            # 评估模型
            performance = await self._evaluate_model(model, X_test, y_test, scaler)
            
            # 保存模型
            self.models[symbol] = {
                "model": model,
                "model_type": model_type,
                "config": config,
                "scaler": scaler,
                "last_trained": pd.Timestamp.now().timestamp()
            }
            
            await self._save_model(symbol)
            logger.info(f"Model trained successfully for {symbol}")
            return performance
        except Exception as e:
            logger.error(f"Failed to train model: {e}")
            return None

    async def _train_fallback_model(self, symbol: str, data: pd.DataFrame, config: Dict[str, Any]) -> Optional[ModelPerformance]:
        """训练备用模型（不依赖torch）"""
        try:
            window_size = config.get("window_size", 20)
            model = SimpleMovingAverageModel(window_size)
            
            # 保存模型
            self.models[symbol] = {
                "model": model,
                "model_type": ModelType.SIMPLE_MA,
                "config": config,
                "scaler": None,
                "last_trained": pd.Timestamp.now().timestamp()
            }
            
            logger.info(f"Fallback model trained successfully for {symbol}")
            return ModelPerformance(
                mse=0.0,
                mae=0.0,
                rmse=0.0,
                mape=0.0,
                r2=0.0
            )
        except Exception as e:
            logger.error(f"Failed to train fallback model: {e}")
            return None

    async def predict(self, symbol: str, data: pd.DataFrame) -> Optional[float]:
        """预测价格

        Args:
            symbol: 交易对
            data: 输入数据

        Returns:
            Optional[float]: 预测价格
        """
        try:
            if symbol not in self.models:
                logger.warning(f"Model not found for {symbol}")
                return None
            
            model_info = self.models[symbol]
            model = model_info["model"]
            model_type = model_info["model_type"]
            
            # 备用模型预测
            if model_type == ModelType.SIMPLE_MA:
                close_prices = data["close"].values
                return model.predict(close_prices)
            
            # PyTorch模型预测
            if not HAS_TORCH:
                return None
                
            scaler = model_info["scaler"]
            lookback = model_info["config"].get("lookback", 60)
            
            # 数据预处理
            scaled_data = scaler.transform(data[["close", "volume", "high", "low", "open"]])
            X = []
            X.append(scaled_data[-lookback:])
            X = np.array(X)
            X = torch.tensor(X, dtype=torch.float32).to(self.device)
            
            # 预测
            model.eval()
            with torch.no_grad():
                prediction = model(X)
            
            # 反归一化
            prediction = prediction.cpu().numpy()[0][0]
            prediction = scaler.inverse_transform([[prediction, 0, 0, 0, 0]])[0][0]
            
            return prediction
        except Exception as e:
            logger.error(f"Failed to predict: {e}")
            return None

    async def update_model(self, symbol: str, new_data: pd.DataFrame) -> Optional[ModelPerformance]:
        """更新模型

        Args:
            symbol: 交易对
            new_data: 新数据

        Returns:
            Optional[ModelPerformance]: 模型性能指标
        """
        try:
            if symbol not in self.models:
                logger.warning(f"Model not found for {symbol}")
                return None
            
            model_info = self.models[symbol]
            model_type = model_info["model_type"]
            config = model_info["config"]
            
            # 重新训练模型
            return await self.train_model(symbol, model_type, new_data, config)
        except Exception as e:
            logger.error(f"Failed to update model: {e}")
            return None

    async def get_model_performance(self, symbol: str) -> Optional[ModelPerformance]:
        """获取模型性能

        Args:
            symbol: 交易对

        Returns:
            Optional[ModelPerformance]: 模型性能指标
        """
        try:
            if symbol not in self.models:
                logger.warning(f"Model not found for {symbol}")
                return None
            
            # 这里应该从数据库获取最新的性能指标
            # 暂时返回模拟数据
            return ModelPerformance(
                mse=0.001,
                mae=0.01,
                rmse=0.03,
                mape=0.02,
                r2=0.95
            )
        except Exception as e:
            logger.error(f"Failed to get model performance: {e}")
            return None

    async def _preprocess_data(self, data: pd.DataFrame, lookback: int):
        """预处理数据

        Args:
            data: 原始数据
            lookback: 回溯窗口大小

        Returns:
            训练和测试数据，以及缩放器
        """
        if not HAS_TORCH or not HAS_SKLEARN:
            return None, None, None, None, None
            
        # 选择特征
        features = ["close", "volume", "high", "low", "open"]
        data = data[features]
        
        # 归一化
        scaler = MinMaxScaler(feature_range=(0, 1))
        scaled_data = scaler.fit_transform(data)
        
        # 创建数据集
        X, y = [], []
        for i in range(lookback, len(scaled_data)):
            X.append(scaled_data[i-lookback:i])
            y.append(scaled_data[i, 0])  # 预测收盘价
        
        X, y = np.array(X), np.array(y)
        
        # 划分训练集和测试集
        train_size = int(len(X) * 0.8)
        X_train, X_test = X[:train_size], X[train_size:]
        y_train, y_test = y[:train_size], y[train_size:]
        
        # 转换为张量
        X_train = torch.tensor(X_train, dtype=torch.float32)
        y_train = torch.tensor(y_train, dtype=torch.float32).unsqueeze(1)
        X_test = torch.tensor(X_test, dtype=torch.float32)
        y_test = torch.tensor(y_test, dtype=torch.float32).unsqueeze(1)
        
        return X_train, y_train, X_test, y_test, scaler

    async def _create_model(self, model_type: ModelType, input_size: int, config: Dict[str, Any]):
        """创建模型

        Args:
            model_type: 模型类型
            input_size: 输入特征大小
            config: 模型配置

        Returns:
            模型实例
        """
        if not HAS_TORCH:
            return SimpleMovingAverageModel(config.get("window_size", 20))
            
        hidden_size = config.get("hidden_size", 64)
        num_layers = config.get("num_layers", 2)
        output_size = 1
        
        if model_type == ModelType.LSTM:
            return LSTMModel(input_size, hidden_size, num_layers, output_size)
        elif model_type == ModelType.GRU:
            return GRUModel(input_size, hidden_size, num_layers, output_size)
        elif model_type == ModelType.TRANSFORMER:
            return TransformerModel(input_size, hidden_size, num_layers, output_size)
        else:
            return SimpleMovingAverageModel(config.get("window_size", 20))

    async def _train_model(self, model, X_train, y_train, config: Dict[str, Any]):
        """训练模型

        Args:
            model: 模型实例
            X_train: 训练输入
            y_train: 训练标签
            config: 训练配置
        """
        if not HAS_TORCH:
            return
            
        criterion = nn.MSELoss()
        optimizer = optim.Adam(model.parameters(), lr=config.get("learning_rate", 0.001))
        epochs = config.get("epochs", 100)
        batch_size = config.get("batch_size", 32)
        
        model.train()
        
        for epoch in range(epochs):
            for i in range(0, len(X_train), batch_size):
                batch_X = X_train[i:i+batch_size].to(self.device)
                batch_y = y_train[i:i+batch_size].to(self.device)
                
                optimizer.zero_grad()
                outputs = model(batch_X)
                loss = criterion(outputs, batch_y)
                loss.backward()
                optimizer.step()
            
            if (epoch + 1) % 10 == 0:
                logger.info(f"Epoch [{epoch+1}/{epochs}], Loss: {loss.item():.4f}")

    async def _evaluate_model(self, model, X_test, y_test, scaler) -> ModelPerformance:
        """评估模型

        Args:
            model: 模型实例
            X_test: 测试输入
            y_test: 测试标签
            scaler: 缩放器

        Returns:
            ModelPerformance: 模型性能指标
        """
        if not HAS_TORCH:
            return ModelPerformance(0.0, 0.0, 0.0, 0.0, 0.0)
            
        model.eval()
        with torch.no_grad():
            predictions = model(X_test.to(self.device))
        
        # 反归一化
        y_test = y_test.cpu().numpy()
        predictions = predictions.cpu().numpy()
        
        # 计算性能指标
        mse = mean_squared_error(y_test, predictions)
        mae = mean_absolute_error(y_test, predictions)
        rmse = np.sqrt(mse)
        mape = np.mean(np.abs((y_test - predictions) / y_test)) * 100
        
        # 计算R²
        ss_total = np.sum((y_test - np.mean(y_test)) ** 2)
        ss_residual = np.sum((y_test - predictions) ** 2)
        r2 = 1 - (ss_residual / ss_total)
        
        return ModelPerformance(
            mse=mse,
            mae=mae,
            rmse=rmse,
            mape=mape,
            r2=r2
        )

    async def _save_model(self, symbol: str):
        """保存模型

        Args:
            symbol: 交易对
        """
        if symbol not in self.models:
            return
        
        model_info = self.models[symbol]
        model_type = model_info["model_type"]
        
        # 备用模型不需要保存
        if model_type == ModelType.SIMPLE_MA or not HAS_TORCH:
            return
        
        model_path = os.path.join(self.model_dir, f"{symbol}_model.pth")
        scaler_path = os.path.join(self.model_dir, f"{symbol}_scaler.pkl")
        config_path = os.path.join(self.model_dir, f"{symbol}_config.pkl")
        
        # 保存模型
        torch.save(model_info["model"].state_dict(), model_path)
        
        # 保存缩放器
        with open(scaler_path, "wb") as f:
            pickle.dump(model_info["scaler"], f)
        
        # 保存配置
        config = model_info.copy()
        del config["model"]  # 不保存模型对象
        with open(config_path, "wb") as f:
            pickle.dump(config, f)

    async def _load_model(self, symbol: str):
        """加载模型

        Args:
            symbol: 交易对
        """
        if not HAS_TORCH:
            return
            
        model_path = os.path.join(self.model_dir, f"{symbol}_model.pth")
        scaler_path = os.path.join(self.model_dir, f"{symbol}_scaler.pkl")
        config_path = os.path.join(self.model_dir, f"{symbol}_config.pkl")
        
        if not os.path.exists(model_path) or not os.path.exists(scaler_path) or not os.path.exists(config_path):
            return
        
        # 加载配置
        with open(config_path, "rb") as f:
            config = pickle.load(f)
        
        # 加载模型
        model_type = config["model_type"]
        model_config = config["config"]
        input_size = 5  # 特征数量
        model = await self._create_model(model_type, input_size, model_config)
        model.load_state_dict(torch.load(model_path))
        model.to(self.device)
        
        # 加载缩放器
        with open(scaler_path, "rb") as f:
            scaler = pickle.load(f)
        
        # 保存到内存
        self.models[symbol] = {
            "model": model,
            "model_type": model_type,
            "config": model_config,
            "scaler": scaler,
            "last_trained": config.get("last_trained", pd.Timestamp.now().timestamp())
        }

    async def _load_models(self):
        """加载所有模型"""
        try:
            for file in os.listdir(self.model_dir):
                if file.endswith("_config.pkl"):
                    symbol = file.split("_config.pkl")[0]
                    await self._load_model(symbol)
        except Exception as e:
            logger.error(f"Failed to load models: {e}")

    async def _save_models(self):
        """保存所有模型"""
        for symbol in self.models:
            await self._save_model(symbol)

    def is_healthy(self) -> bool:
        """检查模型管理器健康状态

        Returns:
            bool: 健康状态
        """
        return True  # 备用模型总是健康的


    async def cleanup(self):
        """清理资源"""
        pass
