"""
AI 指令执行器 - 简化版：直接让AI自主处理
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class AICommandExecutor:
    """
    AI 指令执行器 - 简化版
    
    功能：
    1. 直接把用户输入给AI
    2. AI自己有记忆，自己决定如何响应
    3. 不需要复杂的指令解析
    """
    
    def __init__(self, main_controller=None):
        """
        初始化指令执行器
        
        Args:
            main_controller: 主控制器实例
        """
        self.main_controller = main_controller
        self.llm_integration = None
        self.memory_manager = None
        
        logger.info("AI指令执行器（简化版）初始化完成")
    
    async def initialize(self) -> None:
        """初始化指令执行器"""
        logger.info("初始化AI指令执行器（简化版）...")
        
        # 从主控制器获取组件
        if self.main_controller:
            if hasattr(self.main_controller, 'llm_integration'):
                self.llm_integration = self.main_controller.llm_integration
            
            if hasattr(self.main_controller, 'ai_memory_manager'):
                self.memory_manager = self.main_controller.ai_memory_manager
        
        logger.info("✅ AI指令执行器（简化版）初始化完成")
    
    async def process_input(self, user_input: str) -> Dict[str, Any]:
        """
        处理用户输入 - 直接让AI自主处理
        
        Args:
            user_input: 用户输入的自然语言
            
        Returns:
            处理结果
        """
        logger.info(f"处理用户输入: {user_input}")
        
        try:
            # 直接让AI对话处理，AI自己有记忆和判断能力
            if self.llm_integration:
                response = await self.llm_integration.generate(user_input)
                
                if response.success:
                    # 保存到记忆
                    if self.memory_manager:
                        await self.memory_manager.add_short_term_memory(
                            f"用户: {user_input}",
                            importance=0.7
                        )
                        await self.memory_manager.add_short_term_memory(
                            f"AI: {response.content[:300]}...",
                            importance=0.7
                        )
                    
                    return {
                        "success": True,
                        "response": response.content,
                        "model_id": response.model_id,
                        "tokens_used": response.tokens_used,
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    return {
                        "success": False,
                        "response": f"AI回答失败：{response.error_message}",
                        "timestamp": datetime.now().isoformat()
                    }
            else:
                return {
                    "success": False,
                    "response": "抱歉，AI服务暂时不可用。",
                    "timestamp": datetime.now().isoformat()
                }
            
        except Exception as e:
            logger.error(f"处理用户输入失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "response": f"抱歉，执行过程中出错了：{str(e)}",
                "timestamp": datetime.now().isoformat()
            }
