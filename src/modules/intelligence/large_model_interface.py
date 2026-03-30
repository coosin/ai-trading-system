from __future__ import annotations

import asyncio
import logging
import time
import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple, Union

import aiohttp

from src.modules.core.data_fusion import FusedDataPoint

logger = logging.getLogger(__name__)


class ModelProvider(Enum):
    """模型提供商"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    AZURE = "azure"
    LOCAL = "local"


class ModelType(Enum):
    """模型类型"""
    GPT_3_5 = "gpt-3.5-turbo"
    GPT_4 = "gpt-4"
    GPT_4_TURBO = "gpt-4-turbo"
    CLAUDE_2 = "claude-2"
    CLAUDE_3 = "claude-3"
    GEMINI_PRO = "gemini-pro"
    CUSTOM = "custom"


@dataclass
class ModelResponse:
    """模型响应"""
    content: str
    model: ModelType
    provider: ModelProvider
    timestamp: float
    confidence: float
    tokens_used: int


@dataclass
class AnalysisResult:
    """分析结果"""
    market_analysis: str
    trend_prediction: str
    risk_assessment: str
    strategy_recommendation: str
    confidence: float
    timestamp: float


class LargeModelInterface:
    """大模型接口"""

    def __init__(self, config: Dict[str, Any]):
        """初始化大模型接口

        Args:
            config: 配置信息
        """
        self.config = config
        self.providers = config.get("providers", {})
        self.default_provider = ModelProvider(config.get("default_provider", "openai"))
        self.default_model = ModelType(config.get("default_model", "gpt-4-turbo"))
        self.api_keys = config.get("api_keys", {})
        self.session = None
        self.enabled = False

    async def initialize(self) -> bool:
        """初始化大模型接口

        Returns:
            bool: 初始化是否成功
        """
        try:
            # 创建HTTP会话
            self.session = aiohttp.ClientSession()
            self.enabled = True
            logger.info("LargeModelInterface initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize LargeModelInterface: {e}")
            return False

    async def shutdown(self) -> bool:
        """关闭大模型接口

        Returns:
            bool: 关闭是否成功
        """
        try:
            if self.session:
                await self.session.close()
            self.enabled = False
            logger.info("LargeModelInterface shutdown successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to shutdown LargeModelInterface: {e}")
            return False

    async def analyze_market(self, fused_data: List[FusedDataPoint]) -> Optional[AnalysisResult]:
        """分析市场数据

        Args:
            fused_data: 融合数据点列表

        Returns:
            Optional[AnalysisResult]: 分析结果
        """
        try:
            if not self.enabled:
                logger.warning("LargeModelInterface is not enabled")
                return None

            # 构建分析提示
            prompt = await self._build_market_analysis_prompt(fused_data)

            # 调用大模型
            response = await self.generate_response(prompt)
            if not response:
                return None

            # 解析响应
            analysis_result = await self._parse_analysis_response(response.content)
            if not analysis_result:
                return None

            return AnalysisResult(
                market_analysis=analysis_result.get("market_analysis", ""),
                trend_prediction=analysis_result.get("trend_prediction", ""),
                risk_assessment=analysis_result.get("risk_assessment", ""),
                strategy_recommendation=analysis_result.get("strategy_recommendation", ""),
                confidence=response.confidence,
                timestamp=time.time()
            )
        except Exception as e:
            logger.error(f"Error analyzing market: {e}")
            return None

    async def generate_trading_signal(self, analysis: AnalysisResult) -> Optional[Dict[str, Any]]:
        """生成交易信号

        Args:
            analysis: 分析结果

        Returns:
            Optional[Dict[str, Any]]: 交易信号
        """
        try:
            if not self.enabled:
                logger.warning("LargeModelInterface is not enabled")
                return None

            # 构建交易信号提示
            prompt = await self._build_trading_signal_prompt(analysis)

            # 调用大模型
            response = await self.generate_response(prompt)
            if not response:
                return None

            # 解析响应
            signal = await self._parse_trading_signal(response.content)
            if not signal:
                return None

            return signal
        except Exception as e:
            logger.error(f"Error generating trading signal: {e}")
            return None

    async def generate_response(self, prompt: str, provider: Optional[ModelProvider] = None, model: Optional[ModelType] = None) -> Optional[ModelResponse]:
        """生成模型响应

        Args:
            prompt: 提示文本
            provider: 模型提供商
            model: 模型类型

        Returns:
            Optional[ModelResponse]: 模型响应
        """
        try:
            if not self.enabled:
                logger.warning("LargeModelInterface is not enabled")
                return None

            # 使用默认提供商和模型
            provider = provider or self.default_provider
            model = model or self.default_model

            # 根据提供商调用不同的API
            if provider == ModelProvider.OPENAI:
                return await self._call_openai_api(prompt, model)
            elif provider == ModelProvider.ANTHROPIC:
                return await self._call_anthropic_api(prompt, model)
            elif provider == ModelProvider.GOOGLE:
                return await self._call_google_api(prompt, model)
            else:
                logger.warning(f"Unsupported provider: {provider}")
                return None
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return None

    async def _call_openai_api(self, prompt: str, model: ModelType) -> Optional[ModelResponse]:
        """调用OpenAI API

        Args:
            prompt: 提示文本
            model: 模型类型

        Returns:
            Optional[ModelResponse]: 模型响应
        """
        try:
            api_key = self.api_keys.get("openai")
            if not api_key:
                logger.error("OpenAI API key not configured")
                return None

            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            data = {
                "model": model.value,
                "messages": [
                    {"role": "system", "content": "You are a professional cryptocurrency trading analyst. Provide concise, data-driven analysis and recommendations."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 1000
            }

            async with self.session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    content = result["choices"][0]["message"]["content"]
                    tokens_used = result["usage"]["total_tokens"]
                    return ModelResponse(
                        content=content,
                        model=model,
                        provider=ModelProvider.OPENAI,
                        timestamp=time.time(),
                        confidence=0.9,
                        tokens_used=tokens_used
                    )
                else:
                    logger.error(f"OpenAI API error: {await response.text()}")
                    return None
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            return None

    async def _call_anthropic_api(self, prompt: str, model: ModelType) -> Optional[ModelResponse]:
        """调用Anthropic API

        Args:
            prompt: 提示文本
            model: 模型类型

        Returns:
            Optional[ModelResponse]: 模型响应
        """
        try:
            api_key = self.api_keys.get("anthropic")
            if not api_key:
                logger.error("Anthropic API key not configured")
                return None

            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            }
            data = {
                "model": model.value,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 1000
            }

            async with self.session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    content = result["content"][0]["text"]
                    tokens_used = result["usage"]["total_tokens"]
                    return ModelResponse(
                        content=content,
                        model=model,
                        provider=ModelProvider.ANTHROPIC,
                        timestamp=time.time(),
                        confidence=0.9,
                        tokens_used=tokens_used
                    )
                else:
                    logger.error(f"Anthropic API error: {await response.text()}")
                    return None
        except Exception as e:
            logger.error(f"Error calling Anthropic API: {e}")
            return None

    async def _call_google_api(self, prompt: str, model: ModelType) -> Optional[ModelResponse]:
        """调用Google API

        Args:
            prompt: 提示文本
            model: 模型类型

        Returns:
            Optional[ModelResponse]: 模型响应
        """
        try:
            api_key = self.api_keys.get("google")
            if not api_key:
                logger.error("Google API key not configured")
                return None

            url = f"https://generativelanguage.googleapis.com/v1/models/{model.value}:generateContent?key={api_key}"
            headers = {
                "Content-Type": "application/json"
            }
            data = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt}
                        ]
                    }
                ],
                "temperature": 0.3
            }

            async with self.session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    content = result["candidates"][0]["content"]["parts"][0]["text"]
                    return ModelResponse(
                        content=content,
                        model=model,
                        provider=ModelProvider.GOOGLE,
                        timestamp=time.time(),
                        confidence=0.9,
                        tokens_used=0
                    )
                else:
                    logger.error(f"Google API error: {await response.text()}")
                    return None
        except Exception as e:
            logger.error(f"Error calling Google API: {e}")
            return None

    async def _build_market_analysis_prompt(self, fused_data: List[FusedDataPoint]) -> str:
        """构建市场分析提示

        Args:
            fused_data: 融合数据点列表

        Returns:
            str: 提示文本
        """
        try:
            # 构建数据摘要
            data_summary = []
            for data_point in fused_data:
                data_summary.append(f"- {data_point.source}: {data_point.content} (timestamp: {data_point.timestamp})")

            prompt = f"""作为专业的加密货币交易分析师，请分析以下市场数据并提供详细分析：

{"\n".join(data_summary)}

请提供以下内容：
1. 市场分析：当前市场状况的综合分析
2. 趋势预测：短期和中期价格趋势预测
3. 风险评估：当前市场的风险因素
4. 策略建议：基于分析的交易策略建议

请以JSON格式输出，包含以下字段：
- market_analysis
- trend_prediction
- risk_assessment
- strategy_recommendation
"""

            return prompt
        except Exception as e:
            logger.error(f"Error building market analysis prompt: {e}")
            return ""

    async def _build_trading_signal_prompt(self, analysis: AnalysisResult) -> str:
        """构建交易信号提示

        Args:
            analysis: 分析结果

        Returns:
            str: 提示文本
        """
        try:
            prompt = f"""基于以下市场分析结果，生成具体的交易信号：

市场分析：{analysis.market_analysis}
趋势预测：{analysis.trend_prediction}
风险评估：{analysis.risk_assessment}
策略建议：{analysis.strategy_recommendation}

请提供以下内容：
1. 交易方向：买入/卖出/持有
2. 交易对：具体的交易对
3. 入场价格：建议的入场价格
4. 止损价格：建议的止损价格
5. 止盈价格：建议的止盈价格
6. 仓位大小：建议的仓位大小
7. 杠杆倍数：建议的杠杆倍数
8. 置信度：对该信号的置信度（0-1）

请以JSON格式输出，包含以下字段：
- direction
- symbol
- entry_price
- stop_loss
- take_profit
- position_size
- leverage
- confidence
"""

            return prompt
        except Exception as e:
            logger.error(f"Error building trading signal prompt: {e}")
            return ""

    async def _parse_analysis_response(self, content: str) -> Optional[Dict[str, str]]:
        """解析分析响应

        Args:
            content: 响应内容

        Returns:
            Optional[Dict[str, str]]: 解析结果
        """
        try:
            # 尝试从响应中提取JSON
            # 有时模型会在JSON前后添加一些文本
            import re
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                json_str = json_match.group(0)
                return json.loads(json_str)
            else:
                # 如果没有找到JSON，返回错误
                logger.error("No JSON found in analysis response")
                return None
        except Exception as e:
            logger.error(f"Error parsing analysis response: {e}")
            return None

    async def _parse_trading_signal(self, content: str) -> Optional[Dict[str, Any]]:
        """解析交易信号

        Args:
            content: 响应内容

        Returns:
            Optional[Dict[str, Any]]: 解析结果
        """
        try:
            # 尝试从响应中提取JSON
            import re
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                json_str = json_match.group(0)
                signal = json.loads(json_str)
                # 验证信号格式
                required_fields = ["direction", "symbol", "entry_price", "stop_loss", "take_profit", "position_size", "leverage", "confidence"]
                for field in required_fields:
                    if field not in signal:
                        logger.error(f"Missing required field: {field}")
                        return None
                return signal
            else:
                logger.error("No JSON found in trading signal response")
                return None
        except Exception as e:
            logger.error(f"Error parsing trading signal: {e}")
            return None

    def is_healthy(self) -> bool:
        """检查大模型接口健康状态

        Returns:
            bool: 健康状态
        """
        return self.enabled
