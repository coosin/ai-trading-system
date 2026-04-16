"""
AI 指令执行器 - 智能增强版
参照正常AI对话模式，实现：
1. 记忆实时检索与应用 - 每次响应前检索用户关键规则
2. 深层意图理解 - 理解用户真正想要什么
3. 主动行动能力 - 不只是响应，而是执行
4. 纯自然语言交互 - 像真人对话一样
"""

import asyncio
import logging
import json
import re
import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass

from .model_reply_guard import sanitize_commander_result

logger = logging.getLogger(__name__)


def _finalize_commander_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    """与 CommanderAgentRuntime 单点护栏一致；直连 process_input 的调用方也会经过清洗。"""
    return sanitize_commander_result(result)


def _status_summary_use_llm() -> bool:
    """默认关闭：系统状态用程序生成摘要，避免模型添油加醋。开启：OPENCLAW_COMMANDER_STATUS_USE_LLM=1"""
    return str(os.environ.get("OPENCLAW_COMMANDER_STATUS_USE_LLM", "0") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _json_dumps_status_snapshot(obj: Any) -> str:
    """状态注入 LLM 时用 default=str，避免 Enum/自定义对象导致 dumps 失败。"""
    return json.dumps(obj, ensure_ascii=False, default=str)


def _format_system_status_deterministic(
    status_payload: Dict[str, Any],
    *,
    positions_meta: Dict[str, Any],
) -> str:
    """不含 LLM 的固定格式摘要，杜绝「系统平稳但接口挂了」类矛盾话术。"""
    lines: List[str] = ["【系统状态】以下为本次程序拉取的事实摘要（非模型推测）。"]
    mods = status_payload.get("modules") or {}
    if isinstance(mods, dict) and mods:
        ok = sum(1 for v in mods.values() if v)
        lines.append(f"- 核心子系统挂载: {ok}/{len(mods)}（明细见返回 JSON data.modules）。")
    st = status_payload.get("strategy") or {}
    if isinstance(st, dict):
        ex = st.get("examples") or []
        ex_s = ", ".join(str(x) for x in ex) if ex else "无"
        lines.append(f"- 策略配置数量: {st.get('count', 0)}；示例名: {ex_s}。")
    pos = status_payload.get("positions") or []
    err = positions_meta.get("error")
    if err:
        lines.append(f"- 交易所持仓: 拉取失败 — {err}。请勿根据聊天记录猜测持仓。")
    elif not pos:
        lines.append("- 交易所持仓: 当前快照无记录（可能无仓或未返回）。请勿编造手数/方向/币种。")
    else:
        lines.append("- 交易所持仓（接口快照）:")
        for p in pos[:8]:
            if isinstance(p, dict):
                lines.append(f"  · {p.get('symbol')} {p.get('side')} 数量 {p.get('size')}")
    lines.append("- 更全自检: API `GET /api/v1/modules/commander/audit?enrich=true`。")
    return "\n".join(lines)


from .timing_constants import SLEEP_5S, SLEEP_60S
from .commander_charter import (
    CHARTER,
    CONTEXT_FRAMING_FOR_CHAT,
    HONESTY_CONTRACT,
    WORKSPACE_READ_PREFIXES,
    WORKSPACE_SELF_MAINTAIN_PREFIXES,
    honesty_contract_enabled,
)
from src.modules.memory.memory_schema import SummaryKey, base_metadata, kind_tag, tags
from src.modules.memory.memory_context_policy import (
    format_task_memory_block,
    load_startup_workspace_bundle,
)
from src.modules.memory.workspace_boundaries import (
    WorkspaceBoundaries,
    DEFAULT_FORCE_CLOSE_MSG,
    DEFAULT_FORCE_OPEN_MSG,
    DEFAULT_WORKSPACE_EDIT_MSG,
    effective_high_risk_phrases,
    effective_workspace_phrases,
    load_workspace_boundaries,
)


@dataclass
class Intent:
    """用户意图"""
    action: str
    params: Dict[str, Any]
    confidence: float


class AICommandExecutor:
    """
    AI 指令执行器 - 智能增强版
    
    核心改进：
    1. 记忆驱动 - 每次响应都检索和应用用户规则（含 workspace 自然语言边界）
    2. 交易前结合记忆与黑名单等信号
    3. 授权感知 - 根据授权范围决定行动
    4. 主动工作 - 不等待指令，自主执行职责
    
    业务分寸与闸门文案优先从 workspace/COMMANDER_PROFILE.md 读取；代码仅保留路径安全等必要技术校验。
    """
    
    def __init__(self, main_controller=None):
        self.main_controller = main_controller
        self.llm_integration = None
        self.memory_manager = None
        self.unified_memory = None
        self.user_intent_recognizer = None
        self.ai_core = None  # AI核心决策引擎引用
        
        self.blacklist = set()
        self.authorization = {
            "full_authorization": True,
            "auto_trading": True,
            "auto_strategy": True,
            # 与司令部宪章一致的「授权口径」（供状态展示与未来扩展，未知键不影响 .get）
            "push_trade_lifecycle_alerts": True,
            "push_risk_and_regime_alerts": True,
            "push_data_and_system_anomalies": True,
            "use_skill_manager_capabilities": True,
        }
        self.work_duties = []
        
        self._autonomous_running = False
        self._last_daily_summary_date = None
        self._workspace_startup_bundle: str = ""
        self._workspace_boundaries: Optional[WorkspaceBoundaries] = None
        
        logger.info("AI指令执行器（智能增强版）初始化完成")
    
    async def initialize(self) -> None:
        """初始化指令执行器"""
        logger.info("初始化AI指令执行器（智能增强版）...")
        
        if self.main_controller:
            if hasattr(self.main_controller, "get_llm_integration"):
                self.llm_integration = self.main_controller.get_llm_integration()
            elif hasattr(self.main_controller, 'llm_integration'):
                self.llm_integration = self.main_controller.llm_integration
            
            if hasattr(self.main_controller, 'ai_memory_manager'):
                self.memory_manager = self.main_controller.ai_memory_manager
        
        try:
            from .user_intent_recognizer import UserIntentRecognizer

            # 单一真源：只使用主控制器注入的 MemoryGateway（ai_memory_manager）。
            self.unified_memory = (
                getattr(self.main_controller, "ai_memory_manager", None)
                if self.main_controller else None
            )
            if self.unified_memory is None:
                logger.warning("⚠️ MemoryGateway 未就绪：AI 将在无记忆模式下运行（不会再 fallback 到并行记忆实现）")

            self.user_intent_recognizer = UserIntentRecognizer
            logger.info("✅ 用户意图识别器已加载")

            await self._load_user_rules_from_memory()

            try:
                from pathlib import Path as _Path

                ws = "workspace"
                if self.main_controller and getattr(self.main_controller, "config_manager", None):
                    ws = (
                        self.main_controller.config_manager.get_config_sync(
                            "paths", "workspace_path", ws
                        )
                        or ws
                    )
                self._workspace_startup_bundle = load_startup_workspace_bundle(
                    _Path(ws),
                    config_manager=getattr(self.main_controller, "config_manager", None)
                    if self.main_controller
                    else None,
                )
                if self._workspace_startup_bundle:
                    logger.info("✅ 已加载 Workspace 启动摘要（人格/职责/经验锚点）")
                try:
                    _root = _Path(__file__).resolve().parents[3]
                    _wspath = _Path(ws) if _Path(ws).is_absolute() else _root / ws
                    self._workspace_boundaries = load_workspace_boundaries(_wspath)
                    if self._workspace_boundaries and self._workspace_boundaries.learning_prose:
                        logger.info("✅ 已加载 workspace 边界与学习自然语言")
                except Exception as e:
                    logger.debug(f"Workspace 边界文件跳过: {e}")
            except Exception as e:
                logger.debug(f"Workspace 启动摘要跳过: {e}")
                self._workspace_startup_bundle = ""

        except Exception as e:
            logger.warning(f"加载用户意图识别器/记忆系统失败: {e}")
        
        logger.info("✅ AI指令执行器（智能增强版）初始化完成")
    
    def _get_workspace_boundaries(self) -> WorkspaceBoundaries:
        """懒加载 workspace/COMMANDER_PROFILE.md（initialize 已加载则直接复用）。"""
        if self._workspace_boundaries is None:
            try:
                root = Path(__file__).resolve().parents[3]
                ws = "workspace"
                if self.main_controller and getattr(self.main_controller, "config_manager", None):
                    ws = self.main_controller.config_manager.get_config_sync("paths", "workspace_path", ws) or ws
                wspath = Path(ws) if Path(ws).is_absolute() else root / ws
                self._workspace_boundaries = load_workspace_boundaries(wspath)
            except Exception as e:
                logger.debug(f"workspace boundaries lazy load: {e}")
                self._workspace_boundaries = WorkspaceBoundaries()
        return self._workspace_boundaries
    
    def _get_ai_core(self):
        """动态获取AI核心决策引擎（运行时获取，避免初始化顺序问题）"""
        if self.main_controller and hasattr(self.main_controller, 'ai_core'):
            return self.main_controller.ai_core
        return None
    
    def _get_ai_trading_engine(self):
        """动态获取AI交易引擎"""
        if self.main_controller and hasattr(self.main_controller, 'ai_trading_engine'):
            return self.main_controller.ai_trading_engine
        return None
    
    async def _load_user_rules_from_memory(self) -> None:
        """从记忆中加载用户规则"""
        if not self.unified_memory:
            return
        
        try:
            blacklist_memories = await self.unified_memory.retrieve_memories(
                query="黑名单 禁区 不要操作",
                min_importance=0.8,
                limit=10
            )
            for mem in blacklist_memories:
                # 不再自动将ETH加入黑名单
                if "ETH" in mem.content or "以太坊" in mem.content:
                    logger.info(f"ℹ️ 忽略ETH黑名单记忆: 已移除ETH限制")
            
            auth_memories = await self.unified_memory.retrieve_memories(
                query="全权 负责 授权 交易",
                min_importance=0.8,
                limit=5
            )
            for mem in auth_memories:
                if "全权负责" in mem.content or "整个交易流程" in mem.content:
                    self.authorization["full_authorization"] = True
                    self.authorization["auto_trading"] = True
                    self.authorization["auto_strategy"] = True
                    logger.info("✅ 从记忆加载授权: 全权负责")
            
            logger.info(f"📋 已加载用户规则: 黑名单={self.blacklist}, 授权={self.authorization}")
            
        except Exception as e:
            logger.error(f"加载用户规则失败: {e}")
    
    async def process_input(self, user_input: str, source: str = "system") -> Dict[str, Any]:
        """
        处理用户输入 - 智能增强版
        核心改进：在处理前检索和应用记忆中的用户规则

        source: 与 MainController.process_user_command 对齐（如 telegram、api_chat），用于 MemoryGateway
        的 channel:<source> 对话连续性与 context_policy.channels 覆盖。
        """
        logger.info(f"处理用户输入: {user_input}")
        conv_scope = f"channel:{source}" if source else None
        memory_channel = str(source).strip() if source else None
        
        try:
            if self.unified_memory:
                memory_result = await self.unified_memory.process_user_input(user_input)
                if memory_result.get("recorded"):
                    logger.info(f"📝 自动记录用户意图: {memory_result.get('message')}")
                    
                    if memory_result.get("blacklist_updated"):
                        await self._load_user_rules_from_memory()
                    if memory_result.get("authorization_updated"):
                        await self._load_user_rules_from_memory()

            # 极简模式下原先只走 _general_chat，模型会「假装查价」并编造数字。
            # 1) 身份类：直接回 workspace 已加载摘要，不现编。
            # 2) 「对接数据源/分析系统」类：走系统内 ticker（默认币对可环境变量）。
            # 3) 明确问价短句：同上。
            utter = self._strip_user_utterance_for_routing(user_input)

            if self._looks_like_identity_question(utter):
                result = await self._answer_identity_from_workspace()
                intent = Intent(action="chat", params={}, confidence=1.0)
                if self.unified_memory:
                    try:
                        await self.unified_memory.add_memory(
                            memory_type=self._get_memory_type_from_intent(intent.action),
                            content=f"用户: {user_input}",
                            summary=f"用户指令: {user_input[:100]}",
                            metadata=base_metadata(
                                source_module="ai_command_executor",
                                kind="user_input",
                                extra={"intent": intent.action, "params": intent.params},
                            ),
                            source_module="ai_command_executor",
                        )
                        action_msg = str((result or {}).get("response") or "")[:500]
                        if action_msg:
                            await self.unified_memory.add_memory(
                                memory_type="conversation",
                                content=f"动作结果[{intent.action}] {action_msg}",
                                summary=f"{intent.action} 执行结果摘要",
                                metadata=base_metadata(
                                    source_module="ai_command_executor",
                                    kind="action_result",
                                    extra={
                                        "intent": intent.action,
                                        "success": bool((result or {}).get("success", False)),
                                    },
                                ),
                                source_module="ai_command_executor",
                                importance=0.55,
                                tags=tags(kind_tag("action_result"), kind_tag(intent.action)),
                            )
                    except Exception:
                        pass
                return _finalize_commander_payload(result)

            force_trade_params = (
                self._extract_trade_params_from_text(utter)
                if self._looks_like_trade_execution_request(utter)
                else None
            )
            internal_q = self._looks_like_internal_price_query(utter)
            plain_price_q = self._looks_like_plain_price_quote_question(utter)
            sym = self._resolve_symbol_for_price(utter)
            if internal_q or plain_price_q:
                sym = sym or str(os.environ.get("OPENCLAW_DEFAULT_PRICE_SYMBOL", "ETH/USDT")).strip()
            if (not force_trade_params) and sym and (
                internal_q
                or plain_price_q
                or self._looks_like_live_price_only_request(utter)
            ):
                result = await self._answer_live_price_from_exchange(sym)
                intent = Intent(action="market_analysis", params={"symbol": sym}, confidence=1.0)
                if self.unified_memory:
                    try:
                        await self.unified_memory.add_memory(
                            memory_type=self._get_memory_type_from_intent(intent.action),
                            content=f"用户: {user_input}",
                            summary=f"用户指令: {user_input[:100]}",
                            metadata=base_metadata(
                                source_module="ai_command_executor",
                                kind="user_input",
                                extra={"intent": intent.action, "params": intent.params},
                            ),
                            source_module="ai_command_executor",
                        )
                        action_msg = str((result or {}).get("response") or "")[:500]
                        if action_msg:
                            await self.unified_memory.add_memory(
                                memory_type="conversation",
                                content=f"动作结果[{intent.action}] {action_msg}",
                                summary=f"{intent.action} 执行结果摘要",
                                metadata=base_metadata(
                                    source_module="ai_command_executor",
                                    kind="action_result",
                                    extra={
                                        "intent": intent.action,
                                        "success": bool((result or {}).get("success", False)),
                                    },
                                ),
                                source_module="ai_command_executor",
                                importance=0.55,
                                tags=tags(kind_tag("action_result"), kind_tag(intent.action)),
                            )
                    except Exception:
                        pass
                return _finalize_commander_payload(result)

            if self._looks_like_system_learning_request(utter):
                result = await self._answer_system_familiarity_bootstrap()
                intent = Intent(
                    action="workspace_read",
                    params={"path": "docs/ENGINEERING.md"},
                    confidence=1.0,
                )
                if self.unified_memory:
                    try:
                        await self.unified_memory.add_memory(
                            memory_type=self._get_memory_type_from_intent(intent.action),
                            content=f"用户: {user_input}",
                            summary=f"用户指令: {user_input[:100]}",
                            metadata=base_metadata(
                                source_module="ai_command_executor",
                                kind="user_input",
                                extra={"intent": intent.action, "params": intent.params},
                            ),
                            source_module="ai_command_executor",
                        )
                        action_msg = str((result or {}).get("response") or "")[:500]
                        if action_msg:
                            await self.unified_memory.add_memory(
                                memory_type="conversation",
                                content=f"动作结果[{intent.action}] {action_msg}",
                                summary=f"{intent.action} 执行结果摘要",
                                metadata=base_metadata(
                                    source_module="ai_command_executor",
                                    kind="action_result",
                                    extra={
                                        "intent": intent.action,
                                        "success": bool((result or {}).get("success", False)),
                                    },
                                ),
                                source_module="ai_command_executor",
                                importance=0.55,
                                tags=tags(kind_tag("action_result"), kind_tag(intent.action)),
                            )
                    except Exception:
                        pass
                return _finalize_commander_payload(result)
            
            # 极简模式：只聊天不跑意图；默认关闭，走下方 LLM 意图解析与执行。
            if self._is_minimal_free_mode():
                user_rules = await self._get_user_rules_context()
                result = await self._general_chat(
                    user_input,
                    user_rules,
                    intent_action="chat",
                    conversation_scope=conv_scope,
                    memory_channel=memory_channel,
                )
                intent = Intent(action="chat", params={}, confidence=1.0)
            else:
                if force_trade_params:
                    intent = Intent(action="trade", params=force_trade_params, confidence=1.0)
                else:
                    intent = await self._parse_intent(user_input)
            # 用户已要求“取消限制”：不再把 system_inspection 意图强制降级为 chat。
                user_rules = await self._get_user_rules_context()
                
                if intent.action != "unknown":
                    result = await self._execute_intent(
                        intent,
                        user_input,
                        user_rules,
                        conversation_scope=conv_scope,
                        memory_channel=memory_channel,
                    )
                else:
                    act_ctx = intent.action if intent.action != "unknown" else "chat"
                    result = await self._general_chat(
                        user_input,
                        user_rules,
                        intent_action=act_ctx,
                        conversation_scope=conv_scope,
                        memory_channel=memory_channel,
                    )
            
            if self.unified_memory:
                await self.unified_memory.add_memory(
                    memory_type=self._get_memory_type_from_intent(intent.action),
                    content=f"用户: {user_input}",
                    summary=f"用户指令: {user_input[:100]}",
                    metadata=base_metadata(
                        source_module="ai_command_executor",
                        kind="user_input",
                        extra={"intent": intent.action, "params": intent.params},
                    ),
                    source_module="ai_command_executor"
                )
                try:
                    action_msg = str((result or {}).get("response") or "")[:500]
                    if action_msg:
                        await self.unified_memory.add_memory(
                            memory_type="conversation",
                            content=f"动作结果[{intent.action}] {action_msg}",
                            summary=f"{intent.action} 执行结果摘要",
                            metadata=base_metadata(
                                source_module="ai_command_executor",
                                kind="action_result",
                                extra={
                                    "intent": intent.action,
                                    "success": bool((result or {}).get("success", False)),
                                },
                            ),
                            source_module="ai_command_executor",
                            importance=0.55,
                            tags=tags(kind_tag("action_result"), kind_tag(intent.action)),
                        )
                except Exception:
                    pass
            
            return _finalize_commander_payload(result)
            
        except Exception as e:
            # 中文化错误提示：把常见英文异常翻译成“人话”
            err = str(e)
            friendly = err
            if "UnifiedMemoryType" in err and "TRADING_DECISION" in err:
                friendly = "记忆系统类型枚举不兼容：模块在写入 TRADING_DECISION 记忆时失败。"
            elif "UnifiedMemoryType" in err and "strip" in err:
                friendly = "记忆系统类型参数格式不兼容：把枚举当成字符串处理导致失败。"
            logger.error(f"处理用户输入失败: {e}")
            import traceback
            traceback.print_exc()
            return _finalize_commander_payload(
                {
                    "success": False,
                    "response": f"处理过程中遇到问题：{friendly}",
                    "timestamp": datetime.now().isoformat(),
                }
            )
    
    async def _get_user_rules_context(self) -> str:
        """
        人格与口吻以 workspace/COMMANDER_PROFILE.md（启动摘要）为主，宪章为辅；再补边界解析与记忆禁区。
        """
        parts: List[str] = []

        if getattr(self, "_workspace_startup_bundle", None):
            parts.append(
                "【人格与画像】节选来自 workspace/COMMANDER_PROFILE.md（改这个文件即可调性格与分寸，不必改代码）。\n"
                + self._workspace_startup_bundle.strip()
            )

        parts.append("\n【司令部宪章 · 原则锚点】\n" + CHARTER)
        if honesty_contract_enabled():
            parts.append("\n" + HONESTY_CONTRACT)

        try:
            wb = self._get_workspace_boundaries()
            if wb.learning_prose:
                cap = 4500
                lp = wb.learning_prose.strip()
                if len(lp) > cap:
                    lp = lp[:cap] + "…"
                parts.append("\n【边界与学习（同文件自然语言）】\n" + lp)
        except Exception as e:
            logger.debug(f"inject boundaries prose: {e}")

        if self.unified_memory:
            try:
                blacklist_memories = await self.unified_memory.retrieve_memories(
                    query="黑名单 禁区 不要",
                    min_importance=0.8,
                    limit=3,
                )
                if blacklist_memories:
                    parts.append("\n【记忆：禁区/黑名单要点】")
                    for mem in blacklist_memories:
                        line = (mem.content or "").strip()
                        if "ETH" in line or "以太坊" in line:
                            continue
                        if line:
                            parts.append(f"- {line[:240]}")
            except Exception as e:
                logger.debug(f"检索黑名单记忆失败: {e}")

        return "\n".join(parts).strip()

    def _get_memory_type_from_intent(self, action: str):
        """根据意图类型获取记忆类型"""
        # MemoryGateway 使用字符串 category，并负责映射到内部 MemoryCategory/MemoryLayer。
        mapping = {
            "trade": "trade_record",
            "signals": "market_observation",
            "market_analysis": "market_observation",
            "risk": "risk_event",
            "strategy_create": "decision",
            "strategy_optimize": "decision",
        }
        return mapping.get(action, "conversation")
    
    def _parse_llm_json(self, content: str) -> Optional[Dict[str, Any]]:
        """从模型输出中尽量解析 JSON（允许 ```json 围栏）。"""
        if not content:
            return None
        raw = content.strip()
        if "```" in raw:
            try:
                start = raw.find("```")
                chunk = raw[start + 3 :]
                if chunk.lstrip().startswith("json"):
                    chunk = chunk.lstrip()[4:].lstrip()
                end = chunk.find("```")
                if end != -1:
                    raw = chunk[:end].strip()
            except Exception:
                pass
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # common cleanup: full-width punctuation + trailing commas
            cleaned = (
                raw.replace("，", ",")
                .replace("：", ":")
                .replace("（", "(")
                .replace("）", ")")
            )
            cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                pass
            try:
                i, j = cleaned.find("{"), cleaned.rfind("}")
                if i != -1 and j != -1 and j > i:
                    return json.loads(cleaned[i : j + 1])
            except json.JSONDecodeError:
                return None
        return None

    def _normalize_intent_action(self, action: str) -> str:
        """兼容历史/别名 action 字符串，不做自然语言关键词判断。"""
        if not action:
            return "chat"
        al = str(action).strip().lower()
        aliases = {
            "system.inspection.run": "system_inspection",
            "system.inspection": "system_inspection",
            "system_inspection": "system_inspection",
            "inspection": "system_inspection",
            "health_check": "system_inspection",
            "healthcheck": "system_inspection",
            "trade_history": "trade_history",
            "trades": "trade_history",
            "order_history": "trade_history",
            "history": "trade_history",
        }
        if al in aliases:
            return aliases[al]
        return al.replace(" ", "_").replace("-", "_")

    async def _parse_intent(self, user_input: str) -> Intent:
        """解析用户意图：由 LLM 理解语义并选择动作；不在此处做关键词规则。"""
        params = await self._extract_params(user_input, "")
        if self.llm_integration:
            try:
                prompt = f"""任务：根据用户消息选一个 action，输出一条 JSON。

action ∈ chat, system_status, trade_history, positions, balance, market_analysis, trade, strategy_create, strategy_optimize, backtest, risk, signals, third_party_data, workspace_read, workspace_edit, plugin_list, plugin_reload, plugin_load, plugin_unload

说明：
- 用户可用日常口语、中英文混说，不必固定指令模板；按真实意图选 action。
- 诚实：reasoning 只写从用户话里能推出的判断，不得捏造用户未说的情节或系统状态。
- 非工作话题（生活/学习/娱乐/情绪支持/日常建议）默认 action=chat。
- 只有用户明确要求系统状态/巡检/交易执行/策略操作，才选择对应工作 action。
- workspace_read：params 必须包含 path（相对仓库根，用 /）。可以是**文件**或**允许前缀下的目录**；目录则返回真实列目录树（非推断）。了解本项目优先 path=docs/ENGINEERING.md 或 docs/README.md、ARCHITECTURE.md、README.md；看模块分布用 path=src/modules。勿编造 src/data_source、src/trading 等不存在的顶层路径。
- workspace_edit：params 必须包含 path、edit_type、content；edit_type 为 insert|delete|replace|full_replace；delete/replace 需 start_line、end_line（从 1 起的行号）；full_replace 用 content 替换整个文件；insert 可用 start_line 指定插入位置。

用户消息：
{user_input}

输出 JSON（无 markdown）：
{{"action":"...","params":{{}},"confidence":0.0,"reasoning":"一句话"}}"""

                response = await self.llm_integration.generate(prompt, is_user_input=False)
                if response and response.content:
                    result = self._parse_llm_json(response.content)
                    if isinstance(result, dict):
                        merged_params = dict(params)
                        rp = result.get("params")
                        if isinstance(rp, dict):
                            merged_params.update(rp)
                        action = self._normalize_intent_action(str(result.get("action", "chat")))

                        # 防呆：有时模型会把“检查一下系统/司令部情况”误判成 workspace_read/edit，
                        # 但又不给 path，导致看起来像“机械报错”。这里做最小纠偏：无 path 的 workspace_* 一律回退。
                        if action in ("workspace_read", "workspace_edit") and not merged_params.get("path"):
                            text = (user_input or "").strip()
                            if any(k in text for k in ("检查", "看看", "状态", "情况", "运行")):
                                action = "system_status"
                            else:
                                action = "chat"

                        return Intent(
                            action=action,
                            params=merged_params,
                            confidence=float(result.get("confidence", 0.75) or 0.75),
                        )
            except Exception as e:
                logger.warning(f"LLM解析意图失败: {e}")

        return Intent(action="chat", params=params, confidence=0.5)
    
    async def _extract_params(self, user_input: str, action: str) -> Dict[str, Any]:
        """提取参数"""
        params = {}
        
        symbols = re.findall(r'\b(BTC|ETH|SOL|BNB|XRP|DOGE|ADA|AVAX|DOT|MATIC)[-/]?(USDT|USDT|USD)?\b', user_input, re.IGNORECASE)
        if symbols:
            params['symbol'] = symbols[0][0].upper() + '/USDT'
        
        numbers = re.findall(r'\b(\d+(?:\.\d+)?)\b', user_input)
        if numbers:
            if '天' in user_input or '日' in user_input:
                params['days'] = int(numbers[0])
            elif '%' in user_input:
                params['percentage'] = float(numbers[0])
            else:
                params['value'] = float(numbers[0])
        
        return params

    def _repo_root(self) -> Path:
        return Path(__file__).resolve().parents[3]

    @staticmethod
    def _looks_like_work_topic(text: str) -> bool:
        t = str(text or "").lower()
        keys = [
            "交易", "开仓", "平仓", "止盈", "止损", "风控", "持仓", "余额",
            "策略", "回测", "司令部", "系统", "模块", "运行状态",
            "okx", "btc", "eth", "usdt", "risk", "strategy", "position",
            "balance", "trade", "backtest", "module", "system", "commander",
        ]
        return any(k in t for k in keys)

    @staticmethod
    def _is_commander_unrestricted() -> bool:
        """
        司令部无限制模式（默认开启）：
        - 1/true/yes/on => 开启
        - 0/false/no/off => 关闭
        """
        raw = str(os.environ.get("OPENCLAW_COMMANDER_UNRESTRICTED", "1") or "").strip().lower()
        return raw not in {"0", "false", "no", "off"}

    @staticmethod
    def _is_minimal_free_mode() -> bool:
        """
        极简自由模式（默认关闭）：
        - 关闭时：LLM 解析意图 → _execute_intent，自然语言驱动执行（完全智能主路径）。
        - 开启时：仅“自然对话 + 记忆”，除身份/问价等快路径外不走意图执行；适合只要闲聊、怕误触的场景。
        环境变量 OPENCLAW_COMMANDER_MINIMAL_MODE=1/true/on 可显式开启。
        """
        raw = str(os.environ.get("OPENCLAW_COMMANDER_MINIMAL_MODE", "0") or "").strip().lower()
        return raw not in {"0", "false", "no", "off"}

    @staticmethod
    def _strip_user_utterance_for_routing(raw: str) -> str:
        """
        Telegram 等通道会在用户原话后拼接宪章/记忆节选；意图与查价检测只应看「用户原话」。
        """
        text = (raw or "").strip()
        for sep in ("【司令部宪章】", "【记忆节选】"):
            if sep in text:
                text = text.split(sep, 1)[0].strip()
        return text[:2000]

    @staticmethod
    def _resolve_symbol_for_price(text: str) -> Optional[str]:
        """从用户句子里解析交易对，默认 USDT 计价。"""
        t = (text or "").strip()
        if not t:
            return None
        m = re.search(
            r"\b(BTC|ETH|SOL|BNB|XRP|DOGE|ADA|AVAX|DOT|MATIC|LINK|LTC)[-/]?(USDT|USD)?\b",
            t,
            re.IGNORECASE,
        )
        if m:
            return f"{m.group(1).upper()}/USDT"
        if "比特币" in t:
            return "BTC/USDT"
        if "以太坊" in t or re.search(r"(?<![A-Za-z])以太(?![A-Za-z])", t):
            return "ETH/USDT"
        return None

    @staticmethod
    def _looks_like_trade_execution_request(text: str) -> bool:
        """识别执行型交易口令，避免被问价快路径误吞。"""
        t = (text or "").strip()
        if not t or len(t) > 900:
            return False
        trade_kw = (
            "强制开仓",
            "强制平仓",
            "开仓",
            "平仓",
            "开多",
            "开空",
            "平多",
            "平空",
            "做多",
            "做空",
            "买入",
            "卖出",
            "下单",
            "建仓",
        )
        if not any(k in t for k in trade_kw):
            return False
        if re.search(r"(怎么|如何|为何|为什么|教程|规则|原理|解释).{0,8}(开仓|平仓|做多|做空)", t):
            return False
        return True

    @staticmethod
    def _extract_trade_params_from_text(text: str) -> Dict[str, Any]:
        """从自然语言里提取 symbol/side/quantity/force 参数。"""
        t = (text or "").strip()
        params: Dict[str, Any] = {}
        sym = AICommandExecutor._resolve_symbol_for_price(t)
        if sym:
            params["symbol"] = sym
        low = t.lower()
        if any(k in t for k in ("强制平仓", "立即平仓", "马上平仓", "全平", "清仓")):
            params["force_close"] = True
        if any(k in t for k in ("强制开仓", "立即开仓", "马上开仓")):
            params["force"] = True
        if any(k in t for k in ("做多", "开多", "买入", "long")) or "buy" in low:
            params["side"] = "long"
        elif any(k in t for k in ("做空", "开空", "卖出", "short")) or "sell" in low:
            params["side"] = "short"
        elif "平多" in t:
            params["side"] = "long"
            params["force_close"] = True
        elif "平空" in t:
            params["side"] = "short"
            params["force_close"] = True
        m = re.search(r"(?<![A-Za-z])(\d+(?:\.\d+)?)(?![A-Za-z])", t)
        if m:
            try:
                params["quantity"] = float(m.group(1))
            except ValueError:
                pass
        return params

    @staticmethod
    def _looks_like_internal_price_query(text: str) -> bool:
        """
        用户要求用「本系统数据源 / 分析模块 / 对接」查价，未必带币种简称。
        注意：不要用子串「分析」做排除词，否则会误伤「分析系统」。
        """
        t = (text or "").strip()
        if not t or len(t) > 900:
            return False
        sys_kw = (
            "数据源",
            "分析系统",
            "对接",
            "系统内部",
            "内部数据",
            "对齐",
            "行情模块",
            "交易所接口",
            "market intelligence",
            "数据集成",
        )
        act_kw = ("查", "拉", "读", "取", "多少", "价格", "价位", "行情", "实时", "报价")
        if not any(k in t for k in sys_kw):
            return False
        if not any(k in t for k in act_kw):
            return False
        return True

    @staticmethod
    def _looks_like_identity_question(text: str) -> bool:
        t = (text or "").strip()
        if not t or len(t) > 1200:
            return False
        return bool(
            re.search(
                r"(你是谁|你究竟是谁|什么身份|何种身份|身份文件|人格文件|commander_profile|读取.*身份|读到.*身份|知道你是谁)",
                t,
                re.IGNORECASE,
            )
        )

    async def _answer_identity_from_workspace(self) -> Dict[str, Any]:
        """用已加载的 workspace 摘要回答身份，避免模型现编。"""
        bundle = (getattr(self, "_workspace_startup_bundle", None) or "").strip()
        head = (
            "我是本系统里的「司令部」助理（OpenClaw）。\n"
            "人格、口吻与职责写在 **workspace/COMMANDER_PROFILE.md**，启动时会读入摘要；总原则在《司令部宪章》。\n"
            "下面是你文件里的节选（不是现编的）：\n\n"
        )
        body = bundle[:4500] if bundle else "（当前未读到 COMMANDER_PROFILE.md 摘要，请检查工作区路径与挂载。）"
        return {
            "success": True,
            "response": (head + body)[:6500],
            "source": "identity_workspace",
        }

    @staticmethod
    def _looks_like_plain_price_quote_question(text: str) -> bool:
        """
        用户问价但未写币种（如「能查到价格吗」「现在多少钱」）：走默认 OPENCLAW_DEFAULT_PRICE_SYMBOL。
        若已能解析出币种，交给 _looks_like_live_price_only_request，避免重复。
        """
        t = (text or "").strip()
        if not t or len(t) > 600:
            return False
        if AICommandExecutor._resolve_symbol_for_price(t):
            return False
        if any(
            k in t
            for k in (
                "趋势",
                "走势",
                "建议",
                "看法",
                "技术",
                "多空",
                "布局",
                "策略",
                "预测",
                "怎么看",
                "觉得",
            )
        ):
            return False
        if any(k in t for k in ("你是谁", "什么身份", "什么人格", "宪章")):
            return False
        low = t.lower()
        price_kw = (
            "价格",
            "行情",
            "现价",
            "多少钱",
            "什么价",
            "报价",
            "实时",
            "价位",
            "查价",
            "ticker",
            "quote",
            "u价",
        )
        has_price = any(k in t for k in price_kw) or any(k in low for k in ("ticker", "quote"))
        has_price = has_price or bool(re.search(r"(多少|啥价|几块钱|几个u|几u)", t))
        if not has_price:
            return False
        # 有「价」且很短，多半是问报价（如「当前价」「最新价」）
        if len(t) <= 24 and "价" in t:
            return True
        action_or_meta = bool(
            re.search(
                r"(查|拉|取|读|看|给|报|吗|呢|嘛|能|可不可以|行不行|现在|当前|接口|对接|通了吗|有没有数据|实时)",
                t,
            )
        )
        return action_or_meta or (len(t) <= 40 and has_price)

    @staticmethod
    def _looks_like_live_price_only_request(text: str) -> bool:
        """
        仅「现价/报价」类短问：走交易所真实 ticker，禁止交给纯模型编造数字。
        含「趋势/建议/…」等深度分析意图则不走本快路径（但「分析系统」不在此列）。
        """
        t = (text or "").strip()
        if not t or len(t) > 600:
            return False
        if any(
            k in t
            for k in (
                "趋势",
                "走势",
                "建议",
                "看法",
                "技术",
                "多空",
                "布局",
                "策略",
                "预测",
                "怎么看",
                "觉得",
            )
        ):
            return False
        if any(k in t for k in ("你是谁", "什么身份", "什么人格", "宪章")):
            return False
        sym = AICommandExecutor._resolve_symbol_for_price(t)
        if not sym:
            return False
        low = t.lower()
        price_kw = (
            "价格",
            "行情",
            "现价",
            "多少钱",
            "什么价",
            "报价",
            "实时",
            "价位",
            "ticker",
            "quote",
            "usd",
            "u价",
        )
        if any(k in t for k in price_kw) or any(k in low for k in price_kw):
            return True
        # 「ETH 多少」「比特币现在多少」
        if re.search(r"(多少|几个|几块钱|啥价)", t):
            return True
        return False

    @staticmethod
    def _looks_like_system_learning_request(text: str) -> bool:
        """用户要求读文档/熟悉本仓库（非闲聊编造目录树）。"""
        t = (text or "").strip()
        if not t or len(t) > 900:
            return False
        if re.search(r"(读(取)?|阅读|翻看|打开|先).{0,8}文档", t):
            return True
        if "相关文档" in t or "先看文档" in t or "读一下文档" in t:
            return True
        if re.search(r"(熟悉|了解|弄清楚|搞清|认识).{0,10}(系统|项目|仓库|代码库|咱们|我们).{0,6}(东西|情况)?", t):
            return True
        if "不了解" in t and ("工作" in t or "系统" in t or "项目" in t):
            return True
        if re.search(r"(项目|系统).{0,6}(结构|架构|目录|代码)", t) and any(
            k in t for k in ("读", "看", "翻", "了解", "熟悉", "从")
        ):
            return True
        if re.search(r"(每行|逐行).{0,6}代码", t):
            return True
        return False

    async def _answer_live_price_from_exchange(self, symbol: str) -> Dict[str, Any]:
        """只返回交易所接口事实；拿不到则明确失败，禁止编造。"""
        ticker: Optional[Dict[str, Any]] = None
        mc = self.main_controller
        hub = getattr(mc, "data_source_hub", None) if mc else None
        if hub:
            try:
                ticker = await hub.get_ticker(symbol)
            except Exception as e:
                logger.debug(f"data_source_hub.get_ticker failed: {e}")
                ticker = None
        last = float((ticker or {}).get("last") or (ticker or {}).get("price") or 0.0)
        if last <= 0 and mc:
            okx = getattr(mc, "okx_exchange", None)
            if okx and hasattr(okx, "get_ticker"):
                try:
                    raw = await okx.get_ticker(symbol.replace("/", "-"))
                    if isinstance(raw, dict):
                        ticker = raw
                        last = float(raw.get("last") or raw.get("price") or 0.0)
                except Exception as e:
                    logger.debug(f"okx get_ticker failed: {e}")
        if last <= 0 and mc:
            mi = getattr(mc, "market_intelligence", None)
            if mi and hasattr(mi, "get_symbol_view"):
                try:
                    view = await mi.get_symbol_view(symbol, include_snapshot=False)
                    px = getattr(view, "price", None) if view is not None else None
                    if px is not None and float(px) > 0:
                        last = float(px)
                        ticker = {
                            "last": last,
                            "price": last,
                            "source": "market_intelligence_engine",
                            "provenance": getattr(view, "provenance", None),
                        }
                except Exception as e:
                    logger.debug(f"market_intelligence get_symbol_view: {e}")
        if last <= 0:
            return {
                "success": True,
                "response": (
                    f"我刚用系统内数据源（交易所 / DataSourceHub / 市场情报）拉 {symbol}，都没拿到有效最新价。\n"
                    "这不是推脱：这一下接口确实没有可信数字，我不会编区间糊弄你。请检查 API 与主进程是否就绪。"
                ),
                "source": "live_ticker_unavailable",
                "data": {"symbol": symbol},
            }
        src_lbl = (ticker or {}).get("source") or "exchange"
        if src_lbl == "market_intelligence_engine":
            head = f"{symbol}：市场情报模块本次给出的参考价 {last:,.2f} USDT（系统内计算/汇总，非模型瞎编）。"
        else:
            head = f"{symbol}：接口这次返回的最新价约 {last:,.2f} USDT（来自交易所/数据源，不是模型猜的）。"
        lines = [head]
        hi = (ticker or {}).get("high")
        lo = (ticker or {}).get("low")
        vol = (ticker or {}).get("volume")
        for label, v in (("24h高", hi), ("24h低", lo), ("24h成交量", vol)):
            if v is None:
                continue
            try:
                fv = float(v)
                if fv:
                    lines.append(f"{label}: {fv:,.4f}")
            except (TypeError, ValueError):
                pass
        lines.append(f"（数据来源: {src_lbl}）")
        lines.append("")
        lines.append("若和你 App 里差一点点，多半是延迟或盘口口径差异。")
        return {
            "success": True,
            "response": "\n".join(lines),
            "source": "live_ticker",
            "data": {"symbol": symbol, "ticker": ticker},
        }

    async def _answer_system_familiarity_bootstrap(self) -> Dict[str, Any]:
        """用户要「先读文档再懂系统」时，直接列真实目录 + 读架构文档节选，避免模型空演。"""
        chunks: List[str] = [
            "【以下为进程内刚执行的列目录 / 读文件结果，不是训练记忆里的假项目结构】\n"
            "本仓库主代码在 **src/modules/**（core、data、exchanges、notification 等），"
            "没有 src/data_source、src/trading 这类顶层目录名。\n",
        ]
        src_mod = self._repo_root() / "src" / "modules"
        if src_mod.is_dir():
            tree = self._workspace_dir_tree_lines(src_mod, max_depth=2, max_lines=160)
            chunks.append("\n### src/modules（真实列举）\n" + "\n".join(tree))

        doc_candidates = (
            "docs/ENGINEERING.md",
            "docs/README.md",
            "ARCHITECTURE.md",
            "README.md",
        )
        doc_snip: Optional[str] = None
        for rel in doc_candidates:
            chunk = await self._workspace_read({"path": rel})
            if chunk.get("success") and isinstance(chunk.get("response"), str):
                body = chunk["response"]
                if len(body) > 14_000:
                    body = body[:14_000] + "\n\n…（节选截断，完整请指定 workspace_read 同一 path）"
                doc_snip = body
                break
        if doc_snip:
            chunks.append("\n\n" + doc_snip)
        else:
            chunks.append(
                "\n（未读到优先文档；可让用户指定 path，例如 docs/ENGINEERING.md）"
            )

        try:
            st = await self._get_system_status()
            if st.get("success") and st.get("response"):
                sr = str(st["response"]).strip()
                if sr:
                    chunks.append("\n\n### 系统状态摘要\n" + sr[:4_000])
        except Exception as e:
            logger.debug("bootstrap system_status: %s", e)

        return {
            "success": True,
            "response": "\n".join(chunks),
            "source": "workspace_bootstrap",
            "timestamp": datetime.now().isoformat(),
        }

    @staticmethod
    def _workspace_blocked(rel_posix: str) -> bool:
        lower = rel_posix.lower()
        needles = (".env", "secrets/", ".pem", "id_rsa", "__pycache__", "node_modules/", ".git/")
        return any(n in lower for n in needles)

    @staticmethod
    def _under_workspace_prefix(rel_posix: str, prefixes: Tuple[str, ...]) -> bool:
        rel = rel_posix.replace("\\", "/").lstrip("/")
        for p in prefixes:
            base = p.replace("\\", "/").strip().rstrip("/")
            if rel == base or rel.startswith(base + "/"):
                return True
        return False

    def _is_self_maintain_path(self, rel_posix: str) -> bool:
        return self._under_workspace_prefix(rel_posix, WORKSPACE_SELF_MAINTAIN_PREFIXES)

    def _resolve_workspace_path(self, raw: str) -> Tuple[Optional[Path], Optional[str]]:
        root = self._repo_root()
        s = (raw or "").strip().replace("\\", "/").lstrip("/")
        if not s:
            return None, "未提供 path（相对仓库根，例如 src/modules/core/commander_charter.py）"
        if ".." in Path(s).parts:
            return None, "禁止路径中包含 .."
        path = (root / s).resolve()
        try:
            rel = path.relative_to(root)
        except ValueError:
            return None, "路径必须在仓库根目录内"
        rel_posix = str(rel).replace("\\", "/")
        if self._workspace_blocked(rel_posix) and not self._is_commander_unrestricted():
            return None, "该路径禁止通过司令部工作区接口访问"
        if (not self._is_commander_unrestricted()) and (not self._under_workspace_prefix(rel_posix, WORKSPACE_READ_PREFIXES)):
            return None, (
                "路径不在允许前缀内。可读写的目录前缀为: "
                + ", ".join(WORKSPACE_READ_PREFIXES)
            )
        return path, None

    def _path_relative_repo(self, path: Path) -> str:
        try:
            return str(path.relative_to(self._repo_root())).replace("\\", "/")
        except ValueError:
            return str(path)

    def _workspace_dir_tree_lines(
        self,
        root_dir: Path,
        *,
        max_depth: int,
        max_lines: int,
    ) -> List[str]:
        """列出仓库内目录树（供 workspace_read 目录路径使用）。"""
        rel_root = self._path_relative_repo(root_dir)
        out: List[str] = [f"{rel_root}/"]

        def walk(cur: Path, indent: str, depth_left: int) -> None:
            if depth_left < 0 or len(out) >= max_lines:
                return
            try:
                items = sorted(
                    cur.iterdir(),
                    key=lambda p: (not p.is_dir(), p.name.lower()),
                )
            except OSError:
                return
            for p in items:
                if len(out) >= max_lines:
                    break
                name = p.name
                if name.startswith(".") or name in ("__pycache__", "node_modules", ".git"):
                    continue
                slash = "/" if p.is_dir() else ""
                out.append(f"{indent}{name}{slash}")
                if p.is_dir() and depth_left > 0:
                    walk(p, indent + "  ", depth_left - 1)

        walk(root_dir, "  ", max_depth)
        return out

    async def _workspace_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        raw = params.get("path") or params.get("file_path") or ""
        path, err = self._resolve_workspace_path(str(raw))
        if err:
            return {"success": False, "response": err, "timestamp": datetime.now().isoformat()}
        if path.is_dir():
            try:
                max_depth = int(params.get("depth") or params.get("max_depth") or 2)
            except (TypeError, ValueError):
                max_depth = 2
            try:
                max_lines = int(params.get("max_lines") or 220)
            except (TypeError, ValueError):
                max_lines = 220
            max_depth = max(0, min(max_depth, 4))
            max_lines = max(20, min(max_lines, 500))
            lines = self._workspace_dir_tree_lines(path, max_depth=max_depth, max_lines=max_lines)
            rel = self._path_relative_repo(path)
            body = "\n".join(lines)
            return {
                "success": True,
                "response": (
                    f"【已列举目录 {rel}/】（真实列盘，非推断；深度≤{max_depth}，至多约 {max_lines} 行）\n"
                    f"主代码在 src/modules/ 下；需要正文请再指定文件路径做 workspace_read。\n\n{body}"
                ),
                "data": {"path": rel + "/", "lines": len(lines)},
                "timestamp": datetime.now().isoformat(),
            }
        if not path.is_file():
            return {
                "success": False,
                "response": f"不是文件或不存在: {self._path_relative_repo(path)}",
                "timestamp": datetime.now().isoformat(),
            }
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return {
                "success": False,
                "response": f"读取失败: {e}",
                "timestamp": datetime.now().isoformat(),
            }
        max_len = 120_000
        if len(text) > max_len:
            note = f"\n\n… 已截断，原文件约 {len(text)} 字符"
            text = text[:max_len] + note
        rel = self._path_relative_repo(path)
        return {
            "success": True,
            "response": f"【已读取 {rel}】\n\n{text}",
            "data": {"path": rel, "length": len(text)},
            "timestamp": datetime.now().isoformat(),
        }

    async def _workspace_edit(self, params: Dict[str, Any], user_input: str) -> Dict[str, Any]:
        mc = self.main_controller
        if not mc or not hasattr(mc, "edit_code"):
            return {
                "success": False,
                "response": "主控制器不可用或不支持 edit_code",
                "timestamp": datetime.now().isoformat(),
            }
        raw = params.get("path") or params.get("file_path") or ""
        path, err = self._resolve_workspace_path(str(raw))
        if err:
            return {"success": False, "response": err, "timestamp": datetime.now().isoformat()}
        rel = self._path_relative_repo(path)
        if (not self._is_commander_unrestricted()) and (not self._is_self_maintain_path(rel)):
            b = self._get_workspace_boundaries()
            wph = effective_workspace_phrases(b)
            if not any(k in (user_input or "") for k in wph):
                tmpl = b.workspace_edit_message_template or DEFAULT_WORKSPACE_EDIT_MSG
                try:
                    msg = tmpl.format(rel=rel)
                except Exception:
                    msg = DEFAULT_WORKSPACE_EDIT_MSG.format(rel=rel)
                return {
                    "success": True,
                    "response": msg,
                    "needs_confirmation": True,
                    "timestamp": datetime.now().isoformat(),
                }

        op = str(params.get("edit_type") or params.get("operation") or "replace").lower()
        content = str(params.get("content") if params.get("content") is not None else "")
        start_line = params.get("start_line")
        end_line = params.get("end_line")

        if op in ("full", "full_replace", "replace_all", "whole_file"):
            if not path.is_file():
                return {
                    "success": False,
                    "response": "整文件替换要求文件已存在",
                    "timestamp": datetime.now().isoformat(),
                }
            try:
                original = path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                return {"success": False, "response": f"读取失败: {e}", "timestamp": datetime.now().isoformat()}
            line_list = original.split("\n")
            start_line, end_line = 1, max(1, len(line_list))
            op = "replace"

        if op not in ("insert", "delete", "replace"):
            return {
                "success": False,
                "response": f"不支持的 edit_type: {op}（需 insert / delete / replace 或 full_replace）",
                "timestamp": datetime.now().isoformat(),
            }

        try:
            sl = int(start_line) if start_line is not None else None
            el = int(end_line) if end_line is not None else None
        except (TypeError, ValueError):
            return {
                "success": False,
                "response": "start_line / end_line 必须是整数",
                "timestamp": datetime.now().isoformat(),
            }

        if op == "insert":
            if sl is None:
                sl = 1
            el = sl
        elif sl is None or el is None:
            return {
                "success": False,
                "response": f"{op} 需要 start_line 与 end_line（或在 full_replace 时省略行号）",
                "timestamp": datetime.now().isoformat(),
            }

        desc = str(params.get("description") or "ai_command_executor workspace_edit")
        result = await mc.edit_code(
            file_path=str(path),
            edit_type=op,
            content=content,
            start_line=sl,
            end_line=el,
            description=desc,
        )
        ok = False
        msg = ""
        if isinstance(result, dict):
            st = str(result.get("status") or "").lower()
            errs = result.get("errors") or []
            ok = st == "success" and not errs
            msg = str(result.get("message") or "")
        else:
            msg = str(result)
        if not msg:
            msg = "已完成" if ok else "失败"
        return {
            "success": bool(ok),
            "response": f"【写入 {rel}】{msg}" if ok else f"【写入失败 {rel}】{msg}",
            "data": result if isinstance(result, dict) else {"raw": result},
            "timestamp": datetime.now().isoformat(),
        }
    
    async def _execute_intent(
        self,
        intent: Intent,
        user_input: str,
        user_rules: str = "",
        *,
        conversation_scope: Optional[str] = None,
        memory_channel: Optional[str] = None,
    ) -> Dict[str, Any]:
        """执行意图 - 带用户规则检查"""
        action = self._normalize_intent_action(intent.action)
        params = intent.params or {}

        if (not self._is_commander_unrestricted()) and action in ["trade", "market_analysis"]:
            symbol = params.get('symbol', '')
            if symbol in self.blacklist:
                return {
                    "success": True,
                    "response": f"我注意到您提到 {symbol}，但根据您之前的设定，这个交易对在我的黑名单/禁区中，由您自己操作。我不会对它进行任何交易操作。\n\n如果您需要其他交易对的分析或操作，请告诉我。",
                    "timestamp": datetime.now().isoformat()
                }
        
        try:
            if action == "backtest":
                return await self._execute_backtest(params)
            elif action == "strategy_list":
                return await self._get_strategy_list()
            elif action == "strategy_create":
                return await self._create_strategy(params, user_input)
            elif action == "strategy_optimize":
                return await self._optimize_strategy(params, user_input)
            elif action == "market_analysis":
                return await self._analyze_market(params, user_rules)
            elif action == "market_data":
                return await self._get_market_data(params)
            elif action == "balance":
                return await self._get_balance()
            elif action == "positions":
                return await self._get_positions()
            elif action == "signals":
                return await self._get_signals()
            elif action == "risk":
                return await self._analyze_risk()
            elif action == "trade":
                return await self._execute_trade(params, user_input, user_rules)
            elif action == "third_party_data":
                return await self._get_third_party_data(params, user_input)
            elif action == "system_status":
                return await self._get_system_status()
            elif action == "system_inspection":
                return await self._run_system_inspection()
            elif action == "trade_history":
                return await self._get_trade_history(params)
            elif action == "workspace_read":
                return await self._workspace_read(params)
            elif action == "workspace_edit":
                return await self._workspace_edit(params, user_input)
            elif action == "plugin_list":
                return await self._plugin_list()
            elif action == "plugin_reload":
                return await self._plugin_reload(params)
            elif action == "plugin_unload":
                return await self._plugin_unload(params)
            elif action == "plugin_load":
                return await self._plugin_load(params)
            elif action == "chat":
                return await self._general_chat(
                    user_input,
                    user_rules,
                    intent_action="chat",
                    conversation_scope=conversation_scope,
                    memory_channel=memory_channel,
                )
            else:
                return await self._ai_autonomous_action(
                    action,
                    params,
                    user_input,
                    user_rules,
                    conversation_scope=conversation_scope,
                    memory_channel=memory_channel,
                )
                
        except Exception as e:
            logger.error(f"执行意图失败: {action} - {e}")
            return {
                "success": False,
                "response": f"执行 {action} 时遇到问题：{str(e)}",
                "timestamp": datetime.now().isoformat()
            }

    async def _get_trade_history(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """从统一交易历史服务读取记录，并说明与交易所持仓口径可能不一致。"""
        mc = self.main_controller
        if not mc:
            return {"success": False, "response": "主控制器不可用", "timestamp": datetime.now().isoformat()}
        ths = getattr(mc, "trade_history_service", None)
        if not ths:
            return {"success": False, "response": "交易历史服务未初始化", "timestamp": datetime.now().isoformat()}
        try:
            limit = int(params.get("limit", 25) or 25)
            days = int(params.get("days", 30) or 30)
        except (TypeError, ValueError):
            limit, days = 25, 30

        pos_n = 0
        try:
            if hasattr(mc, "okx_exchange") and mc.okx_exchange:
                positions = await mc.okx_exchange.get_positions()
                for p in positions or []:
                    sz = float(p.get("pos", p.get("size", 0)) or 0)
                    if sz != 0:
                        pos_n += 1
        except Exception as e:
            logger.debug(f"读取持仓数量用于对比说明失败: {e}")

        try:
            stats = await ths.get_statistics(days=days, force_refresh=True)
            trades = await ths.get_recent_trades(limit=limit)
        except Exception as e:
            return {"success": False, "response": f"读取交易历史失败: {e}", "timestamp": datetime.now().isoformat()}

        total = 0
        if isinstance(stats, dict):
            total = int(stats.get("total_trades", 0) or 0)

        lines: List[str] = [
            f"📜 交易历史（本机已记录，近 {days} 天统计口径）",
            f"- 已记录成交/平仓笔数: {total}",
        ]
        if pos_n:
            lines.append(
                f"- 当前交易所仍有约 {pos_n} 笔持仓：若上表为 0，多为本地未写入历史、手动/外部终端下单或同步尚未覆盖，不等同于「无仓位」。"
            )
        if not trades:
            lines.append("\n暂无逐笔明细（本地库为空）。")
        else:
            lines.append("\n最近记录（最多展示 20 条）：")
            for i, t in enumerate(trades[:20], 1):
                if not isinstance(t, dict):
                    continue
                ts = str(t.get("timestamp", ""))[:19]
                sym = t.get("symbol", "?")
                side = t.get("side", "?")
                q = t.get("quantity", 0)
                price = t.get("price", 0)
                pnl = t.get("pnl", 0)
                lines.append(f"{i}. {ts} {sym} {side} qty={q} @ {price} pnl={pnl}")

        return {
            "success": True,
            "response": "\n".join(lines),
            "data": {"stats": stats, "trades": trades[:20], "exchange_open_positions_hint": pos_n},
            "timestamp": datetime.now().isoformat(),
        }

    async def _execute_backtest(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行策略回测"""
        try:
            if self.main_controller and hasattr(self.main_controller, 'strategy_manager'):
                sm = self.main_controller.strategy_manager
                
                strategy_configs = getattr(sm, 'strategy_configs', {})
                if strategy_configs:
                    strategy_id = list(strategy_configs.keys())[0]
                    days = params.get('days', 30)
                    end_date = datetime.now()
                    start_date = end_date - timedelta(days=days)
                    
                    result = await sm.backtest_strategy(
                        strategy_id=strategy_id,
                        start_date=start_date,
                        end_date=end_date
                    )
                    
                    return {
                        "success": True,
                        "response": f"""策略回测完成

策略ID: {strategy_id}
回测周期: {days}天

总收益率: {result.get('total_return', 0)*100:.2f}%
最大回撤: {result.get('max_drawdown', 0)*100:.2f}%
夏普比率: {result.get('sharpe_ratio', 0):.2f}
胜率: {result.get('win_rate', 0)*100:.1f}%""",
                        "data": result,
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    return {"success": False, "response": "目前没有可用的策略。我需要先创建策略才能进行回测。"}
            
            return {"success": False, "response": "策略管理器未初始化"}
            
        except Exception as e:
            logger.error(f"回测执行失败: {e}")
            return {"success": False, "response": f"回测失败: {str(e)}"}
    
    async def _get_strategy_list(self) -> Dict[str, Any]:
        """获取策略列表 - 增强版"""
        try:
            if self.main_controller and hasattr(self.main_controller, 'strategy_manager'):
                sm = self.main_controller.strategy_manager
                
                strategies = []
                strategy_configs = getattr(sm, 'strategy_configs', {})
                
                # 详细获取策略信息
                for strategy_id, config in strategy_configs.items():
                    if hasattr(config, 'name'):
                        # 对象类型
                        strategies.append({
                            'id': strategy_id,
                            'name': getattr(config, 'name', 'Unknown'),
                            'type': getattr(config, 'strategy_type', 'unknown'),
                            'status': 'active' if getattr(config, 'enabled', False) else 'inactive',
                            'symbols': getattr(config, 'symbols', []),
                        })
                    else:
                        # 字典类型
                        strategies.append({
                            'id': strategy_id,
                            'name': config.get('name', 'Unknown'),
                            'type': config.get('strategy_type', 'unknown'),
                            'status': 'active' if config.get('enabled', False) else 'inactive',
                            'symbols': config.get('symbols', []),
                        })
                
                if strategies:
                    response = "📊 策略列表\n\n"
                    response += f"已注册策略: {len(strategies)}个\n\n"
                    for s in strategies:
                        status_emoji = "🟢" if s.get('status') == 'active' else "🔴"
                        response += f"{status_emoji} {s.get('name', 'Unknown')}\n"
                        response += f"   ID: {s.get('id', 'N/A')}\n"
                        response += f"   类型: {s.get('type', 'Unknown')}\n"
                        symbols = s.get('symbols', [])
                        if symbols:
                            response += f"   交易对: {', '.join(symbols[:3])}\n"
                        response += "\n"
                    return {"success": True, "response": response, "data": strategies}
                else:
                    # 检查策略管理器是否有其他方式获取策略
                    if hasattr(sm, 'get_all_strategies'):
                        all_strategies = sm.get_all_strategies()
                        if all_strategies:
                            response = "📊 策略列表\n\n"
                            response += f"已注册策略: {len(all_strategies)}个\n\n"
                            for s in all_strategies[:5]:
                                response += f"🟢 {s.get('name', 'Unknown')}\n"
                            return {"success": True, "response": response, "data": all_strategies}
                    
                    return {"success": True, "response": "目前还没有创建任何策略。根据您的授权，我应该自动开发策略。需要我现在开始创建吗？"}
            
            return {"success": False, "response": "策略管理器未初始化"}
            
        except Exception as e:
            logger.error(f"获取策略列表失败: {e}")
            return {"success": False, "response": f"获取策略列表失败: {str(e)}"}
    
    async def _create_strategy(self, params: Dict[str, Any], user_input: str) -> Dict[str, Any]:
        """创建策略"""
        try:
            if self.main_controller and hasattr(self.main_controller, 'strategy_manager'):
                sm = self.main_controller.strategy_manager
                
                if self.llm_integration:
                    prompt = f"""根据用户需求生成交易策略配置：
用户需求：{user_input}

请以JSON格式返回策略配置，包含：
- name: 策略名称
- type: 策略类型 (trend_following, mean_reversion, grid, ml_based)
- parameters: 策略参数
- risk_config: 风险配置

只返回JSON，不要其他内容。"""
                    
                    response = await self.llm_integration.generate(prompt, is_user_input=False)
                    if response:
                        try:
                            strategy_config = json.loads(response.content)
                            
                            strategy_config_data = {
                                "strategy_id": f"auto_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                                "name": strategy_config.get('name', 'AI Generated Strategy'),
                                "description": strategy_config.get('description', 'Auto generated'),
                                "strategy_type": strategy_config.get('type', 'trend_following'),
                                "parameters": strategy_config.get('parameters', {}),
                                "symbols": [s for s in ['BTC/USDT', 'SOL/USDT', 'BNB/USDT'] if s not in self.blacklist],
                                "timeframe": "1h",
                                "initial_capital": 10000.0
                            }
                            
                            if hasattr(sm, 'load_strategy_config'):
                                await sm.load_strategy_config(strategy_config_data)
                            
                            return {
                                "success": True,
                                "response": f"""策略创建成功！

策略名称: {strategy_config.get('name', 'Unknown')}
策略类型: {strategy_config.get('type', 'Unknown')}
交易对: {', '.join(strategy_config_data['symbols'])}

策略已就绪，可以开始运行。""",
                                "data": {"strategy_id": strategy_config_data['strategy_id']}
                            }
                        except json.JSONDecodeError:
                            pass
                
                return {"success": False, "response": "策略创建失败：无法生成策略配置"}
            
            return {"success": False, "response": "策略管理器未初始化"}
            
        except Exception as e:
            return {"success": False, "response": f"创建策略失败: {str(e)}"}
    
    async def _optimize_strategy(self, params: Dict[str, Any], user_input: str) -> Dict[str, Any]:
        """优化策略"""
        try:
            if self.main_controller and hasattr(self.main_controller, 'parameter_optimizer'):
                optimizer = self.main_controller.parameter_optimizer
                
                if self.main_controller.strategy_manager:
                    strategy_configs = getattr(self.main_controller.strategy_manager, 'strategy_configs', {})
                    if strategy_configs:
                        strategy_id = list(strategy_configs.keys())[0]
                        
                        result = await optimizer.optimize(strategy_id=strategy_id)
                        
                        return {
                            "success": True,
                            "response": f"""策略优化完成

策略ID: {strategy_id}
优化结果: {result.get('improvement', 'N/A')}
新参数已应用。""",
                            "data": result
                        }
                
                return {"success": False, "response": "没有可优化的策略，需要先创建策略"}
            
            return {"success": False, "response": "参数优化器未初始化"}
            
        except Exception as e:
            return {"success": False, "response": f"策略优化失败: {str(e)}"}
    
    async def _analyze_market(self, params: Dict[str, Any], user_rules: str = "") -> Dict[str, Any]:
        """分析市场"""
        try:
            symbol = params.get('symbol', 'BTC/USDT')
            
            if symbol in self.blacklist:
                return {
                    "success": True,
                    "response": f"{symbol} 在您的黑名单中，我只提供行情信息，不进行交易操作。"
                }
            
            # 优先使用统一数据源中心（主/备通道 + 质量评分）
            hub = getattr(self.main_controller, "data_source_hub", None) if self.main_controller else None
            if hub:
                try:
                    snapshot = await hub.get_unified_snapshot(symbol)
                    ticker = (
                        ((snapshot or {}).get("渠道A_交易所实时执行数据") or {}).get("ticker")
                        if isinstance(snapshot, dict)
                        else None
                    ) or {}
                    price = float(ticker.get("last") or ticker.get("price") or 0.0)
                    if price > 0:
                        quality = ((snapshot or {}).get("数据质量评估") or {}).get("score", 0.0)
                        # analysis moved to MarketIntelligenceEngine
                        trend = "unknown"
                        try:
                            mc = self.main_controller
                            mi = getattr(mc, "market_intelligence", None) if mc else None
                            if mi and hasattr(mi, "get_symbol_view"):
                                view = await mi.get_symbol_view(symbol, include_snapshot=False)
                                trend = getattr(view, "trend", "unknown") or "unknown"
                        except Exception:
                            trend = "unknown"
                        if self.llm_integration:
                            prompt = f"""分析以下市场数据：

交易对: {symbol}
当前价格: {price}
24h最高: {ticker.get('high', 0)}
24h最低: {ticker.get('low', 0)}
24h成交量: {ticker.get('volume', 0)}
数据质量评分: {quality}
当前趋势标签: {trend}

请提供简洁的市场分析，包括：
1. 趋势判断
2. 关键价位
3. 操作建议"""
                            response = await self.llm_integration.generate(prompt, is_user_input=False)
                            if response:
                                return {
                                    "success": True,
                                    "response": f"{symbol} 市场分析\n\n{response.content}",
                                    "data": {"symbol": symbol, "ticker": ticker, "quality": quality, "trend": trend},
                                }
                        # LLM 降级时，仍返回结构化行情分析，避免“数据获取失败”
                        return {
                            "success": True,
                            "response": (
                                f"{symbol} 市场分析（降级）\n\n"
                                f"价格: {price}\n"
                                f"24h高/低: {ticker.get('high', 0)} / {ticker.get('low', 0)}\n"
                                f"24h量: {ticker.get('volume', 0)}\n"
                                f"趋势: {trend}\n"
                                f"数据质量: {quality}"
                            ),
                            "data": {"symbol": symbol, "ticker": ticker, "snapshot": snapshot},
                        }
                except Exception as hub_e:
                    logger.debug(f"DataSourceHub 市场分析降级: {hub_e}")

            # 回退到交易所 ticker，兼容不同 symbol 格式
            if self.main_controller and hasattr(self.main_controller, 'ai_trading_engine'):
                engine = self.main_controller.ai_trading_engine
                if engine and getattr(engine, "exchange", None):
                    exchange = engine.exchange
                    candidates = [symbol, symbol.replace("/", "-")]
                    if "/SWAP" not in symbol and not symbol.endswith("SWAP"):
                        candidates.append(f"{symbol}/SWAP")
                    ticker = {}
                    for candidate in candidates:
                        try:
                            ticker = await exchange.get_ticker(candidate)
                        except Exception:
                            ticker = {}
                        if isinstance(ticker, dict) and float(ticker.get("last") or ticker.get("price") or 0.0) > 0:
                            break

                    if self.llm_integration and ticker and float(ticker.get("last") or ticker.get("price") or 0.0) > 0:
                        prompt = f"""分析以下市场数据：

交易对: {symbol}
当前价格: {ticker.get('last', ticker.get('price', 0))}
24h最高: {ticker.get('high', 0)}
24h最低: {ticker.get('low', 0)}
24h成交量: {ticker.get('volume', 0)}

请提供简洁的市场分析，包括：
1. 趋势判断
2. 关键价位
3. 操作建议"""
                        response = await self.llm_integration.generate(prompt, is_user_input=False)
                        if response:
                            return {
                                "success": True,
                                "response": f"{symbol} 市场分析\n\n{response.content}",
                                "data": {"symbol": symbol, "ticker": ticker},
                            }

            return {
                "success": False,
                "response": f"市场分析失败：数据获取失败（{symbol}）。建议先执行“排查数据源情况”，系统将返回ETH数据探针与降级源详情。"
            }
            
        except Exception as e:
            return {"success": False, "response": f"市场分析失败: {str(e)}"}
    
    async def _get_market_data(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取市场数据"""
        try:
            symbol = params.get('symbol', 'BTC/USDT')
            
            if self.main_controller and hasattr(self.main_controller, 'okx_exchange'):
                okx = self.main_controller.okx_exchange
                
                ticker = await okx.get_ticker(symbol.replace('/', '-'))
                
                if ticker:
                    return {
                        "success": True,
                        "response": f"""{symbol} 实时行情

当前价格: ${ticker.get('last', 0):,.2f}
24h最高: ${ticker.get('high', 0):,.2f}
24h最低: ${ticker.get('low', 0):,.2f}
24h成交量: {ticker.get('volume', 0):,.2f}
24h涨跌幅: {ticker.get('change', 0)*100:.2f}%""",
                        "data": ticker
                    }
            
            return {"success": False, "response": "获取市场数据失败"}
            
        except Exception as e:
            return {"success": False, "response": f"获取市场数据失败: {str(e)}"}
    
    async def _get_balance(self) -> Dict[str, Any]:
        """获取账户余额"""
        try:
            if self.main_controller and hasattr(self.main_controller, 'okx_exchange'):
                okx = self.main_controller.okx_exchange
                balance = await okx.get_balance()
                
                if balance:
                    response = "账户余额\n\n"
                    total = 0
                    for currency, amount in balance.items():
                        if isinstance(amount, dict):
                            free = amount.get('free', 0)
                            total += amount.get('total', free)
                            if free > 0:
                                response += f"{currency}: {free:,.4f}\n"
                        else:
                            if amount > 0:
                                total += amount
                                response += f"{currency}: {amount:,.4f}\n"
                    response += f"\n总权益: ${total:,.2f}"
                    
                    return {"success": True, "response": response, "data": {"total": total}}
            
            return {"success": False, "response": "获取余额失败：交易所未连接"}
            
        except Exception as e:
            return {"success": False, "response": f"获取余额失败: {str(e)}"}
    
    async def _get_positions(self) -> Dict[str, Any]:
        """获取持仓"""
        try:
            okx = None
            
            # 优先从 main_controller.okx_exchange 获取
            if self.main_controller and hasattr(self.main_controller, 'okx_exchange'):
                okx = self.main_controller.okx_exchange
            
            # 如果 okx_exchange 还没有设置， 尝试从 ai_trading_engine.exchange 获取
            if okx is None and hasattr(self.main_controller, 'ai_trading_engine'):
                engine = self.main_controller.ai_trading_engine
                if hasattr(engine, 'exchange') and engine.exchange:
                    okx = engine.exchange
            
            if okx is None:
                return {"success": True, "response": "当前没有任何持仓"}
            
            positions = await okx.get_positions()
            
            if positions:
                response = "当前持仓\n\n"
                total_pnl = 0
                for pos in positions:
                    side_emoji = "🟢多" if pos.get('side') == 'long' else "🔴空"
                    pnl = pos.get('unrealized_pnl', 0)
                    total_pnl += pnl
                    
                    response += f"{side_emoji} {pos.get('symbol')} | 数量:{pos.get('size', 0):.4f} | 盈亏:${pnl:+,.2f}\n"
                response += f"\n总盈亏: ${total_pnl:+,.2f}"
                
                return {"success": True, "response": response, "data": positions}
            else:
                return {"success": True, "response": "当前没有任何持仓"}
            
            return {"success": False, "response": "获取持仓失败：交易所未连接"}
            
        except Exception as e:
            return {"success": False, "response": f"获取持仓失败: {str(e)}"}
    
    async def _get_signals(self) -> Dict[str, Any]:
        """获取交易信号"""
        try:
            if self.main_controller and hasattr(self.main_controller, 'ai_trading_engine'):
                engine = self.main_controller.ai_trading_engine
                signals = getattr(engine, 'recent_signals', [])
                
                if signals:
                    response = "最新交易信号\n\n"
                    for i, signal in enumerate(signals[:5], 1):
                        action_emoji = {"buy": "🟢买入", "sell": "🔴卖出", "hold": "🟡持有"}.get(
                            signal.get('action', 'hold').lower(), "⚪"
                        )
                        response += f"{i}. {signal.get('symbol')} - {action_emoji}\n"
                        response += f"   置信度: {signal.get('confidence', 0):.0%}\n"
                    return {"success": True, "response": response, "data": signals}
                else:
                    return {"success": True, "response": "暂无交易信号。系统正在分析市场。"}
            
            return {"success": False, "response": "AI交易引擎未初始化"}
            
        except Exception as e:
            return {"success": False, "response": f"获取信号失败: {str(e)}"}
    
    async def _analyze_risk(self) -> Dict[str, Any]:
        """分析风险"""
        try:
            if self.main_controller and hasattr(self.main_controller, 'risk_monitor'):
                monitor = self.main_controller.risk_monitor
                risk_data = await monitor.check_account_risk()
                
                if risk_data:
                    level_emoji = {
                        "low": "🟢",
                        "medium": "🟡",
                        "high": "🟠",
                        "critical": "🔴"
                    }.get(risk_data.risk_level.value, "⚪")
                    
                    return {
                        "success": True,
                        "response": f"""风险评估

风险等级: {level_emoji} {risk_data.risk_level.value.upper()}
保证金比例: {risk_data.margin_ratio*100:.2f}%
未实现盈亏: ${risk_data.unrealized_pnl:+,.2f}
总权益: ${risk_data.total_equity:,.2f}""",
                        "data": {
                            "level": risk_data.risk_level.value,
                            "margin_ratio": risk_data.margin_ratio,
                        }
                    }
            
            return {"success": False, "response": "风险监控未初始化"}
            
        except Exception as e:
            return {"success": False, "response": f"风险分析失败: {str(e)}"}
    
    async def _execute_trade(self, params: Dict[str, Any], user_input: str, user_rules: str = "") -> Dict[str, Any]:
        """执行交易 - 带黑名单检查"""
        try:
            symbol = str(params.get("symbol") or self._resolve_symbol_for_price(user_input) or "").strip()
            
            if symbol in self.blacklist:
                return {
                    "success": True,
                    "response": f"{symbol} 在您的黑名单中，我不会对这个交易对执行任何操作。这个交易对由您自己负责。"
                }
            
            if not self.authorization.get("auto_trading") and not self.authorization.get("full_authorization"):
                return {
                    "success": True,
                    "response": "我理解您想要交易，但您还没有明确授权我执行交易操作。如果您希望我全权负责交易，请告诉我。"
                }
            
            if self.main_controller and hasattr(self.main_controller, "ai_trading_engine"):
                mc = self.main_controller
                engine = mc.ai_trading_engine
                merged = self._extract_trade_params_from_text(user_input)
                merged.update(params or {})

                symbol = str(merged.get("symbol") or symbol or "").strip()
                if not symbol:
                    return {"success": False, "response": "未识别到交易对，请补充如 BTC/USDT。"}

                qty = float(
                    merged.get("quantity")
                    or merged.get("size")
                    or merged.get("amount")
                    or merged.get("value")
                    or 0.01
                )
                side = str(merged.get("side") or "long").strip().lower()
                if side in ("buy", "b"):
                    side = "long"
                elif side in ("sell", "s"):
                    side = "short"

                reason = str(user_input or "user_trade_command")[:240]
                force_close = bool(merged.get("force_close"))
                if force_close:
                    gw = getattr(mc, "execution_gateway", None)
                    if not gw:
                        return {"success": False, "response": "ExecutionGateway 未初始化，无法执行平仓。"}
                    res = await gw.close_swap(
                        symbol=symbol,
                        side=side,
                        size=qty if qty > 0 else None,
                        source="system",
                        reason=reason,
                        force=True,
                    )
                    ok = bool((res or {}).get("success"))
                    return {
                        "success": ok,
                        "response": "强制平仓已提交。" if ok else f"强制平仓失败: {(res or {}).get('error', 'unknown')}",
                        "data": res or {},
                    }

                gw = getattr(mc, "execution_gateway", None)
                if gw:
                    lev = int(getattr(engine, "contract_config", {}).get("default_leverage", 20))
                    market_reasoning = ""
                    try:
                        mi = getattr(mc, "market_intelligence", None)
                        if mi and hasattr(mi, "get_market_state"):
                            st = await mi.get_market_state(symbol)
                            if isinstance(st, dict):
                                trend = str(st.get("trend") or st.get("market_regime") or "").strip()
                                momentum = str(st.get("momentum") or "").strip()
                                vol = st.get("volatility")
                                pieces = []
                                if trend:
                                    pieces.append(f"趋势={trend}")
                                if momentum:
                                    pieces.append(f"动能={momentum}")
                                if vol is not None:
                                    try:
                                        pieces.append(f"波动={float(vol):.4f}")
                                    except Exception:
                                        pieces.append(f"波动={vol}")
                                market_reasoning = " | ".join(pieces)[:180]
                    except Exception:
                        market_reasoning = ""
                    res = await gw.open_swap(
                        symbol=symbol,
                        side=side,
                        size=qty,
                        leverage=lev,
                        source="manual",
                        reason=reason,
                        margin_mode="cross",
                        price=None,
                        context={
                            "via": "ai_command_executor",
                            "user_input": str(user_input)[:240],
                            "manual_approved": True,
                            "strategy": "managed_manual_trade",
                            "decision_reasoning": market_reasoning or str(reason)[:180],
                        },
                    )
                else:
                    res = await engine.execute_trade(
                        symbol=symbol,
                        side=side,
                        quantity=qty,
                        reasoning=reason,
                    )
                ok = bool((res or {}).get("success"))
                sltp_created = False
                sltp_error = None
                if ok:
                    try:
                        slm = getattr(mc, "stop_loss_manager", None)
                        if slm and hasattr(mc, "create_stop_loss_order"):
                            cfg = getattr(slm, "config", None)
                            sl_pct = float(getattr(cfg, "default_stop_loss_percent", 0.03) or 0.03)
                            tp_pct = float(getattr(cfg, "default_take_profit_percent", 0.06) or 0.06)
                            trailing_enabled = bool(getattr(cfg, "enable_trailing_stop", True))
                            trailing_offset = float(getattr(cfg, "initial_trailing_offset", 0.02) or 0.02)
                            entry_price = float((res or {}).get("price") or 0.0)
                            if entry_price <= 0:
                                try:
                                    t = await engine.exchange.get_ticker(symbol)
                                    entry_price = float((t or {}).get("last") or (t or {}).get("close") or 0.0)
                                except Exception:
                                    entry_price = 0.0
                            if entry_price > 0:
                                order = await mc.create_stop_loss_order(
                                    symbol=symbol,
                                    side=side,
                                    entry_price=entry_price,
                                    quantity=qty,
                                    stop_loss_percent=sl_pct,
                                    take_profit_percent=tp_pct,
                                    enable_trailing=trailing_enabled,
                                    trailing_offset=trailing_offset,
                                    metadata={"source": "ai_command_executor", "reason": reason},
                                )
                                sltp_created = order is not None
                    except Exception as e:
                        sltp_error = str(e)
                return {
                    "success": ok,
                    "response": (
                        "开仓指令已提交执行，并已创建止盈止损跟踪。"
                        if ok and sltp_created
                        else ("开仓指令已提交执行。" if ok else f"开仓失败: {(res or {}).get('error', 'unknown')}")
                    ),
                    "data": {
                        **(res or {}),
                        "sltp_created": sltp_created,
                        "sltp_error": sltp_error,
                    },
                }
            
            return {"success": False, "response": "AI交易引擎未初始化"}
            
        except Exception as e:
            return {"success": False, "response": f"交易执行失败: {str(e)}"}
    
    async def _get_third_party_data(self, params: Dict[str, Any], user_input: str) -> Dict[str, Any]:
        """获取第三方数据 - 检查所有数据源"""
        try:
            response = "📊 第三方数据系统状态\n\n"
            data_sources = []
            
            # 1. 检查多源数据融合系统
            if self.main_controller and hasattr(self.main_controller, 'ai_trading_engine'):
                engine = self.main_controller.ai_trading_engine
                if engine and (
                    (hasattr(engine, 'multi_source_fusion') and engine.multi_source_fusion)
                    or (hasattr(engine, 'data_fusion') and engine.data_fusion)
                ):
                    data_sources.append({
                        'name': '多源数据融合系统',
                        'type': 'fusion',
                        'status': 'running',
                        'description': '综合分析市场情绪、技术指标、链上数据'
                    })
            
            # 2. 检查第三方数据集成器
            if self.main_controller and (
                hasattr(self.main_controller, 'third_party_integrator')
                or hasattr(self.main_controller, 'third_party_data_integrator')
            ):
                integrator = (
                    getattr(self.main_controller, "third_party_data_integrator", None)
                    or getattr(self.main_controller, "third_party_integrator", None)
                )
                if (
                    not integrator
                    and hasattr(self.main_controller, "ai_trading_engine")
                    and self.main_controller.ai_trading_engine
                ):
                    integrator = getattr(self.main_controller.ai_trading_engine, "third_party_data", None)
                if integrator:
                    data_sources.append({
                        'name': '第三方数据集成器',
                        'type': 'integrator',
                        'status': 'running',
                        'description': '整合新闻、社交媒体、链上数据'
                    })
            
            # 3. 检查插件管理器
            if self.main_controller and hasattr(self.main_controller, 'plugin_manager'):
                pm = self.main_controller.plugin_manager
                if pm:
                    plugins_info = pm.get_all_plugin_info() if hasattr(pm, 'get_all_plugin_info') else {}
                    for plugin_name, info in plugins_info.items():
                        plugin_type = info.get('type', 'unknown')
                        if plugin_type == 'data_provider' or 'data' in plugin_name.lower():
                            data_sources.append({
                                'name': plugin_name,
                                'type': plugin_type,
                                'status': 'running' if info.get('enabled', False) else 'stopped',
                            })
            
            # 4. 数据源健康与 ETH 探针（优先读 DataIntegration / DataSourceHub）
            try:
                if self.main_controller and hasattr(self.main_controller, "get_data_integration"):
                    di = self.main_controller.get_data_integration()
                    if di and hasattr(di, "get_source_health_report"):
                        health = di.get_source_health_report()
                        degraded = (health or {}).get("degraded_sources") or []
                        response += "\n【外部数据源健康】\n"
                        response += f"状态: {'退化' if degraded else '正常'}\n"
                        if degraded:
                            response += f"退化源: {', '.join(degraded[:6])}\n"
            except Exception as e:
                logger.debug(f"第三方数据健康检查失败: {e}")

            try:
                hub = getattr(self.main_controller, "data_source_hub", None) if self.main_controller else None
                if hub:
                    eth_ticker = await hub.get_ticker("ETH/USDT")
                    eth_price = float((eth_ticker or {}).get("last") or (eth_ticker or {}).get("price") or 0.0)
                    response += "\n【ETH数据探针】\n"
                    if eth_price > 0:
                        response += f"状态: 正常 | 价格: {eth_price}\n"
                    else:
                        response += "状态: 异常（未拿到有效价格）\n"
            except Exception as e:
                logger.debug(f"ETH 数据探针失败: {e}")

            if data_sources:
                for source in data_sources:
                    status = "🟢" if source.get('status') == 'running' else "🔴"
                    response += f"{status} {source.get('name')} ({source.get('type')})\n"
                    response += f"   功能: {source.get('description', '数据提供')}\n"
                return {"success": True, "response": response, "data": data_sources}
            else:
                return {"success": True, "response": "暂无第三方数据源插件。可以使用插件系统添加数据源。"}
            
        except Exception as e:
            return {"success": False, "response": f"获取第三方数据失败: {str(e)}"}
    
    async def _get_system_status(self) -> Dict[str, Any]:
        """获取系统状态（自然表达版，避免模板化播报）。"""
        try:
            if self.main_controller:
                mc = self.main_controller

                # 注意：不得使用 (a and b and obj) 直接作为 dict 值——真值链会返回 obj 本身，json.dumps 会失败
                _ms_fusion = None
                if hasattr(mc, "ai_trading_engine") and mc.ai_trading_engine:
                    _ms_fusion = getattr(mc.ai_trading_engine, "multi_source_fusion", None) or getattr(
                        mc.ai_trading_engine, "data_fusion", None
                    )
                if _ms_fusion is None:
                    _ms_fusion = getattr(mc, "multi_source_data_fusion", None)

                modules = {
                    "策略管理器": hasattr(mc, 'strategy_manager') and mc.strategy_manager is not None,
                    "AI交易引擎": hasattr(mc, 'ai_trading_engine') and mc.ai_trading_engine is not None,
                    "OKX交易所": hasattr(mc, 'okx_exchange') and mc.okx_exchange is not None,
                    "风险监控": hasattr(mc, 'risk_monitor') and mc.risk_monitor is not None,
                    "LLM集成": hasattr(mc, 'llm_integration') and mc.llm_integration is not None,
                    "记忆系统": self.unified_memory is not None,
                    "回测系统": hasattr(mc, 'enhanced_backtester') and mc.enhanced_backtester is not None,
                    # 兼容历史命名：multi_source_fusion / data_fusion / multi_source_data_fusion（仅布尔，勿嵌入实例）
                    "多源数据融合": _ms_fusion is not None,
                    # 兼容 third_party_integrator / third_party_data 两种挂载方式
                    "第三方数据集成": (
                        (hasattr(mc, 'third_party_data_integrator') and mc.third_party_data_integrator is not None)
                        or (hasattr(mc, 'third_party_integrator') and mc.third_party_integrator is not None)
                        or (hasattr(mc, 'ai_trading_engine') and mc.ai_trading_engine and hasattr(mc.ai_trading_engine, 'third_party_data') and mc.ai_trading_engine.third_party_data is not None)
                    ),
                    "AI核心决策引擎": hasattr(mc, 'ai_core') and mc.ai_core is not None,
                }

                status_payload: Dict[str, Any] = {
                    "modules": modules,
                    "strategy": {},
                    "data_sources": {},
                    "external_data_health": {},
                    "ai_core": {},
                    "user_rules": {},
                    "positions": [],
                }

                # 策略详情
                if hasattr(mc, 'strategy_manager') and mc.strategy_manager:
                    sm = mc.strategy_manager
                    strategies = getattr(sm, 'strategy_configs', {})
                    status_payload["strategy"]["count"] = len(strategies)
                    names = []
                    if strategies:
                        for _sid, config in list(strategies.items())[:3]:
                            name = getattr(config, 'name', None) if hasattr(config, 'name') else (config.get('name') if isinstance(config, dict) else None)
                            if name:
                                names.append(str(name))
                    status_payload["strategy"]["examples"] = names

                # 第三方数据详情
                # 1) 插件体系（若存在）
                if hasattr(mc, 'plugin_manager') and mc.plugin_manager:
                    pm = mc.plugin_manager
                    plugins_info = pm.get_all_plugin_info() if hasattr(pm, 'get_all_plugin_info') else {}
                    status_payload["data_sources"]["plugins_loaded"] = len(plugins_info)
                # 2) 代码内置 ThirdPartyDataIntegrator（若存在）
                try:
                    tpi = getattr(mc, "third_party_data_integrator", None)
                    if not tpi and hasattr(mc, "ai_trading_engine") and mc.ai_trading_engine:
                        tpi = getattr(mc.ai_trading_engine, "third_party_data", None)
                    if tpi:
                        prov = getattr(tpi, "providers", {}) or {}
                        disabled = list(getattr(tpi, "_disabled_providers", set()) or [])
                        status_payload["data_sources"]["builtin_count"] = len(prov)
                        status_payload["data_sources"]["builtin_disabled_count"] = len(disabled)
                        if disabled:
                            # DataSource Enum or str
                            ds = []
                            for x in disabled[:6]:
                                try:
                                    ds.append(getattr(x, "value", str(x)))
                                except Exception:
                                    ds.append(str(x))
                            status_payload["data_sources"]["disabled_examples"] = ds
                except Exception:
                    pass

                # 外部数据源降级状态（如果系统挂载了 DataIntegration）
                try:
                    data_integration = mc.get_data_integration() if hasattr(mc, "get_data_integration") else None
                    if data_integration and hasattr(data_integration, "get_source_health_report"):
                        ds_health = data_integration.get_source_health_report()
                        degraded = ds_health.get("degraded_sources") or []
                        status_payload["external_data_health"]["degraded_count"] = len(degraded)
                        status_payload["external_data_health"]["degraded_examples"] = degraded[:5]
                except Exception as e:
                    logger.debug(f"读取外部数据源健康失败: {e}")

                # AI核心决策引擎详情
                if hasattr(mc, 'ai_core') and mc.ai_core:
                    ai_core = mc.ai_core
                    status = ai_core.get_status() if hasattr(ai_core, 'get_status') else {}
                    modules_status = status.get('modules', {})
                    status_payload["ai_core"]["running"] = bool(status.get("running"))
                    connected = [k for k, v in modules_status.items() if v]
                    status_payload["ai_core"]["connected_modules"] = connected
                    guards = status.get("execution_guards", {})
                    gcfg = guards.get("config", {})
                    gprof = guards.get("adaptive_profile", {})
                    g_global_at = guards.get("global_last_tuned_at")
                    gstats = guards.get("stats", {})
                    status_payload["ai_core"]["execution_guards"] = {
                        "config": gcfg,
                        "adaptive_profile": gprof,
                        "global_last_tuned_at": g_global_at,
                        "stats": gstats,
                    }

                status_payload["user_rules"] = {
                    "blacklist_empty": not bool(self.blacklist),
                    "full_authorization": bool(self.authorization.get("full_authorization")),
                }

                positions_meta: Dict[str, Any] = {"source": "none", "error": None}
                # 获取持仓（仅接口事实；失败则明确标记，禁止模型脑补）
                if hasattr(mc, "okx_exchange") and mc.okx_exchange:
                    positions_meta["source"] = "exchange"
                    try:
                        positions = await mc.okx_exchange.get_positions()
                        if positions:
                            for pos in positions[:5]:
                                symbol = pos.get("instId", pos.get("symbol", "Unknown"))
                                side = pos.get("posSide", pos.get("side", "unknown"))
                                size = pos.get("pos", pos.get("size", 0))
                                status_payload["positions"].append(
                                    {"symbol": symbol, "side": str(side), "size": size}
                                )
                    except Exception as e:
                        positions_meta["error"] = str(e)
                        logger.debug("查询持仓信息失败: %s", e)
                status_payload["evidence"] = {
                    "positions_source": positions_meta.get("source"),
                    "positions_error": positions_meta.get("error"),
                    "positions_count": len(status_payload.get("positions") or []),
                }

                honesty: Dict[str, Any] = {
                    "status_summary_mode": "llm" if _status_summary_use_llm() else "deterministic",
                    "positions_from_exchange_attempted": positions_meta.get("source") == "exchange",
                    "positions_in_payload": len(status_payload.get("positions") or []),
                }

                if _status_summary_use_llm() and self.llm_integration:
                    bundle = (getattr(self, "_workspace_startup_bundle", None) or "").strip()
                    persona_hint = (
                        f"\n【人格与画像节选】\n{bundle[:2500]}\n"
                        if bundle
                        else ""
                    )
                    strict = (
                        "\n【硬约束】JSON 中 evidence.positions_count 为 0 或 evidence.positions_error 非空时，"
                        "禁止描述任何具体持仓、手数、多空方向、盈亏；不得用「上周/之前对话」补全。"
                        "modules 仅为布尔挂载，不得推断「策略正在实盘跑单」除非 strategy 与接口有明确依据。\n"
                    )
                    free_prompt = f"""{persona_hint}
【司令部宪章 · 原则锚点】
{CHARTER}
{strict}
下面是当前系统状态（JSON，事实以这里为准）：
{_json_dumps_status_snapshot(status_payload)}

用符合「人格与画像」的口吻、像真人一样说；别按表格机械念。挑最重要几点说清；有矛盾就点出来；最后最多问一句接下来你最关心啥。
"""
                    try:
                        llm_resp = await self.llm_integration.generate(
                            free_prompt,
                            is_user_input=False,
                        )
                        if llm_resp and getattr(llm_resp, "content", None):
                            out = {
                                "success": True,
                                "response": llm_resp.content,
                                "data": status_payload,
                                "honesty": honesty,
                            }
                            return _finalize_commander_payload(out)
                    except Exception as e:
                        logger.debug(f"系统状态自然化生成失败，降级简答: {e}")

                text = _format_system_status_deterministic(status_payload, positions_meta=positions_meta)
                out = {"success": True, "response": text, "data": status_payload, "honesty": honesty}
                return _finalize_commander_payload(out)
            
            return {"success": False, "response": "主控制器未初始化"}
            
        except Exception as e:
            return {"success": False, "response": f"获取系统状态失败: {str(e)}"}

    @staticmethod
    def _grounded_chat_enabled() -> bool:
        """先拉事实再让模型说话（根上减少空演）；OPENCLAW_COMMANDER_GROUNDED_CHAT=0 可关。"""
        raw = str(os.environ.get("OPENCLAW_COMMANDER_GROUNDED_CHAT", "1") or "").strip().lower()
        return raw not in ("0", "false", "no", "off")

    @staticmethod
    def _chat_requires_tool_grounding(text: str) -> bool:
        """
        判断本轮是否「需要接口/读盘事实」才能负责任地回答。
        纯情绪短骂（无事实关键词）返回 False，避免无谓拉接口。
        """
        t = (text or "").strip()
        if len(t) < 4:
            return False
        if len(t) <= 56 and ("骗" in t or "忽悠" in t):
            if not re.search(r"(读|文档|代码|系统|项目|目录|价格|行情|持仓|余额|架构|模块)", t):
                return False
        patterns = (
            r"(文档|目录|结构|架构|代码|项目|仓库|readme|模块|src/|读本|读取|读一下|了解|熟悉|全景)",
            r"(系统|诊断|巡检|运行|就绪)",
            r"(价格|行情|报价|现价|ticker|多少.?钱|u价)",
            r"(持仓|仓位|余额|账户|权益)",
            r"(别编|不要编|瞎编|胡说|说谎|骗人|忽悠|实事求是|不要骗|不要扯)",
        )
        if "workspace" in t.lower() or "architecture" in t.lower():
            return True
        return any(re.search(p, t, re.IGNORECASE) for p in patterns)

    async def _prefetch_chat_grounding(self, utter: str) -> str:
        """在调用 LLM 前自动拉取可注入的事实（与话题正则互补，不靠无限黑名单）。"""
        parts: List[str] = []
        need_doc = bool(
            re.search(
                r"(文档|目录|结构|架构|代码|项目|仓库|readme|模块|src|读本|读取|读一下|了解|熟悉|全景)",
                utter,
                re.I,
            )
        )
        need_sys = bool(re.search(r"(系统|诊断|巡检|运行|就绪)", utter, re.I))
        need_px = bool(
            self._resolve_symbol_for_price(utter)
            or re.search(r"(价格|行情|报价|现价|ticker|多少.?钱|u价)", utter, re.I)
        )
        need_acc = bool(re.search(r"(持仓|仓位|余额|账户|权益)", utter, re.I))

        if need_doc:
            try:
                for rel in ("docs/ENGINEERING.md", "docs/README.md", "README.md", "ARCHITECTURE.md"):
                    r = await self._workspace_read({"path": rel})
                    if r.get("success") and (r.get("response") or ""):
                        body = str(r["response"])[:5500]
                        parts.append(body)
                        break
                p = self._repo_root() / "src" / "modules"
                if p.is_dir():
                    lines = self._workspace_dir_tree_lines(p, max_depth=2, max_lines=72)
                    parts.append("【src/modules 真实列举】\n" + "\n".join(lines))
            except Exception as e:
                logger.debug("prefetch doc grounding: %s", e)

        if need_sys:
            try:
                st = await self._get_system_status()
                if st.get("success") and st.get("response"):
                    parts.append("【系统状态】\n" + str(st["response"])[:4000])
            except Exception as e:
                logger.debug("prefetch system grounding: %s", e)

        if need_px:
            try:
                sym = self._resolve_symbol_for_price(utter) or str(
                    os.environ.get("OPENCLAW_DEFAULT_PRICE_SYMBOL", "ETH/USDT")
                ).strip()
                px = await self._answer_live_price_from_exchange(sym)
                if px.get("success") and px.get("response"):
                    parts.append(str(px["response"])[:2800])
            except Exception as e:
                logger.debug("prefetch price grounding: %s", e)

        if need_acc:
            try:
                bal = await self._get_balance()
                if bal.get("success") and bal.get("response"):
                    parts.append(str(bal["response"])[:2200])
                pos = await self._get_positions()
                if pos.get("success") and pos.get("response"):
                    parts.append(str(pos["response"])[:3200])
            except Exception as e:
                logger.debug("prefetch account grounding: %s", e)

        if not parts:
            return "（本轮自动拉取未得到可用事实；请勿编造路径、目录树、价格或持仓。）"
        return "\n\n---\n\n".join(parts)[:16000]

    async def _resolve_grounding_anchor(
        self,
        utter: str,
        grounding_facts: Optional[str],
    ) -> str:
        if grounding_facts is not None:
            return grounding_facts
        if not self._grounded_chat_enabled() or not self._chat_requires_tool_grounding(utter):
            return ""
        return await self._prefetch_chat_grounding(utter)

    async def _general_chat(
        self,
        user_input: str,
        user_rules: str = "",
        *,
        intent_action: str = "chat",
        conversation_scope: Optional[str] = None,
        memory_channel: Optional[str] = None,
        grounding_facts: Optional[str] = None,
    ) -> Dict[str, Any]:
        """通用对话 - 带用户规则上下文；事实类话题可先注入 TOOL_ANCHOR（见 GROUNDED_CHAT）。"""
        try:
            utter = self._strip_user_utterance_for_routing(user_input)
            anchor_text = await self._resolve_grounding_anchor(utter, grounding_facts)
            anchor_section = ""
            if self._grounded_chat_enabled() and self._chat_requires_tool_grounding(utter):
                if anchor_text:
                    anchor_section = (
                        f"\n\n【事实锚点 TOOL_ANCHOR — 仅可复述其中事实】\n{anchor_text}\n【/TOOL_ANCHOR】\n"
                        f"凡路径、目录、文件内容、现价、持仓、余额、系统是否在线，只许来自上方锚点；"
                        f"锚点未写到的不得编造；禁止「[调用：…]」与未经验证的目录代码块。\n"
                    )
                else:
                    anchor_section = (
                        "\n\n【事实锚点】为空。不得编造仓库结构/价格/持仓；禁止假装已执行工具。\n"
                    )
            if self.llm_integration:
                use_work_context = bool(intent_action and intent_action != "chat")
                if use_work_context:
                    system_context = await self._get_system_context()
                    task_mem = ""
                    if self.unified_memory:
                        try:
                            task_mem = await format_task_memory_block(
                                self.unified_memory,
                                intent_action,
                                user_input=user_input,
                                config_manager=getattr(self.main_controller, "config_manager", None)
                                if self.main_controller
                                else None,
                            )
                        except Exception as e:
                            logger.debug(f"任务记忆片段注入跳过: {e}")
                    prompt = f"""{user_rules}

{CONTEXT_FRAMING_FOR_CHAT}

{system_context}
{task_mem}

用户消息：{user_input}
{anchor_section}
按上面「人格与画像」与宪章自然说人话；涉及盘面/仓位时只信上文里给的数据，没有就承认没有，别编。
若本回复没有出现「接口/系统」给出的具体数字，就不要写任何价位或区间。
禁止用「[调用：…]」或假装已跑 workspace_read / 系统诊断；没有上文真实读盘/诊断内容时不要写仓库目录树或模块路径。"""
                else:
                    prompt = f"""{user_rules}

{CONTEXT_FRAMING_FOR_CHAT}

用户消息：{user_input}
{anchor_section}
按「人格与画像」与宪章像真人一样说话：有温度、有判断；话题可以很宽。不必套模板、不必列条。没把握就说没把握。
若本回复没有附带系统接口返回的价位，就不要编造价格或「外部联网」假查询。
禁止用「[调用：…]」「假装已执行 workspace_read / 系统诊断」等话术；没有本消息上方由系统注入的真实读盘结果时，不要写本仓库目录树或模块名。需要文档或目录时说明应走系统的 workspace_read / system_status，由执行器跑完再答。"""

                response = await self.llm_integration.generate(
                    prompt,
                    is_user_input=False,
                    conversation_scope=conversation_scope,
                    memory_channel=memory_channel,
                )

                if response:
                    return {
                        "success": True,
                        "response": response.content,
                        "timestamp": datetime.now().isoformat()
                    }

            return {"success": False, "response": "AI服务暂时不可用"}
            
        except Exception as e:
            return {"success": False, "response": f"对话处理失败: {str(e)}"}

    @staticmethod
    def _nonzero_exchange_positions(positions: Optional[List]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for p in positions or []:
            if not isinstance(p, dict):
                continue
            try:
                sz = float(p.get("pos", p.get("size", 0)) or 0)
            except (TypeError, ValueError):
                sz = 0.0
            if abs(sz) > 1e-12:
                out.append(p)
        return out

    async def _refresh_account_cache_if_stale(self, mc: Any, max_age_sec: float = 50.0) -> None:
        """对话生成上下文前适度刷新交易所余额/持仓缓存，供 SLTP 与司令部一致。"""
        if not hasattr(mc, "force_sync_account_state"):
            return
        need = True
        ls = getattr(mc, "_latest_account_state", None)
        if isinstance(ls, dict) and ls.get("timestamp"):
            try:
                raw = str(ls["timestamp"]).replace("Z", "")
                t = datetime.fromisoformat(raw[:26])
                if (datetime.now() - t).total_seconds() < max_age_sec:
                    need = False
            except Exception:
                pass
        if not need:
            return
        try:
            await mc.force_sync_account_state(reason="ai_context")
        except Exception as e:
            logger.debug(f"刷新账户缓存失败: {e}")

    async def _authoritative_position_context_lines(self, mc: Any) -> List[str]:
        """把交易所接口返回的持仓快照放在上下文前部（纯数据，不给模型下行为指令）。"""
        await self._refresh_account_cache_if_stale(mc)
        lines: List[str] = [
            "\n" + "=" * 50,
            "【交易所·持仓快照】",
        ]
        pos: Optional[List] = None
        try:
            if hasattr(mc, "okx_exchange") and mc.okx_exchange:
                pos = await mc.okx_exchange.get_positions()
        except Exception as e:
            lines.append(f"拉取持仓失败: {e}")
            lines.append("=" * 50)
            return lines

        active = self._nonzero_exchange_positions(pos)
        lines.append(f"非零持仓笔数: {len(active)}")
        if not active:
            lines.append("（本次接口返回无非零仓位）")
        for p in active[:12]:
            sym = p.get("instId") or p.get("symbol", "?")
            side = p.get("side", "?")
            psr = p.get("posSide_raw", "")
            sz = p.get("size", p.get("pos", 0))
            upl = p.get("unrealized_pnl", p.get("upl", 0))
            psr_note = f" OKXposSide={psr}" if psr else ""
            lines.append(f"  • {sym} {side}{psr_note} size={sz} 未实现盈亏≈{upl}")

        try:
            if getattr(mc, "stop_loss_manager", None):
                st = mc.stop_loss_manager.get_stats()
                lines.append(
                    f"止盈止损跟踪器: 当前跟踪订单数≈{st.get('total_orders', 0)} "
                    f"(动态调整次数 {st.get('dynamic_adjustments', 0)})"
                )
        except Exception as e:
            logger.debug(f"读取 SLTP 统计失败: {e}")

        ls = getattr(mc, "_latest_account_state", None)
        if isinstance(ls, dict) and ls.get("timestamp"):
            lines.append(f"最近账户同步时间: {ls.get('timestamp')}")
        lines.append("=" * 50)
        return lines
    
    async def _get_system_context(self) -> str:
        """获取系统上下文 - 包含所有模块详细状态"""
        context_parts = []
        
        context_parts.append(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        if self.main_controller:
            mc = self.main_controller
            try:
                context_parts.extend(await self._authoritative_position_context_lines(mc))
            except Exception as e:
                logger.debug(f"权威持仓上下文失败: {e}")
            
            context_parts.append("\n" + "=" * 50)
            context_parts.append("【系统模块状态】")
            context_parts.append("=" * 50)
            
            # 1. 策略管理器状态
            if hasattr(mc, 'strategy_manager') and mc.strategy_manager:
                sm = mc.strategy_manager
                strategies = getattr(sm, 'strategy_configs', {})
                context_parts.append(f"\n📊 策略管理器: ✅ 已连接")
                context_parts.append(f"   - 已注册策略: {len(strategies)}个")
                if strategies:
                    for sid, config in list(strategies.items())[:5]:
                        name = getattr(config, 'name', 'Unknown') if hasattr(config, 'name') else config.get('name', 'Unknown')
                        stype = getattr(config, 'strategy_type', 'unknown') if hasattr(config, 'strategy_type') else config.get('strategy_type', 'unknown')
                        context_parts.append(f"   - {name} ({stype})")
            else:
                context_parts.append(f"\n📊 策略管理器: ❌ 未连接")
            
            # 2. 回测系统状态
            if hasattr(mc, 'enhanced_backtester') and mc.enhanced_backtester:
                context_parts.append(f"\n📈 回测系统: ✅ 已连接")
                context_parts.append(f"   - 回测引擎: BacktestEngine")
            else:
                context_parts.append(f"\n📈 回测系统: ❌ 未连接")
            
            # 3. 第三方数据系统状态 - 检查多个可能的数据源
            third_party_connected = False
            third_party_info = []
            
            # 检查多源数据融合系统
            if hasattr(mc, 'multi_source_data_fusion') and mc.multi_source_data_fusion:
                third_party_connected = True
                third_party_info.append("多源数据融合系统")
            
            # 检查第三方数据集成器
            # 注意：项目现状主要使用 third_party_data_integrator（或 engine.third_party_data）
            if hasattr(mc, 'third_party_data_integrator') and mc.third_party_data_integrator:
                third_party_connected = True
                third_party_info.append("第三方数据集成器(third_party_data_integrator)")

            # 兼容旧字段名 third_party_integrator（历史遗留）
            if hasattr(mc, 'third_party_integrator') and mc.third_party_integrator:
                third_party_connected = True
                third_party_info.append("第三方数据集成器(third_party_integrator)")
            
            # 检查插件管理器
            if hasattr(mc, 'plugin_manager') and mc.plugin_manager:
                pm = mc.plugin_manager
                plugins_info = pm.get_all_plugin_info() if hasattr(pm, 'get_all_plugin_info') else {}
                if plugins_info:
                    third_party_connected = True
                    third_party_info.append(f"插件管理器({len(plugins_info)}个插件)")
            
            # 检查数据源管理器
            if hasattr(mc, 'data_source_manager') and mc.data_source_manager:
                third_party_connected = True
                third_party_info.append("数据源管理器")

            # 兼容：AI交易引擎内部第三方数据集成器
            if hasattr(mc, 'ai_trading_engine') and mc.ai_trading_engine and hasattr(mc.ai_trading_engine, 'third_party_data') and mc.ai_trading_engine.third_party_data:
                third_party_connected = True
                third_party_info.append("AI交易引擎.third_party_data")
            
            if third_party_connected:
                context_parts.append(f"\n🔌 第三方数据系统: ✅ 已连接")
                for info in third_party_info:
                    context_parts.append(f"   - {info}")
                # 显示最近获取的数据
                try:
                    if hasattr(mc, 'multi_source_data_fusion') and mc.multi_source_data_fusion:
                        recent_data = getattr(mc.multi_source_data_fusion, '_recent_analysis', {})
                        if recent_data:
                            context_parts.append(f"   - 最近分析: {list(recent_data.keys())[:3]}")
                except Exception as e:
                    logger.debug(f"读取第三方数据最近分析失败: {e}")
            else:
                context_parts.append(f"\n🔌 第三方数据系统: ❌ 未连接")
            
            # 4. AI交易引擎状态（内存持仓可能与交易所不一致，以上方【交易所·实时持仓】为准）
            if hasattr(mc, 'ai_trading_engine') and mc.ai_trading_engine:
                engine = mc.ai_trading_engine
                context_parts.append(f"\n🤖 AI交易引擎: ✅ 已连接")
                positions = getattr(engine, 'positions', {}) or {}
                context_parts.append(f"   - 引擎内存持仓条目: {len(positions)}（可能与交易所不一致）")
            else:
                context_parts.append(f"\n🤖 AI交易引擎: ❌ 未连接")
            
            # 5. OKX交易所状态
            if hasattr(mc, 'okx_exchange') and mc.okx_exchange:
                context_parts.append(f"\n💱 OKX交易所: ✅ 已连接")
                try:
                    balance = await mc.okx_exchange.get_balance()
                    if balance:
                        total = sum(v if isinstance(v, (int, float)) else v.get('free', 0) for v in balance.values())
                        context_parts.append(f"   - 账户总资产: ${total:,.2f}")
                except Exception as e:
                    logger.debug(f"读取账户余额失败: {e}")
            else:
                context_parts.append(f"\n💱 OKX交易所: ❌ 未连接")
            
            # 6. 风险监控状态
            if hasattr(mc, 'risk_monitor') and mc.risk_monitor:
                context_parts.append(f"\n⚠️ 风险监控: ✅ 已连接")
            else:
                context_parts.append(f"\n⚠️ 风险监控: ❌ 未连接")
            
            # 7. AI核心决策引擎状态
            if hasattr(mc, 'ai_core') and mc.ai_core:
                ai_core = mc.ai_core
                status = ai_core.get_status() if hasattr(ai_core, 'get_status') else {}
                modules = status.get('modules', {})
                context_parts.append(f"\n🧠 AI核心决策引擎: ✅ 已连接")
                context_parts.append(f"   - 运行状态: {'运行中' if status.get('running') else '已停止'}")
                connected_modules = [k for k, v in modules.items() if v]
                context_parts.append(f"   - 已连接模块: {', '.join(connected_modules)}")
            else:
                context_parts.append(f"\n🧠 AI核心决策引擎: ❌ 未连接")
            
            # 8. LLM集成状态
            if hasattr(mc, 'llm_integration') and mc.llm_integration:
                context_parts.append(f"\n💬 LLM集成: ✅ 已连接")
            else:
                context_parts.append(f"\n💬 LLM集成: ❌ 未连接")
            
            # 9. 记忆系统状态
            if self.unified_memory:
                context_parts.append(f"\n📝 记忆系统: ✅ 已连接")
            else:
                context_parts.append(f"\n📝 记忆系统: ❌ 未连接")

            if hasattr(mc, "skill_manager") and mc.skill_manager:
                sm = mc.skill_manager
                reg = sorted(sm.skills.keys())
                context_parts.append(
                    f"\n🔧 SkillManager: ✅ 已注册 {len(reg)} 个技能 — {', '.join(reg)}"
                )
                context_parts.append(
                    "   自然语言可触发 workspace_read / workspace_edit 读取或修改允许路径；"
                    "巡检与健康检查仍走 system_inspection 或司令部 API。"
                )
                context_parts.append(
                    f"   自维护区（编辑可无「确认修改」口令）: {', '.join(WORKSPACE_SELF_MAINTAIN_PREFIXES)}"
                )
            
            context_parts.append("\n" + "=" * 50)

            try:
                ths = getattr(mc, "trade_history_service", None)
                if ths:
                    st = await ths.get_statistics(days=30, force_refresh=False)
                    if isinstance(st, dict):
                        context_parts.append("\n【本机成交记录统计】")
                        context_parts.append(f"  近30天已记录笔数: {st.get('total_trades', 0)}")
            except Exception as e:
                logger.debug(f"交易统计上下文失败: {e}")
        
        return "\n".join(context_parts)
    
    async def _ai_autonomous_action(
        self,
        action: str,
        params: Dict[str, Any],
        user_input: str,
        user_rules: str = "",
        *,
        conversation_scope: Optional[str] = None,
        memory_channel: Optional[str] = None,
    ) -> Dict[str, Any]:
        """AI自主行动"""
        try:
            routed = await self._route_skill_action(action=action, params=params, user_input=user_input, user_rules=user_rules)
            if routed is not None:
                return routed
            if self.llm_integration:
                system_context = await self._get_system_context()
                task_mem = ""
                if self.unified_memory:
                    try:
                        task_mem = await format_task_memory_block(
                            self.unified_memory,
                            str(action or "chat"),
                            user_input=user_input,
                            config_manager=getattr(self.main_controller, "config_manager", None)
                            if self.main_controller
                            else None,
                        )
                    except Exception:
                        pass
                prompt = f"""{user_rules}

{CONTEXT_FRAMING_FOR_CHAT}

{system_context}
{task_mem}

用户消息: {user_input}
当前动作标签: {action}

请按宪章与上文自然回复；需要执行或说明时再引用系统数据。"""

                response = await self.llm_integration.generate(
                    prompt,
                    is_user_input=False,
                    conversation_scope=conversation_scope,
                    memory_channel=memory_channel,
                )
                
                if response:
                    return {
                        "success": True,
                        "response": response.content,
                        "autonomous": True,
                        "timestamp": datetime.now().isoformat()
                    }
            
            return await self._general_chat(
                user_input,
                user_rules,
                intent_action=str(action or "chat"),
                conversation_scope=conversation_scope,
                memory_channel=memory_channel,
            )
            
        except Exception as e:
            return {"success": False, "response": f"AI自主行动失败: {str(e)}"}

    async def _route_skill_action(self, action: str, params: Dict[str, Any], user_input: str, user_rules: str = "") -> Optional[Dict[str, Any]]:
        """
        技能包动作映射：把“能力名”映射到可执行函数，避免只聊天不执行。
        """
        act = str(action or "").strip().lower()
        alias = {
            "strategy.research.run": "strategy_create",
            "strategy.backtest.run": "backtest",
            "strategy.optimize.run": "strategy_optimize",
            "execution.open.force": "trade_force_open",
            "execution.close.force": "trade_force_close",
            "risk.sltp.adjust": "risk_sltp_status",
            "system.inspection.run": "system_inspection",
            "memory.summary.daily": "memory_daily_summary",
        }.get(act, act)

        if alias == "strategy_create":
            return await self._create_strategy(params, user_input)
        if alias == "backtest":
            return await self._execute_backtest(params)
        if alias == "strategy_optimize":
            return await self._optimize_strategy(params, user_input)
        if alias == "trade_force_open":
            if self._is_commander_unrestricted():
                p = dict(params or {})
                p.setdefault("force", True)
                return await self._execute_trade(p, user_input or "强制开仓", user_rules)
            b = self._get_workspace_boundaries()
            hph = effective_high_risk_phrases(b)
            if not any(k in (user_input or "") for k in hph):
                msg = b.force_open_message or DEFAULT_FORCE_OPEN_MSG
                return {
                    "success": True,
                    "response": msg,
                    "needs_confirmation": True,
                    "timestamp": datetime.now().isoformat(),
                }
            p = dict(params or {})
            p.setdefault("force", True)
            return await self._execute_trade(p, user_input or "强制开仓", user_rules)
        if alias == "trade_force_close":
            if self._is_commander_unrestricted():
                p = dict(params or {})
                p.setdefault("force_close", True)
                return await self._execute_trade(p, user_input or "强制平仓", user_rules)
            b = self._get_workspace_boundaries()
            hph = effective_high_risk_phrases(b)
            if not any(k in (user_input or "") for k in hph):
                msg = b.force_close_message or DEFAULT_FORCE_CLOSE_MSG
                return {
                    "success": True,
                    "response": msg,
                    "needs_confirmation": True,
                    "timestamp": datetime.now().isoformat(),
                }
            p = dict(params or {})
            p.setdefault("force_close", True)
            return await self._execute_trade(p, user_input or "强制平仓", user_rules)
        if alias == "risk_sltp_status":
            return await self._get_sltp_status()
        if alias == "system_inspection":
            return await self._run_system_inspection()
        if alias == "memory_daily_summary":
            ok = await self._auto_daily_summary(force=True)
            return {
                "success": bool(ok),
                "response": "已执行每日复盘总结并写入记忆" if ok else "每日复盘总结执行失败",
                "timestamp": datetime.now().isoformat(),
            }
        if alias == "plugin_list":
            return await self._plugin_list()
        if alias == "plugin_reload":
            return await self._plugin_reload(params)
        if alias == "plugin_load":
            return await self._plugin_load(params)
        if alias == "plugin_unload":
            return await self._plugin_unload(params)
        return None

    async def _run_system_inspection(self) -> Dict[str, Any]:
        mc = self.main_controller
        if not mc:
            return {"success": False, "response": "主控制器不可用"}
        try:
            if hasattr(mc, "skill_manager") and mc.skill_manager:
                report = await mc.skill_manager.run_health_check({"source": "ai_command_executor"})
                # 生成“摘要 + 明细”，避免消息通道只收到一句话。
                def _is_benign_failure_dict(r: Dict[str, Any]) -> bool:
                    msg = str((r or {}).get("message") or "")
                    lower_msg = msg.lower()
                    benign_markers = (
                        "缺少编辑请求",
                        "缺少开发请求",
                        "缺少审查请求",
                        "missing request",
                        "no request",
                    )
                    return any(m in msg for m in benign_markers) or any(m in lower_msg for m in benign_markers)

                results = report.get("results") if isinstance(report, dict) else None
                results = results if isinstance(results, list) else []
                actionable = [
                    r
                    for r in results
                    if isinstance(r, dict)
                    and str(r.get("status") or "").lower() == "failed"
                    and not _is_benign_failure_dict(r)
                ]
                warnings = [
                    r
                    for r in results
                    if isinstance(r, dict)
                    and str(r.get("status") or "").lower() == "success"
                    and str(r.get("priority") or "").lower() in {"high"}
                    and isinstance(r.get("recommendations"), list)
                    and len(r.get("recommendations") or []) > 0
                ]

                lines = [
                    f"系统巡检完成：{report.get('status')}，可执行失败 {report.get('actionable_failures', len(actionable))} 项",
                ]
                if actionable:
                    lines.append("")
                    lines.append("失败明细（可执行）：")
                    for i, r in enumerate(actionable[:6], start=1):
                        name = str(r.get("skill_name") or "unknown")
                        msg = str(r.get("message") or "").strip()
                        recs = r.get("recommendations") or []
                        rec_line = f"；建议：{recs[0]}" if isinstance(recs, list) and recs else ""
                        # 控制长度，避免 TG 过长导致截断
                        if len(msg) > 180:
                            msg = msg[:180] + "…"
                        lines.append(f"{i}) {name}: {msg}{rec_line}")
                    if len(actionable) > 6:
                        lines.append(f"... 还有 {len(actionable) - 6} 项（可在UI/司令部快照查看完整结果）")
                if warnings:
                    lines.append("")
                    lines.append("告警/建议：")
                    for i, r in enumerate(warnings[:4], start=1):
                        name = str(r.get("skill_name") or "unknown")
                        recs = r.get("recommendations") or []
                        if isinstance(recs, list) and recs:
                            lines.append(f"- {name}: {str(recs[0])[:180]}")

                return {
                    "success": True,
                    "response": "\n".join(lines).strip(),
                    "data": report,
                    "timestamp": datetime.now().isoformat(),
                }
            return await self._get_system_status()
        except Exception as e:
            return {"success": False, "response": f"系统巡检失败: {e}"}

    async def _plugin_list(self) -> Dict[str, Any]:
        mc = self.main_controller
        if not mc:
            return {"success": False, "response": "主控制器不可用", "timestamp": datetime.now().isoformat()}
        try:
            info = mc.get_all_plugin_info() if hasattr(mc, "get_all_plugin_info") else {}
            items = []
            for name, meta in (info or {}).items():
                if isinstance(meta, dict):
                    items.append(
                        f"- {name}: enabled={meta.get('enabled')} version={meta.get('version', '')} desc={meta.get('description', '')}"
                    )
                else:
                    items.append(f"- {name}")
            txt = "插件列表：\n" + ("\n".join(items) if items else "（当前无已加载插件）")
            return {"success": True, "response": txt, "data": {"plugins": info}, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "response": f"读取插件列表失败: {e}", "timestamp": datetime.now().isoformat()}

    async def _plugin_reload(self, params: Dict[str, Any]) -> Dict[str, Any]:
        mc = self.main_controller
        name = str((params or {}).get("plugin_name") or (params or {}).get("name") or "").strip()
        if not mc or not name:
            return {"success": False, "response": "需要 plugin_name", "timestamp": datetime.now().isoformat()}
        try:
            ok = await mc.reload_plugin(name) if hasattr(mc, "reload_plugin") else False
            return {
                "success": bool(ok),
                "response": f"插件重载{'成功' if ok else '失败'}: {name}",
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "response": f"插件重载失败: {e}", "timestamp": datetime.now().isoformat()}

    async def _plugin_unload(self, params: Dict[str, Any]) -> Dict[str, Any]:
        mc = self.main_controller
        name = str((params or {}).get("plugin_name") or (params or {}).get("name") or "").strip()
        if not mc or not name:
            return {"success": False, "response": "需要 plugin_name", "timestamp": datetime.now().isoformat()}
        try:
            ok = await mc.unload_plugin(name) if hasattr(mc, "unload_plugin") else False
            return {
                "success": bool(ok),
                "response": f"插件卸载{'成功' if ok else '失败'}: {name}",
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "response": f"插件卸载失败: {e}", "timestamp": datetime.now().isoformat()}

    async def _plugin_load(self, params: Dict[str, Any]) -> Dict[str, Any]:
        mc = self.main_controller
        if not mc:
            return {"success": False, "response": "主控制器不可用", "timestamp": datetime.now().isoformat()}
        name = str((params or {}).get("plugin_name") or (params or {}).get("name") or "").strip()
        cfg = (params or {}).get("plugin_config") or (params or {}).get("config") or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}
        if not isinstance(cfg, dict):
            cfg = {}
        if not name:
            return {"success": False, "response": "需要 plugin_name", "timestamp": datetime.now().isoformat()}
        try:
            ok = await mc.load_plugin(name, cfg) if hasattr(mc, "load_plugin") else False
            return {
                "success": bool(ok),
                "response": f"插件加载{'成功' if ok else '失败'}: {name}",
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "response": f"插件加载失败: {e}", "timestamp": datetime.now().isoformat()}

    async def _get_sltp_status(self) -> Dict[str, Any]:
        mc = self.main_controller
        if not mc or not hasattr(mc, "stop_loss_manager") or not mc.stop_loss_manager:
            return {"success": False, "response": "止盈止损管理器不可用"}
        try:
            stats = mc.stop_loss_manager.get_stats()
            return {
                "success": True,
                "response": (
                    f"SLTP状态：总订单={stats.get('total_orders', 0)}，"
                    f"止损触发={stats.get('stop_loss_triggered', 0)}，"
                    f"止盈触发={stats.get('take_profit_triggered', 0)}，"
                    f"动态调整={stats.get('dynamic_adjustments', 0)}"
                ),
                "data": stats,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "response": f"获取SLTP状态失败: {e}"}
    
    async def start_autonomous_work(self) -> None:
        """启动自主工作循环"""
        if self._is_minimal_free_mode():
            logger.info("极简自由模式开启：跳过自主工作循环")
            return
        if self._autonomous_running:
            return
        
        self._autonomous_running = True
        logger.info("🚀 启动自主工作循环")
        
        asyncio.create_task(self._autonomous_work_loop())
    
    async def stop_autonomous_work(self) -> None:
        """停止自主工作循环"""
        self._autonomous_running = False
        logger.info("停止自主工作循环")
    
    async def _autonomous_work_loop(self) -> None:
        """自主工作循环"""
        while self._autonomous_running:
            try:
                await asyncio.sleep(SLEEP_60S)
                
                if not self.authorization.get("auto_trading"):
                    continue
                
                logger.info("🔄 执行自主工作循环...")
                
                await self._auto_strategy_check()
                
                await self._auto_market_scan()
                
                await self._auto_daily_summary()

                # Weekly summary: lightweight + idempotent
                await self._auto_weekly_summary()
                
            except Exception as e:
                logger.error(f"自主工作循环出错: {e}")
    
    async def _auto_strategy_check(self) -> None:
        """自动检查策略"""
        if not self.main_controller or not hasattr(self.main_controller, 'strategy_manager'):
            return
        
        sm = (
            self.main_controller.get_strategy_manager()
            if hasattr(self.main_controller, "get_strategy_manager")
            else self.main_controller.strategy_manager
        )
        strategy_configs = getattr(sm, 'strategy_configs', {})
        
        if not strategy_configs and self.authorization.get("auto_strategy"):
            logger.info("📊 没有策略，自动创建...")
            await self._create_strategy({}, "自动创建趋势跟踪策略")
    
    async def _auto_market_scan(self) -> None:
        """自动扫描市场"""
        symbols = ['BTC/USDT', 'SOL/USDT', 'BNB/USDT']
        symbols = [s for s in symbols if s not in self.blacklist]
        
        for symbol in symbols[:2]:
            try:
                await self._analyze_market({'symbol': symbol})
                await asyncio.sleep(SLEEP_5S)
            except Exception as e:
                logger.error(f"扫描 {symbol} 失败: {e}")

    async def _auto_daily_summary(self, force: bool = False) -> bool:
        """
        每日自动总结：写入经验/历史记忆，支持交易复盘与策略改进。
        """
        today = datetime.now().strftime("%Y-%m-%d")
        if not force and self._last_daily_summary_date == today:
            return True
        mc = self.main_controller
        if not mc:
            return False
        try:
            ths = getattr(mc, "trade_history_service", None)
            stats = await ths.get_statistics(days=1, force_refresh=True) if ths and hasattr(ths, "get_statistics") else {}
            summary = (
                f"每日交易复盘 {today}: 总交易={stats.get('total_trades', 0)}, "
                f"胜率={stats.get('win_rate', 0)}%, 总盈亏={stats.get('total_pnl', 0)}, "
                f"最大回撤={stats.get('max_drawdown', 0)}"
            )
            if self.unified_memory and hasattr(self.unified_memory, "add_memory"):
                # Idempotency: don't generate duplicates for the same day
                try:
                    backend = getattr(self.unified_memory, "memory_backend", None)
                    if backend and hasattr(backend, "_memories"):
                        for _id, entry in (getattr(backend, "_memories", {}) or {}).items():
                            md = dict(getattr(entry, "metadata", {}) or {})
                            if md.get("kind") == "daily_summary" and md.get("date") == today:
                                self._last_daily_summary_date = today
                                return True
                except Exception:
                    pass

                key = SummaryKey(kind="daily_summary", date=today)
                await self.unified_memory.add_memory(
                    memory_type="daily_summary",
                    content=summary,
                    summary="每日交易复盘自动总结（working）",
                    metadata=base_metadata(
                        source_module="ai_command_executor",
                        kind="daily_summary",
                        extra={"date": today, "stats": stats, **key.to_metadata()},
                    ),
                    source_module="ai_command_executor",
                    importance=0.72,
                    tags=tags(kind_tag("summary"), kind_tag("daily")),
                )
                # Also write an experience-level lesson (compact, actionable)
                await self.unified_memory.add_memory(
                    memory_type="lesson_learned",
                    content=f"经验/教训({today}): {summary}",
                    summary="每日经验教训（experience）",
                    metadata=base_metadata(
                        source_module="ai_command_executor",
                        kind="daily_lessons",
                        extra={"date": today, "stats": stats, **key.to_metadata()},
                    ),
                    source_module="ai_command_executor",
                    importance=0.78,
                    tags=tags(kind_tag("lesson"), kind_tag("daily")),
                )
            self._last_daily_summary_date = today
            return True
        except Exception as e:
            logger.warning(f"每日自动总结失败: {e}")
            return False

    async def _auto_weekly_summary(self, force: bool = False) -> bool:
        """每周自动总结：汇总近7天关键指标，写入长期经验（experience）。"""
        now = datetime.now()
        year, week, _ = now.isocalendar()
        week_key = f"{year}-W{int(week):02d}"
        mc = self.main_controller
        if not mc:
            return False
        try:
            # Idempotency
            if not force:
                try:
                    backend = getattr(self.unified_memory, "memory_backend", None) if self.unified_memory else None
                    if backend and hasattr(backend, "_memories"):
                        for _id, entry in (getattr(backend, "_memories", {}) or {}).items():
                            md = dict(getattr(entry, "metadata", {}) or {})
                            if md.get("kind") == "weekly_summary" and md.get("date") == week_key:
                                return True
                except Exception:
                    pass

            ths = getattr(mc, "trade_history_service", None)
            stats = await ths.get_statistics(days=7, force_refresh=True) if ths and hasattr(ths, "get_statistics") else {}
            text = (
                f"每周交易总结 {week_key}: 总交易={stats.get('total_trades', 0)}, "
                f"胜率={stats.get('win_rate', 0)}%, 总盈亏={stats.get('total_pnl', 0)}, "
                f"最大回撤={stats.get('max_drawdown', 0)}"
            )
            if self.unified_memory and hasattr(self.unified_memory, "add_memory"):
                key = SummaryKey(kind='weekly_summary', date=week_key)
                await self.unified_memory.add_memory(
                    memory_type="lesson_learned",
                    content=f"经验/教训({week_key}): {text}",
                    summary="每周经验教训（experience）",
                    metadata=base_metadata(
                        source_module="ai_command_executor",
                        kind="weekly_summary",
                        extra={"date": week_key, "stats": stats, **key.to_metadata()},
                    ),
                    source_module="ai_command_executor",
                    importance=0.8,
                    tags=tags(kind_tag("lesson"), kind_tag("weekly")),
                )
            return True
        except Exception as e:
            logger.warning(f"每周自动总结失败: {e}")
            return False
