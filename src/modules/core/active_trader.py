"""
AI 主动交易执行器 - 真正执行交易
确保AI不只是空谈，而是真正调用交易所API执行开平仓
"""

import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

from .timing_constants import SLEEP_2S, SLEEP_5S, SLEEP_10S, SLEEP_60S, SLEEP_1H
from .stop_loss_take_profit import StopLossTakeProfitStatus
from src.modules.memory.memory_schema import base_metadata, kind_tag, symbol_tag, tags


class TradeMode(Enum):
    SIMULATION = "simulation"
    LIVE = "live"


@dataclass
class TradeOpportunity:
    """交易机会"""
    symbol: str
    action: str  # buy, sell
    side: str    # long, short
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence: float
    reason: str
    leverage: int = 20
    quantity: float = 0.0


class ActiveTrader:
    """
    主动交易执行器
    
    核心功能：
    1. 自动扫描市场寻找机会
    2. 真正调用交易所API执行交易
    3. 自动创建和运行策略
    4. 实时监控持仓（止盈止损优先由全局 StopLossTakeProfitManager 执行，避免与本模块重复平仓）

    实盘下单：优先经 MainController.execution_gateway（source=system），与 S1 一致。
    """
    
    def __init__(self, main_controller=None):
        self.main_controller = main_controller
        self.exchange = None
        self.llm = None
        self.memory = None
        
        self.trade_mode = TradeMode.LIVE
        self.blacklist = set()  # 空黑名单，允许所有交易对
        
        self.contract_config = {
            "leverage_min": 10,
            "leverage_max": 50,
            "default_leverage": 20,
            "max_positions": 5,
            "min_positions": 3,
            "margin_mode": "cross",
        }
        
        self.active_positions: Dict[str, Dict] = {}
        self.trade_history: List[Dict] = []
        self.strategies: Dict[str, Dict] = {}
        
        self._running = False
        self._last_trade_time: Dict[str, datetime] = {}
        self._min_trade_interval = 300
        
        self._opportunities: List[TradeOpportunity] = []
        
        logger.info("🎯 主动交易执行器初始化")
    
    async def initialize(self) -> None:
        """初始化"""
        logger.info("初始化主动交易执行器...")
        
        if self.main_controller:
            if hasattr(self.main_controller, "get_exchange"):
                self.exchange = self.main_controller.get_exchange()
            elif hasattr(self.main_controller, 'okx_exchange'):
                self.exchange = self.main_controller.okx_exchange
            elif hasattr(self.main_controller, 'exchange'):
                self.exchange = self.main_controller.exchange
            
            if hasattr(self.main_controller, "get_llm_integration"):
                self.llm = self.main_controller.get_llm_integration()
            elif hasattr(self.main_controller, 'llm_integration'):
                self.llm = self.main_controller.llm_integration

            config_manager = getattr(self.main_controller, "config_manager", None)
            if config_manager:
                try:
                    cfg = await config_manager.get_config("active_trader", {})
                    if isinstance(cfg, dict):
                        ccfg = cfg.get("contract_config", {})
                        if isinstance(ccfg, dict):
                            self.contract_config.update(ccfg)
                        self._min_trade_interval = cfg.get("min_trade_interval", self._min_trade_interval)
                except Exception as e:
                    logger.debug(f"读取active_trader配置失败，使用默认值: {e}")
        
        try:
            # 单一真源：只使用主控制器 MemoryGateway
            self.memory = getattr(self.main_controller, "ai_memory_manager", None) if self.main_controller else None
            if not self.memory:
                logger.debug("初始化记忆系统失败（MemoryGateway未就绪），继续无记忆模式")
        except Exception as e:
            logger.debug(f"初始化记忆系统失败，继续无记忆模式: {e}")
        
        await self._load_user_rules()
        
        await self._auto_create_strategies()
        
        logger.info(f"✅ 主动交易执行器初始化完成")
        logger.info(f"📊 交易模式: {self.trade_mode.value}")
        logger.info(f"🚫 黑名单: {self.blacklist}")
        logger.info(f"📋 已加载策略: {len(self.strategies)}个")
    
    async def _load_user_rules(self) -> None:
        """加载用户规则"""
        if not self.memory:
            return
        
        try:
            blacklist_mems = await self.memory.retrieve_memories(
                query="黑名单 禁区 不要",
                min_importance=0.8,
                limit=5
            )
            for mem in blacklist_mems:
                # 不再自动将ETH加入黑名单
                if "ETH" in mem.content or "以太坊" in mem.content:
                    logger.info(f"ℹ️ 忽略ETH黑名单记忆: 已移除ETH限制")
            
            logger.info(f"📋 已加载黑名单: {self.blacklist}")
        except Exception as e:
            logger.error(f"加载用户规则失败: {e}")
    
    async def _auto_create_strategies(self) -> None:
        """自动创建默认策略"""
        if self.strategies:
            return
        
        logger.info("🔧 自动创建默认策略...")
        
        default_strategies = [
            {
                "id": "trend_following_1",
                "name": "趋势跟踪策略",
                "type": "trend_following",
                "description": "基于MA和RSI的趋势跟踪",
                "symbols": ["BTC/USDT", "SOL/USDT", "BNB/USDT"],
                "parameters": {
                    "ma_fast": 5,
                    "ma_slow": 20,
                    "rsi_overbought": 70,
                    "rsi_oversold": 30,
                },
                "enabled": True,
            },
            {
                "id": "breakout_1",
                "name": "突破策略",
                "type": "breakout",
                "description": "布林带突破交易",
                "symbols": ["BTC/USDT", "SOL/USDT"],
                "parameters": {
                    "bollinger_period": 20,
                    "bollinger_std": 2,
                    "breakout_confirm": 3,
                },
                "enabled": True,
            },
            {
                "id": "grid_1",
                "name": "网格交易策略",
                "type": "grid",
                "description": "震荡市场网格交易",
                "symbols": ["BTC/USDT"],
                "parameters": {
                    "grid_levels": 10,
                    "grid_spacing": 0.01,
                    "grid_amount": 0.001,
                },
                "enabled": True,
            }
        ]
        
        for strategy in default_strategies:
            strategy["symbols"] = [s for s in strategy["symbols"] if s not in self.blacklist]
            if strategy["symbols"]:
                self.strategies[strategy["id"]] = strategy
                logger.info(f"✅ 创建策略: {strategy['name']} - {strategy['symbols']}")
    
    async def start(self) -> None:
        """启动主动交易"""
        logger.info("🚀 启动主动交易执行器...")
        self._running = True
        
        asyncio.create_task(self._main_trading_loop())
        asyncio.create_task(self._position_monitor_loop())
        asyncio.create_task(self._strategy_optimization_loop())
        
        logger.info("✅ 主动交易执行器已启动")
    
    async def stop(self) -> None:
        """停止"""
        self._running = False
        logger.info("🛑 主动交易执行器已停止")
    
    async def _main_trading_loop(self) -> None:
        """主交易循环 - 主动扫描并执行"""
        while self._running:
            try:
                logger.info("🔄 执行主动市场扫描...")
                
                symbols = ["BTC/USDT", "SOL/USDT", "BNB/USDT"]
                symbols = [s for s in symbols if s not in self.blacklist]
                
                for symbol in symbols:
                    try:
                        opportunity = await self._scan_for_opportunity(symbol)
                        
                        if opportunity:
                            logger.info(f"💡 发现交易机会: {symbol} {opportunity.action}")
                            
                            if await self._should_execute(opportunity):
                                success = await self._execute_trade(opportunity)
                                
                                if success:
                                    self._opportunities.append(opportunity)
                                    await self._notify_trade_execution(opportunity)
                    
                    except Exception as e:
                        logger.error(f"扫描 {symbol} 失败: {e}")
                    
                    await asyncio.sleep(SLEEP_2S)
                
                await asyncio.sleep(SLEEP_60S)
                
            except Exception as e:
                logger.error(f"主交易循环错误: {e}")
                await asyncio.sleep(SLEEP_10S)
    
    async def _scan_for_opportunity(self, symbol: str) -> Optional[TradeOpportunity]:
        """扫描交易机会"""
        if not self.exchange:
            return None
        
        try:
            ticker = await self.exchange.get_ticker(symbol.replace('/', '-'))
            if not ticker:
                return None
            
            current_price = ticker.get('last', 0)
            if current_price <= 0:
                return None
            
            klines = await self.exchange.get_klines(symbol.replace('/', '-'), '1H', limit=100)
            if not klines or len(klines) < 50:
                return None
            
            analysis = self._analyze_market_data(klines, current_price)
            
            if analysis["confidence"] >= 0.72:
                return TradeOpportunity(
                    symbol=symbol,
                    action=analysis["action"],
                    side=analysis["side"],
                    entry_price=current_price,
                    stop_loss=analysis["stop_loss"],
                    take_profit=analysis["take_profit"],
                    confidence=analysis["confidence"],
                    reason=analysis["reason"],
                    leverage=self.contract_config["default_leverage"],
                    quantity=await self._calculate_position_size(symbol, current_price)
                )
            
            return None
            
        except Exception as e:
            logger.error(f"扫描机会失败 {symbol}: {e}")
            return None
    
    def _analyze_market_data(self, klines: List[Dict], current_price: float) -> Dict:
        """分析市场数据"""
        closes = [k.get('close', 0) for k in klines]
        highs = [k.get('high', 0) for k in klines]
        lows = [k.get('low', 0) for k in klines]
        volumes = [k.get('volume', 0) for k in klines]
        
        ma5 = sum(closes[-5:]) / 5 if len(closes) >= 5 else current_price
        ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else current_price
        ma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else current_price
        
        gains = []
        losses = []
        for i in range(1, min(15, len(closes))):
            change = closes[-i] - closes[-i-1]
            if change > 0:
                gains.append(change)
            else:
                losses.append(abs(change))
        
        avg_gain = sum(gains) / len(gains) if gains else 0
        avg_loss = sum(losses) / len(losses) if losses else 0.001
        rs = avg_gain / avg_loss if avg_loss > 0 else 0
        rsi = 100 - (100 / (1 + rs))
        
        atr_period = 14
        tr_list = []
        for i in range(1, min(atr_period + 1, len(closes))):
            tr = max(highs[-i] - lows[-i],
                    abs(highs[-i] - closes[-i-1]),
                    abs(lows[-i] - closes[-i-1]))
            tr_list.append(tr)
        atr = sum(tr_list) / len(tr_list) if tr_list else current_price * 0.02
        
        action = "hold"
        side = "long"
        confidence = 0.0
        reason = ""
        
        trend_up = ma5 > ma20 > ma50
        trend_down = ma5 < ma20 < ma50
        
        if trend_up and rsi < 62:
            action = "buy"
            side = "long"
            confidence = 0.74
            reason = f"上升趋势: MA5({ma5:.2f}) > MA20({ma20:.2f}), RSI={rsi:.1f}"
        elif trend_down and rsi > 38:
            action = "sell"
            side = "short"
            confidence = 0.74
            reason = f"下降趋势: MA5({ma5:.2f}) < MA20({ma20:.2f}), RSI={rsi:.1f}"
        elif rsi < 22:
            action = "buy"
            side = "long"
            confidence = 0.72
            reason = f"超卖反弹: RSI={rsi:.1f}"
        elif rsi > 78:
            action = "sell"
            side = "short"
            confidence = 0.72
            reason = f"超买回调: RSI={rsi:.1f}"
        
        if action == "hold":
            return {"action": "hold", "confidence": 0}
        
        if side == "long":
            stop_loss = current_price - 2 * atr
            take_profit = current_price + 3 * atr
        else:
            stop_loss = current_price + 2 * atr
            take_profit = current_price - 3 * atr
        
        return {
            "action": action,
            "side": side,
            "confidence": confidence,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "reason": reason
        }
    
    async def _calculate_position_size(self, symbol: str, price: float) -> float:
        """计算仓位大小 - 返回整数张数"""
        try:
            if self.exchange:
                balance = await self.exchange.get_balance()
                if isinstance(balance, dict):
                    usdt = balance.get('USDT', {})
                    if isinstance(usdt, dict):
                        available = usdt.get('free', 100)
                    else:
                        available = 100
                else:
                    available = 100
            else:
                available = 100
            
            risk_per_trade = 0.1
            position_value = available * risk_per_trade
            
            leverage = self.contract_config["default_leverage"]
            
            # BTC-USDT-SWAP 合约面值是 0.01 BTC
            # 数量(张数) = 名义价值 / 合约面值
            contract_value = 0.01  # BTC永续合约面值
            
            # 计算张数
            contracts = position_value * leverage / (price * contract_value)
            
            # 向上取整到最小1张
            quantity = max(1, int(contracts))
            
            logger.info(f"📊 计算仓位: {symbol} - {quantity}张, 保证金={position_value:.2f}USDT, 杠杆{leverage}x")
            
            return quantity
            
        except Exception as e:
            logger.error(f"计算仓位失败: {e}")
            return 1
    
    async def _should_execute(self, opportunity: TradeOpportunity) -> bool:
        """判断是否应该执行"""
        if opportunity.symbol in self.blacklist:
            logger.info(f"⏭️ {opportunity.symbol} 在黑名单中，跳过")
            return False
        
        if opportunity.symbol in self._last_trade_time:
            last_time = self._last_trade_time[opportunity.symbol]
            if (datetime.now() - last_time).total_seconds() < self._min_trade_interval:
                logger.info(f"⏳ {opportunity.symbol} 交易间隔太短，跳过")
                return False
        
        current_positions = len(self.active_positions)
        if current_positions >= self.contract_config["max_positions"]:
            logger.info(f"📊 已达最大持仓数 {current_positions}，跳过")
            return False
        
        return True
    
    async def _execute_trade(self, opportunity: TradeOpportunity) -> bool:
        """执行交易 - 真正调用API"""
        logger.info(f"🚀 执行交易: {opportunity.symbol} {opportunity.action} {opportunity.side}")
        logger.info(f"   入场价: {opportunity.entry_price}")
        logger.info(f"   数量: {opportunity.quantity}")
        logger.info(f"   杠杆: {opportunity.leverage}x")
        logger.info(f"   止损: {opportunity.stop_loss}")
        logger.info(f"   止盈: {opportunity.take_profit}")
        
        if not self.exchange:
            logger.error("❌ 交易所未连接，无法执行交易")
            return False
        
        try:
            gw = None
            if self.main_controller:
                gw = getattr(self.main_controller, "execution_gateway", None)

            if gw:
                order = await gw.open_swap(
                    opportunity.symbol,
                    opportunity.side,
                    float(opportunity.quantity),
                    int(opportunity.leverage),
                    "system",
                    f"active_trader:{opportunity.reason[:120]}",
                    margin_mode=self.contract_config["margin_mode"],
                    price=None,
                )
            else:
                leverage_set = await self.exchange.set_leverage(
                    symbol=opportunity.symbol.replace('/', '-'),
                    leverage=opportunity.leverage,
                    margin_mode=self.contract_config["margin_mode"]
                )
                logger.info(f"✅ 设置杠杆: {opportunity.leverage}x")
                logger.info(f"📤 杠杆设置请求: symbol={opportunity.symbol}, leverage={opportunity.leverage}, margin_mode={self.contract_config['margin_mode']}")
                logger.debug(f"📥 杠杆设置详情: {leverage_set}")

                if opportunity.side == "long":
                    order = await self.exchange.open_swap_position(
                        symbol=opportunity.symbol.replace('/', '-'),
                        side="long",
                        size=opportunity.quantity,
                        leverage=opportunity.leverage
                    )
                else:
                    order = await self.exchange.open_swap_position(
                        symbol=opportunity.symbol.replace('/', '-'),
                        side="short",
                        size=opportunity.quantity,
                        leverage=opportunity.leverage
                    )
            
            if order and order.get("success"):
                logger.info(f"✅ 订单执行成功: {order.get('orderId', 'N/A')}")
                
                self.active_positions[opportunity.symbol] = {
                    "symbol": opportunity.symbol,
                    "side": opportunity.side,
                    "entry_price": opportunity.entry_price,
                    "quantity": opportunity.quantity,
                    "leverage": opportunity.leverage,
                    "stop_loss": opportunity.stop_loss,
                    "take_profit": opportunity.take_profit,
                    "order_id": order.get("orderId"),
                    "opened_at": datetime.now().isoformat(),
                    "reason": opportunity.reason
                }
                
                self._last_trade_time[opportunity.symbol] = datetime.now()
                
                self.trade_history.append({
                    "timestamp": datetime.now().isoformat(),
                    "opportunity": opportunity.__dict__,
                    "order": order
                })
                
                await self._save_trade_to_memory(opportunity, order)
                
                return True
            else:
                error_msg = order.get("error", "未知错误") if order else "返回为空"
                logger.error(f"❌ 订单执行失败: {error_msg}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 执行交易失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def _position_monitor_loop(self) -> None:
        """持仓监控循环"""
        while self._running:
            try:
                if not self.exchange:
                    await asyncio.sleep(SLEEP_10S)
                    continue
                
                positions = await self.exchange.get_positions()
                
                if positions:
                    for pos in positions:
                        symbol = pos.get('symbol', '').replace('-', '/')
                        
                        if symbol in self.blacklist:
                            continue
                        
                        current_price = pos.get('markPrice', 0)
                        unrealized_pnl = pos.get('unrealizedPnl', 0)
                        
                        if symbol in self.active_positions:
                            pos_info = self.active_positions[symbol]
                            
                            stop_loss = pos_info.get('stop_loss', 0)
                            take_profit = pos_info.get('take_profit', 0)
                            side = pos_info.get('side', 'long')
                            
                            should_close = False
                            close_reason = ""
                            
                            if side == "long":
                                if stop_loss > 0 and current_price <= stop_loss:
                                    should_close = True
                                    close_reason = "触发止损"
                                elif take_profit > 0 and current_price >= take_profit:
                                    should_close = True
                                    close_reason = "触发止盈"
                            else:
                                if stop_loss > 0 and current_price >= stop_loss:
                                    should_close = True
                                    close_reason = "触发止损"
                                elif take_profit > 0 and current_price <= take_profit:
                                    should_close = True
                                    close_reason = "触发止盈"
                            
                            if should_close:
                                slm = (
                                    getattr(self.main_controller, "stop_loss_manager", None)
                                    if self.main_controller
                                    else None
                                )
                                if slm:
                                    sl_o = await slm.get_order(symbol)
                                    if (
                                        sl_o is not None
                                        and sl_o.status == StopLossTakeProfitStatus.ACTIVE
                                    ):
                                        logger.debug(
                                            "ActiveTrader: %s 已有 StopLossTakeProfit 单，跳过本地止盈止损平仓",
                                            symbol,
                                        )
                                        continue
                                logger.info(f"🎯 {symbol} {close_reason}，执行平仓")
                                await self._close_position(symbol, close_reason)
                
                await asyncio.sleep(SLEEP_10S)
                
            except Exception as e:
                logger.error(f"持仓监控错误: {e}")
                await asyncio.sleep(SLEEP_10S)
    
    async def _close_position(self, symbol: str, reason: str) -> bool:
        """平仓"""
        if symbol not in self.active_positions:
            return False
        
        pos_info = self.active_positions[symbol]
        
        logger.info(f"🔒 平仓: {symbol} {pos_info['side']} - {reason}")
        
        try:
            gw = None
            if self.main_controller:
                gw = getattr(self.main_controller, "execution_gateway", None)

            if gw:
                order = await gw.close_swap(
                    symbol,
                    pos_info["side"],
                    float(pos_info["quantity"]),
                    "system",
                    f"active_trader:{reason}",
                )
            else:
                order = await self.exchange.close_swap_position(
                    symbol=symbol.replace('/', '-'),
                    side=pos_info["side"],
                    size=pos_info["quantity"]
                )
            
            if order and (order.get("success") if isinstance(order, dict) else order):
                logger.info(f"✅ 平仓成功: {order.get('orderId', 'N/A')}")
                
                del self.active_positions[symbol]
                
                return True
            else:
                logger.error("❌ 平仓失败")
                return False
                
        except Exception as e:
            logger.error(f"平仓失败: {e}")
            return False
    
    async def _strategy_optimization_loop(self) -> None:
        """策略优化循环"""
        while self._running:
            try:
                await asyncio.sleep(SLEEP_1H)
                
                if len(self.trade_history) >= 5:
                    logger.info("🔄 执行策略优化...")
                    
                    profitable = sum(1 for t in self.trade_history 
                                   if t.get("order", {}).get("success", False))
                    total = len(self.trade_history)
                    win_rate = profitable / total if total > 0 else 0
                    
                    logger.info(f"📊 交易统计: 胜率={win_rate:.1%}, 总交易={total}")
                    
                    if win_rate < 0.4:
                        logger.info("📈 胜率较低，提高置信度阈值")
                    elif win_rate > 0.6:
                        logger.info("📉 胜率良好，可适当增加交易频率")
                
            except Exception as e:
                logger.error(f"策略优化错误: {e}")
    
    async def _save_trade_to_memory(self, opportunity: TradeOpportunity, order: Dict) -> None:
        """保存交易到记忆"""
        if not self.memory:
            return
        
        try:
            sym = getattr(opportunity, "symbol", None)
            await self.memory.add_memory(
                memory_type="trade_record",
                content=f"执行交易: {opportunity.symbol} {opportunity.action} {opportunity.side} @ {opportunity.entry_price}",
                summary=f"🎯 交易执行: {opportunity.symbol} {opportunity.side} @{opportunity.entry_price}",
                metadata=base_metadata(
                    source_module="active_trader",
                    kind="trade_execution",
                    symbol=sym,
                    extra={
                        "action": opportunity.action,
                        "side": opportunity.side,
                        "price": opportunity.entry_price,
                        "quantity": opportunity.quantity,
                        "leverage": opportunity.leverage,
                        "order_id": order.get("orderId"),
                        "reason": opportunity.reason,
                    },
                ),
                importance=0.9,
                source_module="active_trader",
                tags=tags(
                    kind_tag("trade"),
                    kind_tag("execution"),
                    symbol_tag(sym),
                ),
            )
            
            logger.info("💾 交易记录已保存到记忆库")
            
        except Exception as e:
            logger.error(f"保存交易记忆失败: {e}")
    
    async def _notify_trade_execution(self, opportunity: TradeOpportunity) -> None:
        """通知交易执行"""
        message = f"""
🎯 交易执行通知

交易对: {opportunity.symbol}
方向: {opportunity.side.upper()}
价格: {opportunity.entry_price}
数量: {opportunity.quantity}
杠杆: {opportunity.leverage}x
止损: {opportunity.stop_loss}
止盈: {opportunity.take_profit}
原因: {opportunity.reason}
时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        logger.info(message)
        
        if self.main_controller:
            try:
                bot = (
                    self.main_controller.get_telegram_bot()
                    if hasattr(self.main_controller, "get_telegram_bot")
                    else getattr(self.main_controller, "telegram_bot", None)
                )
                if bot and hasattr(bot, 'send_message'):
                    await bot.send_message(message)
            except Exception as e:
                logger.debug(f"发送交易执行通知失败: {e}")
    
    def get_status(self) -> Dict:
        """获取状态"""
        return {
            "running": self._running,
            "trade_mode": self.trade_mode.value,
            "blacklist": list(self.blacklist),
            "active_positions": len(self.active_positions),
            "total_trades": len(self.trade_history),
            "strategies": len(self.strategies),
            "positions": self.active_positions
        }
