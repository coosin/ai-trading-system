import asyncio
import logging
import random
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

class SimulatedMarket:
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化模拟交易环境

        Args:
            config: 配置参数
        """
        self.config = config or {}
        self.symbols = self.config.get("symbols", ["BTC/USDT", "ETH/USDT", "BNB/USDT"])
        self.initial_prices = self.config.get("initial_prices", {
            "BTC/USDT": 50000.0,
            "ETH/USDT": 3000.0,
            "BNB/USDT": 300.0
        })
        self.current_prices = self.initial_prices.copy()
        self.historical_data = {symbol: [] for symbol in self.symbols}
        self.order_book = {symbol: {"bids": [], "asks": []} for symbol in self.symbols}
        self.trades = {symbol: [] for symbol in self.symbols}
        self.volatility = self.config.get("volatility", 0.02)  # 日波动率
        self.trend_strength = self.config.get("trend_strength", 0.1)  # 趋势强度
        self.liquidity = self.config.get("liquidity", 1000000)  # 流动性
        self.spread = self.config.get("spread", 0.001)  # 买卖价差
        self.start_time = datetime.now()
        self.current_time = self.start_time
        self.running = False
        self._task = None
    
    async def initialize(self):
        """初始化模拟市场"""
        # 初始化订单簿
        for symbol in self.symbols:
            self._initialize_order_book(symbol)
        
        # 生成初始历史数据
        for symbol in self.symbols:
            self._generate_initial_data(symbol)
        
        logger.info("模拟市场初始化完成")
    
    def _initialize_order_book(self, symbol: str):
        """初始化订单簿"""
        price = self.current_prices[symbol]
        spread = price * self.spread
        
        # 添加买单
        for i in range(10):
            bid_price = price - (i + 1) * spread
            bid_size = random.uniform(0.1, 1.0) * self.liquidity / 10
            self.order_book[symbol]["bids"].append((bid_price, bid_size))
        
        # 添加卖单
        for i in range(10):
            ask_price = price + (i + 1) * spread
            ask_size = random.uniform(0.1, 1.0) * self.liquidity / 10
            self.order_book[symbol]["asks"].append((ask_price, ask_size))
        
        # 按价格排序
        self.order_book[symbol]["bids"].sort(key=lambda x: -x[0])
        self.order_book[symbol]["asks"].sort(key=lambda x: x[0])
    
    def _generate_initial_data(self, symbol: str):
        """生成初始历史数据"""
        price = self.initial_prices[symbol]
        now = self.start_time
        
        for i in range(100):
            timestamp = now - timedelta(minutes=100 - i)
            # 生成随机价格变动
            change = np.random.normal(0, self.volatility / np.sqrt(24 * 60), 1)[0]
            price *= (1 + change)
            
            self.historical_data[symbol].append({
                "timestamp": timestamp,
                "open": price,
                "high": price * (1 + random.uniform(0, 0.005)),
                "low": price * (1 - random.uniform(0, 0.005)),
                "close": price,
                "volume": random.uniform(1000, 10000)
            })
    
    async def start(self):
        """启动模拟市场"""
        self.running = True
        self._task = asyncio.create_task(self._run_market())
        logger.info("模拟市场启动")
    
    async def stop(self):
        """停止模拟市场"""
        self.running = False
        if self._task:
            await self._task
        logger.info("模拟市场停止")
    
    async def _run_market(self):
        """运行模拟市场"""
        while self.running:
            # 更新价格
            self._update_prices()
            
            # 更新订单簿
            for symbol in self.symbols:
                self._update_order_book(symbol)
            
            # 生成交易
            for symbol in self.symbols:
                self._generate_trades(symbol)
            
            # 记录历史数据
            self._record_history()
            
            # 等待下一个时间步
            await asyncio.sleep(1)  # 每秒更新一次
    
    def _update_prices(self):
        """更新价格"""
        for symbol in self.symbols:
            # 生成随机价格变动
            daily_volatility = self.volatility
            minute_volatility = daily_volatility / np.sqrt(24 * 60)
            
            # 添加趋势成分
            trend = random.uniform(-self.trend_strength, self.trend_strength) * minute_volatility
            
            # 生成最终价格变动
            change = np.random.normal(trend, minute_volatility, 1)[0]
            self.current_prices[symbol] *= (1 + change)
    
    def _update_order_book(self, symbol: str):
        """更新订单簿"""
        price = self.current_prices[symbol]
        spread = price * self.spread
        
        # 移除过期订单
        self.order_book[symbol]["bids"] = [(p, s) for p, s in self.order_book[symbol]["bids"] if s > 0]
        self.order_book[symbol]["asks"] = [(p, s) for p, s in self.order_book[symbol]["asks"] if s > 0]
        
        # 添加新订单
        if random.random() < 0.3:  # 30%的概率添加买单
            bid_price = price - spread * random.uniform(1, 5)
            bid_size = random.uniform(0.1, 1.0) * self.liquidity / 20
            self.order_book[symbol]["bids"].append((bid_price, bid_size))
        
        if random.random() < 0.3:  # 30%的概率添加卖单
            ask_price = price + spread * random.uniform(1, 5)
            ask_size = random.uniform(0.1, 1.0) * self.liquidity / 20
            self.order_book[symbol]["asks"].append((ask_price, ask_size))
        
        # 按价格排序
        self.order_book[symbol]["bids"].sort(key=lambda x: -x[0])
        self.order_book[symbol]["asks"].sort(key=lambda x: x[0])
        
        # 限制订单簿深度
        self.order_book[symbol]["bids"] = self.order_book[symbol]["bids"][:20]
        self.order_book[symbol]["asks"] = self.order_book[symbol]["asks"][:20]
    
    def _generate_trades(self, symbol: str):
        """生成交易"""
        if random.random() < 0.1:  # 10%的概率生成交易
            order_book = self.order_book[symbol]
            if order_book["bids"] and order_book["asks"]:
                best_bid = order_book["bids"][0]
                best_ask = order_book["asks"][0]
                
                if best_bid[0] >= best_ask[0]:
                    # 成交
                    trade_price = (best_bid[0] + best_ask[0]) / 2
                    trade_size = min(best_bid[1], best_ask[1])
                    
                    # 更新订单簿
                    order_book["bids"][0] = (best_bid[0], best_bid[1] - trade_size)
                    order_book["asks"][0] = (best_ask[0], best_ask[1] - trade_size)
                    
                    # 记录交易
                    self.trades[symbol].append({
                        "timestamp": datetime.now(),
                        "price": trade_price,
                        "size": trade_size,
                        "side": "buy" if random.random() < 0.5 else "sell"
                    })
    
    def _record_history(self):
        """记录历史数据"""
        self.current_time = datetime.now()
        
        for symbol in self.symbols:
            price = self.current_prices[symbol]
            self.historical_data[symbol].append({
                "timestamp": self.current_time,
                "open": price,
                "high": price * (1 + random.uniform(0, 0.002)),
                "low": price * (1 - random.uniform(0, 0.002)),
                "close": price,
                "volume": random.uniform(100, 1000)
            })
            
            # 限制历史数据长度
            if len(self.historical_data[symbol]) > 1000:
                self.historical_data[symbol] = self.historical_data[symbol][-1000:]
    
    def get_price(self, symbol: str) -> float:
        """获取当前价格"""
        return self.current_prices.get(symbol, 0.0)
    
    def get_order_book(self, symbol: str) -> Dict[str, List[tuple]]:
        """获取订单簿"""
        return self.order_book.get(symbol, {"bids": [], "asks": []})
    
    def get_trades(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取交易记录"""
        trades = self.trades.get(symbol, [])
        return trades[-limit:]
    
    def get_historical_data(self, symbol: str, timeframe: str = "1m", limit: int = 100) -> pd.DataFrame:
        """获取历史数据"""
        data = self.historical_data.get(symbol, [])
        df = pd.DataFrame(data)
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df.set_index("timestamp", inplace=True)
            
            # 按时间周期重采样
            if timeframe == "1m":
                resampled = df
            elif timeframe == "5m":
                resampled = df.resample("5T").agg({
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum"
                })
            elif timeframe == "15m":
                resampled = df.resample("15T").agg({
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum"
                })
            elif timeframe == "1h":
                resampled = df.resample("1H").agg({
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum"
                })
            elif timeframe == "4h":
                resampled = df.resample("4H").agg({
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum"
                })
            elif timeframe == "1d":
                resampled = df.resample("1D").agg({
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum"
                })
            else:
                resampled = df
            
            return resampled.tail(limit)
        return pd.DataFrame()
    
    def execute_order(self, symbol: str, side: str, size: float, price: Optional[float] = None) -> Dict[str, Any]:
        """执行订单"""
        current_price = self.current_prices.get(symbol, 0.0)
        
        if price is None:
            # 市价单
            if side == "buy":
                execution_price = current_price * (1 + self.spread)
            else:
                execution_price = current_price * (1 - self.spread)
        else:
            # 限价单
            execution_price = price
        
        # 模拟执行延迟
        time.sleep(random.uniform(0.01, 0.1))
        
        # 生成执行结果
        execution = {
            "symbol": symbol,
            "side": side,
            "size": size,
            "price": execution_price,
            "timestamp": datetime.now(),
            "status": "filled",
            "filled_size": size,
            "remaining_size": 0
        }
        
        # 记录交易
        self.trades[symbol].append({
            "timestamp": execution["timestamp"],
            "price": execution_price,
            "size": size,
            "side": side
        })
        
        # 更新价格（模拟订单对市场的影响）
        price_impact = size / self.liquidity * 0.01
        if side == "buy":
            self.current_prices[symbol] *= (1 + price_impact)
        else:
            self.current_prices[symbol] *= (1 - price_impact)
        
        return execution
    
    def get_market_state(self) -> Dict[str, Any]:
        """获取市场状态"""
        return {
            "symbols": self.symbols,
            "current_prices": self.current_prices,
            "order_books": self.order_book,
            "last_updated": self.current_time,
            "uptime": (self.current_time - self.start_time).total_seconds()
        }
    
    def reset(self):
        """重置模拟市场"""
        self.current_prices = self.initial_prices.copy()
        self.historical_data = {symbol: [] for symbol in self.symbols}
        self.order_book = {symbol: {"bids": [], "asks": []} for symbol in self.symbols}
        self.trades = {symbol: [] for symbol in self.symbols}
        self.start_time = datetime.now()
        self.current_time = self.start_time
        
        # 重新初始化
        for symbol in self.symbols:
            self._initialize_order_book(symbol)
            self._generate_initial_data(symbol)
        
        logger.info("模拟市场重置")
    
    def set_volatility(self, volatility: float):
        """设置波动率"""
        self.volatility = volatility
    
    def set_trend_strength(self, trend_strength: float):
        """设置趋势强度"""
        self.trend_strength = trend_strength
    
    def set_liquidity(self, liquidity: float):
        """设置流动性"""
        self.liquidity = liquidity
    
    def set_spread(self, spread: float):
        """设置买卖价差"""
        self.spread = spread