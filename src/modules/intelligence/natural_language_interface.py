"""
自然语言接口 - 支持情感智能、技能包和主动关怀

功能：
1. 自然语言命令识别
2. 情感智能集成
3. 人格文件加载
4. 主动关怀系统
5. 技能包集成
6. 记忆系统集成
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List

from src.modules.core.llm_integration import EnhancedLLMIntegration

try:
    from src.modules.core.emotional_intelligence import EmotionalIntelligence, UserEmotion
    from src.modules.core.proactive_care import ProactiveCareSystem
    from src.modules.core.personality_config import get_personality_summary, CONVERSATION_TEMPLATES
    EMOTIONAL_ENABLED = True
except ImportError as e:
    EMOTIONAL_ENABLED = False
    UserEmotion = None
    logging.warning(f"情感智能模块导入失败: {e}")

try:
    from src.modules.skills.skill_manager import SkillManager
    SKILL_ENABLED = True
except ImportError as e:
    SKILL_ENABLED = False
    logging.warning(f"技能包模块导入失败: {e}")

logger = logging.getLogger(__name__)


class NaturalLanguageInterface:
    def __init__(self, llm_integration: EnhancedLLMIntegration, main_controller=None):
        self.llm_integration = llm_integration
        self.main_controller = main_controller
        self.system_prompt = "你是一个专业的量化交易助手。"
        
        self.command_templates = {
            "get_system_status": {
                "description": "获取系统状态",
                "keywords": ["系统状态", "运行状态", "健康状态", "系统信息"],
                "function": "get_system_status"
            },
            "get_strategy_performance": {
                "description": "获取策略性能",
                "keywords": ["策略性能", "策略表现", "收益情况", "策略统计"],
                "function": "get_strategy_performance"
            },
            "analyze_market": {
                "description": "分析市场",
                "keywords": ["市场分析", "行情分析", "市场趋势", "市场预测"],
                "function": "analyze_market"
            },
            "generate_strategy": {
                "description": "生成策略",
                "keywords": ["生成策略", "创建策略", "推荐策略", "策略建议"],
                "function": "generate_strategy"
            },
            "evaluate_strategy": {
                "description": "评估策略",
                "keywords": ["评估策略", "策略评价", "策略分析", "策略指标"],
                "function": "evaluate_strategy"
            },
            "run_backtest": {
                "description": "运行回测",
                "keywords": ["回测", "历史测试", "模拟测试", "回测结果"],
                "function": "run_backtest"
            },
            "get_market_data": {
                "description": "获取市场数据",
                "keywords": ["市场数据", "行情数据", "价格数据", "K线数据"],
                "function": "get_market_data"
            },
            "get_portfolio_analysis": {
                "description": "获取投资组合分析",
                "keywords": ["投资组合", "资产配置", "组合分析", "风险分析"],
                "function": "get_portfolio_analysis"
            },
            "optimize_parameters": {
                "description": "优化策略参数",
                "keywords": ["参数优化", "调优", "优化参数", "参数调整"],
                "function": "optimize_parameters"
            },
            "get_alert_history": {
                "description": "获取告警历史",
                "keywords": ["告警历史", "预警记录", "异常记录", "告警信息"],
                "function": "get_alert_history"
            },
            "diagnose_system": {
                "description": "诊断系统问题",
                "keywords": ["诊断", "检查问题", "系统诊断", "故障排查"],
                "function": "diagnose_system",
                "use_skill": True,
                "skill_name": "system_diagnosis"
            },
            "repair_system": {
                "description": "自动修复系统",
                "keywords": ["修复", "自动修复", "修好", "解决问题"],
                "function": "repair_system",
                "use_skill": True,
                "skill_name": "auto_repair"
            },
            "optimize_system": {
                "description": "优化系统性能",
                "keywords": ["优化系统", "性能优化", "系统优化"],
                "function": "optimize_system",
                "use_skill": True,
                "skill_name": "optimization"
            },
            "write_code": {
                "description": "编写代码",
                "keywords": ["写代码", "编写", "开发", "实现功能"],
                "function": "write_code",
                "use_skill": True,
                "skill_name": "code_developer"
            },
            "review_code": {
                "description": "代码审查",
                "keywords": ["代码审查", "检查代码", "代码review"],
                "function": "review_code",
                "use_skill": True,
                "skill_name": "code_reviewer"
            },
            "search_web": {
                "description": "搜索网络",
                "keywords": ["搜索", "查一下", "搜索网络", "网上查"],
                "function": "search_web",
                "use_skill": True,
                "skill_name": "web_search"
            },
            "self_learn": {
                "description": "自主学习",
                "keywords": ["学习", "自主学习", "提升", "改进自己"],
                "function": "self_learn",
                "use_skill": True,
                "skill_name": "self_learning"
            }
        }
        
        self._load_personality_files()
        
        self.skill_manager = None
        if SKILL_ENABLED and main_controller:
            self.skill_manager = getattr(main_controller, 'skill_manager', None)
            if self.skill_manager:
                logger.info(f"✅ 技能管理器已连接 - {len(self.skill_manager.skills)} 个技能可用")
        
        if EMOTIONAL_ENABLED:
            self.emotional_intelligence = EmotionalIntelligence()
            self.proactive_care = ProactiveCareSystem(main_controller)
            logger.info("✅ 情感智能和主动关怀系统已初始化")
        else:
            self.emotional_intelligence = None
            self.proactive_care = None
            logger.warning("⚠️ 情感智能模块未加载")
        
        self.memory = None
    
    async def _ensure_memory_initialized(self):
        if self.memory is None:
            if self.main_controller and hasattr(self.main_controller, "ai_memory_manager"):
                self.memory = self.main_controller.ai_memory_manager
                if self.memory is not None:
                    logger.info("✅ 记忆系统已连接到自然语言接口（主控制器核心记忆）")
                    return
            try:
                from src.modules.core.unified_intelligent_memory import get_unified_memory
                self.memory = await get_unified_memory()
                logger.info("✅ 记忆系统已连接到自然语言接口")
            except Exception as e:
                logger.warning(f"记忆系统连接失败: {e}")
    
    def _load_personality_files(self):
        personality_parts = []
        
        personality_files = [
            "workspace/SOUL.md",
            "workspace/IDENTITY.md", 
            "workspace/USER.md",
            "workspace/TRADING.md"
        ]
        
        cm = getattr(self, "config_manager", None)
        base_path = (
            cm.get_path_sync("trading_path", None) if cm else None
        ) or "/app"
        
        for file_path in personality_files:
            full_path = os.path.join(base_path, file_path)
            try:
                if os.path.exists(full_path):
                    with open(full_path, 'r', encoding='utf-8') as f:
                        content_text = f.read()
                        personality_parts.append(f"\n### {file_path}\n{content_text}")
                        logger.info(f"✅ 加载人格文件: {file_path}")
            except Exception as e:
                logger.warning(f"⚠️ 加载人格文件失败: {file_path} - {e}")
        
        if personality_parts:
            self.system_prompt = "\n\n".join(personality_parts)
            logger.info(f"✅ 系统提示词已更新，长度: {len(self.system_prompt)} 字符")
        else:
            self.system_prompt = "你是一个专业的量化交易助手，名叫小智。你专业、友善、有同理心。"
            logger.warning("⚠️ 未找到人格文件，使用默认提示词")
    
    def _get_personality_prompt(self) -> str:
        return self.system_prompt
    
    def _get_response_content(self, response) -> str:
        if hasattr(response, 'content'):
            return response.content
        elif isinstance(response, str):
            return response
        return str(response)
    
    def get_available_skills(self) -> List[str]:
        if self.skill_manager:
            return list(self.skill_manager.skills.keys())
        return []
    
    async def execute_skill(self, skill_name: str, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.skill_manager:
            logger.warning("技能管理器未初始化")
            return None
        
        skill = self.skill_manager.get_skill(skill_name)
        if not skill:
            logger.warning(f"技能不存在: {skill_name}")
            return None
        
        try:
            result = await self.skill_manager.execute_skill(skill_name, context)
            if result:
                return {
                    "success": result.status.value == "success",
                    "skill_name": skill_name,
                    "output": result.output,
                    "recommendations": result.recommendations,
                    "execution_time": result.execution_time
                }
        except Exception as e:
            logger.error(f"执行技能失败: {skill_name} - {e}")
            return {"success": False, "error": str(e)}
        
        return None
    
    async def process_query(self, query: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        try:
            if context is None:
                context = {}
            
            command = await self._identify_command(query)
            
            if command:
                command_info = self.command_templates.get(command, {})
                
                if command_info.get("use_skill") and command_info.get("skill_name"):
                    skill_result = await self.execute_skill(command_info["skill_name"], {
                        **context,
                        "query": query,
                        "command": command
                    })
                    if skill_result:
                        return skill_result
                
                result = await self._execute_command(command, query, context)
                return result
            else:
                return await self._general_qa(query, context)
        except Exception as e:
            logger.error(f"处理自然语言查询时出错: {e}")
            return {
                "error": str(e),
                "message": "处理查询时发生错误"
            }
    
    async def _identify_command(self, query: str) -> Optional[str]:
        query_lower = query.lower()
        
        for cmd, info in self.command_templates.items():
            for keyword in info.get("keywords", []):
                if keyword in query_lower:
                    return cmd
        
        prompt = f"""请从以下命令中识别用户查询 '{query}' 对应的命令：

可用命令：
{chr(10).join([f"- {cmd}: {info['description']}" for cmd, info in self.command_templates.items()])}

如果没有匹配的命令，请返回 'unknown'。

只返回命令名称，不要返回其他内容。"""
        
        response = await self.llm_integration.generate(prompt)
        content = self._get_response_content(response)
        command = content.strip() if response and hasattr(response, 'success') and response.success else 'unknown'
        
        if command not in self.command_templates and command != 'unknown':
            command = 'unknown'
        
        logger.debug(f"识别命令: {query} -> {command}")
        return command
    
    async def _execute_command(self, command: str, query: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        if command not in self.command_templates:
            return {
                "error": "命令不存在",
                "message": f"未知命令: {command}"
            }
        
        params = await self._extract_parameters(command, query, context)
        
        prompt = f"""请执行以下命令并返回结果：

命令: {command}
描述: {self.command_templates[command]['description']}
参数: {json.dumps(params, ensure_ascii=False)}

请以JSON格式返回执行结果，包含以下字段：
- success: 是否成功
- data: 执行结果数据
- message: 执行消息
- details: 详细信息（可选）"""
        
        response = await self.llm_integration.generate(prompt)
        content = self._get_response_content(response)
        
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            result = {
                "success": False,
                "data": None,
                "message": "命令执行失败",
                "details": f"无法解析命令执行结果: {content}"
            }
        
        return result
    
    async def _extract_parameters(self, command: str, query: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        prompt = f'''请从查询 '{query}' 中提取命令 '{command}' 的参数：

命令描述: {self.command_templates[command]['description']}

请以JSON格式返回提取的参数，只返回参数，不要返回其他内容。
如果没有参数，请返回空对象 {{}}。'''
        
        response = await self.llm_integration.generate(prompt)
        content = self._get_response_content(response)
        
        try:
            params = json.loads(content)
        except json.JSONDecodeError:
            params = {}
        
        return params
    
    async def _general_qa(self, query: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        user_emotion = UserEmotion.NEUTRAL if UserEmotion else None
        emotion_confidence = 0.0
        
        if self.emotional_intelligence and UserEmotion:
            user_emotion, emotion_confidence = self.emotional_intelligence.detect_emotion(query)
            logger.info(f"检测到用户情绪: {user_emotion.value}, 置信度: {emotion_confidence:.2f}")
        
        await self._ensure_memory_initialized()
        
        memory_context = ""
        if self.memory:
            try:
                relevant_memories = await self.memory.retrieve_memories(
                    query=query,
                    limit=3
                )
                if relevant_memories:
                    memory_context = "\n\n相关记忆:\n" + "\n".join([
                        f"- {m.get('content', str(m))}" for m in relevant_memories
                    ])
            except Exception as e:
                logger.warning(f"检索记忆失败: {e}")
        
        personality_prompt = self._get_personality_prompt()
        
        prompt = f"""{personality_prompt}

{memory_context}

请回答用户的问题：

问题: {query}

请以JSON格式返回回答，包含以下字段：
- answer: 回答内容
- confidence: 置信度（0-1）
- source: 回答来源
- related_commands: 相关命令（可选）"""
        
        response = await self.llm_integration.generate(prompt)
        content = self._get_response_content(response)
        
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            result = {
                "answer": content,
                "confidence": 0.8,
                "source": "llm",
                "related_commands": []
            }
        
        if self.emotional_intelligence and user_emotion and UserEmotion:
            result["answer"] = self.emotional_intelligence.adapt_response(
                result.get("answer", ""), user_emotion
            )
            result["emotion_detected"] = user_emotion.value
            result["emotion_confidence"] = emotion_confidence
        
        if self.memory:
            try:
                await self.memory.store_memory(
                    content=f"用户问: {query}\n助手答: {result.get('answer', '')}",
                    memory_type="conversation"
                )
            except Exception as e:
                logger.warning(f"存储记忆失败: {e}")
        
        return result
    
    async def generate_response(self, result: Dict[str, Any], query: str) -> str:
        prompt = f"""请根据以下执行结果，生成一个自然友好的回答，回复用户的查询 '{query}'：

执行结果: {json.dumps(result, ensure_ascii=False)}

请直接返回回答内容，不要包含任何格式标记。"""
        
        response = await self.llm_integration.generate(prompt)
        return self._get_response_content(response)
    
    async def process_and_respond(self, query: str, context: Dict[str, Any] = None) -> str:
        result = await self.process_query(query, context)
        response = await self.generate_response(result, query)
        
        if self.proactive_care:
            self.proactive_care.record_user_message(query)
        
        return response
    
    def get_available_commands(self) -> Dict[str, Dict[str, Any]]:
        return self.command_templates
    
    def add_command(self, command_name: str, description: str, keywords: list, function: str) -> bool:
        if command_name in self.command_templates:
            return False
        
        self.command_templates[command_name] = {
            "description": description,
            "keywords": keywords,
            "function": function
        }
        return True
    
    def remove_command(self, command_name: str) -> bool:
        if command_name in self.command_templates:
            del self.command_templates[command_name]
            return True
        return False
