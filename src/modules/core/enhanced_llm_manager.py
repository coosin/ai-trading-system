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
    timeout: float = 30.0
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


class BaseLLMProvider(ABC):
    """LLM提供者基类"""

    def __init__(self, config: ModelConfig):
        self.config = config
        self.session: Optional[httpx.AsyncClient] = None

    async def initialize(self):
        """初始化"""
        self.session = httpx.AsyncClient(timeout=self.config.timeout)

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

    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """生成文本"""
        start_time = time.time()
        
        try:
            # 构建完整的URL
            base_url = self.config.base_url or "https://api.openai.com/v1"
            # 如果base_url已经包含/chat/completions，则不再添加
            if base_url.endswith('/chat/completions'):
                url = base_url
            elif base_url.endswith('/v1'):
                url = f"{base_url}/chat/completions"
            else:
                # 对于其他情况，尝试添加/chat/completions
                url = f"{base_url}/chat/completions"
            
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": self.config.model_id,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": kwargs.get("temperature", self.config.temperature),
                "max_tokens": kwargs.get("max_tokens", self.config.max_tokens)
            }
            
            response = await self.session.post(url, headers=headers, json=data)
            response.raise_for_status()
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
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"OpenAI API调用失败: {e}")
            return LLMResponse(
                content="",
                model_id=self.config.model_id,
                provider=self.config.provider,
                latency_ms=latency_ms,
                success=False,
                error_message=str(e)
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
        predefined = [
            # OpenAI模型
            ModelConfig(
                provider=ModelProvider.OPENAI,
                model_id="gpt-4",
                display_name="GPT-4",
                base_url="https://api.openai.com/v1/chat/completions",
                cost_per_input_token=0.00003,
                cost_per_output_token=0.00006,
                context_window=8192,
                priority=10
            ),
            ModelConfig(
                provider=ModelProvider.OPENAI,
                model_id="gpt-4-turbo",
                display_name="GPT-4 Turbo",
                base_url="https://api.openai.com/v1/chat/completions",
                cost_per_input_token=0.00001,
                cost_per_output_token=0.00003,
                context_window=128000,
                priority=9
            ),
            # DeepSeek模型
            ModelConfig(
                provider=ModelProvider.DEEPSEEK,
                model_id="deepseek-chat",
                display_name="DeepSeek Chat",
                base_url="https://api.deepseek.com/v1/chat/completions",
                cost_per_input_token=0.000001,
                cost_per_output_token=0.000002,
                context_window=32768,
                priority=8
            ),
            ModelConfig(
                provider=ModelProvider.DEEPSEEK,
                model_id="deepseek-reasoner",
                display_name="DeepSeek Reasoner",
                base_url="https://api.deepseek.com/v1/chat/completions",
                cost_per_input_token=0.000002,
                cost_per_output_token=0.000008,
                context_window=65536,
                supports_reasoning=True,
                priority=7
            ),
            # Anthropic模型
            ModelConfig(
                provider=ModelProvider.ANTHROPIC,
                model_id="claude-3-opus-20240229",
                display_name="Claude 3 Opus",
                base_url="https://api.anthropic.com/v1/messages",
                cost_per_input_token=0.000015,
                cost_per_output_token=0.000075,
                context_window=200000,
                priority=6
            ),
            # Qwen模型
            ModelConfig(
                provider=ModelProvider.QWEN,
                model_id="qwen-max",
                display_name="Qwen Max",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                cost_per_input_token=0.000008,
                cost_per_output_token=0.00002,
                context_window=32768,
                priority=5
            ),
            # 讯飞模型
            ModelConfig(
                provider=ModelProvider.OPENAI,
                model_id="astron-code-latest",
                display_name="讯飞 astron-code-latest",
                base_url="https://maas-coding-api.cn-huabei-1.xf-yun.com/v2/chat/completions",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                context_window=32768,
                priority=8
            ),
            # 本地模型
            ModelConfig(
                provider=ModelProvider.LOCAL,
                model_id="llama3",
                display_name="Llama 3",
                base_url="http://localhost:11434/api/chat",
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                context_window=8192,
                priority=1
            )
        ]
        
        for model in predefined:
            self.models[model.model_id] = model
            self.usage_stats[model.model_id] = ModelUsageStats(model_id=model.model_id)

    async def _register_model_from_config(self, model_config: Dict[str, Any]):
        """从配置注册模型"""
        try:
            provider = ModelProvider(model_config.get("provider", "custom"))
            
            model = ModelConfig(
                provider=provider,
                model_id=model_config["model_id"],
                display_name=model_config.get("display_name", model_config["model_id"]),
                api_key=model_config.get("api_key", ""),
                base_url=model_config.get("base_url", ""),
                temperature=model_config.get("temperature", 0.7),
                max_tokens=model_config.get("max_tokens", 2000),
                timeout=model_config.get("timeout", 30.0),
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
        # 首先检查任务特定的模型映射
        if task_type in self.task_model_mapping:
            for model_id in self.task_model_mapping[task_type]:
                model = self.models.get(model_id)
                if model and model.enabled:
                    if prefer_reasoning and not model.supports_reasoning:
                        continue
                    if max_cost is not None:
                        if (model.cost_per_input_token + model.cost_per_output_token * 1000) > max_cost:
                            continue
                    return model_id
        
        # 如果没有任务映射，按优先级选择
        available_models = sorted(
            [m for m in self.models.values() if m.enabled],
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
        
        # 选择模型
        if not model_id:
            model_id = await self.select_model(task_type, prefer_reasoning)
        
        if not model_id:
            return LLMResponse(
                content="",
                model_id="none",
                provider=ModelProvider.CUSTOM,
                success=False,
                error_message="没有可用的模型"
            )
        
        # 尝试使用选定的模型
        response = await self._generate_with_model(prompt, model_id, task_type, **kwargs)
        
        # 如果失败且启用了回退，尝试回退模型
        if not response.success and use_fallback:
            model_config = self.models.get(model_id)
            if model_config and model_config.fallback_models:
                for fallback_model_id in model_config.fallback_models:
                    if fallback_model_id in self.models and self.models[fallback_model_id].enabled:
                        logger.info(f"尝试回退模型: {fallback_model_id}")
                        fallback_response = await self._generate_with_model(
                            prompt, fallback_model_id, task_type, **kwargs
                        )
                        if fallback_response.success:
                            return fallback_response
        
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
        print(f"[DEBUG switch_model] model_id: {model_id}", flush=True)
        print(f"[DEBUG switch_model] models keys: {list(self.models.keys())}", flush=True)
        exists = model_id in self.models
        print(f"[DEBUG switch_model] model_id in models: {exists}", flush=True)
        if exists:
            print(f"[DEBUG switch_model] model enabled: {self.models[model_id].enabled}", flush=True)
        if model_id in self.models and self.models[model_id].enabled:
            self.default_model = model_id
            logger.info(f"默认模型已切换为: {model_id}")
            return True
        print(f"[DEBUG switch_model] returning False", flush=True)
        return False

    async def set_model_api_key(self, model_id: str, api_key: str) -> bool:
        """设置模型API密钥"""
        if model_id not in self.models:
            return False
        
        self.models[model_id].api_key = api_key
        
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
