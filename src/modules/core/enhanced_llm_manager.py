"""
增强的大模型管理器 - 提供灵活的模型选择和配置功能

功能：
1. 支持多种模型提供商（OpenAI、Anthropic、Google、Azure、DeepSeek、Qwen等）
2. 动态模型切换和负载均衡
3. 自定义模型配置
4. 模型回退和故障转移
5. 使用统计和性能监控
6. 按任务类型选择最优模型
"""

import asyncio
import logging
import json
import os
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx

logger = logging.getLogger(__name__)


class ModelProvider(Enum):
    """模型提供商"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    AZURE = "azure"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    KIMI = "kimi"
    GLM = "glm"
    LOCAL = "local"
    CUSTOM = "custom"


class TaskType(Enum):
    """任务类型"""
    GENERAL = "general"
    MARKET_ANALYSIS = "market_analysis"
    STRATEGY_GENERATION = "strategy_generation"
    SIGNAL_GENERATION = "signal_generation"
    RISK_ASSESSMENT = "risk_assessment"
    NEWS_ANALYSIS = "news_analysis"
    CODE_GENERATION = "code_generation"
    NATURAL_LANGUAGE = "natural_language"


@dataclass
class ModelConfig:
    """模型配置"""
    provider: ModelProvider
    model_id: str
    display_name: str
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.7
    max_tokens: int = 2000
    timeout: float = 60.0
    max_retries: int = 3
    cost_per_input_token: float = 0.0
    cost_per_output_token: float = 0.0
    context_window: int = 8192
    supports_vision: bool = False
    supports_reasoning: bool = False
    enabled: bool = True
    priority: int = 0
    fallback_models: List[str] = field(default_factory=list)


@dataclass
class ModelUsageStats:
    """模型使用统计"""
    model_id: str
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost: float = 0.0
    total_latency_ms: float = 0.0
    avg_latency_ms: float = 0.0
    last_used: Optional[datetime] = None


@dataclass
class LLMResponse:
    """LLM响应"""
    content: str
    model_id: str
    provider: ModelProvider
    task_type: TaskType = TaskType.GENERAL
    timestamp: datetime = field(default_factory=datetime.now)
    latency_ms: float = 0.0
    tokens_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    success: bool = True
    error_message: Optional[str] = None
    error_code: Optional[str] = None


class BaseLLMProvider(ABC):
    """LLM提供者基类"""

    def __init__(self, config: ModelConfig):
        self.config = config
        self.session: Optional[httpx.AsyncClient] = None
        # OPENCLAW_LLM_DIRECT_FALLBACK=1 且代理连续失败时，切换为直连客户端（容器须能直达各模型 base_url）
        self._httpx_force_direct: bool = False

    def _build_httpx_client(self) -> httpx.AsyncClient:
        """创建 httpx 客户端（显式超时与连接池，降低复用死连接导致的 Server disconnected）"""
        proxy = (
            None
            if self._httpx_force_direct
            else (os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY"))
        )
        total = float(self.config.timeout or 60.0)
        connect_cap = min(30.0, max(5.0, total))
        timeout = httpx.Timeout(total, connect=connect_cap, read=total, write=total, pool=connect_cap)
        # 根因：对端/代理/中间盒常提前关空闲 TCP，复用池内连接时触发 RemoteProtocolError: Server disconnected。
        # 默认关闭 keep-alive；稳定链路可设 OPENCLAW_LLM_ENABLE_KEEPALIVE=1。
        ka_force_off = os.getenv("OPENCLAW_LLM_DISABLE_KEEPALIVE", "").strip().lower() in ("1", "true", "yes")
        ka_force_on = os.getenv("OPENCLAW_LLM_ENABLE_KEEPALIVE", "").strip().lower() in ("1", "true", "yes")
        proxy_keepalive = os.getenv("OPENCLAW_LLM_PROXY_KEEPALIVE", "").strip().lower() in ("1", "true", "yes")
        proxied = bool(proxy)
        if ka_force_off:
            use_keepalive = False
        elif proxied:
            use_keepalive = proxy_keepalive
        else:
            use_keepalive = ka_force_on
        limits = httpx.Limits(
            max_connections=100,
            max_keepalive_connections=(8 if use_keepalive else 0),
            keepalive_expiry=(12.0 if use_keepalive else 5.0),
        )
        kw: Dict[str, Any] = {"timeout": timeout, "limits": limits, "http2": False}
        if proxy:
            kw["proxy"] = proxy
            # 仅走显式 HTTP(S)_PROXY，避免与 ALL_PROXY(socks) 叠加或触发 socksio 依赖问题
            kw["trust_env"] = False
            logger.info(
                f"LLM Provider 使用代理: {proxy}（keep-alive: {'开' if use_keepalive else '关'}）"
            )
        elif ka_force_off:
            logger.debug("LLM Provider: keep-alive 已禁用 (OPENCLAW_LLM_DISABLE_KEEPALIVE)")
        elif use_keepalive:
            logger.debug("LLM Provider: keep-alive 已启用")
        return httpx.AsyncClient(**kw)

    async def initialize(self):
        """初始化 HTTP 会话"""
        await self.recycle_session(force=True)

    async def recycle_session(self, force: bool = False, *, force_direct: Optional[bool] = None) -> None:
        """关闭并重新打开会话；网络/协议错误重试前调用，避免复用已断开的连接"""
        if self.session is not None:
            await self.session.aclose()
            self.session = None
        if force_direct is not None:
            self._httpx_force_direct = bool(force_direct)
        if force or self.session is None:
            self.session = self._build_httpx_client()

    async def cleanup(self):
        """清理"""
        if self.session:
            await self.session.aclose()

    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """生成文本"""
        pass


class OpenAIProvider(BaseLLMProvider):
    """OpenAI兼容API提供者（支持OpenAI、DeepSeek等）"""

    def _is_auth_error(self, status_code: int, error_text: str) -> bool:
        """检查是否是认证错误"""
        if status_code == 401:
            return True
        if status_code == 403 and 'auth' in error_text.lower():
            return True
        auth_error_codes = ['invalid_api_key', 'invalid_iam_token', 'authentication_failed', 'unauthorized']
        for code in auth_error_codes:
            if code in error_text.lower():
                return True
        return False

    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """生成文本（带重试机制和认证错误检测）"""
        start_time = time.time()
        max_retries = int(kwargs.get('max_retries', self.config.max_retries) or 3)
        env_mr = os.getenv("OPENCLAW_LLM_MAX_RETRIES", "").strip()
        if env_mr.isdigit():
            max_retries = max(1, int(env_mr))
        last_error = None
        is_auth_failure = False
        api_key = (self.config.api_key or "").strip()
        if not api_key:
            return LLMResponse(
                content="",
                model_id=self.config.model_id,
                provider=self.config.provider,
                latency_ms=(time.time() - start_time) * 1000,
                success=False,
                error_message="API key 缺失",
                error_code="AUTH_FAILED"
            )
        
        direct_fb = os.getenv("OPENCLAW_LLM_DIRECT_FALLBACK", "").strip().lower() in ("1", "true", "yes")
        proxy_env_set = bool(os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY"))
        tried_direct_fallback = False

        for retry in range(max_retries):
            try:
                base_url = self.config.base_url or "https://api.openai.com/v1"
                if base_url.endswith('/chat/completions'):
                    url = base_url
                elif base_url.endswith('/v1'):
                    url = f"{base_url}/chat/completions"
                else:
                    url = f"{base_url}/chat/completions"
                
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                
                data = {
                    "model": self.config.model_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": kwargs.get("temperature", self.config.temperature),
                    "max_tokens": kwargs.get("max_tokens", self.config.max_tokens)
                }
                
                response = await self.session.post(url, headers=headers, json=data)
                
                if response.status_code != 200:
                    error_text = response.text
                    is_auth_failure = self._is_auth_error(response.status_code, error_text)
                    
                    if is_auth_failure:
                        logger.warning(f"LLM API认证失败 ({self.config.model_id}): {error_text[:200]}")
                        last_error = f"API认证失败: {response.status_code}"
                        return LLMResponse(
                            content="",
                            model_id=self.config.model_id,
                            provider=self.config.provider,
                            latency_ms=(time.time() - start_time) * 1000,
                            success=False,
                            error_message=last_error,
                            error_code="AUTH_FAILED"
                        )
                    
                    logger.error(f"OpenAI API返回错误: status={response.status_code}, url={url}, response={error_text[:500]}")
                    last_error = f"API返回错误: {response.status_code}"
                    if retry < max_retries - 1:
                        logger.warning(f"LLM API重试 ({retry + 2}/{max_retries})...")
                        await asyncio.sleep(1)
                        continue
                    return LLMResponse(
                        content="",
                        model_id=self.config.model_id,
                        provider=self.config.provider,
                        latency_ms=(time.time() - start_time) * 1000,
                        success=False,
                        error_message=last_error
                    )
                
                result = response.json()
                
                content = result["choices"][0]["message"]["content"]
                usage = result.get("usage", {})
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)
                total_tokens = usage.get("total_tokens", 0)
                
                cost = (input_tokens * self.config.cost_per_input_token + 
                       output_tokens * self.config.cost_per_output_token)
                
                latency_ms = (time.time() - start_time) * 1000
                
                return LLMResponse(
                    content=content,
                    model_id=self.config.model_id,
                    provider=self.config.provider,
                    latency_ms=latency_ms,
                    tokens_used=total_tokens,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost=cost,
                    success=True
                )
            except httpx.ReadTimeout as e:
                latency_ms = (time.time() - start_time) * 1000
                logger.warning(f"OpenAI API超时 (重试 {retry + 1}/{max_retries}): {type(e).__name__}")
                last_error = f"请求超时"
                if retry < max_retries - 1:
                    if (
                        direct_fb
                        and proxy_env_set
                        and not tried_direct_fallback
                        and not self._httpx_force_direct
                    ):
                        tried_direct_fallback = True
                        logger.warning(
                            "LLM 经代理读超时，尝试直连回退 (OPENCLAW_LLM_DIRECT_FALLBACK=1)"
                        )
                        try:
                            await self.recycle_session(force=True, force_direct=True)
                        except Exception as re:
                            logger.debug(f"LLM recycle_session after timeout direct: {re}")
                        await asyncio.sleep(min(5.0, 1.0 + random.random()))
                        continue
                    try:
                        await self.recycle_session(force=True)
                    except Exception as re:
                        logger.debug(f"LLM recycle_session after timeout: {re}")
                    await asyncio.sleep(min(30.0, 2.0 * (2**retry) + random.random()))
                    continue
                return LLMResponse(
                    content="",
                    model_id=self.config.model_id,
                    provider=self.config.provider,
                    latency_ms=latency_ms,
                    success=False,
                    error_message=last_error
                )
            except httpx.HTTPStatusError as e:
                latency_ms = (time.time() - start_time) * 1000
                logger.error(f"OpenAI API HTTP错误: {e.response.status_code} - {e.response.text[:200]}")
                last_error = f"HTTP错误: {e.response.status_code}"
                if retry < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return LLMResponse(
                    content="",
                    model_id=self.config.model_id,
                    provider=self.config.provider,
                    latency_ms=latency_ms,
                    success=False,
                    error_message=last_error
                )
            except httpx.RequestError as e:
                latency_ms = (time.time() - start_time) * 1000
                logger.warning(f"OpenAI API网络错误 (重试 {retry + 1}/{max_retries}): {type(e).__name__}: {e}")
                last_error = f"网络错误: {type(e).__name__}"
                if retry < max_retries - 1:
                    err_l = str(e).lower()
                    proxyish = any(
                        x in err_l
                        for x in (
                            "disconnected",
                            "connection reset",
                            "broken pipe",
                            "proxy",
                            "tunnel",
                            "connect",
                            "timed out",
                            "timeout",
                        )
                    )
                    if (
                        direct_fb
                        and proxy_env_set
                        and not tried_direct_fallback
                        and proxyish
                        and not self._httpx_force_direct
                    ):
                        tried_direct_fallback = True
                        logger.warning(
                            "LLM 经代理请求失败，启用直连回退 (OPENCLAW_LLM_DIRECT_FALLBACK=1)；"
                            "若仍失败请检查容器出口或关闭此选项"
                        )
                        try:
                            await self.recycle_session(force=True, force_direct=True)
                        except Exception as re:
                            logger.debug(f"LLM recycle_session direct fallback: {re}")
                        await asyncio.sleep(min(5.0, 1.0 + random.random()))
                        continue
                    try:
                        await self.recycle_session(force=True)
                    except Exception as re:
                        logger.debug(f"LLM recycle_session after RequestError: {re}")
                    await asyncio.sleep(min(30.0, 2.0 * (2**retry) + random.random()))
                    continue
                return LLMResponse(
                    content="",
                    model_id=self.config.model_id,
                    provider=self.config.provider,
                    latency_ms=latency_ms,
                    success=False,
                    error_message=last_error
                )
            except Exception as e:
                latency_ms = (time.time() - start_time) * 1000
                logger.error(f"OpenAI API调用失败: {type(e).__name__}: {e}")
                last_error = str(e)
                if retry < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return LLMResponse(
                    content="",
                    model_id=self.config.model_id,
                    provider=self.config.provider,
                    latency_ms=latency_ms,
                    success=False,
                    error_message=last_error
                )
        
        return LLMResponse(
            content="",
            model_id=self.config.model_id,
            provider=self.config.provider,
            latency_ms=(time.time() - start_time) * 1000,
            success=False,
            error_message=last_error or "未知错误"
        )


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude提供者"""

    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """生成文本"""
        start_time = time.time()
        
        try:
            url = self.config.base_url or "https://api.anthropic.com/v1/messages"
            
            headers = {
                "x-api-key": self.config.api_key,
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01"
            }
            
            data = {
                "model": self.config.model_id,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
                "temperature": kwargs.get("temperature", self.config.temperature)
            }
            
            response = await self.session.post(url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            
            content = result["content"][0]["text"]
            usage = result.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            total_tokens = input_tokens + output_tokens
            
            cost = (input_tokens * self.config.cost_per_input_token + 
                   output_tokens * self.config.cost_per_output_token)
            
            latency_ms = (time.time() - start_time) * 1000
            
            return LLMResponse(
                content=content,
                model_id=self.config.model_id,
                provider=self.config.provider,
                latency_ms=latency_ms,
                tokens_used=total_tokens,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
                success=True
            )
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"Anthropic API调用失败: {e}")
            return LLMResponse(
                content="",
                model_id=self.config.model_id,
                provider=self.config.provider,
                latency_ms=latency_ms,
                success=False,
                error_message=str(e)
            )


class GoogleProvider(BaseLLMProvider):
    """Google Gemini提供者"""

    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """生成文本"""
        start_time = time.time()
        
        try:
            url = f"{self.config.base_url or 'https://generativelanguage.googleapis.com/v1beta/models'}/{self.config.model_id}:generateContent"
            
            params = {"key": self.config.api_key}
            headers = {"Content-Type": "application/json"}
            
            data = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": kwargs.get("temperature", self.config.temperature),
                    "maxOutputTokens": kwargs.get("max_tokens", self.config.max_tokens)
                }
            }
            
            response = await self.session.post(url, headers=headers, params=params, json=data)
            response.raise_for_status()
            result = response.json()
            
            content = result["candidates"][0]["content"]["parts"][0]["text"]
            latency_ms = (time.time() - start_time) * 1000
            
            return LLMResponse(
                content=content,
                model_id=self.config.model_id,
                provider=self.config.provider,
                latency_ms=latency_ms,
                tokens_used=0,
                success=True
            )
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"Google API调用失败: {e}")
            return LLMResponse(
                content="",
                model_id=self.config.model_id,
                provider=self.config.provider,
                latency_ms=latency_ms,
                success=False,
                error_message=str(e)
            )


class EnhancedLLMManager:
    """增强的大模型管理器"""

    def __init__(self):
        self.models: Dict[str, ModelConfig] = {}
        self.providers: Dict[str, BaseLLMProvider] = {}
        self.usage_stats: Dict[str, ModelUsageStats] = {}
        self.task_model_mapping: Dict[TaskType, List[str]] = {}
        self.default_model: Optional[str] = None
        self._initialized = False
        self._lock = asyncio.Lock()

    async def initialize(self, config: Dict[str, Any]):
        """初始化管理器"""
        logger.info("初始化增强大模型管理器...")
        
        # 加载预定义模型
        self._load_predefined_models()
        
        # 从配置加载自定义模型
        if "models" in config:
            for model_config in config["models"]:
                await self._register_model_from_config(model_config)
        
        # 设置任务-模型映射
        if "task_model_mapping" in config:
            for task_type, model_ids in config["task_model_mapping"].items():
                try:
                    task = TaskType(task_type)
                    self.task_model_mapping[task] = model_ids
                except ValueError:
                    logger.warning(f"未知任务类型: {task_type}")
        
        # 设置默认模型
        self.default_model = config.get("default_model", list(self.models.keys())[0] if self.models else None)
        
        # 初始化提供者
        for model_id, model_config in self.models.items():
            if model_config.enabled:
                await self._initialize_provider(model_id)
        
        self._initialized = True
        logger.info(f"增强大模型管理器初始化完成，加载了 {len(self.models)} 个模型")

    def _load_predefined_models(self):
        """加载预定义模型"""
        import os
        
        # 从环境变量读取API密钥
        xunfei_api_key = os.getenv("XUNFEI_API_KEY", "").strip()
        qianfan_api_key = os.getenv("QIANFAN_API_KEY", "").strip()
        
        predefined = [
            ModelConfig(
                provider=ModelProvider.OPENAI,
                model_id="astron-code-latest",
                display_name="讯飞 Astron Code Latest",
                base_url="https://maas-coding-api.cn-huabei-1.xf-yun.com/v2/chat/completions",
                api_key=xunfei_api_key,
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                context_window=32768,
                priority=15,
                fallback_models=["deepseek-v3.2", "lite"]
            ),
            ModelConfig(
                provider=ModelProvider.OPENAI,
                model_id="lite",
                display_name="讯飞星火 Spark Lite",
                base_url="https://spark-api-open.xf-yun.com/v1/chat/completions",
                api_key=xunfei_api_key,
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                context_window=32768,
                priority=14,
                fallback_models=["astron-code-latest", "deepseek-v3.2"]
            ),
            ModelConfig(
                provider=ModelProvider.OPENAI,
                model_id="generalv3.5",
                display_name="讯飞星火 Spark Max",
                base_url="https://spark-api-open.xf-yun.com/v1/chat/completions",
                api_key=xunfei_api_key,
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                context_window=98304,
                priority=13,
                fallback_models=["astron-code-latest", "lite"]
            ),
            ModelConfig(
                provider=ModelProvider.OPENAI,
                model_id="deepseek-v3.2",
                display_name="百度千帆 DeepSeek V3.2",
                base_url="https://qianfan.baidubce.com/v2/coding/chat/completions",
                api_key=qianfan_api_key,
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                context_window=98304,
                priority=12,
                fallback_models=["astron-code-latest", "lite"]
            ),
            ModelConfig(
                provider=ModelProvider.OPENAI,
                model_id="qianfan-code-latest",
                display_name="百度千帆 qianfan-code-latest",
                base_url="https://qianfan.baidubce.com/v2/coding/chat/completions",
                api_key=qianfan_api_key,
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                context_window=98304,
                priority=11,
                fallback_models=["astron-code-latest", "deepseek-v3.2"]
            ),
            ModelConfig(
                provider=ModelProvider.LOCAL,
                model_id="llama3",
                display_name="Llama 3 (本地)",
                base_url="http://localhost:11434/api/chat",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                context_window=8192,
                priority=5,
                fallback_models=[]
            )
        ]
        
        for model in predefined:
            self.models[model.model_id] = model
            self.usage_stats[model.model_id] = ModelUsageStats(model_id=model.model_id)

    async def _register_model_from_config(self, model_config: Dict[str, Any]):
        """从配置注册模型"""
        try:
            model_id = model_config["model_id"]
            
            # 如果预定义模型中已经有该模型，跳过（保留预定义模型的API Key）
            if model_id in self.models:
                logger.info(f"模型 {model_id} 已在预定义模型中，跳过配置加载")
                return
            
            provider = ModelProvider(model_config.get("provider", "custom"))
            
            model = ModelConfig(
                provider=provider,
                model_id=model_id,
                display_name=model_config.get("display_name", model_id),
                api_key=str(model_config.get("api_key", "") or "").strip(),
                base_url=model_config.get("base_url", ""),
                temperature=model_config.get("temperature", 0.7),
                max_tokens=model_config.get("max_tokens", 2000),
                timeout=model_config.get("timeout", 30.0),
                max_retries=int(model_config.get("max_retries", 3) or 3),
                cost_per_input_token=model_config.get("cost_per_input_token", 0.0),
                cost_per_output_token=model_config.get("cost_per_output_token", 0.0),
                context_window=model_config.get("context_window", 8192),
                supports_vision=model_config.get("supports_vision", False),
                supports_reasoning=model_config.get("supports_reasoning", False),
                enabled=model_config.get("enabled", True),
                priority=model_config.get("priority", 0),
                fallback_models=model_config.get("fallback_models", [])
            )
            
            self.models[model.model_id] = model
            self.usage_stats[model.model_id] = ModelUsageStats(model_id=model.model_id)
            logger.info(f"注册模型: {model.display_name} ({model.model_id})")
        except Exception as e:
            logger.error(f"注册模型失败: {e}")

    async def _initialize_provider(self, model_id: str):
        """初始化模型提供者"""
        if model_id not in self.models:
            return
        
        model_config = self.models[model_id]
        
        model_config.api_key = (model_config.api_key or "").strip()
        if not model_config.api_key and model_config.provider not in [ModelProvider.LOCAL]:
            logger.warning(f"模型 {model_id} 没有配置 API key，跳过初始化")
            model_config.enabled = False
            return
        
        if model_config.provider in [ModelProvider.OPENAI, ModelProvider.DEEPSEEK, 
                                    ModelProvider.QWEN, ModelProvider.KIMI, 
                                    ModelProvider.GLM, ModelProvider.CUSTOM]:
            provider = OpenAIProvider(model_config)
        elif model_config.provider == ModelProvider.ANTHROPIC:
            provider = AnthropicProvider(model_config)
        elif model_config.provider == ModelProvider.GOOGLE:
            provider = GoogleProvider(model_config)
        elif model_config.provider == ModelProvider.LOCAL:
            provider = OpenAIProvider(model_config)
        else:
            logger.warning(f"不支持的提供者: {model_config.provider}")
            return
        
        await provider.initialize()
        self.providers[model_id] = provider
        logger.info(f"✅ 模型 {model_id} 提供者初始化成功")

    def get_available_models(self) -> List[ModelConfig]:
        """获取可用模型列表"""
        return [model for model in self.models.values() if model.enabled]

    def get_model_config(self, model_id: str) -> Optional[ModelConfig]:
        """获取模型配置"""
        return self.models.get(model_id)

    async def select_model(self, task_type: TaskType = TaskType.GENERAL, 
                          prefer_reasoning: bool = False,
                          max_cost: Optional[float] = None) -> Optional[str]:
        """根据任务选择最优模型"""
        if task_type in self.task_model_mapping:
            for model_id in self.task_model_mapping[task_type]:
                if model_id in self.providers:
                    model = self.models.get(model_id)
                    if model and model.enabled:
                        if prefer_reasoning and not model.supports_reasoning:
                            continue
                        if max_cost is not None:
                            if (model.cost_per_input_token + model.cost_per_output_token * 1000) > max_cost:
                                continue
                        return model_id
        
        available_models = sorted(
            [m for m in self.models.values() if m.enabled and m.model_id in self.providers],
            key=lambda x: (-x.priority, x.cost_per_input_token)
        )
        
        for model in available_models:
            if prefer_reasoning and not model.supports_reasoning:
                continue
            if max_cost is not None:
                if (model.cost_per_input_token + model.cost_per_output_token * 1000) > max_cost:
                    continue
            return model.model_id
        
        return None

    async def generate(self, prompt: str, 
                      model_id: Optional[str] = None,
                      task_type: TaskType = TaskType.GENERAL,
                      prefer_reasoning: bool = False,
                      use_fallback: bool = True,
                      **kwargs) -> LLMResponse:
        """生成文本"""
        if not self._initialized:
            return LLMResponse(
                content="",
                model_id="none",
                provider=ModelProvider.CUSTOM,
                success=False,
                error_message="LLM管理器未初始化"
            )
        
        if not model_id:
            model_id = await self.select_model(task_type, prefer_reasoning)
            logger.debug(f"自动选择模型: {model_id}, 可用providers: {list(self.providers.keys())}")
        
        if not model_id:
            logger.error("没有可用的模型")
            return LLMResponse(
                content="",
                model_id="none",
                provider=ModelProvider.CUSTOM,
                success=False,
                error_message="没有可用的模型"
            )
        
        if model_id not in self.providers:
            logger.error(f"模型 {model_id} 没有初始化provider，可用: {list(self.providers.keys())}")
            return LLMResponse(
                content="",
                model_id=model_id,
                provider=ModelProvider.CUSTOM,
                success=False,
                error_message=f"模型提供者未初始化: {model_id}"
            )
        
        response = await self._generate_with_model(prompt, model_id, task_type, **kwargs)
        
        if not response.success and use_fallback:
            is_auth_error = getattr(response, 'error_code', None) == 'AUTH_FAILED'
            
            model_config = self.models.get(model_id)
            if model_config and model_config.fallback_models:
                for fallback_model_id in model_config.fallback_models:
                    if fallback_model_id in self.providers:
                        logger.info(f"尝试回退模型: {fallback_model_id}")
                        fallback_response = await self._generate_with_model(
                            prompt, fallback_model_id, task_type, **kwargs
                        )
                        if fallback_response.success:
                            return fallback_response
            
            if is_auth_error or (model_config and not model_config.fallback_models):
                available_models = sorted(
                    [m for m in self.models.values() 
                     if m.enabled and m.model_id in self.providers and m.model_id != model_id],
                    key=lambda x: -x.priority
                )
                for alt_model in available_models:
                    logger.info(f"认证失败，尝试备用模型: {alt_model.model_id}")
                    alt_response = await self._generate_with_model(
                        prompt, alt_model.model_id, task_type, **kwargs
                    )
                    if alt_response.success:
                        return alt_response
        
        return response

    async def _generate_with_model(self, prompt: str, model_id: str,
                                   task_type: TaskType, **kwargs) -> LLMResponse:
        """使用指定模型生成"""
        if model_id not in self.providers:
            return LLMResponse(
                content="",
                model_id=model_id,
                provider=self.models.get(model_id, ModelConfig(ModelProvider.CUSTOM, model_id, model_id)).provider,
                success=False,
                error_message=f"模型提供者未初始化: {model_id}"
            )
        
        MAX_PROMPT_CHARS = 150000
        if len(prompt) > MAX_PROMPT_CHARS:
            logger.warning(f"Prompt过长 ({len(prompt)} chars), 截断至 {MAX_PROMPT_CHARS}")
            prompt = prompt[:MAX_PROMPT_CHARS] + "\n\n[...内容已截断...]"
        
        provider = self.providers[model_id]
        response = await provider.generate(prompt, **kwargs)
        response.task_type = task_type
        
        # 更新使用统计
        await self._update_usage_stats(model_id, response)
        
        return response

    async def _update_usage_stats(self, model_id: str, response: LLMResponse):
        """更新使用统计"""
        if model_id not in self.usage_stats:
            return
        
        stats = self.usage_stats[model_id]
        stats.total_calls += 1
        
        if response.success:
            stats.successful_calls += 1
            stats.total_tokens += response.tokens_used
            stats.input_tokens += response.input_tokens
            stats.output_tokens += response.output_tokens
            stats.total_cost += response.cost
            stats.total_latency_ms += response.latency_ms
            stats.avg_latency_ms = stats.total_latency_ms / stats.successful_calls
        else:
            stats.failed_calls += 1
        
        stats.last_used = datetime.now()

    def get_usage_stats(self, model_id: Optional[str] = None) -> Union[ModelUsageStats, Dict[str, ModelUsageStats]]:
        """获取使用统计"""
        if model_id:
            return self.usage_stats.get(model_id)
        return self.usage_stats.copy()

    def get_success_rate(self, model_id: str) -> float:
        """获取成功率"""
        stats = self.usage_stats.get(model_id)
        if not stats or stats.total_calls == 0:
            return 0.0
        return stats.successful_calls / stats.total_calls

    async def switch_model(self, model_id: str) -> bool:
        """切换默认模型"""
        logger.info(f"[DEBUG switch_model] model_id: {model_id}", flush=True)
        logger.info(f"[DEBUG switch_model] models keys: {list(self.models.keys())}", flush=True)
        exists = model_id in self.models
        logger.info(f"[DEBUG switch_model] model_id in models: {exists}", flush=True)
        if exists:
            logger.info(f"[DEBUG switch_model] model enabled: {self.models[model_id].enabled}", flush=True)
        if model_id in self.models and self.models[model_id].enabled:
            self.default_model = model_id
            logger.info(f"默认模型已切换为: {model_id}")
            return True
        logger.info(f"[DEBUG switch_model] returning False", flush=True)
        return False

    async def set_model_api_key(self, model_id: str, api_key: str) -> bool:
        """设置模型API密钥"""
        if model_id not in self.models:
            return False
        
        self.models[model_id].api_key = (api_key or "").strip()
        
        # 重新初始化提供者
        if model_id in self.providers:
            await self.providers[model_id].cleanup()
        
        await self._initialize_provider(model_id)
        logger.info(f"已更新模型API密钥: {model_id}")
        return True

    async def enable_model(self, model_id: str) -> bool:
        """启用模型"""
        if model_id not in self.models:
            return False
        
        self.models[model_id].enabled = True
        if model_id not in self.providers:
            await self._initialize_provider(model_id)
        
        logger.info(f"已启用模型: {model_id}")
        return True

    async def disable_model(self, model_id: str) -> bool:
        """禁用模型"""
        if model_id not in self.models:
            return False
        
        self.models[model_id].enabled = False
        if model_id in self.providers:
            await self.providers[model_id].cleanup()
            del self.providers[model_id]
        
        logger.info(f"已禁用模型: {model_id}")
        return True

    async def cleanup(self):
        """清理资源"""
        for provider in self.providers.values():
            await provider.cleanup()
        self.providers.clear()
        self._initialized = False
        logger.info("增强大模型管理器已清理")


# 全局实例
_enhanced_llm_manager: Optional[EnhancedLLMManager] = None


def get_enhanced_llm_manager() -> EnhancedLLMManager:
    """获取增强LLM管理器单例"""
    global _enhanced_llm_manager
    if _enhanced_llm_manager is None:
        _enhanced_llm_manager = EnhancedLLMManager()
    return _enhanced_llm_manager
