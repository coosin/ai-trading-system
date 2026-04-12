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
import re
import uuid
from datetime import datetime
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
    def __init__(
        self,
        llm_integration: EnhancedLLMIntegration,
        main_controller=None,
        config_manager=None,
    ):
        self.llm_integration = llm_integration
        self.main_controller = main_controller
        self.config_manager = config_manager or (
            getattr(main_controller, "config_manager", None) if main_controller else None
        )
        self.system_prompt = "你是一个专业的量化交易助手。"
        self.session_id = f"nli:{uuid.uuid4()}"
        self._session_history: List[Dict[str, str]] = []
        self._turn_counter = 0
        self._market_context_last_turn = -999
        self._market_context_last_at: Optional[datetime] = None
        
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
            ,
            "update_config": {
                "description": "更新系统配置（支持通知/心跳/研究门控等）",
                "keywords": ["配置", "改配置", "更新配置", "修改配置", "通知频率", "通知", "心跳", "研究门控", "阈值", "冷却", "限流"],
                "function": "update_config"
            },
            "learn_memory_filter": {
                "description": "学习记忆过滤规则（把低价值/垃圾信息加入过滤）",
                "keywords": ["垃圾信息", "别记忆", "不要记住", "不需要记忆", "加入过滤", "过滤这类", "这类别存"],
                "function": "learn_memory_filter",
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
            # Prefer unified MemoryGateway if available.
            if self.main_controller and hasattr(self.main_controller, "memory_gateway"):
                mg = getattr(self.main_controller, "memory_gateway", None)
                if mg is not None:
                    self.memory = mg
                    logger.info("✅ 记忆系统已连接到自然语言接口（MemoryGateway）")
                    return
            if self.main_controller and hasattr(self.main_controller, "ai_memory_manager"):
                self.memory = self.main_controller.ai_memory_manager
                if self.memory is not None:
                    logger.info("✅ 记忆系统已连接到自然语言接口（主控制器核心记忆）")
                    return
            # 单一真源：不再 fallback 到并行记忆实现
            logger.warning("⚠️ MemoryGateway 未就绪：自然语言接口将以无记忆模式运行")
    
    def _load_personality_files(self):
        personality_parts = []
        
        # 合并为一套 system_prompt：仅保留单一人格/规则入口。
        personality_files = [
            "workspace/COMMANDER_PROFILE.md",
        ]
        
        cm = getattr(self, "config_manager", None)
        base_path = "/app"
        if cm is not None:
            try:
                if hasattr(cm, "get_path_sync"):
                    base_path = cm.get_path_sync("trading_path", None) or base_path
                elif hasattr(cm, "get_config_sync"):
                    base_path = cm.get_config_sync("paths", "trading_path", base_path) or base_path
            except Exception:
                base_path = "/app"
        
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

    def _parse_json_loose(self, raw: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """尽量从LLM文本中提取JSON（支持```json代码块/前后缀文本）。"""
        text = str(raw or "").strip()
        if not text:
            return default or {}
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else (default or {})
        except json.JSONDecodeError:
            pass

        fence = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, flags=re.IGNORECASE)
        if fence:
            candidate = fence.group(1).strip()
            try:
                parsed = json.loads(candidate)
                return parsed if isinstance(parsed, dict) else (default or {})
            except json.JSONDecodeError:
                pass

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end + 1]
            try:
                parsed = json.loads(candidate)
                return parsed if isinstance(parsed, dict) else (default or {})
            except json.JSONDecodeError:
                pass

        return default or {}
    
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
            self._turn_counter += 1
            q_text = str(query or "")
            q_lower = q_text.lower()

            # Direct intent: user explicitly teaches what should not be stored in memory.
            memory_filter_result = await self._try_handle_memory_filter_learning(query)
            if memory_filter_result is not None:
                return memory_filter_result

            # 直连执行验证查询，避免LLM命令识别不稳定导致“unknown”
            if self.main_controller and (
                "最近执行" in q_text
                or ("执行" in q_text and ("记录" in q_text or "历史" in q_text))
                or "failed execution" in q_lower
            ):
                return await self.main_controller.query_execution_status(q_text)

            self._session_history.append({"role": "user", "content": str(query)})
            if len(self._session_history) > 20:
                self._session_history = self._session_history[-20:]
            
            command = await self._identify_command(query)
            
            # "unknown" 应走通用问答，而非按命令执行（否则无匹配模板会得到错误结构）
            if command and command != "unknown":
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
                # store assistant side in session buffer for continuity even if recall fails
                try:
                    if isinstance(result, dict):
                        msg = result.get("message") or (result.get("data") and str(result.get("data"))) or ""
                        if msg:
                            self._session_history.append({"role": "assistant", "content": str(msg)[:800]})
                except Exception:
                    pass
                return result
            else:
                result = await self._general_qa(query, context)
                try:
                    if isinstance(result, dict) and result.get("answer"):
                        self._session_history.append({"role": "assistant", "content": str(result["answer"])[:800]})
                except Exception:
                    pass
                return result
        except Exception as e:
            logger.error(f"处理自然语言查询时出错: {e}")
            return {
                "error": str(e),
                "message": "处理查询时发生错误"
            }

    async def _try_handle_memory_filter_learning(self, query: str) -> Optional[Dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return None
        lowered = q.lower()
        markers = ["垃圾", "别记忆", "不要记住", "不需要记忆", "过滤这类", "这类别存", "low value", "noise"]
        if not any(m in lowered for m in markers):
            return None
        return await self._execute_memory_filter_learning(query)

    async def _execute_memory_filter_learning(self, query: str) -> Dict[str, Any]:
        if not self.main_controller or not getattr(self.main_controller, "config_manager", None):
            return {"success": False, "message": "配置管理器不可用", "data": None}
        cm = self.main_controller.config_manager

        # Extract candidate phrase after trigger words; fallback to full query.
        fragment = self._extract_filter_fragment(query)
        if not fragment:
            fragment = query.strip()

        policy = cm.get_config_path_sync("memory.auto_capture.policy", {}) or {}
        if not isinstance(policy, dict):
            policy = {}
        deny_contains = list(policy.get("deny_content_contains", []) or [])
        if fragment not in deny_contains:
            deny_contains.append(fragment)
        policy["deny_content_contains"] = deny_contains

        ok = await cm.set_config_path("memory.auto_capture.policy", policy, validate=False)
        if not ok:
            return {"success": False, "message": "更新过滤策略失败", "data": {"fragment": fragment}}

        # audit + memory record
        try:
            if hasattr(self.main_controller, "log_audit_event"):
                from src.modules.core.audit_logger import AuditEventType, AuditSeverity
                await self.main_controller.log_audit_event(
                    event_type=AuditEventType.CONFIG_CHANGE,
                    severity=AuditSeverity.INFO,
                    action="learn_memory_filter",
                    details={"query": query, "fragment": fragment},
                    source="natural_language_interface",
                )
        except Exception:
            pass

        return {
            "success": True,
            "message": f"已学习过滤规则：后续包含“{fragment}”的内容将优先不入记忆",
            "data": {"fragment": fragment, "path": "memory.auto_capture.policy.deny_content_contains"},
        }

    def _extract_filter_fragment(self, query: str) -> str:
        q = (query or "").strip()
        patterns = [
            r"(?:这类|这种|像这种|把|将)?(.+?)(?:不要记住|别记忆|不需要记忆|加入过滤|过滤掉)",
            r"(?:过滤|屏蔽)(.+)",
        ]
        for p in patterns:
            m = re.search(p, q)
            if m:
                frag = (m.group(1) or "").strip(" ，。,:：")
                if frag:
                    return frag[:80]
        return ""
    
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
        content = (self._get_response_content(response) or "").strip()
        # 兼容单元测试 Mock / 纯字符串返回；仅有显式 success=False 时视为 unknown
        if response is not None and hasattr(response, "success") and getattr(response, "success") is False:
            command = "unknown"
        else:
            command = content or "unknown"

        if command not in self.command_templates and command != "unknown":
            command = "unknown"
        
        logger.debug(f"识别命令: {query} -> {command}")
        return command
    
    async def _execute_command(self, command: str, query: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        if command not in self.command_templates:
            return {
                "error": "命令不存在",
                "message": f"未知命令: {command}"
            }
        
        params = await self._extract_parameters(command, query, context)
        if command == "update_config":
            return await self._execute_update_config(query=query, params=params)
        
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
        
        result = self._parse_json_loose(content)
        if not result:
            result = {
                "success": False,
                "data": None,
                "message": "命令执行失败",
                "details": f"无法解析命令执行结果: {content}"
            }
        
        return result

    async def _execute_update_config(self, query: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply natural-language config changes through ConfigManager.

        Expected params format (LLM extracted):
        {
          "changes": [
            {"path": "notifications.smart.dedup_windows_sec.high", "value": 1200, "reason": "..."},
            {"path": "heartbeat.interval_sec", "value": 900}
          ]
        }
        """
        if not self.main_controller or not getattr(self.main_controller, "config_manager", None):
            return {"success": False, "data": None, "message": "配置管理器不可用"}
        cm = self.main_controller.config_manager

        # Looser by default, but still block obvious secrets/paths.
        allowed_prefixes = (
            "notifications.",
            "heartbeat.",
            "research.",
            "controller.",
            "ai_trading.",
            "proactive_ai.",
            "api.",
            "memory.",
        )
        denied_fragments = (
            "api_key",
            "secret",
            "token",
            "password",
            "private_key",
            "paths.",
            ".env",
        )
        changes = params.get("changes", [])
        if not isinstance(changes, list):
            changes = []

        applied = []
        rejected = []
        for ch in changes:
            if not isinstance(ch, dict):
                continue
            path = str(ch.get("path") or "").strip()
            if not path or not any(path.startswith(p) for p in allowed_prefixes):
                rejected.append({"path": path, "reason": "path_not_allowed"})
                continue
            lowered = path.lower()
            if any(d in lowered for d in denied_fragments):
                rejected.append({"path": path, "reason": "path_denied_sensitive"})
                continue
            value = ch.get("value")
            ok = await cm.set_config_path(path, value, validate=False)
            if ok:
                applied.append({"path": path, "value": value, "reason": ch.get("reason")})
            else:
                rejected.append({"path": path, "reason": "apply_failed"})

        # audit + memory
        try:
            if hasattr(self.main_controller, "log_audit_event"):
                from src.modules.core.audit_logger import AuditEventType, AuditSeverity

                await self.main_controller.log_audit_event(
                    event_type=AuditEventType.CONFIG_CHANGE,
                    severity=AuditSeverity.INFO,
                    action="nl_update_config",
                    details={"query": query, "applied": applied, "rejected": rejected},
                    source="natural_language_interface",
                )
        except Exception:
            pass
        try:
            if hasattr(self.main_controller, "memory_gateway") and self.main_controller.memory_gateway:
                await self.main_controller.memory_gateway.add_memory(
                    memory_type="config",
                    content=f"自然语言配置变更: {query}",
                    metadata={"applied": applied, "rejected": rejected},
                    source_module="natural_language_interface",
                    importance=0.7,
                    tags=["config", "nl"],
                )
        except Exception:
            pass

        return {
            "success": len(applied) > 0,
            "data": {"applied": applied, "rejected": rejected},
            "message": f"已应用 {len(applied)} 项配置变更，拒绝 {len(rejected)} 项",
        }
    
    async def _extract_parameters(self, command: str, query: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        if command == "update_config":
            prompt = f'''你将从用户的自然语言中提取“配置变更”参数。

用户话术: "{query}"

请只输出 JSON，格式如下：
{{
  "changes": [
    {{"path": "notifications.smart.dedup_windows_sec.high", "value": 1200, "reason": "将高优先级去重窗口改成20分钟"}},
    {{"path": "heartbeat.interval_sec", "value": 900}}
  ]
}}

约束：
- 只能输出上述 JSON（不要 Markdown、不要解释）
- path 必须使用点号路径，优先使用这些前缀：notifications., heartbeat., research., controller.health_check_interval
- value 用秒/数值，时间类都转换成“秒”
'''
        else:
            prompt = f'''请从查询 '{query}' 中提取命令 '{command}' 的参数：

命令描述: {self.command_templates[command]['description']}

请以JSON格式返回提取的参数，只返回参数，不要返回其他内容。
如果没有参数，请返回空对象 {{}}。'''
        
        response = await self.llm_integration.generate(prompt)
        content = self._get_response_content(response)
        
        params = self._parse_json_loose(content, default={})
        
        return params

    def _query_needs_market_context(self, query: str) -> bool:
        text = str(query or "").lower()
        keywords = [
            "行情", "价格", "k线", "持仓", "仓位", "账户", "余额", "风险", "敞口",
            "market", "price", "position", "portfolio", "balance", "exposure", "ticker",
        ]
        return any(k in text for k in keywords)

    def _should_attach_market_snapshot(self, query: str) -> bool:
        if self._query_needs_market_context(query):
            return True
        turn_gap = self._turn_counter - self._market_context_last_turn
        if turn_gap >= 4:
            return True
        if self._market_context_last_at is None:
            return False
        return (datetime.now() - self._market_context_last_at).total_seconds() >= 300

    def _sanitize_text_for_prompt(self, text: str, max_len: int = 500) -> str:
        s = str(text or "")
        s = re.sub(r"```.*?```", "[代码片段已省略]", s, flags=re.S)
        s = re.sub(r"`([^`]*)`", r"\1", s)
        s = re.sub(r"\s+", " ", s).strip()
        if len(s) > max_len:
            return s[:max_len] + "..."
        return s

    async def _build_market_snapshot(self) -> str:
        mc = self.main_controller
        if not mc:
            return ""
        try:
            engine = getattr(mc, "ai_trading_engine", None)
            positions = getattr(engine, "positions", {}) if engine else {}
            balance = getattr(engine, "balance", None) if engine else None
            state_parts: List[str] = []
            if isinstance(balance, (int, float)):
                state_parts.append(f"账户余额: {float(balance):.2f} USDT")
            if isinstance(positions, dict):
                state_parts.append(f"持仓数量: {len(positions)}")
                if positions:
                    state_parts.append("持仓品种: " + ", ".join(list(positions.keys())[:5]))
            if hasattr(mc, "get_simulated_market_state"):
                try:
                    mkt = mc.get_simulated_market_state()
                    if isinstance(mkt, dict) and "error" not in mkt:
                        vol = mkt.get("volatility")
                        if isinstance(vol, (int, float)):
                            state_parts.append(f"模拟市场波动: {float(vol):.4f}")
                except Exception:
                    pass
            return "\n".join(state_parts[:6])
        except Exception:
            return ""
    
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
                # 1) session "working memory" (always include last few turns)
                recent_turns = self._session_history[-8:]
                session_block = ""
                if recent_turns:
                    session_block = "\n".join(
                        [f"{t['role']}: {self._sanitize_text_for_prompt(t['content'], max_len=220)}" for t in recent_turns]
                    )

                # 2) recent conversation memories from gateway (recency-first safety net)
                recent_memories = []
                if hasattr(self.memory, "recent_conversation"):
                    recent_memories = await self.memory.recent_conversation(scope=f"channel:{(context or {}).get('source','system')}", limit=6)

                # 3) relevant long-term recall (similarity-based)
                relevant_memories = await self.memory.retrieve_memories(query=query, limit=5)

                blocks = []
                if session_block:
                    blocks.append("[会话上下文(最近)]\n" + session_block)
                if recent_memories:
                    blocks.append(
                        "[最近对话记忆]\n"
                        + "\n".join(
                            [f"- {self._sanitize_text_for_prompt(m.get('content', str(m)), max_len=220)}" for m in recent_memories]
                        )
                    )
                if relevant_memories:
                    blocks.append(
                        "[相关长期记忆]\n"
                        + "\n".join(
                            [f"- {self._sanitize_text_for_prompt(m.get('content', str(m)), max_len=220)}" for m in relevant_memories]
                        )
                    )
                if blocks:
                    memory_context = "\n\n" + "\n\n".join(blocks)
            except Exception as e:
                logger.warning(f"检索记忆失败: {e}")

        market_context = ""
        if self._should_attach_market_snapshot(query):
            snapshot = await self._build_market_snapshot()
            if snapshot:
                market_context = "\n\n[交易状态摘要]\n" + snapshot
                self._market_context_last_turn = self._turn_counter
                self._market_context_last_at = datetime.now()
        
        personality_prompt = self._get_personality_prompt()
        
        prompt = f"""{personality_prompt}

{memory_context}
{market_context}

请回答用户的问题：

问题: {query}

请以JSON格式返回回答，包含以下字段：
- answer: 回答内容
- confidence: 置信度（0-1）
- source: 回答来源
- related_commands: 相关命令（可选）

回复要求：
1) 默认简洁直接；
2) 不输出长代码块；
3) 不输出大段原始JSON或字典；如需数据，只给摘要。"""
        
        response = await self.llm_integration.generate(prompt)
        content = self._get_response_content(response)
        
        result = self._parse_json_loose(content)
        if not result:
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
                # MemoryGateway compatibility: prefer add_memory, fallback store_memory
                if hasattr(self.memory, "add_memory"):
                    await self.memory.add_memory(
                        memory_type="conversation",
                        content=f"用户问: {query}\n助手答: {result.get('answer', '')}",
                        importance=0.3,
                        tags=["conversation"],
                        source_module="natural_language_interface",
                    )
                else:
                    await self.memory.store_memory(
                        content=f"用户问: {query}\n助手答: {result.get('answer', '')}",
                        memory_type="conversation"
                    )
            except Exception as e:
                logger.warning(f"存储记忆失败: {e}")
        
        return result
    
    async def generate_response(self, result: Dict[str, Any], query: str) -> str:
        compact_result = dict(result or {})
        if "answer" in compact_result:
            compact_result["answer"] = self._sanitize_text_for_prompt(compact_result["answer"], max_len=1000)
        if "data" in compact_result:
            compact_result["data"] = self._sanitize_text_for_prompt(
                json.dumps(compact_result["data"], ensure_ascii=False),
                max_len=400,
            )
        prompt = f"""请根据以下执行结果，生成一个自然友好的回答，回复用户的查询 '{query}'：

执行结果: {json.dumps(compact_result, ensure_ascii=False)}

请直接返回回答内容，不要包含任何格式标记。
不要附加代码块，不要输出大段原始数据。"""
        
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
