"""
策略基类

定义所有策略必须实现的接口
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class Strategy(ABC):
    """策略基类"""
    
    def __init__(self, config: Dict[str, Any]):
        """初始化策略
        
        Args:
            config: 策略配置
        """
        self.config = config
        self.name = config.get("name", self.__class__.__name__)
        self.active = True
    
    @abstractmethod
    def generate_signal(self, market_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """生成交易信号
        
        Args:
            market_data: 市场数据
            
        Returns:
            交易信号，格式为：
            {
                "symbol": str,  # 交易对
                "side": str,    # 方向 (long/short)
                "type": str,    # 订单类型 (market/limit)
                "quantity": float,  # 数量
                "price": float,     # 价格 (limit订单需要)
                "stop_loss": float, # 止损价格
                "take_profit": float # 止盈价格
            }
        """
        pass
    
    @abstractmethod
    def update_parameters(self, params: Dict[str, Any]):
        """更新策略参数
        
        Args:
            params: 新的参数
        """
        pass
    
    @abstractmethod
    def get_performance(self) -> Dict[str, Any]:
        """获取策略性能指标
        
        Returns:
            性能指标
        """
        pass
    
    def activate(self):
        """激活策略"""
        self.active = True
    
    def deactivate(self):
        """停用策略"""
        self.active = False
    
    def is_active(self) -> bool:
        """检查策略是否激活
        
        Returns:
            是否激活
        """
        return self.active