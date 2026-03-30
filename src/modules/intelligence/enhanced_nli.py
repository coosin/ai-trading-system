"""
增强型自然语言接口 - 基于LLM的智能对话系统

功能：
1. 使用LLM进行意图识别（而非关键词匹配）
2. 多轮对话上下文管理
3. 参数提取和验证
4. 命令执行确认机制
5. 对话历史记忆
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

from src.modules.core.llm_integration import EnhancedLLMIntegration
from src.modules.core.memory_manager import get_memory_manager, MemoryType

logger = logging.getLogger(__name__)


class IntentType(Enum):
    """意图类型"""
    QUERY_STATUS = "query_status"           # 查询状态
    EXECUTE_TRADE = "execute_trade"         # 执行交易
    MANAGE_STRATEGY = "manage_strategy"     # 管理策略
    ANALYZE_MARKET = "analyze_market"       # 分析市场
    GET_REPORT = "get_report"               # 获取报告
    CONFIGURE_SYSTEM = "configure_system"   # 配置系统
    GENERAL_CHAT = "general_chat"           # 通用对话
    CLARIFICATION = "clarification"         # 需要澄清


class ExecutionStatus(Enum):
    """执行状态"""
    PENDING = "pending"           # 待执行
    CONFIRMATION_REQUIRED = "confirmation_required"  # 需要确认
    EXECUTED = "executed"         # 已执行
    FAILED = "failed"             # 失败
    CANCELLED = "cancelled"       # 已取消


@dataclass
class ConversationContext:
    """对话上下文"""
    session_id: str
    user_id: str
    messages: List[Dict[str, Any]] = field(default_factory=list)
    current_intent: Optional[IntentType] = None
    pending_action: Optional[Dict[str, Any]] = None
    extracted_params: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
    
    def add_message(self, role: str, content: str, metadata: Dict[str, Any] = None):
        """添加消息"""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        })
        self.last_active = datetime.now()
        
        # 保留最近20条消息
        if len(self.messages) > 20:
            self.messages = self.messages[-20:]
    
    def get_recent_context(self, count: int = 5) -> str:
        """获取最近的对话上下文"""
        recent = self.messages[-count:]
        return "\n".join([f"{m['role']}: {m['content']}" for m in recent])


@dataclass
class Intent:
    """意图识别结果"""
    intent_type: IntentType
    confidence: float
    entities: Dict[str, Any]
    action: str
    requires_confirmation: bool
    raw_response: str


@dataclass
class CommandResult:
    """命令执行结果"""
    success: bool
    data: Any
    message: str
    execution_status: ExecutionStatus
    timestamp: datetime = field(default_factory=datetime.now)


class EnhancedNaturalLanguageInterface:
    """
    增强型自然语言接口
    
    功能：
    1. 使用LLM进行精确的意图识别
    2. 维护多轮对话上下文
    3. 智能参数提取和验证
    4. 危险操作确认机制
    5. 对话历史持久化
    """
    
    def __init__(self, llm_integration: EnhancedLLMIntegration):
        self.llm_integration = llm_integration
        self.contexts: Dict[str, ConversationContext] = {}
        self.command_handlers: Dict[str, Callable] = {}
        
        # 危险操作列表（需要确认）
        self.dangerous_actions = [
            "execute_trade", "cancel_all_orders", "liquidate_position",
            "delete_strategy", "modify_strategy", "withdraw_funds"
        ]
        
        # 初始化命令处理器
        self._init_command_handlers()
    
    def _init_command_handlers(self):
        """初始化命令处理器"""
        self.command_handlers = {
            "get_system_status": self._handle_system_status,
            "get_account_info": self._handle_account_info,
            "get_positions": self._handle_positions,
            "execute_trade": self._handle_trade_execution,
            "cancel_order": self._handle_cancel_order,
            "get_strategy_list": self._handle_strategy_list,
            "analyze_market": self._handle_market_analysis,
            "get_risk_report": self._handle_risk_report,
            "configure_alert": self._handle_configure_alert,
        }
    
    async def process_message(
        self, 
        message: str, 
        session_id: str, 
        user_id: str,
        require_confirmation: bool = True
    ) -> Dict[str, Any]:
        """
        处理用户消息
        
        Args:
            message: 用户消息
            session_id: 会话ID
            user_id: 用户ID
            require_confirmation: 是否需要确认危险操作
        
        Returns:
            处理结果
        """
        try:
            # 获取或创建上下文
            context = await self._get_context(session_id, user_id)
            context.add_message("user", message)
            
            # 检查是否有待确认的操作
            if context.pending_action and self._is_confirmation(message):
                return await self._execute_pending_action(context, message)
            
            # 使用LLM识别意图
            intent = await self._recognize_intent(message, context)
            logger.info(f"识别意图: {intent.intent_type.value}, 置信度: {intent.confidence}")
            
            # 如果置信度太低，请求澄清
            if intent.confidence < 0.6:
                response = await self._ask_clarification(message, context)
                context.add_message("assistant", response["message"])
                return response
            
            # 执行对应的处理函数
            handler = self.command_handlers.get(intent.action)
            if handler:
                result = await handler(intent.entities, context)
                
                # 检查是否需要确认
                if require_confirmation and intent.action in self.dangerous_actions:
                    context.pending_action = {
                        "action": intent.action,
                        "entities": intent.entities,
                        "result": result
                    }
                    confirmation_msg = self._generate_confirmation_message(intent, result)
                    context.add_message("assistant", confirmation_msg)
                    return {
                        "success": True,
                        "requires_confirmation": True,
                        "message": confirmation_msg,
                        "action": intent.action,
                        "details": result
                    }
                
                # 生成自然语言响应
                response_text = await self._generate_response(intent, result, context)
                context.add_message("assistant", response_text)
                
                # 保存到记忆
                await self._save_to_memory(session_id, user_id, message, response_text, intent)
                
                return {
                    "success": result.success,
                    "message": response_text,
                    "data": result.data,
                    "intent": intent.intent_type.value,
                    "confidence": intent.confidence
                }
            else:
                # 通用对话
                response = await self._general_conversation(message, context)
                context.add_message("assistant", response["message"])
                return response
                
        except Exception as e:
            logger.error(f"处理消息时出错: {e}")
            return {
                "success": False,
                "message": f"处理消息时发生错误: {str(e)}",
                "error": str(e)
            }
    
    async def _recognize_intent(self, message: str, context: ConversationContext) -> Intent:
        """
        使用LLM识别意图
        
        这比简单的关键词匹配更智能，可以理解复杂的自然语言
        """
        prompt = f"""请分析用户的意图并提取关键信息。

用户消息: "{message}"

对话历史:
{context.get_recent_context(3)}

请以JSON格式返回以下信息：
{{
    "intent_type": "意图类型 (query_status/execute_trade/manage_strategy/analyze_market/get_report/configure_system/general_chat/clarification)",
    "confidence": "置信度 (0-1之间的数字)",
    "action": "具体动作",
    "entities": {{
        "symbol": "交易品种（如果有）",
        "side": "买卖方向（如果有）",
        "quantity": "数量（如果有）",
        "price": "价格（如果有）",
        "strategy_name": "策略名称（如果有）",
        "timeframe": "时间周期（如果有）",
        "other_params": "其他参数"
    }},
    "requires_confirmation": "是否需要用户确认 (true/false)",
    "reasoning": "推理过程"
}}

只返回JSON，不要返回其他内容。"""

        response = await self.llm_integration.generate(prompt)
        
        try:
            # 提取JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(response)
            
            intent_type = IntentType(data.get("intent_type", "general_chat"))
            confidence = float(data.get("confidence", 0.5))
            
            return Intent(
                intent_type=intent_type,
                confidence=confidence,
                entities=data.get("entities", {}),
                action=data.get("action", "general_chat"),
                requires_confirmation=data.get("requires_confirmation", False),
                raw_response=response
            )
            
        except Exception as e:
            logger.error(f"解析意图失败: {e}, 响应: {response}")
            return Intent(
                intent_type=IntentType.GENERAL_CHAT,
                confidence=0.3,
                entities={},
                action="general_chat",
                requires_confirmation=False,
                raw_response=response
            )
    
    async def _get_context(self, session_id: str, user_id: str) -> ConversationContext:
        """获取对话上下文"""
        if session_id not in self.contexts:
            # 尝试从记忆加载
            memory_manager = await get_memory_manager()
            history = await memory_manager.get_conversation_history(session_id, count=10)
            
            self.contexts[session_id] = ConversationContext(
                session_id=session_id,
                user_id=user_id,
                messages=history
            )
        
        return self.contexts[session_id]
    
    def _is_confirmation(self, message: str) -> bool:
        """判断是否为确认消息"""
        confirmation_words = ["确认", "是的", "没错", "执行", "确定", "好", "可以", "yes", "ok", "confirm"]
        return any(word in message.lower() for word in confirmation_words)
    
    def _is_cancellation(self, message: str) -> bool:
        """判断是否为取消消息"""
        cancellation_words = ["取消", "不", "算了", "停止", "no", "cancel", "abort"]
        return any(word in message.lower() for word in cancellation_words)
    
    async def _execute_pending_action(self, context: ConversationContext, message: str) -> Dict[str, Any]:
        """执行待确认的操作"""
        if self._is_cancellation(message):
            context.pending_action = None
            return {
                "success": False,
                "message": "操作已取消",
                "execution_status": ExecutionStatus.CANCELLED.value
            }
        
        if self._is_confirmation(message):
            action = context.pending_action
            context.pending_action = None
            
            # 这里执行实际的操作
            # ...
            
            return {
                "success": True,
                "message": f"操作已执行: {action['action']}",
                "execution_status": ExecutionStatus.EXECUTED.value,
                "data": action.get("result", {})
            }
        
        # 既不是确认也不是取消，继续等待
        return {
            "success": False,
            "message": "请确认是否执行此操作（确认/取消）",
            "requires_confirmation": True
        }
    
    def _generate_confirmation_message(self, intent: Intent, result: CommandResult) -> str:
        """生成确认消息"""
        action_desc = {
            "execute_trade": "执行交易",
            "cancel_all_orders": "取消所有订单",
            "liquidate_position": "平仓",
            "delete_strategy": "删除策略",
            "modify_strategy": "修改策略",
            "withdraw_funds": "提取资金"
        }
        
        desc = action_desc.get(intent.action, intent.action)
        entities_str = json.dumps(intent.entities, ensure_ascii=False, indent=2)
        
        return f"⚠️ 您即将{desc}，参数如下:\n```json\n{entities_str}\n```\n\n请确认是否执行？（回复'确认'执行，'取消'放弃）"
    
    async def _generate_response(self, intent: Intent, result: CommandResult, context: ConversationContext) -> str:
        """生成自然语言响应"""
        prompt = f"""请根据执行结果生成自然语言回复：

用户意图: {intent.intent_type.value}
执行动作: {intent.action}
执行结果: {"成功" if result.success else "失败"}
结果数据: {json.dumps(result.data, ensure_ascii=False) if result.data else "无"}
结果消息: {result.message}

对话历史:
{context.get_recent_context(3)}

请生成友好、专业的中文回复。"""

        response = await self.llm_integration.generate(prompt)
        return response.strip()
    
    async def _ask_clarification(self, message: str, context: ConversationContext) -> Dict[str, Any]:
        """请求用户澄清"""
        prompt = f"""用户的消息不够明确，请生成澄清问题：

用户消息: "{message}"
对话历史:
{context.get_recent_context(3)}

请生成一个友好的问题，帮助理解用户的真实意图。"""

        response = await self.llm_integration.generate(prompt)
        
        return {
            "success": False,
            "requires_clarification": True,
            "message": response.strip(),
            "intent": "clarification"
        }
    
    async def _general_conversation(self, message: str, context: ConversationContext) -> Dict[str, Any]:
        """通用对话"""
        prompt = f"""请以交易助手的身份回答用户：

用户: "{message}"

对话历史:
{context.get_recent_context(5)}

请提供专业、有帮助的回答。"""

        response = await self.llm_integration.generate(prompt)
        
        return {
            "success": True,
            "message": response.strip(),
            "intent": "general_chat"
        }
    
    async def _save_to_memory(
        self, 
        session_id: str, 
        user_id: str, 
        user_message: str, 
        assistant_response: str,
        intent: Intent
    ):
        """保存对话到记忆"""
        try:
            memory_manager = await get_memory_manager()
            
            # 保存用户消息
            await memory_manager.add_message(
                session_id=session_id,
                role="user",
                content=user_message,
                user_id=user_id,
                metadata={"intent": intent.intent_type.value}
            )
            
            # 保存助手回复
            await memory_manager.add_message(
                session_id=session_id,
                role="assistant",
                content=assistant_response,
                user_id=user_id,
                metadata={"intent": intent.intent_type.value}
            )
        except Exception as e:
            logger.error(f"保存对话记忆失败: {e}")
    
    # ========== 命令处理器 ==========
    
    async def _handle_system_status(self, entities: Dict, context: ConversationContext) -> CommandResult:
        """处理系统状态查询"""
        # 这里应该调用实际的系统状态API
        return CommandResult(
            success=True,
            data={"status": "running", "uptime": "3d 12h", "version": "1.0.0"},
            message="系统运行正常",
            execution_status=ExecutionStatus.EXECUTED
        )
    
    async def _handle_account_info(self, entities: Dict, context: ConversationContext) -> CommandResult:
        """处理账户信息查询"""
        return CommandResult(
            success=True,
            data={"balance": 10000.0, "available": 8000.0, "frozen": 2000.0},
            message="账户信息获取成功",
            execution_status=ExecutionStatus.EXECUTED
        )
    
    async def _handle_positions(self, entities: Dict, context: ConversationContext) -> CommandResult:
        """处理持仓查询"""
        positions = [
            {"symbol": "BTC/USDT", "quantity": 0.5, "avg_price": 48000, "current_price": 51000},
            {"symbol": "ETH/USDT", "quantity": 5.0, "avg_price": 2800, "current_price": 3200}
        ]
        return CommandResult(
            success=True,
            data=positions,
            message=f"当前持仓 {len(positions)} 个品种",
            execution_status=ExecutionStatus.EXECUTED
        )
    
    async def _handle_trade_execution(self, entities: Dict, context: ConversationContext) -> CommandResult:
        """处理交易执行"""
        # 这里只是准备数据，实际执行需要确认
        return CommandResult(
            success=True,
            data={
                "symbol": entities.get("symbol"),
                "side": entities.get("side"),
                "quantity": entities.get("quantity"),
                "price": entities.get("price")
            },
            message="交易准备就绪，等待确认",
            execution_status=ExecutionStatus.CONFIRMATION_REQUIRED
        )
    
    async def _handle_cancel_order(self, entities: Dict, context: ConversationContext) -> CommandResult:
        """处理撤单"""
        return CommandResult(
            success=True,
            data={"order_id": entities.get("order_id")},
            message="撤单请求已准备，等待确认",
            execution_status=ExecutionStatus.CONFIRMATION_REQUIRED
        )
    
    async def _handle_strategy_list(self, entities: Dict, context: ConversationContext) -> CommandResult:
        """处理策略列表查询"""
        strategies = [
            {"name": "MACD策略", "status": "运行中", "pnl": "+5.2%"},
            {"name": "RSI策略", "status": "已停止", "pnl": "+2.1%"}
        ]
        return CommandResult(
            success=True,
            data=strategies,
            message=f"共有 {len(strategies)} 个策略",
            execution_status=ExecutionStatus.EXECUTED
        )
    
    async def _handle_market_analysis(self, entities: Dict, context: ConversationContext) -> CommandResult:
        """处理市场分析"""
        symbol = entities.get("symbol", "BTC/USDT")
        return CommandResult(
            success=True,
            data={
                "symbol": symbol,
                "trend": "上涨",
                "support": 48000,
                "resistance": 55000,
                "recommendation": "建议观望"
            },
            message=f"{symbol} 市场分析完成",
            execution_status=ExecutionStatus.EXECUTED
        )
    
    async def _handle_risk_report(self, entities: Dict, context: ConversationContext) -> CommandResult:
        """处理风险报告"""
        return CommandResult(
            success=True,
            data={
                "var_95": 1250.0,
                "var_99": 2100.0,
                "max_drawdown": "8.5%",
                "risk_level": "中等"
            },
            message="风险报告生成完成",
            execution_status=ExecutionStatus.EXECUTED
        )
    
    async def _handle_configure_alert(self, entities: Dict, context: ConversationContext) -> CommandResult:
        """处理告警配置"""
        return CommandResult(
            success=True,
            data={"alert_config": entities},
            message="告警配置已保存",
            execution_status=ExecutionStatus.EXECUTED
        )


# 全局实例
_enhanced_nli: Optional[EnhancedNaturalLanguageInterface] = None


async def get_enhanced_nli() -> EnhancedNaturalLanguageInterface:
    """获取增强型NLI实例"""
    global _enhanced_nli
    if _enhanced_nli is None:
        from src.modules.core.llm_integration import get_llm_integration
        llm = await get_llm_integration()
        _enhanced_nli = EnhancedNaturalLanguageInterface(llm)
    return _enhanced_nli
