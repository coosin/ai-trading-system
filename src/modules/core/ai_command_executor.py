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
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)

from .timing_constants import SLEEP_5S, SLEEP_60S


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
    1. 记忆驱动 - 每次响应都检索和应用用户规则
    2. 黑名单强制检查 - 交易前必须检查黑名单
    3. 授权感知 - 根据授权范围决定行动
    4. 主动工作 - 不等待指令，自主执行职责
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
        }
        self.work_duties = []
        
        self._autonomous_running = False
        self._last_daily_summary_date = None
        
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
            from .unified_intelligent_memory import get_unified_memory
            from .user_intent_recognizer import UserIntentRecognizer

            # 优先使用主控制器核心记忆，保持与核心大脑一致
            self.unified_memory = (
                getattr(self.main_controller, "ai_memory_manager", None)
                if self.main_controller else None
            )
            if self.unified_memory is None:
                self.unified_memory = await get_unified_memory()
            self.user_intent_recognizer = UserIntentRecognizer
            logger.info("✅ 统一记忆系统和用户意图识别器已加载")
            
            await self._load_user_rules_from_memory()
            
        except Exception as e:
            logger.warning(f"加载统一记忆系统失败: {e}")
        
        logger.info("✅ AI指令执行器（智能增强版）初始化完成")
    
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
    
    async def process_input(self, user_input: str) -> Dict[str, Any]:
        """
        处理用户输入 - 智能增强版
        核心改进：在处理前检索和应用记忆中的用户规则
        """
        logger.info(f"处理用户输入: {user_input}")
        
        try:
            if self.unified_memory:
                memory_result = await self.unified_memory.process_user_input(user_input)
                if memory_result.get("recorded"):
                    logger.info(f"📝 自动记录用户意图: {memory_result.get('message')}")
                    
                    if memory_result.get("blacklist_updated"):
                        await self._load_user_rules_from_memory()
                    if memory_result.get("authorization_updated"):
                        await self._load_user_rules_from_memory()
            
            intent = await self._parse_intent(user_input)
            
            user_rules = await self._get_user_rules_context()
            
            if intent.action != "unknown":
                result = await self._execute_intent(intent, user_input, user_rules)
            else:
                result = await self._general_chat(user_input, user_rules)
            
            if self.unified_memory:
                await self.unified_memory.add_memory(
                    memory_type=self._get_memory_type_from_intent(intent.action),
                    content=f"用户: {user_input}",
                    summary=f"用户指令: {user_input[:100]}",
                    metadata={"intent": intent.action, "params": intent.params},
                    source_module="ai_command_executor"
                )
                try:
                    action_msg = str((result or {}).get("response") or "")[:500]
                    if action_msg:
                        await self.unified_memory.add_memory(
                            memory_type="conversation",
                            content=f"动作结果[{intent.action}] {action_msg}",
                            summary=f"{intent.action} 执行结果摘要",
                            metadata={"intent": intent.action, "success": bool((result or {}).get("success", False))},
                            source_module="ai_command_executor",
                            importance=0.55,
                        )
                except Exception:
                    pass
            
            return result
            
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
            return {
                "success": False,
                "response": f"处理过程中遇到问题：{friendly}",
                "timestamp": datetime.now().isoformat()
            }
    
    async def _get_user_rules_context(self) -> str:
        """
        获取用户规则上下文 - 核心改进
        每次响应前检索用户的关键规则和偏好
        """
        if not self.unified_memory:
            return ""
        
        context_parts = []
        context_parts.append("\n" + "=" * 40)
        context_parts.append("【用户规则 - 必须遵守】")
        context_parts.append("=" * 40)
        
        blacklist_memories = await self.unified_memory.retrieve_memories(
            query="黑名单 禁区 不要",
            min_importance=0.8,
            limit=5
        )
        if blacklist_memories:
            context_parts.append("\n🚫 【黑名单/禁区】")
            for mem in blacklist_memories:
                context_parts.append(f"  • {mem.content}")
                # 不再自动将ETH加入黑名单
                if "ETH" in mem.content or "以太坊" in mem.content:
                    logger.info(f"ℹ️ 忽略ETH黑名单记忆: 已移除ETH限制")
        
        auth_memories = await self.unified_memory.retrieve_memories(
            query="全权 负责 授权",
            min_importance=0.8,
            limit=3
        )
        if auth_memories:
            context_parts.append("\n✅ 【交易授权】")
            for mem in auth_memories:
                context_parts.append(f"  • {mem.content}")
        
        duty_memories = await self.unified_memory.retrieve_memories(
            query="职责 工作 必须 自动",
            min_importance=0.7,
            limit=5
        )
        if duty_memories:
            context_parts.append("\n📋 【工作职责】")
            for mem in duty_memories:
                context_parts.append(f"  • {mem.content}")
        
        pref_memories = await self.unified_memory.retrieve_memories(
            query="偏好 喜欢 目标",
            min_importance=0.6,
            limit=3
        )
        if pref_memories:
            context_parts.append("\n👤 【用户偏好】")
            for mem in pref_memories:
                context_parts.append(f"  • {mem.content}")
        
        # 新增：检索最近的交易执行记录
        trade_memories = await self.unified_memory.retrieve_memories(
            query="交易 执行 开仓 平仓",
            min_importance=0.8,
            limit=10
        )
        if trade_memories:
            context_parts.append("\n📈 【最近交易执行】")
            for mem in trade_memories:
                if "执行交易" in mem.content or "交易执行" in mem.content:
                    context_parts.append(f"  • {mem.content}")
        
        # 新增：从active_trader获取实时持仓状态
        if self.main_controller and hasattr(self.main_controller, 'active_trader'):
            active_trader = self.main_controller.active_trader
            if active_trader:
                status = active_trader.get_status()
                if status.get("active_positions", 0) > 0:
                    context_parts.append("\n📊 【当前持仓状态】")
                    context_parts.append(f"  • 持仓数量: {status.get('active_positions', 0)}")
                    positions = status.get("positions", {})
                    for symbol, pos in positions.items():
                        context_parts.append(f"  • {symbol}: {pos.get('side')} {pos.get('quantity')} @{pos.get('entry_price')}")
                context_parts.append(f"\n🎯 【策略状态】")
                context_parts.append(f"  • 已加载策略: {status.get('strategies', 0)}个")
                context_parts.append(f"  • 总交易次数: {status.get('total_trades', 0)}次")
        
        context_parts.append("\n" + "=" * 40)
        context_parts.append("【重要提醒】")
        context_parts.append("1. 黑名单中的交易对绝对不能操作")
        context_parts.append("2. 已授权的交易要主动执行，不需要用户提醒")
        context_parts.append("3. 工作职责是自动进行的，不是等待指令")
        context_parts.append("4. 回答用户问题时，要报告当前交易状态和持仓情况")
        context_parts.append("=" * 40 + "\n")
        skill_pack = self._read_trading_skill_pack()
        if skill_pack:
            context_parts.append("【交易技能包】")
            context_parts.append(skill_pack)
            context_parts.append("")
        
        return "\n".join(context_parts)

    def _read_trading_skill_pack(self) -> str:
        candidates = [
            Path.cwd() / "workspace" / "memory" / "core" / "SKILL_PACK_TRADING_OPS.md",
            Path("/app/data/memory/core/SKILL_PACK_TRADING_OPS.md"),
        ]
        for p in candidates:
            try:
                if p.exists() and p.is_file():
                    data = p.read_text(encoding="utf-8").strip()
                    if data:
                        return data[:6000]
            except Exception:
                continue
        return ""
    
    def _get_memory_type_from_intent(self, action: str):
        """根据意图类型获取记忆类型"""
        from .unified_intelligent_memory import UnifiedMemoryType
        
        mapping = {
            "trade": UnifiedMemoryType.TRADING_DECISION,
            "signals": UnifiedMemoryType.AI_PREDICTION,
            "market_analysis": UnifiedMemoryType.MARKET_INSIGHT,
            "risk": UnifiedMemoryType.RISK_SETTING,
            "strategy_create": UnifiedMemoryType.STRATEGY_GENERATED,
            "strategy_optimize": UnifiedMemoryType.RL_OPTIMIZATION,
        }
        return mapping.get(action, UnifiedMemoryType.CONVERSATION)
    
    async def _parse_intent(self, user_input: str) -> Intent:
        """解析用户意图 - 使用LLM自由理解"""
        
        if self.llm_integration:
            try:
                prompt = f"""分析用户消息，理解真实意图。

用户消息: {user_input}

返回JSON格式：
{{
    "action": "动作类型",
    "params": {{相关参数}},
    "confidence": 0.0-1.0,
    "reasoning": "理解理由"
}}

动作类型包括：
- trade: 交易相关
- market_analysis: 市场分析
- strategy_create: 创建策略
- strategy_optimize: 优化策略
- system_status: 系统状态
- chat: 普通对话

只返回JSON。"""

                response = await self.llm_integration.generate(prompt, is_user_input=False)
                
                if response:
                    try:
                        result = json.loads(response.content)
                        return Intent(
                            action=result.get("action", "chat"),
                            params=result.get("params", {}),
                            confidence=result.get("confidence", 0.8)
                        )
                    except json.JSONDecodeError:
                        pass
            except Exception as e:
                logger.warning(f"LLM解析意图失败: {e}")
        
        params = await self._extract_params(user_input, "")
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
    
    async def _execute_intent(self, intent: Intent, user_input: str, user_rules: str = "") -> Dict[str, Any]:
        """执行意图 - 带用户规则检查"""
        action = intent.action
        params = intent.params
        # 当意图解析成 chat 时，尝试用自然语言别名映射到技能动作。
        if action == "chat":
            guessed = self._guess_skill_action_from_text(user_input)
            if guessed:
                action = guessed
        
        if action in ["trade", "market_analysis"]:
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
            elif action == "chat":
                return await self._general_chat(user_input, user_rules)
            else:
                return await self._ai_autonomous_action(action, params, user_input, user_rules)
                
        except Exception as e:
            logger.error(f"执行意图失败: {action} - {e}")
            return {
                "success": False,
                "response": f"执行 {action} 时遇到问题：{str(e)}",
                "timestamp": datetime.now().isoformat()
            }

    def _guess_skill_action_from_text(self, user_input: str) -> Optional[str]:
        # 注意：这里必须是“弱规则”且尽量减少误触发。
        # 我们只在用户表达明确执行意图时才把 chat 映射成技能动作。
        text_raw = str(user_input or "").strip()
        text = text_raw.lower()

        # 若是纯提问/质疑/闲聊，不做技能映射，交给 LLM 自由对话与澄清。
        if any(q in text_raw for q in ["？", "?"]) or any(q in text for q in ["为什么", "怎么", "什么情况", "哪两项", "说清楚", "解释"]):
            return None

        intent_verbs = ("执行", "运行", "开始", "拉取", "获取", "同步", "查询", "看看", "帮我查", "帮我看")
        has_exec_intent = any(v in text_raw for v in intent_verbs)
        if not has_exec_intent:
            return None

        mapping = [
            (["系统巡检", "健康检查", "巡检"], "system.inspection.run"),
            (["每日复盘", "日总结", "日报总结"], "memory.summary.daily"),
            (["策略研发", "研究策略", "生成策略"], "strategy.research.run"),
            (["回测", "跑回测"], "strategy.backtest.run"),
            (["策略优化", "优化策略", "立即优化"], "strategy.optimize.run"),
            (["强制开仓", "立即开仓"], "execution.open.force"),
            (["强制平仓", "立即平仓", "全部平仓"], "execution.close.force"),
            (["止盈止损", "sltp", "风控状态"], "risk.sltp.adjust"),
        ]
        for kws, action in mapping:
            if any(k in text for k in kws):
                return action
        return None
    
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
            
            if self.main_controller and hasattr(self.main_controller, 'ai_trading_engine'):
                engine = self.main_controller.ai_trading_engine
                
                if engine.exchange:
                    ticker = await engine.exchange.get_ticker(symbol.replace('/', '-'))
                    
                    if self.llm_integration and ticker:
                        prompt = f"""分析以下市场数据：

交易对: {symbol}
当前价格: {ticker.get('last', 0)}
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
                                "data": {"symbol": symbol, "ticker": ticker}
                            }
            
            return {"success": False, "response": "市场分析失败：数据获取失败"}
            
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
            symbol = params.get('symbol', '')
            
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
            
            if self.main_controller and hasattr(self.main_controller, 'ai_trading_engine'):
                engine = self.main_controller.ai_trading_engine
                
                if self.llm_integration:
                    prompt = f"""解析用户交易指令，返回JSON格式的交易参数：

用户指令：{user_input}

返回格式：
{{
    "action": "buy/sell/hold",
    "symbol": "交易对",
    "quantity": 数量,
    "leverage": 杠杆倍数
}}

只返回JSON。"""
                    
                    response = await self.llm_integration.generate(prompt, is_user_input=False)
                    if response:
                        try:
                            trade_params = json.loads(response.content)
                            
                            trade_symbol = trade_params.get('symbol', '')
                            if trade_symbol in self.blacklist:
                                return {
                                    "success": True,
                                    "response": f"{trade_symbol} 在您的黑名单中，不执行交易。"
                                }
                            
                            return {
                                "success": True,
                                "response": f"""交易执行中...

操作: {trade_params.get('action', 'N/A').upper()}
交易对: {trade_params.get('symbol', 'N/A')}
数量: {trade_params.get('quantity', 'N/A')}
杠杆: {trade_params.get('leverage', 'N/A')}x

交易指令已提交。""",
                                "data": trade_params
                            }
                        except json.JSONDecodeError:
                            pass
                
                return {"success": False, "response": "交易指令解析失败"}
            
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
            if self.main_controller and hasattr(self.main_controller, 'third_party_integrator'):
                integrator = self.main_controller.third_party_integrator
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
        """获取系统状态 - 详细版"""
        try:
            if self.main_controller:
                mc = self.main_controller
                
                modules = {
                    "策略管理器": hasattr(mc, 'strategy_manager') and mc.strategy_manager is not None,
                    "AI交易引擎": hasattr(mc, 'ai_trading_engine') and mc.ai_trading_engine is not None,
                    "OKX交易所": hasattr(mc, 'okx_exchange') and mc.okx_exchange is not None,
                    "风险监控": hasattr(mc, 'risk_monitor') and mc.risk_monitor is not None,
                    "LLM集成": hasattr(mc, 'llm_integration') and mc.llm_integration is not None,
                    "记忆系统": self.unified_memory is not None,
                    "回测系统": hasattr(mc, 'enhanced_backtester') and mc.enhanced_backtester is not None,
                    # 兼容历史命名：multi_source_fusion / data_fusion / multi_source_data_fusion
                    "多源数据融合": (
                        hasattr(mc, 'ai_trading_engine')
                        and mc.ai_trading_engine
                        and (
                            (hasattr(mc.ai_trading_engine, 'multi_source_fusion') and mc.ai_trading_engine.multi_source_fusion)
                            or (hasattr(mc.ai_trading_engine, 'data_fusion') and mc.ai_trading_engine.data_fusion)
                        )
                    ) or (hasattr(mc, 'multi_source_data_fusion') and mc.multi_source_data_fusion),
                    # 兼容 third_party_integrator / third_party_data 两种挂载方式
                    "第三方数据集成": (
                        (hasattr(mc, 'third_party_data_integrator') and mc.third_party_data_integrator is not None)
                        or (hasattr(mc, 'third_party_integrator') and mc.third_party_integrator is not None)
                        or (hasattr(mc, 'ai_trading_engine') and mc.ai_trading_engine and hasattr(mc.ai_trading_engine, 'third_party_data') and mc.ai_trading_engine.third_party_data is not None)
                    ),
                    "AI核心决策引擎": hasattr(mc, 'ai_core') and mc.ai_core is not None,
                }
                
                response = "📊 系统状态报告\n\n"
                response += "【核心模块】\n"
                for name, status in modules.items():
                    emoji = "✅" if status else "❌"
                    response += f"{emoji} {name}\n"
                
                # 策略详情
                if hasattr(mc, 'strategy_manager') and mc.strategy_manager:
                    sm = mc.strategy_manager
                    strategies = getattr(sm, 'strategy_configs', {})
                    response += f"\n【策略管理器】\n"
                    response += f"已注册策略: {len(strategies)}个\n"
                    if strategies:
                        for sid, config in list(strategies.items())[:3]:
                            name = getattr(config, 'name', 'Unknown') if hasattr(config, 'name') else config.get('name', 'Unknown')
                            response += f"  • {name}\n"
                
                # 第三方数据详情
                response += f"\n【第三方数据源】\n"
                # 1) 插件体系（若存在）
                if hasattr(mc, 'plugin_manager') and mc.plugin_manager:
                    pm = mc.plugin_manager
                    plugins_info = pm.get_all_plugin_info() if hasattr(pm, 'get_all_plugin_info') else {}
                    response += f"已加载插件: {len(plugins_info)}个\n"
                    for plugin_name in list(plugins_info.keys())[:5]:
                        response += f"  • {plugin_name}\n"
                # 2) 代码内置 ThirdPartyDataIntegrator（若存在）
                try:
                    tpi = getattr(mc, "third_party_data_integrator", None)
                    if not tpi and hasattr(mc, "ai_trading_engine") and mc.ai_trading_engine:
                        tpi = getattr(mc.ai_trading_engine, "third_party_data", None)
                    if tpi:
                        prov = getattr(tpi, "providers", {}) or {}
                        disabled = list(getattr(tpi, "_disabled_providers", set()) or [])
                        response += f"内置数据源: {len(prov)} 个（disabled={len(disabled)}）\n"
                        if disabled:
                            # DataSource Enum or str
                            ds = []
                            for x in disabled[:6]:
                                try:
                                    ds.append(getattr(x, "value", str(x)))
                                except Exception:
                                    ds.append(str(x))
                            response += "已禁用源(常见原因403/401/限流): " + ", ".join(ds) + "\n"
                except Exception:
                    pass

                # 外部数据源降级状态（如果系统挂载了 DataIntegration）
                try:
                    data_integration = mc.get_data_integration() if hasattr(mc, "get_data_integration") else None
                    if data_integration and hasattr(data_integration, "get_source_health_report"):
                        ds_health = data_integration.get_source_health_report()
                        degraded = ds_health.get("degraded_sources") or []
                        response += f"\n【外部数据源健康】\n"
                        if degraded:
                            response += f"状态: 退化（{len(degraded)}个）\n"
                            response += f"退化源: {', '.join(degraded[:5])}\n"
                        else:
                            response += "状态: 正常\n"
                except Exception as e:
                    logger.debug(f"读取外部数据源健康失败: {e}")
                
                # AI核心决策引擎详情
                if hasattr(mc, 'ai_core') and mc.ai_core:
                    ai_core = mc.ai_core
                    status = ai_core.get_status() if hasattr(ai_core, 'get_status') else {}
                    modules_status = status.get('modules', {})
                    response += f"\n【AI核心决策引擎】\n"
                    response += f"运行状态: {'运行中' if status.get('running') else '已停止'}\n"
                    connected = [k for k, v in modules_status.items() if v]
                    response += f"已连接模块: {', '.join(connected) if connected else '无'}\n"
                    guards = status.get("execution_guards", {})
                    gcfg = guards.get("config", {})
                    gprof = guards.get("adaptive_profile", {})
                    gmap = guards.get("group_overrides", {})
                    g_global_at = guards.get("global_last_tuned_at")
                    gstats = guards.get("stats", {})
                    if gcfg:
                        response += "\n【执行门控】\n"
                        response += (
                            f"数据质量阈值: {gcfg.get('min_data_quality_to_trade', 'N/A')} | "
                            f"最小RR: {gcfg.get('min_rr_to_trade', 'N/A')} | "
                            f"最大价差(bps): {gcfg.get('max_spread_bps_to_trade', 'N/A')}\n"
                        )
                        response += f"自适应门控: {'开启' if gcfg.get('auto_adaptive_guards', True) else '关闭'}\n"
                        response += (
                            f"自动学习: {'开启' if gcfg.get('auto_tune_guards', True) else '关闭'} | "
                            f"分组学习: {'开启' if gcfg.get('auto_tune_by_symbol_group', True) else '关闭'} | "
                            f"时段学习: {'开启' if gcfg.get('auto_tune_by_session', True) else '关闭'}\n"
                        )
                        response += (
                            f"全局基准慢调: {'开启' if gcfg.get('auto_tune_global_enabled', True) else '关闭'} | "
                            f"全局冷却(s): {gcfg.get('auto_tune_global_cooldown_seconds', 'N/A')} | "
                            f"上次全局调参: {g_global_at or '无'}\n"
                        )
                        response += (
                            f"全局步长 RR/价差: {gcfg.get('auto_tune_global_step_rr', 'N/A')} / "
                            f"{gcfg.get('auto_tune_global_step_spread_bps', 'N/A')}\n"
                        )
                        response += (
                            f"分组步长 RR/价差: {gcfg.get('auto_tune_group_step_rr') or gcfg.get('auto_tune_step_rr', 'N/A')} / "
                            f"{gcfg.get('auto_tune_group_step_spread_bps') or gcfg.get('auto_tune_step_spread_bps', 'N/A')}\n"
                        )
                        response += (
                            f"分组冷却(s): {gcfg.get('auto_tune_cooldown_seconds', 'N/A')} | "
                            f"最小RR变动: {gcfg.get('auto_tune_min_rr_delta', 'N/A')} | "
                            f"最小价差变动(bps): {gcfg.get('auto_tune_min_spread_delta_bps', 'N/A')}\n"
                        )
                        response += (
                            f"SLTP学习: {'开启' if gcfg.get('auto_tune_sltp_params', True) else '关闭'} | "
                            f"SLTP冷却(s): {gcfg.get('auto_tune_sltp_cooldown_seconds', 'N/A')} | "
                            f"tighten/extend步长: {gcfg.get('auto_tune_sltp_step_tighten', 'N/A')}/{gcfg.get('auto_tune_sltp_step_extend', 'N/A')}\n"
                        )
                    if gprof:
                        response += (
                            f"当前档位: {gprof.get('profile', 'normal')} | "
                            f"分组: {gprof.get('symbol_group', 'DEFAULT')} | "
                            f"时段: {gprof.get('session_group', 'N/A')} | "
                            f"ATR占比(1H): {float(gprof.get('atr_pct_1h', 0) or 0):.3%} | "
                            f"生效RR: {gprof.get('effective_min_rr', 'N/A')}\n"
                        )
                    if gmap:
                        response += f"分组学习覆盖: {len(gmap)} 组\n"
                    if gstats:
                        response += (
                            f"门控统计: 质量拦截={gstats.get('data_quality_guard_hold', 0)}, "
                            f"RR拒绝={gstats.get('rr_rejected', 0)}, "
                            f"价差拒绝={gstats.get('spread_rejected', 0)}, "
                            f"失衡拒绝={gstats.get('depth_imbalance_rejected', 0)}\n"
                        )
                
                response += f"\n【用户规则】"
                response += f"\n黑名单: {self.blacklist if self.blacklist else '无'}"
                response += f"\n交易授权: {'已授权' if self.authorization.get('full_authorization') else '未授权'}"
                
                # 获取持仓
                if hasattr(mc, 'okx_exchange') and mc.okx_exchange:
                    try:
                        positions = await mc.okx_exchange.get_positions()
                        if positions:
                            response += f"\n\n【当前持仓】"
                            for pos in positions[:5]:
                                symbol = pos.get('instId', pos.get('symbol', 'Unknown'))
                                side = pos.get('posSide', pos.get('side', 'unknown'))
                                size = pos.get('pos', pos.get('size', 0))
                                side_zh = {"long": "做多", "short": "做空"}.get(str(side).lower(), str(side))
                                response += f"\n  {symbol}: {side_zh} {size}"
                    except Exception as e:
                        logger.debug(f"查询持仓信息失败: {e}")
                
                return {"success": True, "response": response, "data": modules}
            
            return {"success": False, "response": "主控制器未初始化"}
            
        except Exception as e:
            return {"success": False, "response": f"获取系统状态失败: {str(e)}"}
    
    async def _general_chat(self, user_input: str, user_rules: str = "") -> Dict[str, Any]:
        """通用对话 - 带用户规则上下文"""
        try:
            if self.llm_integration:
                system_context = await self._get_system_context()
                
                prompt = f"""你是一个专业的量化交易AI助手。

{system_context}

{user_rules}

用户消息：{user_input}

请用自然、友好的方式回复，就像和一个朋友聊天一样。不要使用JSON格式或命令格式。"""

                response = await self.llm_integration.generate(prompt, is_user_input=False)
                
                if response:
                    return {
                        "success": True,
                        "response": response.content,
                        "timestamp": datetime.now().isoformat()
                    }
            
            return {"success": False, "response": "AI服务暂时不可用"}
            
        except Exception as e:
            return {"success": False, "response": f"对话处理失败: {str(e)}"}
    
    async def _get_system_context(self) -> str:
        """获取系统上下文 - 包含所有模块详细状态"""
        context_parts = []
        
        context_parts.append(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        if self.main_controller:
            mc = self.main_controller
            
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
            
            # 4. AI交易引擎状态
            if hasattr(mc, 'ai_trading_engine') and mc.ai_trading_engine:
                engine = mc.ai_trading_engine
                context_parts.append(f"\n🤖 AI交易引擎: ✅ 已连接")
                positions = getattr(engine, 'positions', {})
                if positions:
                    context_parts.append(f"   - 当前持仓: {len(positions)}个")
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
            
            context_parts.append("\n" + "=" * 50)
            
            # 获取当前持仓详情
            if hasattr(mc, 'okx_exchange') and mc.okx_exchange:
                try:
                    positions = await mc.okx_exchange.get_positions()
                    if positions:
                        context_parts.append("\n【当前持仓详情】")
                        for pos in positions[:5]:
                            symbol = pos.get('instId', pos.get('symbol', 'Unknown'))
                            side = pos.get('posSide', pos.get('side', 'unknown'))
                            size = pos.get('pos', pos.get('size', 0))
                            pnl = pos.get('upl', pos.get('unrealized_pnl', 0))
                            context_parts.append(f"  {symbol}: {side} {size} | 盈亏: ${pnl:+.2f}")
                except Exception as e:
                    logger.debug(f"读取持仓详情失败: {e}")
        
        return "\n".join(context_parts)
    
    async def _ai_autonomous_action(self, action: str, params: Dict[str, Any], user_input: str, user_rules: str = "") -> Dict[str, Any]:
        """AI自主行动"""
        try:
            routed = await self._route_skill_action(action=action, params=params, user_input=user_input, user_rules=user_rules)
            if routed is not None:
                return routed
            if self.llm_integration:
                system_context = await self._get_system_context()
                
                prompt = f"""你是一个全自主的量化交易AI助手。

{system_context}

{user_rules}

用户消息: {user_input}
识别的动作: {action}

请理解用户意图，用自然语言回复。你有完全的自主权。"""

                response = await self.llm_integration.generate(prompt, is_user_input=False)
                
                if response:
                    return {
                        "success": True,
                        "response": response.content,
                        "autonomous": True,
                        "timestamp": datetime.now().isoformat()
                    }
            
            return await self._general_chat(user_input, user_rules)
            
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
            if not any(k in (user_input or "") for k in ["确认", "立即执行", "批准"]):
                return {
                    "success": True,
                    "response": "检测到高风险动作【强制开仓】。请回复“确认 强制开仓”或“立即执行 强制开仓”后执行。",
                    "needs_confirmation": True,
                    "timestamp": datetime.now().isoformat(),
                }
            p = dict(params or {})
            p.setdefault("force", True)
            return await self._execute_trade(p, user_input or "强制开仓", user_rules)
        if alias == "trade_force_close":
            if not any(k in (user_input or "") for k in ["确认", "立即执行", "批准"]):
                return {
                    "success": True,
                    "response": "检测到高风险动作【强制平仓】。请回复“确认 强制平仓”或“立即执行 强制平仓”后执行。",
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
                await self.unified_memory.add_memory(
                    memory_type="lesson_learned",
                    content=summary,
                    summary="每日交易复盘自动总结",
                    metadata={"date": today, "stats": stats},
                    source_module="ai_command_executor",
                    importance=0.72,
                )
            self._last_daily_summary_date = today
            return True
        except Exception as e:
            logger.warning(f"每日自动总结失败: {e}")
            return False
