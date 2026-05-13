"""
大模型集成模块

功能：
1. 支持多种大模型的统一接口
2. 市场分析和预测
3. 策略生成和优化
4. 风险评估和管理
5. 自然语言处理和理解
"""

import asyncio
import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import httpx

logger = logging.getLogger(__name__)


def _repair_loose_json(text: str) -> str:
    """修复模型常见非标准 JSON：尾随逗号等。"""
    if not text:
        return text
    t = text.strip()
    # 连续应用以处理嵌套尾随逗号
    for _ in range(4):
        n = re.sub(r",\s*([}\]])", r"\1", t)
        if n == t:
            break
        t = n
    return t


def extract_first_balanced_json_object(text: str) -> Optional[str]:
    """从文本中提取第一个花括号平衡的 JSON 对象子串（忽略字符串内的括号）。"""
    if not text:
        return None
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def safe_json_parse(content: str) -> Dict[str, Any]:
    """安全解析JSON，支持从markdown代码块、平衡括号与宽松修复中提取"""
    if not content:
        return {"error": "内容为空"}

    content = content.strip()

    candidates: List[str] = []

    def _try_parse(raw: str) -> Optional[Dict[str, Any]]:
        raw = raw.strip()
        if not raw:
            return None
        for attempt in (raw, _repair_loose_json(raw)):
            try:
                val = json.loads(attempt)
                if isinstance(val, dict):
                    return val
            except Exception:
                continue
        return None

    direct = _try_parse(content)
    if direct is not None:
        return direct

    # fenced ```json ... ```
    for m in re.finditer(r"```(?:json)?\s*([\s\S]*?)\s*```", content, re.IGNORECASE):
        chunk = (m.group(1) or "").strip()
        parsed = _try_parse(chunk)
        if parsed is not None:
            return parsed

    balanced = extract_first_balanced_json_object(content)
    if balanced:
        parsed = _try_parse(balanced)
        if parsed is not None:
            return parsed

    # 最后：首 { 到末 }（可能跨度过大，仅作兜底）
    try:
        s, e = content.find("{"), content.rfind("}")
        if s != -1 and e != -1 and e > s:
            parsed = _try_parse(content[s : e + 1])
            if parsed is not None:
                return parsed
    except Exception as ex:
        logger.debug("括号范围JSON解析失败: %s", ex)

    return {"error": "JSON解析失败", "raw_content": content[:500]}


def trading_signal_parse_fallback(raw_content: str) -> Dict[str, Any]:
    """解析失败时的模块化降级：返回与 AITradingEngine 兼容的观望结构。"""
    return {
        "signal": "hold",
        "confidence": 0.0,
        "reasoning": "模型输出无法解析为有效 JSON，已降级为观望",
        "risk_level": "medium",
        "parse_failed": True,
        "raw_excerpt": (raw_content or "")[:400],
    }


class LLMProvider(ABC):
    """大模型提供者抽象基类"""
    
    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> str:
        """生成文本"""
        pass
    
    @abstractmethod
    async def analyze_market(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析市场数据"""
        pass
    
    @abstractmethod
    async def generate_strategy(self, market_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """生成交易策略"""
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI大模型提供者"""
    
    def __init__(self, api_key: str, model: str = "gpt-4-turbo"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.openai.com/v1/chat/completions"
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """生成文本"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": prompt
            }],
            **kwargs
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.base_url, headers=headers, json=data, timeout=30.0)
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"OpenAI API调用失败: {e}")
            return ""  
    
    async def analyze_market(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析市场数据"""
        prompt = f"""请分析以下市场数据并提供详细的市场分析报告：

{market_data}

分析内容应包括：
1. 市场趋势分析
2. 关键支撑和阻力位
3. 技术指标分析
4. 市场情绪评估
5. 潜在的交易机会
6. 风险因素

请以JSON格式返回分析结果。"""
        
        response = await self.generate(prompt, temperature=0.7, max_tokens=2000, is_user_input=False)
        
        return safe_json_parse(response)
    
    async def generate_strategy(self, market_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """生成交易策略"""
        prompt = f"""基于以下市场分析，生成详细的交易策略：

{market_analysis}

策略应包括：
1. 入场条件
2. 出场条件
3. 止损设置
4. 止盈设置
5. 仓位管理
6. 风险控制
7. 适合的交易工具

请以JSON格式返回策略结果。"""
        
        response = await self.generate(prompt, temperature=0.7, max_tokens=2000, is_user_input=False)
        
        return safe_json_parse(response)


class AnthropicProvider(LLMProvider):
    """Anthropic大模型提供者"""
    
    def __init__(self, api_key: str, model: str = "claude-3-opus-20240229"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.anthropic.com/v1/messages"
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """生成文本"""
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        
        data = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": prompt
            }],
            **kwargs
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.base_url, headers=headers, json=data, timeout=30.0)
                response.raise_for_status()
                return response.json()["content"][0]["text"]
        except Exception as e:
            logger.error(f"Anthropic API调用失败: {e}")
            return ""  
    
    async def analyze_market(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析市场数据"""
        prompt = f"""请分析以下市场数据并提供详细的市场分析报告：

{market_data}

分析内容应包括：
1. 市场趋势分析
2. 关键支撑和阻力位
3. 技术指标分析
4. 市场情绪评估
5. 潜在的交易机会
6. 风险因素

请以JSON格式返回分析结果。"""
        
        response = await self.generate(prompt, temperature=0.7, max_tokens=2000, is_user_input=False)
        
        return safe_json_parse(response)
    
    async def generate_strategy(self, market_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """生成交易策略"""
        prompt = f"""基于以下市场分析，生成详细的交易策略：

{market_analysis}

策略应包括：
1. 入场条件
2. 出场条件
3. 止损设置
4. 止盈设置
5. 仓位管理
6. 风险控制
7. 适合的交易工具

请以JSON格式返回策略结果。"""
        
        response = await self.generate(prompt, temperature=0.7, max_tokens=2000, is_user_input=False)
        
        try:
            import json
            return json.loads(response)
        except Exception as e:
            logger.error(f"解析策略结果失败: {e}")
            return {"error": "策略生成失败"}


class LocalLLMProvider(LLMProvider):
    """本地大模型提供者"""
    
    def __init__(self, base_url: str = "http://localhost:11434/api/generate", model: str = "llama3"):
        self.base_url = base_url
        self.model = model
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """生成文本"""
        data = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            **kwargs
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.base_url, json=data, timeout=60.0)
                response.raise_for_status()
                return response.json()["response"]
        except Exception as e:
            logger.error(f"本地LLM API调用失败: {e}")
            return ""  
    
    async def analyze_market(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析市场数据"""
        prompt = f"""请分析以下市场数据并提供详细的市场分析报告：

{market_data}

分析内容应包括：
1. 市场趋势分析
2. 关键支撑和阻力位
3. 技术指标分析
4. 市场情绪评估
5. 潜在的交易机会
6. 风险因素

请以JSON格式返回分析结果。"""
        
        response = await self.generate(prompt, temperature=0.7, max_tokens=2000, is_user_input=False)
        
        try:
            import json
            return json.loads(response)
        except Exception as e:
            logger.error(f"解析分析结果失败: {e}")
            return {"error": "分析失败"}
    
    async def generate_strategy(self, market_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """生成交易策略"""
        prompt = f"""基于以下市场分析，生成详细的交易策略：

{market_analysis}

策略应包括：
1. 入场条件
2. 出场条件
3. 止损设置
4. 止盈设置
5. 仓位管理
6. 风险控制
7. 适合的交易工具

请以JSON格式返回策略结果。"""
        
        response = await self.generate(prompt, temperature=0.7, max_tokens=2000, is_user_input=False)
        
        try:
            import json
            return json.loads(response)
        except Exception as e:
            logger.error(f"解析策略结果失败: {e}")
            return {"error": "策略生成失败"}


# 注意：使用 enhanced_llm_manager 中的 LLMResponse
# 删除旧的 LLMResponse 定义，避免混淆
# 旧的 LLMManager 类已删除，使用 EnhancedLLMManager


class EnhancedLLMIntegration:
    """增强的大模型集成 - 使用EnhancedLLMManager"""
    
    def __init__(self, llm_manager=None, memory_manager=None):
        """
        初始化大模型集成
        
        Args:
            llm_manager: 可选的EnhancedLLMManager实例，如果不提供则创建新的
            memory_manager: 可选的AIMemoryManager实例，用于记忆管理
        """
        self.llm_manager = llm_manager
        self.memory_manager = memory_manager
        self.enhanced_memory = None
        # 可选：用于读取 memory.context_policy（条数/Budget）
        self.policy_config_manager = None
        self._initialized = False
    
    async def initialize(self, config: Dict[str, Any]):
        """初始化大模型集成"""
        if self.llm_manager is None:
            # 如果没有提供llm_manager，创建一个新的
            from src.modules.core.enhanced_llm_manager import EnhancedLLMManager
            self.llm_manager = EnhancedLLMManager()
            await self.llm_manager.initialize(config)
        self._initialized = True
        logger.info("增强大模型集成初始化完成")
    
    async def cleanup(self):
        """清理资源"""
        if self.llm_manager:
            await self.llm_manager.cleanup()
        self._initialized = False
        logger.info("增强大模型集成清理完成")
    
    def set_llm_manager(self, llm_manager):
        """设置外部提供的LLM管理器"""
        self.llm_manager = llm_manager
        self._initialized = True
        logger.info("增强大模型集成已设置外部LLM管理器")
    
    async def generate(self, prompt: str, provider: Optional[str] = None, 
                       is_user_input: bool = True,
                       conversation_scope: Optional[str] = None,
                       memory_channel: Optional[str] = None,
                       **kwargs):
        """生成文本（带记忆注入）
        
        Args:
            prompt: 输入提示词
            provider: 模型提供商
            is_user_input: 是否是真正的用户输入（False表示系统生成的提示词，不保存到记忆）
            conversation_scope: 若设置（如 channel:telegram），注入该 scope 的最近对话；可与 is_user_input=False 联用（主入口已写入 MainController 时避免重复存用户句）
            memory_channel: 记忆策略里的渠道键（如 telegram），用于合并 context_policy.channels.<key> 的条数上限
        """
        from src.modules.core.enhanced_llm_manager import LLMResponse
        
        if not self.llm_manager:
            return LLMResponse(
                content="",
                model_id="",
                provider=None,
                success=False,
                error_message="LLM管理器未初始化"
            )
        
        memory_context = ""
        
        if self.enhanced_memory and (is_user_input or conversation_scope is not None):
            try:
                from src.modules.memory.memory_context_policy import get_effective_context_policy

                pol = get_effective_context_policy(
                    getattr(self, "policy_config_manager", None),
                    channel=memory_channel,
                )
                recent_n = int(pol.get("conversation_recent_limit", 12))
                recall_n = int(pol.get("conversation_recall_limit", 8))
                rules_n = int(pol.get("rules_recall_limit", 5))
                line_mc = int(pol.get("line_max_chars", 220))
                recall_mc = int(pol.get("recall_line_max_chars", 240))
                rules_q = str(pol.get("rules_recall_query", "黑名单 授权 偏好 风控"))

                parts = []
                # 1) Hard context: recent conversation in the same channel/scope (prevents immediate amnesia)
                try:
                    if hasattr(self.enhanced_memory, "recent_conversation"):
                        recent_scope = None
                        if conversation_scope is not None:
                            recent_scope = conversation_scope
                        elif is_user_input:
                            recent_scope = None  # global history
                        recent = await self.enhanced_memory.recent_conversation(
                            scope=recent_scope, limit=max(4, recent_n)
                        )
                        if isinstance(recent, list) and recent:
                            parts.append("【最近对话】")
                            for r in recent[-recent_n:]:
                                try:
                                    c = str(getattr(r, "content", "") or (r.get("content") if isinstance(r, dict) else ""))
                                except Exception:
                                    c = str(r)
                                if c:
                                    parts.append(f"- {c[:line_mc]}")
                except Exception:
                    pass

                # 2) Soft context: relevant recalled memories（仅对用户原句检索，避免对编排后超长 system prompt 噪声检索）
                if is_user_input and hasattr(self.enhanced_memory, "retrieve_memories"):
                    items = await self.enhanced_memory.retrieve_memories(query=prompt, limit=recall_n)
                    if isinstance(items, list) and items:
                        parts.append("\n【相关记忆】")
                        for m in items[:recall_n]:
                            try:
                                c = str(getattr(m, "content", "") or (m.get("content") if isinstance(m, dict) else ""))
                            except Exception:
                                c = str(m)
                            if c:
                                parts.append(f"- {c[:recall_mc]}")

                # 3) Rules / preferences
                if hasattr(self.enhanced_memory, "retrieve_memories") and (
                    is_user_input or conversation_scope is not None
                ):
                    rules = await self.enhanced_memory.retrieve_memories(
                        query=rules_q, limit=rules_n
                    )
                    if isinstance(rules, list) and rules:
                        parts.append("\n【规则/偏好要点】")
                        for m in rules[:rules_n]:
                            try:
                                c = str(getattr(m, "content", "") or (m.get("content") if isinstance(m, dict) else ""))
                            except Exception:
                                c = str(m)
                            if c:
                                parts.append(f"- {c[:recall_mc]}")

                memory_context = "\n".join([p for p in parts if p]).strip()

                if is_user_input:
                    if hasattr(self.enhanced_memory, "add_message"):
                        self.enhanced_memory.add_message("user", prompt)
                    elif hasattr(self.enhanced_memory, "add_memory"):
                        await self.enhanced_memory.add_memory(
                            memory_type="conversation",
                            content=f"用户: {prompt}",
                            importance=0.7,
                            tags=["conversation"],
                            source_module="llm_integration",
                        )
            except Exception as e:
                logger.warning(f"增强记忆注入失败: {e}")
        elif self.memory_manager and is_user_input:
            try:
                memory_context = await self.memory_manager.build_memory_context(prompt)
                await self.memory_manager.add_short_term_memory(
                    f"用户: {prompt}",
                    importance=0.7
                )
            except Exception as e:
                logger.warning(f"记忆注入失败: {e}")
        
        if memory_context:
            full_prompt = f"""[系统记忆上下文]
{memory_context}

---

[当前对话]
{prompt}

请根据你的核心信念和身份定义，以专业、主动的方式回应用户。记住用户的偏好和指令，并在回答中体现你的专业性和主动性。"""
        else:
            full_prompt = prompt
        
        from src.modules.core.enhanced_llm_manager import TaskType
        model_id = kwargs.pop('model_id', None) or provider
        task_type = kwargs.pop('task_type', TaskType.GENERAL)
        prefer_reasoning = bool(kwargs.pop('prefer_reasoning', False))
        response = await self.llm_manager.generate(
            prompt=full_prompt,
            model_id=model_id,
            task_type=task_type,
            prefer_reasoning=prefer_reasoning,
            **kwargs
        )
        
        if response.success:
            if is_user_input:
                if self.enhanced_memory:
                    try:
                        if hasattr(self.enhanced_memory, "add_message"):
                            self.enhanced_memory.add_message("assistant", response.content)
                        elif hasattr(self.enhanced_memory, "add_memory"):
                            await self.enhanced_memory.add_memory(
                                memory_type="conversation",
                                content=f"AI: {response.content[:500]}...",
                                importance=0.8,
                                tags=["conversation"],
                                source_module="llm_integration",
                            )
                    except Exception as e:
                        logger.warning(f"增强记忆记录AI回复失败: {e}")
                elif self.memory_manager:
                    try:
                        await self.memory_manager.add_short_term_memory(
                            f"AI: {response.content[:500]}...",
                            importance=0.8
                        )
                    except Exception as e:
                        logger.warning(f"保存AI回复记忆失败: {e}")
        
        return response
    
    async def analyze_market(self, market_data: Dict[str, Any], provider: Optional[str] = None) -> Dict[str, Any]:
        """分析市场数据"""
        if not self.llm_manager:
            return {"error": "LLM管理器未初始化"}
        
        prompt = f"""分析以下市场数据：

{market_data}

请提供：
1. 市场趋势分析
2. 关键支撑位和阻力位
3. 技术指标解读
4. 市场情绪分析
5. 交易建议

请以JSON格式返回分析结果。"""

        response = await self.generate(prompt, model_id=provider, temperature=0.7, max_tokens=2000, is_user_input=False)
        
        if response.success:
            try:
                import json
                result = json.loads(response.content)
                result["provider"] = response.provider.value if response.provider else provider
                return result
            except Exception as e:
                logger.debug(f"市场分析JSON解析失败，回退文本结果: {e}")
                return {
                    "analysis": response.content,
                    "provider": response.provider.value if response.provider else provider
                }
        else:
            return {"error": response.error_message or "市场分析失败"}
    
    async def generate_strategy(self, market_analysis: Dict[str, Any], provider: Optional[str] = None) -> Dict[str, Any]:
        """生成交易策略"""
        if not self.llm_manager:
            return {"error": "LLM管理器未初始化"}
        
        prompt = f"""基于以下市场分析，生成交易策略：

{market_analysis}

请提供：
1. 策略名称和描述
2. 入场条件
3. 出场条件
4. 止损止盈设置
5. 仓位管理建议
6. 风险提示

请以JSON格式返回策略。"""

        response = await self.generate(prompt, model_id=provider, temperature=0.7, max_tokens=2000, is_user_input=False)
        
        if response.success:
            try:
                import json
                result = json.loads(response.content)
                result["provider"] = response.provider.value if response.provider else provider
                return result
            except Exception as e:
                logger.debug(f"策略JSON解析失败，回退文本结果: {e}")
                return {
                    "strategy": response.content,
                    "provider": response.provider.value if response.provider else provider
                }
        else:
            return {"error": response.error_message or "策略生成失败"}
    
    async def analyze_news(self, news: List[str], provider: Optional[str] = None) -> Dict[str, Any]:
        """分析新闻"""
        if not self.llm_manager:
            return {"error": "LLM管理器未初始化"}
        
        news_text = "\n".join(news)
        prompt = f"""分析以下新闻：

{news_text}

请提供：
1. 新闻摘要
2. 市场影响分析
3. 情绪分析（正面/负面/中性）
4. 交易机会识别
5. 风险提示

请以JSON格式返回分析结果。"""

        response = await self.generate(prompt, model_id=provider, temperature=0.7, max_tokens=2000, is_user_input=False)
        
        if response.success:
            try:
                import json
                result = json.loads(response.content)
                result["provider"] = response.provider.value if response.provider else provider
                return result
            except Exception as e:
                logger.debug(f"新闻分析JSON解析失败，回退文本结果: {e}")
                return {
                    "analysis": response.content,
                    "provider": response.provider.value if response.provider else provider
                }
        else:
            return {"error": response.error_message or "新闻分析失败"}
    
    async def evaluate_risk(self, position: Dict[str, Any], provider: Optional[str] = None) -> Dict[str, Any]:
        """评估风险"""
        if not self.llm_manager:
            return {"error": "LLM管理器未初始化"}
        
        prompt = f"""评估以下持仓的风险：

{position}

请提供：
1. 风险等级（低/中/高）
2. 最大可能损失
3. 风险因素分析
4. 风险缓解建议
5. 止损建议

请以JSON格式返回风险评估。"""

        response = await self.generate(prompt, model_id=provider, temperature=0.7, max_tokens=2000, is_user_input=False)
        
        if response.success:
            try:
                import json
                result = json.loads(response.content)
                result["provider"] = response.provider.value if response.provider else provider
                return result
            except Exception as e:
                logger.debug(f"风险评估JSON解析失败，回退文本结果: {e}")
                return {
                    "risk_assessment": response.content,
                    "provider": response.provider.value if response.provider else provider
                }
        else:
            return {"error": response.error_message or "风险评估失败"}
    
    async def generate_trading_signal(self, market_data: Dict[str, Any], provider: Optional[str] = None) -> Dict[str, Any]:
        """生成交易信号"""
        # 先分析市场
        analysis = await self.analyze_market(market_data, provider)
        
        if "error" in analysis:
            return analysis
        
        # 基于分析生成策略
        strategy = await self.generate_strategy(analysis, provider)
        
        if "error" in strategy:
            return strategy
        
        # 生成交易信号
        prompt = f"""基于以下市场分析和策略，生成具体的交易信号：

市场分析：
{analysis}

策略：
{strategy}

交易信号应包括：
1. 交易方向（买入/卖出）
2. 交易品种
3. 入场价格
4. 止损价格
5. 止盈价格
6. 仓位大小
7. 信号强度
8. 有效期

请以JSON格式返回交易信号。"""
        
        response = await self.generate(prompt, provider, temperature=0.5, max_tokens=1000, is_user_input=False)
        
        try:
            raw = getattr(response, "content", None) or ""
            signal = safe_json_parse(raw)
            if "error" in signal and "raw_content" in signal:
                logger.warning(
                    "解析交易信号失败，已使用观望降级: %s",
                    signal.get("error"),
                )
                fb = trading_signal_parse_fallback(signal.get("raw_content", raw))
                fb["timestamp"] = datetime.now().isoformat()
                fb["provider"] = (
                    response.provider.value
                    if response.provider
                    else provider or self.llm_manager.default_model
                )
                return fb
            signal["timestamp"] = datetime.now().isoformat()
            signal["provider"] = response.provider.value if response.provider else provider or self.llm_manager.default_model
            return signal
        except Exception as e:
            logger.warning("解析交易信号异常，已使用观望降级: %s", e)
            fb = trading_signal_parse_fallback("")
            fb["timestamp"] = datetime.now().isoformat()
            try:
                fb["provider"] = (
                    response.provider.value
                    if response.provider
                    else provider or self.llm_manager.default_model
                )
            except Exception:
                fb["provider"] = provider or "unknown"
            return fb


# 使用示例
async def example_usage():
    """使用示例"""
    # 创建大模型集成
    llm_integration = EnhancedLLMIntegration()
    
    # 配置
    config = {
        "local": {
            "base_url": "http://localhost:11434/api/generate",
            "model": "llama3"
        },
        "default_provider": "local"
    }
    
    await llm_integration.initialize(config)
    
    try:
        # 模拟市场数据
        market_data = {
            "symbol": "BTC/USDT",
            "price": 50000,
            "volume": 1000000000,
            "ohlcv": [
                [1704067200, 49000, 51000, 48500, 50000, 1000000000],
                [1704153600, 50000, 52000, 49500, 51000, 1200000000],
                [1704240000, 51000, 53000, 50500, 52000, 1500000000]
            ],
            "indicators": {
                "ma5": 51000,
                "ma20": 49000,
                "rsi": 65,
                "macd": {
                    "macd": 500,
                    "signal": 300,
                    "histogram": 200
                }
            }
        }
        
        # 分析市场
        analysis = await llm_integration.analyze_market(market_data)
        logger.info("市场分析:")
        logger.info(analysis)
        
        # 生成策略
        strategy = await llm_integration.generate_strategy(analysis)
        logger.info("\n交易策略:")
        logger.info(strategy)
        
        # 生成交易信号
        signal = await llm_integration.generate_trading_signal(market_data)
        logger.info("\n交易信号:")
        logger.info(signal)
        
        # 分析新闻
        news = [
            "美联储宣布加息25个基点",
            "比特币突破60000美元大关",
            "大型机构开始配置加密资产"
        ]
        news_analysis = await llm_integration.analyze_news(news)
        logger.info("\n新闻分析:")
        logger.info(news_analysis)
        
        # 评估风险
        position = {
            "symbol": "BTC/USDT",
            "size": 0.1,
            "entry_price": 50000,
            "stop_loss": 48000,
            "take_profit": 55000
        }
        risk_evaluation = await llm_integration.evaluate_risk(position)
        logger.info("\n风险评估:")
        logger.info(risk_evaluation)
        
    finally:
        await llm_integration.cleanup()


if __name__ == "__main__":
    asyncio.run(example_usage())
