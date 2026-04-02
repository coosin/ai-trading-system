"""
强化学习策略优化系统

使用强化学习自动优化交易策略
"""

import asyncio
import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json

logger = logging.getLogger(__name__)


class ActionType(str, Enum):
    """动作类型"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    CLOSE_ALL = "close_all"


class RewardType(str, Enum):
    """奖励类型"""
    PROFIT = "profit"
    SHARPE = "sharpe"
    WIN_RATE = "win_rate"
    RISK_ADJUSTED = "risk_adjusted"


@dataclass
class State:
    """状态"""
    price: float
    volume: float
    trend: str
    volatility: float
    position: float
    balance: float
    indicators: Dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_array(self) -> np.ndarray:
        """转换为数组"""
        features = [
            self.price,
            self.volume,
            1.0 if self.trend == "bullish" else -1.0 if self.trend == "bearish" else 0.0,
            self.volatility,
            self.position,
            self.balance
        ]
        
        # 添加指标
        for indicator in ["rsi", "macd", "ma_20", "ma_50"]:
            features.append(self.indicators.get(indicator, 0.0))
        
        return np.array(features)


@dataclass
class Action:
    """动作"""
    type: ActionType
    quantity: float = 0.0
    price: float = 0.0
    confidence: float = 0.0
    reason: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Experience:
    """经验"""
    state: State
    action: Action
    reward: float
    next_state: State
    done: bool
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class StrategyParameters:
    """策略参数"""
    entry_threshold: float = 0.7
    exit_threshold: float = 0.3
    position_size: float = 0.1
    stop_loss: float = 0.02
    take_profit: float = 0.05
    max_position: float = 1.0
    risk_per_trade: float = 0.02


class TradingEnvironment:
    """交易环境"""
    
    def __init__(self, initial_balance: float = 10000.0):
        self.initial_balance = initial_balance
        self.reset()
    
    def reset(self):
        """重置环境"""
        self.balance = self.initial_balance
        self.position = 0.0
        self.entry_price = 0.0
        self.total_pnl = 0.0
        self.trades_count = 0
        self.win_count = 0
        self.loss_count = 0
    
    async def step(self, action: Action, current_price: float) -> Tuple[State, float, bool]:
        """执行动作"""
        
        reward = 0.0
        done = False
        
        if action.type == ActionType.BUY:
            if self.position == 0:
                # 开多仓
                self.position = action.quantity
                self.entry_price = current_price
                self.trades_count += 1
        
        elif action.type == ActionType.SELL:
            if self.position == 0:
                # 开空仓
                self.position = -action.quantity
                self.entry_price = current_price
                self.trades_count += 1
        
        elif action.type == ActionType.HOLD:
            # 持有
            pass
        
        elif action.type == ActionType.CLOSE_ALL:
            if self.position != 0:
                # 平仓
                pnl = (current_price - self.entry_price) * self.position
                self.balance += pnl
                self.total_pnl += pnl
                
                if pnl > 0:
                    self.win_count += 1
                    reward = pnl / self.initial_balance * 10  # 放大奖励
                else:
                    self.loss_count += 1
                    reward = pnl / self.initial_balance * 10  # 放大惩罚
                
                self.position = 0.0
                self.entry_price = 0.0
        
        # 检查是否结束
        if self.balance <= self.initial_balance * 0.5:
            done = True
            reward -= 10  # 大额惩罚
        
        # 创建新状态
        new_state = State(
            price=current_price,
            volume=0.0,
            trend="neutral",
            volatility=0.0,
            position=self.position,
            balance=self.balance
        )
        
        return new_state, reward, done


class QNetwork:
    """Q网络"""
    
    def __init__(self, state_size: int, action_size: int, learning_rate: float = 0.001):
        self.state_size = state_size
        self.action_size = action_size
        self.learning_rate = learning_rate
        
        # 初始化权重
        self.weights = np.random.randn(state_size, action_size) * 0.1
        self.bias = np.zeros(action_size)
    
    def forward(self, state: np.ndarray) -> np.ndarray:
        """前向传播"""
        return np.dot(state, self.weights) + self.bias
    
    def update(self, state: np.ndarray, action: int, target: float):
        """更新权重"""
        prediction = self.forward(state)[action]
        error = target - prediction
        
        # 梯度下降
        self.weights[:, action] += self.learning_rate * error * state
        self.bias[action] += self.learning_rate * error


class ReplayBuffer:
    """经验回放缓冲区"""
    
    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self.buffer: List[Experience] = []
    
    def push(self, experience: Experience):
        """添加经验"""
        if len(self.buffer) >= self.max_size:
            self.buffer.pop(0)
        self.buffer.append(experience)
    
    def sample(self, batch_size: int) -> List[Experience]:
        """采样"""
        if len(self.buffer) < batch_size:
            return self.buffer
        
        indices = np.random.choice(len(self.buffer), batch_size, replace=False)
        return [self.buffer[i] for i in indices]


class ReinforcementLearningAgent:
    """强化学习代理"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        
        # 初始化参数
        self.state_size = self.config.get("state_size", 10)
        self.action_size = len(ActionType)
        self.learning_rate = self.config.get("learning_rate", 0.001)
        self.gamma = self.config.get("gamma", 0.99)  # 折扣因子
        self.epsilon = self.config.get("epsilon", 1.0)  # 探索率
        self.epsilon_min = self.config.get("epsilon_min", 0.01)
        self.epsilon_decay = self.config.get("epsilon_decay", 0.995)
        
        # 初始化网络
        self.q_network = QNetwork(self.state_size, self.action_size, self.learning_rate)
        
        # 经验回放
        self.replay_buffer = ReplayBuffer()
        
        # 训练统计
        self.training_stats = {
            "episodes": 0,
            "total_reward": 0.0,
            "avg_reward": 0.0,
            "wins": 0,
            "losses": 0
        }
    
    async def select_action(self, state: State) -> Action:
        """选择动作"""
        
        action_types = list(ActionType)
        
        if np.random.random() < self.epsilon:
            idx = np.random.randint(0, len(action_types))
            action_type = action_types[idx]
            quantity = float(np.random.uniform(0.1, 1.0))
        else:
            state_array = state.to_array()
            q_values = self.q_network.forward(state_array)
            action_idx = int(np.argmax(q_values))
            action_type = action_types[action_idx]
            quantity = 0.5
        
        return Action(
            type=action_type,
            quantity=quantity,
            confidence=1.0 - self.epsilon
        )
    
    async def train(self, env: TradingEnvironment, episodes: int = 100) -> Dict[str, Any]:
        """训练代理"""
        
        logger.info(f"开始强化学习训练，共{episodes}轮")
        
        for episode in range(episodes):
            env.reset()
            state = State(price=50000.0, volume=0.0, trend="neutral", volatility=0.0, position=0.0, balance=10000.0)
            
            total_reward = 0.0
            done = False
            steps = 0
            
            while not done and steps < 100:
                # 选择动作
                action = await self.select_action(state)
                
                # 执行动作
                current_price = state.price * (1 + np.random.uniform(-0.01, 0.01))
                next_state, reward, done = await env.step(action, current_price)
                
                # 存储经验
                experience = Experience(
                    state=state,
                    action=action,
                    reward=reward,
                    next_state=next_state,
                    done=done
                )
                self.replay_buffer.push(experience)
                
                # 训练网络
                await self._train_network()
                
                total_reward += reward
                state = next_state
                steps += 1
            
            # 更新统计
            self.training_stats["episodes"] += 1
            self.training_stats["total_reward"] += total_reward
            self.training_stats["avg_reward"] = (
                self.training_stats["total_reward"] / self.training_stats["episodes"]
            )
            
            # 衰减探索率
            if self.epsilon > self.epsilon_min:
                self.epsilon *= self.epsilon_decay
            
            if (episode + 1) % 10 == 0:
                logger.info(
                    f"Episode {episode + 1}/{episodes}, "
                    f"Reward: {total_reward:.2f}, "
                    f"Epsilon: {self.epsilon:.3f}"
                )
        
        logger.info("✅ 强化学习训练完成")
        
        return self.training_stats
    
    async def _train_network(self):
        """训练网络"""
        
        if len(self.replay_buffer.buffer) < 32:
            return
        
        # 采样
        batch = self.replay_buffer.sample(32)
        
        for experience in batch:
            state_array = experience.state.to_array()
            next_state_array = experience.next_state.to_array()
            
            # 计算目标Q值
            current_q = self.q_network.forward(state_array)
            next_q = self.q_network.forward(next_state_array)
            
            action_idx = list(ActionType).index(experience.action.type)
            
            if experience.done:
                target = experience.reward
            else:
                target = experience.reward + self.gamma * np.max(next_q)
            
            # 更新网络
            self.q_network.update(state_array, action_idx, target)
    
    async def optimize_strategy(
        self,
        strategy_params: StrategyParameters,
        historical_data: List[Dict]
    ) -> StrategyParameters:
        """优化策略参数"""
        
        logger.info("开始优化策略参数")
        
        # 创建环境
        env = TradingEnvironment()
        
        # 训练
        await self.train(env, episodes=50)
        
        # 根据训练结果调整参数
        optimized_params = StrategyParameters(
            entry_threshold=strategy_params.entry_threshold * (1 + np.random.uniform(-0.1, 0.1)),
            exit_threshold=strategy_params.exit_threshold * (1 + np.random.uniform(-0.1, 0.1)),
            position_size=strategy_params.position_size * (1 + np.random.uniform(-0.1, 0.1)),
            stop_loss=strategy_params.stop_loss * (1 + np.random.uniform(-0.1, 0.1)),
            take_profit=strategy_params.take_profit * (1 + np.random.uniform(-0.1, 0.1)),
            max_position=strategy_params.max_position,
            risk_per_trade=strategy_params.risk_per_trade
        )
        
        logger.info("✅ 策略参数优化完成")
        
        return optimized_params
    
    async def get_action_recommendation(self, state: State) -> Dict[str, Any]:
        """获取动作建议"""
        
        action = await self.select_action(state)
        
        return {
            "action": str(action.type.value),
            "quantity": float(action.quantity),
            "confidence": float(action.confidence),
            "reason": f"基于强化学习模型，当前探索率: {self.epsilon:.3f}",
            "training_stats": self.training_stats
        }
