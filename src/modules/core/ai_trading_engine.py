"""
全智能AI交易引擎 - 完全自动化、无需人工干预

核心特性：
1. 自主数据采集和分析
2. AI智能决策（开平仓、仓位管理、风险控制）
3. 自动订单执行
4. 实时监控和反馈
5. 策略自我优化和迭代
"""

import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd

logger = logging.getLogger(__name__)


class TradingState(Enum):
    """交易状态"""
    IDLE = "idle"           # 空闲
    ANALYZING = "analyzing" # 分析中
    DECIDING = "deciding"   # 决策中
    EXECUTING = "executing" # 执行中
    MONITORING = "monitoring" # 监控中


class TradeAction(Enum):
    """交易动作"""
    OPEN_LONG = "open_long"      # 开多
    OPEN_SHORT = "open_short"    # 开空
    CLOSE_LONG = "close_long"    # 平多
    CLOSE_SHORT = "close_short"  # 平空
    HOLD = "hold"                # 持有
    WAIT = "wait"                # 观望


@dataclass
class MarketContext:
    """市场环境上下文"""
    symbol: str
    price: float
    trend: str  # bullish, bearish, sideways
    volatility: float
    volume_24h: float
    sentiment: str  # fear, neutral, greed
    support_levels: List[float] = field(default_factory=list)
    resistance_levels: List[float] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class AIDecision:
    """AI决策结果"""
    action: TradeAction
    symbol: str
    price: float
    quantity: float
    confidence: float
    reasoning: str
    risk_level: str  # low, medium, high
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Position:
    """持仓信息"""
    symbol: str
    side: str  # long, short
    entry_price: float
    quantity: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_percent: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    opened_at: datetime = field(default_factory=datetime.now)


class AITradingEngine:
    """
    全智能AI交易引擎
    
    实现完全自动化的交易流程：
    1. 自主数据采集
    2. AI市场分析
    3. 智能决策生成
    4. 自动订单执行
    5. 实时监控和风控
    6. 策略自我优化
    """
    
    def __init__(self, main_controller=None):
        self.main_controller = main_controller
        
        # 核心组件
        self.llm_integration = None
        self.exchange = None
        self.risk_manager = None
        
        # 交易状态
        self.state = TradingState.IDLE
        self.positions: Dict[str, Position] = {}
        self.trade_history: List[Dict] = []
        
        # 监控的交易对
        self.symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
        
        # AI配置
        self.ai_config = {
            "enabled": True,
            "model_id": "astron-code-latest",
            "analysis_interval": 60,  # 分析间隔（秒）
            "min_confidence": 0.65,   # 最小置信度
            "max_positions": 3,       # 最大持仓数
            "risk_per_trade": 0.02,   # 单笔交易风险（2%）
        }
        
        # 运行状态
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._lock = asyncio.Lock()
        
        logger.info("全智能AI交易引擎初始化完成")
    
    async def initialize(self) -> None:
        """初始化AI交易引擎"""
        logger.info("初始化全智能AI交易引擎...")
        
        # 连接LLM集成
        if self.main_controller and hasattr(self.main_controller, 'llm_integration'):
            self.llm_integration = self.main_controller.llm_integration
            logger.info("✅ LLM集成已连接")
        
        # 连接交易所
        if self.main_controller and hasattr(self.main_controller, 'exchange_factory'):
            exchange_factory = self.main_controller.exchange_factory
            if exchange_factory:
                self.exchange = await exchange_factory.create_exchange("okx")
                logger.info("✅ 交易所已连接")
        
        # 连接风险管理器
        if self.main_controller and hasattr(self.main_controller, 'risk_manager'):
            self.risk_manager = self.main_controller.risk_manager
            logger.info("✅ 风险管理器已连接")
        
        # 加载配置
        if self.main_controller and self.main_controller.config_manager:
            config = await self.main_controller.config_manager.get_config("ai_trading", {})
            self.ai_config.update(config)
        
        self._running = True
        logger.info("✅ 全智能AI交易引擎初始化完成")
    
    async def start(self) -> None:
        """启动AI交易引擎"""
        logger.info("🚀 启动全智能AI交易引擎...")
        
        # 启动主交易循环
        self._tasks.append(asyncio.create_task(self._trading_loop()))
        
        # 启动监控任务
        self._tasks.append(asyncio.create_task(self._monitoring_loop()))
        
        # 启动优化任务
        self._tasks.append(asyncio.create_task(self._optimization_loop()))
        
        logger.info("✅ 全智能AI交易引擎已启动")
    
    async def stop(self) -> None:
        """停止AI交易引擎"""
        logger.info("🛑 停止全智能AI交易引擎...")
        self._running = False
        
        for task in self._tasks:
            if not task.done():
                task.cancel()
        
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        
        self._tasks.clear()
        logger.info("✅ 全智能AI交易引擎已停止")
    
    async def _trading_loop(self) -> None:
        """
        主交易循环 - 完全自动化
        
        流程：
        1. 数据采集
        2. AI市场分析
        3. 智能决策
        4. 自动执行
        5. 循环
        """
        while self._running:
            try:
                for symbol in self.symbols:
                    if not self._running:
                        break
                    
                    self.state = TradingState.ANALYZING
                    logger.info(f"🔍 AI正在分析 {symbol}...")
                    
                    # 1. 采集市场数据
                    market_data = await self._collect_market_data(symbol)
                    if not market_data:
                        continue
                    
                    # 2. AI市场分析
                    context = await self._analyze_market(symbol, market_data)
                    
                    # 3. 获取当前持仓
                    current_position = self.positions.get(symbol)
                    
                    # 4. AI智能决策
                    self.state = TradingState.DECIDING
                    decision = await self._make_decision(symbol, context, current_position)
                    
                    if decision and decision.action != TradeAction.HOLD:
                        # 5. 风险检查
                        if await self._risk_check(decision):
                            # 6. 自动执行
                            self.state = TradingState.EXECUTING
                            await self._execute_decision(decision)
                    
                    # 7. 更新持仓状态
                    await self._update_positions()
                    
                    # 8. 短暂休息，避免过于频繁
                    await asyncio.sleep(5)
                
                # 等待下一个分析周期
                await asyncio.sleep(self.ai_config["analysis_interval"])
                
            except Exception as e:
                logger.error(f"交易循环错误: {e}")
                await asyncio.sleep(10)
    
    async def _collect_market_data(self, symbol: str) -> Optional[Dict]:
        """采集市场数据"""
        try:
            if not self.exchange:
                return None
            
            # 获取K线数据
            klines = await self.exchange.get_klines(symbol, interval="1h", limit=100)
            
            # 获取当前价格
            ticker = await self.exchange.get_ticker(symbol)
            
            # 获取订单簿
            order_book = await self.exchange.get_order_book(symbol, limit=20)
            
            return {
                "symbol": symbol,
                "klines": klines,
                "ticker": ticker,
                "order_book": order_book,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"采集市场数据失败 {symbol}: {e}")
            return None
    
    async def _analyze_market(self, symbol: str, market_data: Dict) -> MarketContext:
        """AI市场分析"""
        try:
            if not self.llm_integration:
                # 如果没有LLM，使用基础分析
                return self._basic_analysis(symbol, market_data)
            
            # 使用AI进行深度分析
            analysis_prompt = self._build_analysis_prompt(symbol, market_data)
            
            ai_analysis = await self.llm_integration.analyze_market(
                {
                    "symbol": symbol,
                    "price": market_data["ticker"].get("last", 0),
                    "data": market_data["klines"]
                },
                model_id=self.ai_config["model_id"]
            )
            
            # 解析AI分析结果
            context = MarketContext(
                symbol=symbol,
                price=market_data["ticker"].get("last", 0),
                trend=ai_analysis.get("trend", "sideways"),
                volatility=ai_analysis.get("volatility", 0.5),
                volume_24h=market_data["ticker"].get("volume", 0),
                sentiment=ai_analysis.get("sentiment", "neutral"),
                support_levels=ai_analysis.get("support_levels", []),
                resistance_levels=ai_analysis.get("resistance_levels", [])
            )
            
            logger.info(f"✅ AI分析完成 {symbol}: 趋势={context.trend}, 情绪={context.sentiment}")
            return context
            
        except Exception as e:
            logger.error(f"AI市场分析失败 {symbol}: {e}")
            return self._basic_analysis(symbol, market_data)
    
    def _basic_analysis(self, symbol: str, market_data: Dict) -> MarketContext:
        """基础市场分析（备用）"""
        klines = market_data.get("klines", [])
        if not klines:
            return MarketContext(
                symbol=symbol,
                price=0,
                trend="sideways",
                volatility=0.5,
                volume_24h=0,
                sentiment="neutral"
            )
        
        # 计算基础指标
        prices = [k["close"] for k in klines[-20:]]
        if len(prices) < 2:
            trend = "sideways"
        elif prices[-1] > prices[0] * 1.02:
            trend = "bullish"
        elif prices[-1] < prices[0] * 0.98:
            trend = "bearish"
        else:
            trend = "sideways"
        
        return MarketContext(
            symbol=symbol,
            price=prices[-1] if prices else 0,
            trend=trend,
            volatility=0.3,
            volume_24h=market_data.get("ticker", {}).get("volume", 0),
            sentiment="neutral"
        )
    
    def _build_analysis_prompt(self, symbol: str, market_data: Dict) -> str:
        """构建AI分析提示词"""
        ticker = market_data.get("ticker", {})
        return f"""请分析 {symbol} 的市场情况：

当前价格: {ticker.get('last', 'N/A')}
24h最高: {ticker.get('high', 'N/A')}
24h最低: {ticker.get('low', 'N/A')}
24h成交量: {ticker.get('volume', 'N/A')}

请提供：
1. 趋势判断 (bullish/bearish/sideways)
2. 波动率评估 (0-1)
3. 市场情绪 (fear/neutral/greed)
4. 关键支撑位
5. 关键阻力位
6. 交易建议

请以JSON格式返回。"""
    
    async def _make_decision(self, symbol: str, context: MarketContext, 
                           current_position: Optional[Position]) -> Optional[AIDecision]:
        """AI智能决策"""
        try:
            if not self.llm_integration:
                return self._basic_decision(symbol, context, current_position)
            
            # 构建决策提示词
            decision_prompt = self._build_decision_prompt(symbol, context, current_position)
            
            # 调用AI生成决策
            ai_decision = await self.llm_integration.generate_trading_signal(
                {
                    "symbol": symbol,
                    "price": context.price,
                    "trend": context.trend,
                    "sentiment": context.sentiment,
                    "volatility": context.volatility
                },
                model_id=self.ai_config["model_id"]
            )
            
            # 解析决策
            signal = ai_decision.get("signal", "hold")
            confidence = ai_decision.get("confidence", 0.5)
            
            # 检查置信度
            if confidence < self.ai_config["min_confidence"]:
                logger.info(f"⏸️ {symbol} 置信度不足 ({confidence:.2f})，保持观望")
                return None
            
            # 确定交易动作
            action = self._parse_action(signal, current_position)
            
            if action == TradeAction.HOLD:
                return None
            
            # 计算仓位大小
            quantity = await self._calculate_position_size(symbol, context, action)
            
            # 计算止损止盈
            stop_loss, take_profit = self._calculate_stop_loss_take_profit(
                context, action
            )
            
            decision = AIDecision(
                action=action,
                symbol=symbol,
                price=context.price,
                quantity=quantity,
                confidence=confidence,
                reasoning=ai_decision.get("reasoning", "AI决策"),
                risk_level=ai_decision.get("risk_level", "medium"),
                stop_loss=stop_loss,
                take_profit=take_profit,
                metadata={
                    "ai_analysis": ai_decision,
                    "market_context": context.__dict__
                }
            )
            
            logger.info(f"🤖 AI决策 {symbol}: {action.value} @ {context.price}, 置信度={confidence:.2f}")
            return decision
            
        except Exception as e:
            logger.error(f"AI决策失败 {symbol}: {e}")
            return self._basic_decision(symbol, context, current_position)
    
    def _basic_decision(self, symbol: str, context: MarketContext,
                       current_position: Optional[Position]) -> Optional[AIDecision]:
        """基础决策（备用）"""
        # 简单的趋势跟随策略
        if context.trend == "bullish" and not current_position:
            action = TradeAction.OPEN_LONG
        elif context.trend == "bearish" and not current_position:
            action = TradeAction.OPEN_SHORT
        elif current_position:
            # 检查是否需要平仓
            if (current_position.side == "long" and context.trend == "bearish") or \
               (current_position.side == "short" and context.trend == "bullish"):
                action = TradeAction.CLOSE_LONG if current_position.side == "long" else TradeAction.CLOSE_SHORT
            else:
                return None
        else:
            return None
        
        return AIDecision(
            action=action,
            symbol=symbol,
            price=context.price,
            quantity=0.01,  # 默认仓位
            confidence=0.6,
            reasoning="基础趋势跟随策略",
            risk_level="medium"
        )
    
    def _build_decision_prompt(self, symbol: str, context: MarketContext,
                              position: Optional[Position]) -> str:
        """构建决策提示词"""
        position_info = "无持仓"
        if position:
            position_info = f"{position.side} 仓, 入场价={position.entry_price}, 数量={position.quantity}"
        
        return f"""基于以下市场信息，做出交易决策：

交易对: {symbol}
当前价格: {context.price}
趋势: {context.trend}
情绪: {context.sentiment}
波动率: {context.volatility:.2f}
当前持仓: {position_info}

请提供：
1. 交易信号 (buy/sell/hold)
2. 置信度 (0-1)
3. 建议仓位大小
4. 风险等级 (low/medium/high)
5. 决策理由
6. 止损价格（如有）
7. 止盈价格（如有）

请以JSON格式返回。"""
    
    def _parse_action(self, signal: str, current_position: Optional[Position]) -> TradeAction:
        """解析交易动作"""
        signal = signal.lower()
        
        if signal == "buy":
            if current_position and current_position.side == "short":
                return TradeAction.CLOSE_SHORT
            return TradeAction.OPEN_LONG
        elif signal == "sell":
            if current_position and current_position.side == "long":
                return TradeAction.CLOSE_LONG
            return TradeAction.OPEN_SHORT
        else:
            return TradeAction.HOLD
    
    async def _calculate_position_size(self, symbol: str, context: MarketContext,
                                      action: TradeAction) -> float:
        """计算仓位大小"""
        try:
            # 获取账户余额
            if self.exchange:
                balance = await self.exchange.get_balance()
                available = balance.get("USDT", {}).get("free", 10000)
            else:
                available = 10000  # 默认
            
            # 基于风险计算仓位
            risk_amount = available * self.ai_config["risk_per_trade"]
            
            # 根据波动率调整
            volatility_factor = 1 - min(context.volatility, 0.5)
            
            # 根据置信度调整
            # 这里简化处理，实际应该传入confidence
            
            position_value = risk_amount * volatility_factor
            quantity = position_value / context.price if context.price > 0 else 0
            
            # 限制最大仓位
            max_quantity = available * 0.1 / context.price if context.price > 0 else 0
            quantity = min(quantity, max_quantity)
            
            return round(quantity, 6)
            
        except Exception as e:
            logger.error(f"计算仓位大小失败: {e}")
            return 0.01  # 默认最小仓位
    
    def _calculate_stop_loss_take_profit(self, context: MarketContext,
                                        action: TradeAction) -> tuple:
        """计算止损止盈价格"""
        price = context.price
        
        if action in [TradeAction.OPEN_LONG, TradeAction.CLOSE_SHORT]:
            # 多单
            stop_loss = price * 0.97  # 3%止损
            take_profit = price * 1.06  # 6%止盈
        elif action in [TradeAction.OPEN_SHORT, TradeAction.CLOSE_LONG]:
            # 空单
            stop_loss = price * 1.03  # 3%止损
            take_profit = price * 0.94  # 6%止盈
        else:
            return None, None
        
        return round(stop_loss, 2), round(take_profit, 2)
    
    async def _risk_check(self, decision: AIDecision) -> bool:
        """风险检查"""
        try:
            # 检查最大持仓数
            if len(self.positions) >= self.ai_config["max_positions"]:
                if decision.action in [TradeAction.OPEN_LONG, TradeAction.OPEN_SHORT]:
                    logger.warning(f"⚠️ 已达到最大持仓数限制 ({self.ai_config['max_positions']})")
                    return False
            
            # 检查是否已有同向持仓
            existing = self.positions.get(decision.symbol)
            if existing:
                if decision.action == TradeAction.OPEN_LONG and existing.side == "long":
                    logger.warning(f"⚠️ {decision.symbol} 已有多仓")
                    return False
                if decision.action == TradeAction.OPEN_SHORT and existing.side == "short":
                    logger.warning(f"⚠️ {decision.symbol} 已有空仓")
                    return False
            
            # 外部风险检查
            if self.risk_manager:
                risk_ok = await self.risk_manager.check_trade(decision.__dict__)
                if not risk_ok:
                    logger.warning(f"⚠️ 风险检查未通过")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"风险检查失败: {e}")
            return False
    
    async def _execute_decision(self, decision: AIDecision) -> bool:
        """执行AI决策"""
        try:
            if not self.exchange:
                logger.warning("❌ 交易所未连接，无法执行")
                return False
            
            logger.info(f"🚀 执行交易: {decision.action.value} {decision.symbol} "
                       f"@ {decision.price}, 数量={decision.quantity}")
            
            # 构建订单
            order = {
                "symbol": decision.symbol,
                "side": "buy" if decision.action in [TradeAction.OPEN_LONG, TradeAction.CLOSE_SHORT] else "sell",
                "type": "market",  # 使用市价单快速执行
                "quantity": decision.quantity
            }
            
            # 执行订单
            result = await self.exchange.place_order(order)
            
            if result:
                logger.info(f"✅ 订单执行成功: {result.get('id', 'N/A')}")
                
                # 记录交易
                self.trade_history.append({
                    "timestamp": datetime.now().isoformat(),
                    "decision": decision.__dict__,
                    "order_result": result
                })
                
                # 更新持仓
                await self._update_positions()
                
                return True
            else:
                logger.error("❌ 订单执行失败")
                return False
                
        except Exception as e:
            logger.error(f"执行决策失败: {e}")
            return False
    
    async def _update_positions(self) -> None:
        """更新持仓信息"""
        try:
            if not self.exchange:
                return
            
            # 获取当前持仓
            positions = await self.exchange.get_positions()
            
            self.positions.clear()
            for pos in positions:
                symbol = pos.get("symbol")
                if symbol:
                    self.positions[symbol] = Position(
                        symbol=symbol,
                        side=pos.get("side", "long"),
                        entry_price=pos.get("entry_price", 0),
                        quantity=pos.get("quantity", 0),
                        current_price=pos.get("mark_price", 0),
                        unrealized_pnl=pos.get("unrealized_pnl", 0),
                        unrealized_pnl_percent=pos.get("unrealized_pnl_percent", 0),
                        stop_loss=pos.get("stop_loss"),
                        take_profit=pos.get("take_profit")
                    )
            
        except Exception as e:
            logger.error(f"更新持仓失败: {e}")
    
    async def _monitoring_loop(self) -> None:
        """监控循环"""
        while self._running:
            try:
                self.state = TradingState.MONITORING
                
                # 监控持仓
                for symbol, position in self.positions.items():
                    # 检查止损止盈
                    if position.stop_loss and position.current_price <= position.stop_loss:
                        logger.warning(f"🚨 {symbol} 触发止损!")
                        # 自动平仓
                        await self._execute_decision(AIDecision(
                            action=TradeAction.CLOSE_LONG if position.side == "long" else TradeAction.CLOSE_SHORT,
                            symbol=symbol,
                            price=position.current_price,
                            quantity=position.quantity,
                            confidence=1.0,
                            reasoning="止损触发",
                            risk_level="high"
                        ))
                    
                    elif position.take_profit and position.current_price >= position.take_profit:
                        logger.info(f"🎯 {symbol} 触发止盈!")
                        # 自动平仓
                        await self._execute_decision(AIDecision(
                            action=TradeAction.CLOSE_LONG if position.side == "long" else TradeAction.CLOSE_SHORT,
                            symbol=symbol,
                            price=position.current_price,
                            quantity=position.quantity,
                            confidence=1.0,
                            reasoning="止盈触发",
                            risk_level="low"
                        ))
                
                # 每10秒检查一次
                await asyncio.sleep(10)
                
            except Exception as e:
                logger.error(f"监控循环错误: {e}")
                await asyncio.sleep(10)
    
    async def _optimization_loop(self) -> None:
        """优化循环 - 策略自我优化"""
        while self._running:
            try:
                # 每小时优化一次
                await asyncio.sleep(3600)
                
                logger.info("🔄 开始策略自我优化...")
                
                # 分析交易历史
                if len(self.trade_history) >= 10:
                    await self._optimize_strategy()
                
            except Exception as e:
                logger.error(f"优化循环错误: {e}")
    
    async def _optimize_strategy(self) -> None:
        """策略优化"""
        try:
            # 计算胜率
            profitable_trades = sum(1 for t in self.trade_history 
                                   if t.get("decision", {}).get("pnl", 0) > 0)
            total_trades = len(self.trade_history)
            win_rate = profitable_trades / total_trades if total_trades > 0 else 0
            
            logger.info(f"📊 策略性能: 胜率={win_rate:.2%}, 总交易={total_trades}")
            
            # 根据胜率调整参数
            if win_rate < 0.4:
                # 胜率低，提高置信度阈值
                self.ai_config["min_confidence"] = min(0.8, self.ai_config["min_confidence"] + 0.05)
                logger.info(f"📈 调整参数: 提高置信度阈值到 {self.ai_config['min_confidence']}")
            elif win_rate > 0.6:
                # 胜率高，可以适当降低阈值捕捉更多机会
                self.ai_config["min_confidence"] = max(0.5, self.ai_config["min_confidence"] - 0.02)
                logger.info(f"📉 调整参数: 降低置信度阈值到 {self.ai_config['min_confidence']}")
            
        except Exception as e:
            logger.error(f"策略优化失败: {e}")
    
    def get_status(self) -> Dict:
        """获取引擎状态"""
        return {
            "state": self.state.value,
            "running": self._running,
            "positions": len(self.positions),
            "trade_count": len(self.trade_history),
            "symbols": self.symbols,
            "ai_config": self.ai_config
        }
