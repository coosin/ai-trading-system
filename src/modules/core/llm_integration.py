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
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import httpx

logger = logging.getLogger(__name__)


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
        
        response = await self.generate(prompt, temperature=0.7, max_tokens=2000)
        
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
        
        response = await self.generate(prompt, temperature=0.7, max_tokens=2000)
        
        try:
            import json
            return json.loads(response)
        except Exception as e:
            logger.error(f"解析策略结果失败: {e}")
            return {"error": "策略生成失败"}


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
        
        response = await self.generate(prompt, max_tokens=2000)
        
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
        
        response = await self.generate(prompt, max_tokens=2000)
        
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
        
        response = await self.generate(prompt, temperature=0.7, max_tokens=2000)
        
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
        
        response = await self.generate(prompt, temperature=0.7, max_tokens=2000)
        
        try:
            import json
            return json.loads(response)
        except Exception as e:
            logger.error(f"解析策略结果失败: {e}")
            return {"error": "策略生成失败"}


@dataclass
class LLMResponse:
    """大模型响应"""
    content: str
    provider: str
    model: str
    timestamp: datetime = field(default_factory=datetime.now)
    processing_time: float = 0.0
    tokens_used: int = 0


class LLMManager:
    """大模型管理器"""
    
    def __init__(self):
        self.providers: Dict[str, LLMProvider] = {}
        self.default_provider: Optional[str] = None
        self._initialized = False
    
    async def initialize(self, config: Dict[str, Any]):
        """初始化大模型管理器"""
        # 注册OpenAI提供者
        if "openai" in config and config["openai"].get("api_key"):
            openai_config = config["openai"]
            self.providers["openai"] = OpenAIProvider(
                api_key=openai_config["api_key"],
                model=openai_config.get("model", "gpt-4-turbo")
            )
            logger.info("注册OpenAI大模型提供者")
        
        # 注册Anthropic提供者
        if "anthropic" in config and config["anthropic"].get("api_key"):
            anthropic_config = config["anthropic"]
            self.providers["anthropic"] = AnthropicProvider(
                api_key=anthropic_config["api_key"],
                model=anthropic_config.get("model", "claude-3-opus-20240229")
            )
            logger.info("注册Anthropic大模型提供者")
        
        # 注册本地LLM提供者
        if "local" in config:
            local_config = config["local"]
            self.providers["local"] = LocalLLMProvider(
                base_url=local_config.get("base_url", "http://localhost:11434/api/generate"),
                model=local_config.get("model", "llama3")
            )
            logger.info("注册本地大模型提供者")
        
        # 设置默认提供者
        self.default_provider = config.get("default_provider", "local")
        
        self._initialized = True
        logger.info("大模型管理器初始化完成")
    
    async def cleanup(self):
        """清理资源"""
        self.providers.clear()
        self.default_provider = None
        self._initialized = False
        logger.info("大模型管理器清理完成")
    
    def get_provider(self, provider_name: Optional[str] = None) -> Optional[LLMProvider]:
        """获取大模型提供者"""
        if not self._initialized:
            return None
        
        provider_name = provider_name or self.default_provider
        return self.providers.get(provider_name)
    
    async def generate(self, prompt: str, provider: Optional[str] = None, **kwargs) -> LLMResponse:
        """生成文本"""
        llm_provider = self.get_provider(provider)
        if not llm_provider:
            return LLMResponse(content="", provider="none", model="none")
        
        start_time = time.time()
        try:
            content = await llm_provider.generate(prompt, **kwargs)
            processing_time = time.time() - start_time
            
            return LLMResponse(
                content=content,
                provider=provider or self.default_provider or "none",
                model=getattr(llm_provider, "model", "unknown"),
                processing_time=processing_time
            )
        except Exception as e:
            logger.error(f"生成文本失败: {e}")
            return LLMResponse(
                content="",
                provider=provider or self.default_provider or "none",
                model=getattr(llm_provider, "model", "unknown")
            )
    
    async def analyze_market(self, market_data: Dict[str, Any], provider: Optional[str] = None) -> Dict[str, Any]:
        """分析市场数据"""
        llm_provider = self.get_provider(provider)
        if not llm_provider:
            return {"error": "未找到大模型提供者"}
        
        try:
            return await llm_provider.analyze_market(market_data)
        except Exception as e:
            logger.error(f"市场分析失败: {e}")
            return {"error": "分析失败"}
    
    async def generate_strategy(self, market_analysis: Dict[str, Any], provider: Optional[str] = None) -> Dict[str, Any]:
        """生成交易策略"""
        llm_provider = self.get_provider(provider)
        if not llm_provider:
            return {"error": "未找到大模型提供者"}
        
        try:
            return await llm_provider.generate_strategy(market_analysis)
        except Exception as e:
            logger.error(f"策略生成失败: {e}")
            return {"error": "策略生成失败"}
    
    async def analyze_news(self, news: List[str], provider: Optional[str] = None) -> Dict[str, Any]:
        """分析新闻"""
        prompt = f"""请分析以下新闻并提供市场影响评估：

{"\n".join(news)}

分析内容应包括：
1. 新闻对市场的潜在影响
2. 可能的价格走势
3. 投资建议
4. 风险评估

请以JSON格式返回分析结果。"""
        
        response = await self.generate(prompt, provider, temperature=0.7, max_tokens=2000)
        
        try:
            import json
            return json.loads(response.content)
        except Exception as e:
            logger.error(f"解析新闻分析结果失败: {e}")
            return {"error": "分析失败"}
    
    async def evaluate_risk(self, position: Dict[str, Any], provider: Optional[str] = None) -> Dict[str, Any]:
        """评估风险"""
        prompt = f"""请评估以下交易仓位的风险：

{position}

评估内容应包括：
1. 风险等级
2. 潜在损失
3. 风险缓解措施
4. 建议操作

请以JSON格式返回评估结果。"""
        
        response = await self.generate(prompt, provider, temperature=0.7, max_tokens=1000)
        
        try:
            import json
            return json.loads(response.content)
        except Exception as e:
            logger.error(f"解析风险评估结果失败: {e}")
            return {"error": "评估失败"}


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
    
    async def generate(self, prompt: str, provider: Optional[str] = None, **kwargs) -> LLMResponse:
        """生成文本（带记忆注入）"""
        if not self.llm_manager:
            return LLMResponse(
                content="",
                success=False,
                error_message="LLM管理器未初始化"
            )
        
        # 构建完整提示词（包含记忆）
        full_prompt = prompt
        if self.memory_manager:
            try:
                # 构建记忆上下文
                memory_context = await self.memory_manager.build_memory_context(prompt)
                if memory_context:
                    full_prompt = f"""请根据以下记忆和当前问题进行回答。

【记忆信息】
{memory_context}

【当前问题】
{prompt}

请参考记忆信息来回答当前问题，保持回答的连贯性和一致性。"""
                
                # 保存用户问题到短期记忆
                await self.memory_manager.add_short_term_memory(
                    f"用户: {prompt}",
                    importance=0.7
                )
                
            except Exception as e:
                logger.warning(f"记忆注入失败: {e}")
        
        # 使用EnhancedLLMManager的generate方法
        from src.modules.core.enhanced_llm_manager import TaskType
        # provider参数实际上是model_id，直接使用
        model_id = kwargs.get('model_id') or provider
        response = await self.llm_manager.generate(
            prompt=full_prompt,
            model_id=model_id,
            task_type=TaskType.GENERAL,
            **kwargs
        )
        
        # 保存AI回复到短期记忆
        if response.success and self.memory_manager:
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

        response = await self.generate(prompt, provider, temperature=0.7, max_tokens=2000)
        
        if response.success:
            try:
                import json
                result = json.loads(response.content)
                result["provider"] = response.provider.value if response.provider else provider
                return result
            except:
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

        response = await self.generate(prompt, provider, temperature=0.7, max_tokens=2000)
        
        if response.success:
            try:
                import json
                result = json.loads(response.content)
                result["provider"] = response.provider.value if response.provider else provider
                return result
            except:
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

        response = await self.generate(prompt, provider, temperature=0.7, max_tokens=2000)
        
        if response.success:
            try:
                import json
                result = json.loads(response.content)
                result["provider"] = response.provider.value if response.provider else provider
                return result
            except:
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

        response = await self.generate(prompt, provider, temperature=0.7, max_tokens=2000)
        
        if response.success:
            try:
                import json
                result = json.loads(response.content)
                result["provider"] = response.provider.value if response.provider else provider
                return result
            except:
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
        
        response = await self.generate(prompt, provider, temperature=0.5, max_tokens=1000)
        
        try:
            import json
            signal = json.loads(response.content)
            signal["timestamp"] = datetime.now().isoformat()
            signal["provider"] = provider or self.llm_manager.default_provider
            return signal
        except Exception as e:
            logger.error(f"解析交易信号失败: {e}")
            return {"error": "信号生成失败"}


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
        print("市场分析:")
        print(analysis)
        
        # 生成策略
        strategy = await llm_integration.generate_strategy(analysis)
        print("\n交易策略:")
        print(strategy)
        
        # 生成交易信号
        signal = await llm_integration.generate_trading_signal(market_data)
        print("\n交易信号:")
        print(signal)
        
        # 分析新闻
        news = [
            "美联储宣布加息25个基点",
            "比特币突破60000美元大关",
            "大型机构开始配置加密资产"
        ]
        news_analysis = await llm_integration.analyze_news(news)
        print("\n新闻分析:")
        print(news_analysis)
        
        # 评估风险
        position = {
            "symbol": "BTC/USDT",
            "size": 0.1,
            "entry_price": 50000,
            "stop_loss": 48000,
            "take_profit": 55000
        }
        risk_evaluation = await llm_integration.evaluate_risk(position)
        print("\n风险评估:")
        print(risk_evaluation)
        
    finally:
        await llm_integration.cleanup()


if __name__ == "__main__":
    asyncio.run(example_usage())
