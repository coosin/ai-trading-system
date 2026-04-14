"""
业务流程管理器 - 实现数据采集→策略分析→信号生成→交易执行的完整闭环

核心功能：
1. 数据管道管理（市场数据采集、清洗、存储）
2. 策略分析引擎（多策略协同分析）
3. 信号生成器（基于策略和市场分析生成交易信号）
4. 交易执行器（订单路由和执行管理）
5. 风险管理（实时风险评估和控制）
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class PipelineStatus(Enum):
    """管道状态"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


class SignalType(Enum):
    """信号类型"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class TradingSignal:
    """交易信号"""
    signal_id: str
    strategy_id: str
    symbol: str
    signal_type: SignalType
    price: float
    quantity: float
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class MarketDataPipeline:
    """市场数据管道"""
    symbol: str
    interval: str = "1m"
    last_update: Optional[datetime] = None
    data_buffer: pd.DataFrame = field(default_factory=pd.DataFrame)
    status: PipelineStatus = PipelineStatus.IDLE


@dataclass
class StrategyAnalysis:
    """策略分析结果"""
    strategy_id: str
    symbol: str
    signals: List[TradingSignal] = field(default_factory=list)
    performance_metrics: Dict[str, float] = field(default_factory=dict)
    risk_assessment: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class BusinessProcessManager:
    """
    业务流程管理器 - 核心业务流程协调

    负责协调：
    - 市场数据采集管道
    - 策略分析引擎
    - 信号生成器
    - 交易执行器
    - 风险管理
    """

    def __init__(self, main_controller=None):
        """
        初始化业务流程管理器

        Args:
            main_controller: 主控制器实例
        """
        self.main_controller = main_controller

        # 管道管理
        self.data_pipelines: Dict[str, MarketDataPipeline] = {}
        self.pipeline_status: PipelineStatus = PipelineStatus.IDLE

        # 策略分析
        self.strategy_analyses: List[StrategyAnalysis] = []

        # 信号管理
        self.pending_signals: List[TradingSignal] = []
        self.executed_signals: List[TradingSignal] = []

        # AI集成
        self.llm_integration = None
        self.ai_analyses: Dict[str, Dict[str, Any]] = {}
        self.ai_strategies: Dict[str, Dict[str, Any]] = {}

        # 配置
        self.config = {
            "pipeline_interval": 60,  # 秒
            "signal_cooldown": 300,  # 秒
            "max_pending_signals": 10,
            "risk_check_enabled": True,
            "ai_enabled": True,
            "ai_model_id": "astron-code-latest",
        }

        # 状态管理
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._lock = asyncio.Lock()

        logger.info("业务流程管理器初始化完成")

    async def initialize(self) -> None:
        """初始化业务流程管理器"""
        logger.info("初始化业务流程管理器...")

        # 从主控制器加载配置
        if self.main_controller and self.main_controller.config_manager:
            bp_config = await self.main_controller.config_manager.get_config("business_process", {})
            self.config.update(bp_config)

        # 初始化LLM集成
        if self.main_controller and hasattr(self.main_controller, 'llm_integration'):
            self.llm_integration = self.main_controller.llm_integration
            logger.info("AI大模型集成已连接到业务流程管理器")

        self._running = True
        logger.info("业务流程管理器初始化完成")

    async def shutdown(self) -> None:
        """关闭业务流程管理器"""
        logger.info("关闭业务流程管理器...")

        self._running = False

        # 取消所有任务
        for task in self._tasks:
            if not task.done():
                task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()
        logger.info("业务流程管理器已关闭")

    async def start_pipeline(self) -> bool:
        """启动数据管道"""
        async with self._lock:
            if self.pipeline_status == PipelineStatus.RUNNING:
                logger.warning("数据管道已经在运行")
                return True

            self.pipeline_status = PipelineStatus.RUNNING

            # 启动管道处理任务
            self._tasks.append(asyncio.create_task(self._pipeline_worker()))

            logger.info("数据管道启动成功")
            return True

    async def stop_pipeline(self) -> bool:
        """停止数据管道"""
        async with self._lock:
            if self.pipeline_status != PipelineStatus.RUNNING:
                logger.warning("数据管道未在运行")
                return True

            self.pipeline_status = PipelineStatus.IDLE
            logger.info("数据管道停止成功")
            return True

    async def register_data_pipeline(self, symbol: str, interval: str = "1m") -> bool:
        """注册数据管道"""
        async with self._lock:
            if symbol in self.data_pipelines:
                logger.warning(f"数据管道已存在: {symbol}")
                return False

            self.data_pipelines[symbol] = MarketDataPipeline(
                symbol=symbol,
                interval=interval,
                status=PipelineStatus.IDLE
            )

            logger.info(f"注册数据管道: {symbol}")
            return True

    async def unregister_data_pipeline(self, symbol: str) -> bool:
        """注销数据管道"""
        async with self._lock:
            if symbol not in self.data_pipelines:
                logger.warning(f"数据管道不存在: {symbol}")
                return False

            del self.data_pipelines[symbol]
            logger.info(f"注销数据管道: {symbol}")
            return True

    async def process_market_data(self, symbol: str, data: pd.DataFrame) -> None:
        """
        处理市场数据

        Args:
            symbol: 交易对
            data: 市场数据
        """
        async with self._lock:
            if symbol not in self.data_pipelines:
                logger.warning(f"未注册的数据管道: {symbol}")
                return

            pipeline = self.data_pipelines[symbol]

            # 清洗和验证数据
            cleaned_data = await self._clean_market_data(data)

            # 更新数据缓冲区
            if pipeline.data_buffer.empty:
                pipeline.data_buffer = cleaned_data
            else:
                pipeline.data_buffer = pd.concat([pipeline.data_buffer, cleaned_data])
                pipeline.data_buffer = pipeline.data_buffer.drop_duplicates(subset=['timestamp'])
                pipeline.data_buffer = pipeline.data_buffer.sort_values('timestamp')

                # 限制缓冲区大小
                max_size = 10000
                if len(pipeline.data_buffer) > max_size:
                    pipeline.data_buffer = pipeline.data_buffer.tail(max_size)

            pipeline.last_update = datetime.now()
            pipeline.status = PipelineStatus.RUNNING

            logger.debug(f"处理市场数据: {symbol}, 数据点: {len(cleaned_data)}")

        # 触发策略分析
        await self._trigger_strategy_analysis(symbol)

    async def _clean_market_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        清洗市场数据

        Args:
            data: 原始市场数据

        Returns:
            清洗后的市场数据
        """
        if data.empty:
            return data

        cleaned = data.copy()

        # 移除无效值
        cleaned = cleaned.dropna()

        # 移除异常值（简单的3σ方法）
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in cleaned.columns:
                mean = cleaned[col].mean()
                std = cleaned[col].std()
                if std > 0:
                    cleaned = cleaned[
                        (cleaned[col] >= mean - 3 * std) &
                        (cleaned[col] <= mean + 3 * std)
                    ]

        return cleaned

    async def _trigger_strategy_analysis(self, symbol: str) -> None:
        """
        触发策略分析（集成 MarketIntelligenceEngine / 可选LLM）

        Args:
            symbol: 交易对
        """
        try:
            # 获取策略管理器
            strategy_manager = None
            if self.main_controller:
                strategy_manager = self.main_controller.get_strategy_manager()

            if not strategy_manager:
                logger.warning("策略管理器不可用")
                return

            # 获取市场数据
            pipeline = self.data_pipelines.get(symbol)
            if not pipeline or pipeline.data_buffer.empty:
                return

            # 构建市场数据
            latest_data = pipeline.data_buffer.tail(1).iloc[0]
            market_data_dict = {
                'symbol': symbol,
                'price': float(latest_data.get('close', 0)),
                'data': pipeline.data_buffer.tail(100).to_dict('records')
            }

            # ============================================
            # AI 智能分析集成
            # ============================================
            if self.config.get('ai_enabled', True) and self.llm_integration:
                try:
                    model_id = self.config.get('ai_model_id', 'astron-code-latest')
                    
                    # 1. AI 市场分析
                    logger.info(f"AI 正在分析 {symbol} 市场...")
                    ai_analysis = await self.llm_integration.analyze_market(
                        market_data_dict,
                        model_id=model_id
                    )
                    self.ai_analyses[symbol] = ai_analysis
                    logger.info(f"AI 市场分析完成: {symbol}")

                    # 2. AI 生成交易信号
                    logger.info(f"AI 正在生成 {symbol} 交易信号...")
                    ai_signal = await self.llm_integration.generate_trading_signal(
                        market_data_dict,
                        model_id=model_id
                    )
                    
                    # 处理 AI 生成的交易信号
                    if ai_signal and 'signal' in ai_signal:
                        signal_type_str = ai_signal.get('signal', 'hold')
                        if signal_type_str in ['buy', 'sell']:
                            signal_data = {
                                'signal_id': f'ai_sig_{datetime.now().timestamp()}',
                                'strategy_id': 'ai_strategy',
                                'signal_type': signal_type_str,
                                'price': market_data_dict['price'],
                                'quantity': ai_signal.get('quantity', 0.01),
                                'confidence': ai_signal.get('confidence', 0.7),
                                'metadata': {
                                    'ai_analysis': ai_analysis,
                                    'ai_signal': ai_signal,
                                    'is_ai_generated': True
                                }
                            }
                            
                            signal = TradingSignal(
                                signal_id=signal_data['signal_id'],
                                strategy_id=signal_data['strategy_id'],
                                symbol=symbol,
                                signal_type=SignalType(signal_data['signal_type']),
                                price=signal_data['price'],
                                quantity=signal_data['quantity'],
                                confidence=signal_data['confidence'],
                                metadata=signal_data['metadata'],
                                timestamp=datetime.now()
                            )
                            
                            logger.info(f"AI 生成信号: {signal_type_str} {symbol} @ {signal_data['price']}")
                            await self._process_signal(signal)
                
                except Exception as ai_error:
                    logger.error(f"AI 分析失败: {ai_error}")
            
            # ============================================
            # 传统策略分析（作为补充）
            # ============================================
            signals = await strategy_manager.generate_signals(market_data_dict)

            # 处理生成的信号
            for signal_data in signals:
                signal = TradingSignal(
                    signal_id=signal_data.get('signal_id', f'sig_{datetime.now().timestamp()}'),
                    strategy_id=signal_data.get('strategy_id', 'unknown'),
                    symbol=symbol,
                    signal_type=SignalType(signal_data.get('signal_type', 'hold')),
                    price=signal_data.get('price', 0.0),
                    quantity=signal_data.get('quantity', 0.0),
                    confidence=signal_data.get('confidence', 0.5),
                    metadata=signal_data.get('metadata', {})
                )

                await self._process_signal(signal)

        except Exception as e:
            logger.error(f"策略分析失败: {e}")

    async def _process_signal(self, signal: TradingSignal) -> bool:
        """
        处理交易信号

        Args:
            signal: 交易信号

        Returns:
            是否处理成功
        """
        # 风险检查
        if self.config["risk_check_enabled"]:
            if not await self._check_risk(signal):
                logger.warning(f"信号被风险检查拒绝: {signal.signal_id}")
                return False

        # 信号去重和冷却
        if await self._check_signal_cooldown(signal):
            logger.debug(f"信号在冷却期: {signal.signal_id}")
            return False

        async with self._lock:
            # 添加到待执行队列
            if len(self.pending_signals) < self.config["max_pending_signals"]:
                self.pending_signals.append(signal)
                logger.info(f"添加待执行信号: {signal.signal_id}, {signal.signal_type.value} {signal.symbol}")
                return True
            else:
                logger.warning(f"待执行信号队列已满，丢弃信号: {signal.signal_id}")
                return False

    async def _check_risk(self, signal: TradingSignal) -> bool:
        """
        检查风险

        Args:
            signal: 交易信号

        Returns:
            是否通过风险检查
        """
        try:
            # 获取风险管理器
            risk_manager = None
            if self.main_controller:
                # 这里可以集成风险管理器
                pass

            # 简单的风险检查
            if signal.confidence < 0.3:
                return False

            # 最大持仓检查
            # 最大亏损检查
            # VaR检查

            return True

        except Exception as e:
            logger.error(f"风险检查失败: {e}")
            return False

    async def _check_signal_cooldown(self, signal: TradingSignal) -> bool:
        """
        检查信号冷却期

        Args:
            signal: 交易信号

        Returns:
            是否在冷却期
        """
        cooldown_seconds = self.config["signal_cooldown"]

        # 检查最近是否有相同类型的信号
        now = datetime.now()
        for executed in self.executed_signals:
            if (executed.symbol == signal.symbol and
                executed.signal_type == signal.signal_type and
                (now - executed.timestamp).total_seconds() < cooldown_seconds):
                return True

        return False

    async def execute_pending_signals(self) -> int:
        """
        执行待处理信号

        Returns:
            执行的信号数量
        """
        executed_count = 0

        async with self._lock:
            signals_to_execute = self.pending_signals.copy()
            self.pending_signals.clear()

        for signal in signals_to_execute:
            if await self._execute_signal(signal):
                self.executed_signals.append(signal)
                executed_count += 1

                # 限制已执行信号历史
                max_history = 1000
                if len(self.executed_signals) > max_history:
                    self.executed_signals = self.executed_signals[-max_history:]

        return executed_count

    async def _execute_signal(self, signal: TradingSignal) -> bool:
        """
        执行单个信号

        Args:
            signal: 交易信号

        Returns:
            是否执行成功
        """
        try:
            logger.info(f"执行交易信号: {signal.signal_id}, {signal.signal_type.value} {signal.symbol} @ {signal.price}")

            # 获取交易所接口
            exchange = None
            if self.main_controller:
                # 这里可以集成交易所接口
                pass

            if not exchange:
                # 模拟执行
                logger.info(f"模拟执行交易: {signal.signal_type.value} {signal.quantity} {signal.symbol}")
                return True

            # 实际交易执行
            # order = await exchange.create_order(...)

            return True

        except Exception as e:
            logger.error(f"执行信号失败 {signal.signal_id}: {e}")
            return False

    async def _pipeline_worker(self) -> None:
        """管道工作任务"""
        logger.info("启动管道工作任务")

        while self._running:
            try:
                if self.pipeline_status == PipelineStatus.RUNNING:
                    # 执行待处理信号
                    await self.execute_pending_signals()

                await asyncio.sleep(self.config["pipeline_interval"])

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"管道工作任务错误: {e}")
                await asyncio.sleep(self.config["pipeline_interval"])

        logger.info("管道工作任务停止")

    async def get_pipeline_status(self) -> Dict[str, Any]:
        """获取管道状态"""
        async with self._lock:
            return {
                "status": self.pipeline_status.value,
                "pipeline_count": len(self.data_pipelines),
                "pending_signals": len(self.pending_signals),
                "executed_signals": len(self.executed_signals),
                "pipelines": {
                    symbol: {
                        "interval": pipeline.interval,
                        "last_update": pipeline.last_update.isoformat() if pipeline.last_update else None,
                        "buffer_size": len(pipeline.data_buffer),
                        "status": pipeline.status.value
                    }
                    for symbol, pipeline in self.data_pipelines.items()
                }
            }


# 使用示例
async def example_usage():
    """业务流程管理器使用示例"""

    # 创建业务流程管理器
    bp_manager = BusinessProcessManager()
    await bp_manager.initialize()

    try:
        # 注册数据管道
        await bp_manager.register_data_pipeline("BTC/USDT", "1m")

        # 启动管道
        await bp_manager.start_pipeline()

        # 模拟市场数据
        import numpy as np

        dates = pd.date_range(start='2024-01-01', periods=100, freq='1min')
        data = pd.DataFrame({
            'timestamp': dates,
            'open': np.random.normal(40000, 100, 100),
            'high': np.random.normal(40100, 100, 100),
            'low': np.random.normal(39900, 100, 100),
            'close': np.random.normal(40000, 100, 100),
            'volume': np.random.normal(1000, 100, 100)
        })

        # 处理市场数据
        await bp_manager.process_market_data("BTC/USDT", data)

        # 获取状态
        status = await bp_manager.get_pipeline_status()
        logger.info(f"管道状态: {status}")

        # 运行一段时间
        await asyncio.sleep(5)

    finally:
        await bp_manager.stop_pipeline()
        await bp_manager.shutdown()


if __name__ == "__main__":
    asyncio.run(example_usage())


    async def cleanup(self):
        """清理资源"""
        pass
