"""
AI策略生成器

让AI能够根据市场条件自主生成新的交易策略
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import json

logger = logging.getLogger(__name__)


class StrategyType(str, Enum):
    """策略类型"""
    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT = "breakout"
    SCALPING = "scalping"
    GRID = "grid"
    MOMENTUM = "momentum"
    CUSTOM = "custom"


@dataclass
class GeneratedStrategy:
    """生成的策略"""
    strategy_id: str
    name: str
    type: StrategyType
    description: str
    indicators: List[str]
    entry_rules: Dict[str, Any]
    exit_rules: Dict[str, Any]
    risk_management: Dict[str, Any]
    timeframes: List[str]
    symbols: List[str]
    parameters: Dict[str, Any]
    code: Optional[str] = None
    backtest_result: Optional[Dict] = None
    status: str = "generated"  # generated, backtesting, approved, deployed
    created_at: datetime = field(default_factory=datetime.now)
    performance_score: float = 0.0


@dataclass
class MarketCondition:
    """市场条件"""
    trend: str  # bullish, bearish, sideways
    volatility: float  # 0-1
    volume: float
    sentiment: str  # fear, neutral, greed
    onchain_metrics: Dict[str, Any] = field(default_factory=dict)
    social_sentiment: float = 0.0
    news_impact: str = "neutral"


class AIStrategyGenerator:
    """AI策略生成器"""
    
    def __init__(self, llm_integration=None, backtest_engine=None):
        self.llm_integration = llm_integration
        self.backtest_engine = backtest_engine
        
        self.generated_strategies: Dict[str, GeneratedStrategy] = {}
        self.strategy_templates = self._load_strategy_templates()
        
        self.config = {
            "min_confidence": 0.7,
            "min_backtest_sharpe": 1.5,
            "min_backtest_win_rate": 0.55,
            "max_strategies": 20,
        }
    
    def _load_strategy_templates(self) -> Dict[str, str]:
        """加载策略模板"""
        
        return {
            "trend_following": """
# 趋势跟踪策略
# 当市场趋势明确时使用

def trend_following_strategy(data):
    # 计算趋势指标
    ma_short = data['close'].rolling(window=20).mean()
    ma_long = data['close'].rolling(window=50).mean()
    
    # 生成信号
    signal = None
    if ma_short.iloc[-1] > ma_long.iloc[-1] and data['rsi'].iloc[-1] < 70:
        signal = 'buy'
    elif ma_short.iloc[-1] < ma_long.iloc[-1] and data['rsi'].iloc[-1] > 30:
        signal = 'sell'
    
    return signal
""",
            "mean_reversion": """
# 均值回归策略
# 当市场震荡时使用

def mean_reversion_strategy(data):
    # 计算布林带
    ma = data['close'].rolling(window=20).mean()
    std = data['close'].rolling(window=20).std()
    upper = ma + 2 * std
    lower = ma - 2 * std
    
    # 生成信号
    signal = None
    if data['close'].iloc[-1] < lower.iloc[-1]:
        signal = 'buy'
    elif data['close'].iloc[-1] > upper.iloc[-1]:
        signal = 'sell'
    
    return signal
""",
            "breakout": """
# 突破策略
# 当市场即将突破时使用

def breakout_strategy(data):
    # 计算支撑阻力位
    high = data['high'].rolling(window=20).max()
    low = data['low'].rolling(window=20).min()
    
    # 生成信号
    signal = None
    if data['close'].iloc[-1] > high.iloc[-2]:
        signal = 'buy'
    elif data['close'].iloc[-1] < low.iloc[-2]:
        signal = 'sell'
    
    return signal
"""
        }
    
    async def generate_strategy(
        self,
        market_condition: MarketCondition,
        strategy_type: Optional[StrategyType] = None
    ) -> GeneratedStrategy:
        """生成新策略"""
        
        import uuid
        
        logger.info(f"开始生成策略，市场条件: {market_condition.trend}")
        
        # 1. 分析市场条件，确定策略类型
        if not strategy_type:
            strategy_type = self._determine_strategy_type(market_condition)
        
        # 2. AI生成策略
        strategy = await self._generate_with_ai(market_condition, strategy_type)
        
        if not strategy:
            logger.error("AI策略生成失败")
            return None
        
        # 3. 回测验证
        backtest_result = await self._backtest_strategy(strategy)
        
        if backtest_result:
            strategy.backtest_result = backtest_result
            strategy.performance_score = self._calculate_performance_score(backtest_result)
            
            # 4. 如果通过验证，保存策略
            if self._is_strategy_valid(backtest_result):
                strategy.status = "approved"
                self.generated_strategies[strategy.strategy_id] = strategy
                
                logger.info(f"✅ 策略生成成功: {strategy.name}")
            else:
                strategy.status = "rejected"
                logger.warning(f"⚠️ 策略未通过验证: {strategy.name}")
        
        return strategy
    
    def _determine_strategy_type(self, condition: MarketCondition) -> StrategyType:
        """根据市场条件确定策略类型"""
        
        if condition.trend == "bullish" and condition.volatility < 0.3:
            return StrategyType.TREND_FOLLOWING
        elif condition.trend == "sideways" and condition.volatility > 0.5:
            return StrategyType.MEAN_REVERSION
        elif condition.volatility > 0.7:
            return StrategyType.BREAKOUT
        elif condition.volatility < 0.2:
            return StrategyType.SCALPING
        else:
            return StrategyType.MOMENTUM
    
    async def _generate_with_ai(
        self,
        condition: MarketCondition,
        strategy_type: StrategyType
    ) -> Optional[GeneratedStrategy]:
        """使用AI生成策略"""
        
        import uuid
        
        try:
            # 构建提示词
            prompt = f"""
根据以下市场条件，生成一个{strategy_type.value}类型的交易策略：

市场条件：
- 趋势: {condition.trend}
- 波动率: {condition.volatility:.2f}
- 成交量: {condition.volume:.2f}
- 市场情绪: {condition.sentiment}
- 链上指标: {json.dumps(condition.onchain_metrics, indent=2)}
- 社交媒体情绪: {condition.social_sentiment:.2f}
- 新闻影响: {condition.news_impact}

请生成一个完整的交易策略，包括：
1. 策略名称和描述
2. 使用的技术指标
3. 入场规则
4. 出场规则
5. 风险管理规则
6. 适用的时间框架
7. 适用的交易对

以JSON格式返回。
"""
            
            # 调用AI生成
            if self.llm_integration:
                response = await self.llm_integration.generate(prompt)
                
                # 解析AI响应
                strategy_data = self._parse_strategy_response(response, strategy_type)
                
                if strategy_data:
                    return GeneratedStrategy(
                        strategy_id=str(uuid.uuid4()),
                        name=strategy_data.get("name", f"AI_{strategy_type.value}"),
                        type=strategy_type,
                        description=strategy_data.get("description", ""),
                        indicators=strategy_data.get("indicators", []),
                        entry_rules=strategy_data.get("entry_rules", {}),
                        exit_rules=strategy_data.get("exit_rules", {}),
                        risk_management=strategy_data.get("risk_management", {}),
                        timeframes=strategy_data.get("timeframes", ["1h"]),
                        symbols=strategy_data.get("symbols", ["BTC/USDT"]),
                        parameters=strategy_data.get("parameters", {}),
                        code=strategy_data.get("code", self.strategy_templates.get(strategy_type.value))
                    )
            
            # 如果AI生成失败，使用模板
            return self._generate_from_template(strategy_type)
            
        except Exception as e:
            logger.error(f"AI策略生成失败: {e}")
            return self._generate_from_template(strategy_type)
    
    def _parse_strategy_response(self, response: str, strategy_type: StrategyType) -> Optional[Dict]:
        """解析AI响应"""
        
        try:
            # 尝试解析JSON
            if isinstance(response, dict):
                return response
            
            # 尝试从文本中提取JSON
            import re
            
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group(0))
            
        except Exception as e:
            logger.error(f"解析AI响应失败: {e}")
        
        return None
    
    def _generate_from_template(self, strategy_type: StrategyType) -> GeneratedStrategy:
        """从模板生成策略"""
        
        import uuid
        
        template = self.strategy_templates.get(strategy_type.value, "")
        
        return GeneratedStrategy(
            strategy_id=str(uuid.uuid4()),
            name=f"Template_{strategy_type.value}",
            type=strategy_type,
            description=f"基于模板的{strategy_type.value}策略",
            indicators=["MA", "RSI", "MACD"],
            entry_rules={},
            exit_rules={},
            risk_management={},
            timeframes=["1h"],
            symbols=["BTC/USDT"],
            parameters={},
            code=template
        )
    
    async def _backtest_strategy(self, strategy: GeneratedStrategy) -> Optional[Dict]:
        """回测策略"""
        
        if not self.backtest_engine:
            return None
        
        try:
            # 执行回测
            result = await self.backtest_engine.run_backtest(
                strategy_code=strategy.code,
                symbol=strategy.symbols[0] if strategy.symbols else "BTC/USDT",
                timeframe=strategy.timeframes[0] if strategy.timeframes else "1h"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"策略回测失败: {e}")
            return None
    
    def _calculate_performance_score(self, backtest_result: Dict) -> float:
        """计算策略表现分数"""
        
        score = 0.0
        
        # Sharpe比率 (权重40%)
        sharpe = backtest_result.get("sharpe_ratio", 0)
        score += min(sharpe / 3.0, 1.0) * 0.4
        
        # 胜率 (权重30%)
        win_rate = backtest_result.get("win_rate", 0)
        score += win_rate * 0.3
        
        # 最大回撤 (权重30%)
        max_dd = backtest_result.get("max_drawdown", 1)
        score += max(1 - max_dd, 0) * 0.3
        
        return score
    
    def _is_strategy_valid(self, backtest_result: Dict) -> bool:
        """验证策略是否有效"""
        
        sharpe = backtest_result.get("sharpe_ratio", 0)
        win_rate = backtest_result.get("win_rate", 0)
        max_dd = backtest_result.get("max_drawdown", 1)
        
        return (
            sharpe >= self.config["min_backtest_sharpe"] and
            win_rate >= self.config["min_backtest_win_rate"] and
            max_dd < 0.3
        )
    
    async def optimize_existing_strategy(
        self,
        strategy_id: str,
        performance_data: Dict
    ) -> Optional[GeneratedStrategy]:
        """优化现有策略"""
        
        if strategy_id not in self.generated_strategies:
            return None
        
        strategy = self.generated_strategies[strategy_id]
        
        # AI分析表现数据
        optimization_suggestions = await self._analyze_performance(performance_data)
        
        # 应用优化建议
        optimized_strategy = await self._apply_optimizations(strategy, optimization_suggestions)
        
        return optimized_strategy
    
    async def _analyze_performance(self, performance_data: Dict) -> List[str]:
        """分析表现数据"""
        
        suggestions = []
        
        # 分析胜率
        if performance_data.get("win_rate", 0) < 0.5:
            suggestions.append("提高入场条件严格度")
        
        # 分析最大回撤
        if performance_data.get("max_drawdown", 0) > 0.15:
            suggestions.append("加强止损机制")
        
        # 分析盈亏比
        if performance_data.get("profit_factor", 0) < 1.5:
            suggestions.append("优化止盈策略")
        
        return suggestions
    
    async def _apply_optimizations(
        self,
        strategy: GeneratedStrategy,
        suggestions: List[str]
    ) -> GeneratedStrategy:
        """应用优化建议"""
        
        # 创建优化后的策略副本
        import uuid
        
        optimized = GeneratedStrategy(
            strategy_id=str(uuid.uuid4()),
            name=f"{strategy.name}_optimized",
            type=strategy.type,
            description=f"{strategy.description} (已优化)",
            indicators=strategy.indicators.copy(),
            entry_rules=strategy.entry_rules.copy(),
            exit_rules=strategy.exit_rules.copy(),
            risk_management=strategy.risk_management.copy(),
            timeframes=strategy.timeframes.copy(),
            symbols=strategy.symbols.copy(),
            parameters=strategy.parameters.copy(),
            code=strategy.code
        )
        
        # 应用建议
        for suggestion in suggestions:
            if "入场条件" in suggestion:
                optimized.entry_rules["confidence_threshold"] = 0.75
            elif "止损" in suggestion:
                optimized.risk_management["stop_loss_percent"] = 0.02
            elif "止盈" in suggestion:
                optimized.risk_management["take_profit_percent"] = 0.05
        
        return optimized
    
    def get_all_strategies(self) -> List[GeneratedStrategy]:
        """获取所有策略"""
        return list(self.generated_strategies.values())
    
    def get_approved_strategies(self) -> List[GeneratedStrategy]:
        """获取已批准的策略"""
        return [s for s in self.generated_strategies.values() if s.status == "approved"]
