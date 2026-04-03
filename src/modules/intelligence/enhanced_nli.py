"""
增强型自然语言接口 - 纯LLM智能对话系统

功能：
1. 使用LLM自由理解用户意图，无固定模式
2. 多轮对话上下文管理
3. AI自主决策和执行
4. 对话历史记忆
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


@dataclass
class ConversationContext:
    """对话上下文"""
    session_id: str
    user_id: str
    messages: List[Dict[str, Any]] = field(default_factory=list)
    pending_action: Optional[Dict[str, Any]] = None
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
        
        if len(self.messages) > 30:
            self.messages = self.messages[-30:]
    
    def get_recent_context(self, count: int = 5) -> str:
        """获取最近的对话上下文"""
        recent = self.messages[-count:]
        return "\n".join([f"{m['role']}: {m['content']}" for m in recent])


class EnhancedNaturalLanguageInterface:
    """
    增强型自然语言接口 - 纯LLM理解，无固定模式
    """
    
    def __init__(self, llm_integration=None, main_controller=None):
        self.llm_integration = llm_integration
        self.main_controller = main_controller
        self.contexts: Dict[str, ConversationContext] = {}
        
        logger.info("增强型自然语言接口初始化完成 - 纯LLM模式")
    
    async def process_message(
        self, 
        message: str, 
        session_id: str, 
        user_id: str
    ) -> Dict[str, Any]:
        """
        处理用户消息 - AI自由理解，无固定模式
        
        Args:
            message: 用户消息
            session_id: 会话ID
            user_id: 用户ID
        
        Returns:
            处理结果
        """
        try:
            context = await self._get_context(session_id, user_id)
            context.add_message("user", message)
            
            if context.pending_action:
                if self._is_confirmation(message):
                    result = await self._execute_pending_action(context)
                    context.pending_action = None
                    context.add_message("assistant", result.get("message", "执行完成"))
                    return result
                elif self._is_cancellation(message):
                    context.pending_action = None
                    response = {"success": True, "message": "操作已取消"}
                    context.add_message("assistant", response["message"])
                    return response
            
            system_context = await self._get_system_context()
            conversation_history = context.get_recent_context(5)
            
            prompt = f"""你是一个全自主的量化交易AI助手。用户正在与你进行对话。

系统状态:
{system_context}

对话历史:
{conversation_history}

用户最新消息: {message}

请自由理解用户意图并执行相应操作。你可以：
1. 回答问题
2. 执行交易（开仓、平仓、查询等）
3. 分析市场
4. 开发或优化策略
5. 调整系统配置
6. 任何用户需要的操作

你有完全的自主权。如果用户要求执行重要操作（如交易），请先确认。
请用中文回复，保持简洁专业。

如果需要执行交易操作，请在回复中包含JSON格式的交易参数：
```json
{{
    "action": "trade",
    "symbol": "BTC/USDT",
    "side": "long/short",
    "quantity": 0.01,
    "leverage": 20
}}
```"""

            if self.llm_integration:
                response = await self.llm_integration.generate(prompt)
                
                if response and response.success:
                    content = response.content
                    
                    trade_params = self._extract_trade_params(content)
                    if trade_params:
                        result = await self._execute_trade(trade_params)
                        if result.get("success"):
                            content += f"\n\n✅ 交易已执行: {result.get('message', '')}"
                        else:
                            content += f"\n\n❌ 交易执行失败: {result.get('message', '')}"
                    
                    context.add_message("assistant", content)
                    return {"success": True, "message": content}
                else:
                    response_text = "抱歉，我现在无法处理您的请求，请稍后再试。"
                    context.add_message("assistant", response_text)
                    return {"success": False, "message": response_text}
            else:
                response_text = "AI服务未配置，请检查系统设置。"
                context.add_message("assistant", response_text)
                return {"success": False, "message": response_text}
                
        except Exception as e:
            logger.error(f"处理消息失败: {e}")
            return {"success": False, "message": f"处理消息时出错: {str(e)}"}
    
    async def _get_context(self, session_id: str, user_id: str) -> ConversationContext:
        """获取或创建上下文"""
        key = f"{session_id}_{user_id}"
        if key not in self.contexts:
            self.contexts[key] = ConversationContext(
                session_id=session_id,
                user_id=user_id
            )
        return self.contexts[key]
    
    async def _get_system_context(self) -> str:
        """获取系统上下文"""
        context_parts = [
            "- 模式: 实盘交易",
            "- 交易类型: 永续合约",
            "- 杠杆: 10-50倍",
            "- 黑名单: ETH/USDT"
        ]
        
        if self.main_controller:
            mc = self.main_controller
            
            if hasattr(mc, 'ai_trading_engine') and mc.ai_trading_engine:
                engine = mc.ai_trading_engine
                positions = getattr(engine, 'positions', {})
                context_parts.append(f"- 当前持仓: {len(positions)}个")
            
            if hasattr(mc, 'okx_exchange') and mc.okx_exchange:
                context_parts.append("- 交易所: OKX (已连接)")
        
        return "\n".join(context_parts)
    
    def _is_confirmation(self, message: str) -> bool:
        """检查是否是确认"""
        confirm_words = ["确认", "是的", "对", "好", "执行", "yes", "ok", "确定"]
        return any(word in message.lower() for word in confirm_words)
    
    def _is_cancellation(self, message: str) -> bool:
        """检查是否是取消"""
        cancel_words = ["取消", "不", "算了", "不要", "no", "cancel"]
        return any(word in message.lower() for word in cancel_words)
    
    async def _execute_pending_action(self, context: ConversationContext) -> Dict[str, Any]:
        """执行待执行的操作"""
        if not context.pending_action:
            return {"success": False, "message": "没有待执行的操作"}
        
        action = context.pending_action
        if action.get("type") == "trade":
            return await self._execute_trade(action.get("params", {}))
        
        return {"success": True, "message": "操作已执行"}
    
    def _extract_trade_params(self, content: str) -> Optional[Dict[str, Any]]:
        """从回复中提取交易参数"""
        try:
            import re
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
        except Exception:
            pass
        return None
    
    async def _execute_trade(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行交易"""
        try:
            if not self.main_controller:
                return {"success": False, "message": "系统未初始化"}
            
            symbol = params.get("symbol", "BTC/USDT")
            side = params.get("side", "long")
            quantity = params.get("quantity", 0.01)
            leverage = params.get("leverage", 20)
            
            if hasattr(self.main_controller, 'okx_exchange'):
                okx = self.main_controller.okx_exchange
                
                if hasattr(okx, 'open_swap_position'):
                    result = await okx.open_swap_position(
                        symbol=symbol,
                        side=side,
                        size=quantity,
                        leverage=leverage
                    )
                    return {
                        "success": result.get("success", False),
                        "message": f"{symbol} {side} {quantity} @ {leverage}x"
                    }
            
            return {"success": False, "message": "交易所未连接"}
            
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    async def cleanup(self):
        """清理资源"""
        self.contexts.clear()
        logger.info("自然语言接口已清理")
