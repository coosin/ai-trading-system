"""
AI 指令解析器 - 将自然语言指令解析为交易操作
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class CommandType(Enum):
    """指令类型"""
    OPEN_POSITION = "open_position"       # 开仓
    CLOSE_POSITION = "close_position"     # 平仓
    ANALYZE_MARKET = "analyze_market"     # 分析市场
    START_TRADING = "start_trading"       # 开始自动交易
    STOP_TRADING = "stop_trading"         # 停止自动交易
    SET_RISK = "set_risk"                 # 设置风险参数
    QUERY_STATUS = "query_status"         # 查询状态
    CHAT = "chat"                         # 普通对话
    UNKNOWN = "unknown"                   # 未知指令


class PositionSide(Enum):
    """持仓方向"""
    LONG = "long"    # 做多
    SHORT = "short"  # 做空


@dataclass
class ParsedCommand:
    """解析后的指令"""
    command_type: CommandType
    symbol: Optional[str] = None
    side: Optional[PositionSide] = None
    quantity: Optional[float] = None
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_level: Optional[str] = None
    confidence: float = 0.8
    raw_input: str = ""


class AICommandParser:
    """
    AI 指令解析器
    
    功能：
    1. 将自然语言指令解析为结构化交易指令
    2. 支持多轮对话理解上下文
    3. 连接到交易流程
    """
    
    def __init__(self, llm_integration=None):
        """
        初始化指令解析器
        
        Args:
            llm_integration: LLM集成实例，用于智能解析
        """
        self.llm_integration = llm_integration
        
        # 关键词映射
        self.keywords = {
            "open": ["开仓", "买入", "做多", "开多", "做空", "开空", "建立仓位"],
            "close": ["平仓", "卖出", "平掉", "清仓", "关闭仓位"],
            "analyze": ["分析", "看看", "研究", "分析一下", "市场分析"],
            "start": ["开始", "启动", "开启", "开始交易"],
            "stop": ["停止", "暂停", "结束", "停止交易"],
            "query": ["查询", "看看", "状态", "持仓", "余额"],
            "risk": ["风险", "止损", "止盈", "设置"],
        }
        
        # 常用交易对
        self.symbols = {
            "btc": "BTC/USDT",
            "eth": "ETH/USDT",
            "sol": "SOL/USDT",
            "bnb": "BNB/USDT",
            "ada": "ADA/USDT",
            "比特币": "BTC/USDT",
            "以太坊": "ETH/USDT",
        }
        
        logger.info("AI指令解析器初始化完成")
    
    async def parse(self, user_input: str) -> ParsedCommand:
        """
        解析用户输入
        
        Args:
            user_input: 用户输入的自然语言
            
        Returns:
            ParsedCommand: 解析后的指令
        """
        logger.info(f"解析用户输入: {user_input}")
        
        # 先尝试基于规则的快速解析
        command = self._rule_based_parse(user_input)
        
        # 如果规则解析是 UNKNOWN，或者置信度低，尝试用AI解析
        # 但如果规则解析已经是 CHAT，就不要覆盖它
        if (command.command_type == CommandType.UNKNOWN or command.confidence < 0.7) and self.llm_integration:
            ai_command = await self._ai_parse(user_input)
            # 只有当AI解析结果不是UNKNOWN，且置信度更高时，才使用AI解析结果
            if (ai_command.command_type != CommandType.UNKNOWN and 
                ai_command.confidence > command.confidence):
                command = ai_command
        
        # 最终兜底：如果还是UNKNOWN，默认设为CHAT
        if command.command_type == CommandType.UNKNOWN:
            command.command_type = CommandType.CHAT
            command.confidence = 0.5
        
        logger.info(f"解析结果: type={command.command_type.value}, "
                   f"symbol={command.symbol}, side={command.side}, "
                   f"confidence={command.confidence:.2f}")
        
        return command
    
    def _rule_based_parse(self, user_input: str) -> ParsedCommand:
        """基于规则的快速解析"""
        input_lower = user_input.lower()
        command = ParsedCommand(
            command_type=CommandType.UNKNOWN,
            raw_input=user_input
        )
        
        # 检测交易对
        for keyword, symbol in self.symbols.items():
            if keyword in input_lower:
                command.symbol = symbol
                break
        
        # 检测方向
        if "多" in user_input or "做多" in user_input or "买" in user_input:
            command.side = PositionSide.LONG
        elif "空" in user_input or "做空" in user_input or "卖" in user_input:
            command.side = PositionSide.SHORT
        
        # 检测指令类型
        for keyword in self.keywords["open"]:
            if keyword in user_input:
                command.command_type = CommandType.OPEN_POSITION
                command.confidence = 0.8
                break
        
        if command.command_type == CommandType.UNKNOWN:
            for keyword in self.keywords["close"]:
                if keyword in user_input:
                    command.command_type = CommandType.CLOSE_POSITION
                    command.confidence = 0.8
                    break
        
        if command.command_type == CommandType.UNKNOWN:
            for keyword in self.keywords["analyze"]:
                if keyword in user_input:
                    command.command_type = CommandType.ANALYZE_MARKET
                    command.confidence = 0.8
                    break
        
        if command.command_type == CommandType.UNKNOWN:
            for keyword in self.keywords["start"]:
                if keyword in user_input:
                    command.command_type = CommandType.START_TRADING
                    command.confidence = 0.8
                    break
        
        if command.command_type == CommandType.UNKNOWN:
            for keyword in self.keywords["stop"]:
                if keyword in user_input:
                    command.command_type = CommandType.STOP_TRADING
                    command.confidence = 0.8
                    break
        
        if command.command_type == CommandType.UNKNOWN:
            for keyword in self.keywords["query"]:
                if keyword in user_input:
                    command.command_type = CommandType.QUERY_STATUS
                    command.confidence = 0.7
                    break
        
        # 如果没有识别到特定指令，默认为普通对话
        if command.command_type == CommandType.UNKNOWN:
            command.command_type = CommandType.CHAT
            command.confidence = 0.6
        
        return command
    
    async def _ai_parse(self, user_input: str) -> ParsedCommand:
        """使用AI进行智能解析"""
        command = ParsedCommand(
            command_type=CommandType.UNKNOWN,
            raw_input=user_input
        )
        
        if not self.llm_integration:
            return command
        
        try:
            prompt = f"""请解析以下用户输入，判断用户想要执行什么操作。

用户输入: {user_input}

请判断：
1. 指令类型（可选：open_position-开仓, close_position-平仓, analyze_market-分析市场, 
   start_trading-开始自动交易, stop_trading-停止自动交易, query_status-查询状态, chat-普通对话）
2. 交易对（如 BTC/USDT, ETH/USDT 等）
3. 方向（long-做多, short-做空）
4. 置信度（0-1之间的数字）

请以JSON格式返回，格式如下：
{{
  "command_type": "open_position",
  "symbol": "BTC/USDT",
  "side": "long",
  "confidence": 0.9
}}"""
            
            response = await self.llm_integration.generate(prompt)
            
            if response.success:
                # 尝试解析AI返回的JSON
                import json
                try:
                    result = json.loads(response.content)
                    
                    command_type = CommandType(result.get("command_type", "chat"))
                    command.command_type = command_type
                    command.symbol = result.get("symbol")
                    
                    side_str = result.get("side")
                    if side_str == "long":
                        command.side = PositionSide.LONG
                    elif side_str == "short":
                        command.side = PositionSide.SHORT
                    
                    command.confidence = float(result.get("confidence", 0.5))
                    
                except Exception as e:
                    logger.warning(f"AI解析结果JSON解析失败: {e}")
            
        except Exception as e:
            logger.warning(f"AI智能解析失败: {e}")
        
        return command
    
    def format_response(self, command: ParsedCommand) -> str:
        """格式化AI响应"""
        if command.command_type == CommandType.CHAT:
            return None  # 让普通对话走正常流程
        
        responses = {
            CommandType.OPEN_POSITION: 
                f"好的！我马上为您分析{command.symbol or '市场'}并执行开仓操作。\n"
                f"让我先采集市场数据，进行AI分析，然后执行交易...",
            
            CommandType.CLOSE_POSITION:
                f"好的！我马上为您平掉{command.symbol or '当前'}的仓位。\n"
                f"让我先检查当前持仓，然后执行平仓...",
            
            CommandType.ANALYZE_MARKET:
                f"好的！我马上为您分析{command.symbol or '市场'}。\n"
                f"让我采集最新的市场数据，进行深度分析...",
            
            CommandType.START_TRADING:
                "好的！我现在启动全智能自动交易系统。\n"
                "系统将自动：采集数据 → AI分析 → 智能决策 → 自动执行 → 实时监控",
            
            CommandType.STOP_TRADING:
                "好的！我现在停止自动交易系统。\n"
                "系统将停止自动交易，但会继续监控当前持仓。",
            
            CommandType.QUERY_STATUS:
                "好的！让我为您查询当前状态...",
            
            CommandType.SET_RISK:
                "好的！我来为您设置风险参数...",
        }
        
        return responses.get(command.command_type, "好的，我明白了！")
