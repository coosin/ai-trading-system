"""
统一信息收集分析管理器

整合所有信息收集和分析功能：
1. 实时数据采集
2. 市场分析
3. 情感分析
4. 数据融合
5. 智能报告
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class MarketInfo:
    """市场信息汇总"""
    symbol: str
    timestamp: datetime
    
    # 价格数据
    current_price: float = 0.0
    price_change_24h: float = 0.0
    volume_24h: float = 0.0
    
    # 市场情绪
    sentiment_score: float = 0.0  # -1 到 1
    fear_greed_index: float = 50.0  # 0 到 100
    market_mood: str = "neutral"  # bullish, bearish, neutral
    
    # 技术指标
    rsi: float = 50.0
    macd_signal: str = "neutral"
    trend: str = "sideways"
    
    # 链上数据
    active_addresses: int = 0
    whale_activity: str = "normal"
    
    # 社交媒体
    twitter_sentiment: float = 0.0
    reddit_sentiment: float = 0.0
    news_sentiment: float = 0.0
    
    # 数据质量
    data_quality_score: float = 0.0
    sources_count: int = 0


@dataclass
class InfoCollectorConfig:
    """信息收集器配置"""
    enabled: bool = True
    update_interval: float = 60.0  # 秒
    
    # 功能开关
    enable_realtime_collection: bool = True
    enable_market_analysis: bool = True
    enable_sentiment_analysis: bool = True
    enable_onchain_analysis: bool = True
    
    # 数据源配置
    symbols: List[str] = field(default_factory=lambda: [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",
        "XRP/USDT", "ADA/USDT", "DOGE/USDT", "DOT/USDT"
    ])
    
    # 情感分析源
    sentiment_sources: List[str] = field(default_factory=lambda: [
        "twitter", "reddit", "news", "telegram"
    ])
    
    # 缓存配置
    cache_ttl: int = 300  # 秒
    max_cache_size: int = 1000


class UnifiedInfoCollector:
    """
    统一信息收集分析管理器
    
    整合所有信息收集和分析功能，提供统一接口
    """
    
    def __init__(self, main_controller=None, config: InfoCollectorConfig = None):
        """
        初始化统一信息收集器
        
        Args:
            main_controller: 主控制器实例
            config: 配置对象
        """
        self.main_controller = main_controller
        self.config = config or InfoCollectorConfig()
        
        # 子模块实例
        self.realtime_collector = None
        self.market_analyzer = None
        self.sentiment_analyzer = None
        self.onchain_integrator = None
        
        # 数据缓存
        self._market_info_cache: Dict[str, MarketInfo] = {}
        self._last_update: Dict[str, datetime] = {}
        
        # 回调函数
        self._callbacks: List[Callable] = []
        
        # 运行状态
        self._running = False
        self._tasks: List[asyncio.Task] = []
        
        logger.info("统一信息收集分析管理器初始化")
    
    async def initialize(self) -> bool:
        """
        初始化所有子模块
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            logger.info("🔧 初始化统一信息收集分析管理器...")
            
            # 1. 初始化实时数据采集器
            if self.config.enable_realtime_collection:
                await self._init_realtime_collector()
            
            # 2. 初始化市场分析器
            if self.config.enable_market_analysis:
                await self._init_market_analyzer()
            
            # 3. 初始化情感分析器
            if self.config.enable_sentiment_analysis:
                await self._init_sentiment_analyzer()
            
            # 4. 初始化链上数据集成器
            if self.config.enable_onchain_analysis:
                await self._init_onchain_integrator()
            
            logger.info("✅ 统一信息收集分析管理器初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ 统一信息收集分析管理器初始化失败: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False
    
    async def _init_realtime_collector(self):
        """初始化实时数据采集器"""
        try:
            from src.modules.data.realtime_data_collector import RealTimeDataCollector
            
            bpm = self.main_controller.business_process_manager if self.main_controller else None
            self.realtime_collector = RealTimeDataCollector(business_process_manager=bpm)
            
            # 配置数据源
            for symbol in self.config.symbols[:4]:  # 限制前4个
                await self.realtime_collector.add_data_source({
                    "name": f"{symbol}_ws",
                    "source_type": "websocket",
                    "symbol": symbol,
                    "enabled": True
                })
            
            logger.info("✅ 实时数据采集器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 实时数据采集器初始化失败: {e}")
            self.realtime_collector = None
    
    async def _init_market_analyzer(self):
        """初始化市场分析器"""
        try:
            from src.modules.data.own_market_analyzer import OwnMarketAnalyzer
            
            exchange = None
            if self.main_controller and hasattr(self.main_controller, 'ai_trading_engine'):
                exchange = self.main_controller.ai_trading_engine.exchange
            
            if exchange:
                self.market_analyzer = OwnMarketAnalyzer(exchange)
                logger.info("✅ 市场分析器已初始化")
            else:
                logger.warning("⚠️ 交易所未连接，市场分析器初始化延迟")
                self.market_analyzer = None
        except Exception as e:
            logger.warning(f"⚠️ 市场分析器初始化失败: {e}")
            self.market_analyzer = None
    
    async def _init_sentiment_analyzer(self):
        """初始化情感分析器"""
        try:
            from src.modules.intelligence.sentiment_analyzer.analyzer import SentimentAnalyzer
            
            db_manager = None
            if self.main_controller and hasattr(self.main_controller, 'database_manager'):
                db_manager = self.main_controller.database_manager
            
            if db_manager:
                config = {
                    "sources": self.config.sentiment_sources,
                    "model_config": {
                        "threshold": 0.3,
                        "window_size": 60,
                        "min_confidence": 0.5
                    }
                }
                self.sentiment_analyzer = SentimentAnalyzer(db_manager, config)
                await self.sentiment_analyzer.initialize()
                logger.info("✅ 情感分析器已初始化")
            else:
                logger.warning("⚠️ 数据库管理器未连接，情感分析器初始化延迟")
                self.sentiment_analyzer = None
        except Exception as e:
            logger.warning(f"⚠️ 情感分析器初始化失败: {e}")
            self.sentiment_analyzer = None
    
    async def _init_onchain_integrator(self):
        """初始化链上数据集成器"""
        try:
            from src.modules.data.onchain_integrator import OnChainDataIntegrator
            
            self.onchain_integrator = OnChainDataIntegrator()
            logger.info("✅ 链上数据集成器已初始化")
        except Exception as e:
            logger.warning(f"⚠️ 链上数据集成器初始化失败: {e}")
            self.onchain_integrator = None
    
    async def start(self):
        """启动信息收集"""
        if self._running:
            logger.warning("信息收集器已在运行")
            return
        
        logger.info("🚀 启动统一信息收集分析管理器...")
        self._running = True
        
        # 启动实时数据采集
        if self.realtime_collector:
            try:
                await self.realtime_collector.start()
                logger.info("✅ 实时数据采集已启动")
            except Exception as e:
                logger.error(f"实时数据采集启动失败: {e}")
        
        # 启动定时更新任务
        task = asyncio.create_task(self._periodic_update())
        self._tasks.append(task)
        
        logger.info("✅ 统一信息收集分析管理器已启动")
    
    async def stop(self):
        """停止信息收集"""
        if not self._running:
            return
        
        logger.info("🛑 停止统一信息收集分析管理器...")
        self._running = False
        
        # 停止实时数据采集
        if self.realtime_collector:
            try:
                await self.realtime_collector.stop()
            except Exception as e:
                logger.error(f"停止实时数据采集失败: {e}")
        
        # 取消所有任务
        for task in self._tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        self._tasks.clear()
        logger.info("✅ 统一信息收集分析管理器已停止")
    
    async def _periodic_update(self):
        """定时更新市场信息"""
        while self._running:
            try:
                # 更新所有监控的交易对
                for symbol in self.config.symbols:
                    try:
                        await self.update_market_info(symbol)
                        await asyncio.sleep(1)  # 避免请求过快
                    except Exception as e:
                        logger.debug(f"更新 {symbol} 市场信息失败: {e}")
                
                # 等待下次更新
                await asyncio.sleep(self.config.update_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"定时更新失败: {e}")
                await asyncio.sleep(10)
    
    async def update_market_info(self, symbol: str) -> Optional[MarketInfo]:
        """
        更新指定交易对的市场信息
        
        Args:
            symbol: 交易对符号
        
        Returns:
            MarketInfo: 市场信息对象
        """
        try:
            market_info = MarketInfo(
                symbol=symbol,
                timestamp=datetime.now()
            )
            
            # 1. 获取价格数据
            if self.main_controller and hasattr(self.main_controller, 'ai_trading_engine'):
                engine = self.main_controller.ai_trading_engine
                if engine and engine.exchange:
                    try:
                        ticker = await engine.exchange.get_ticker(symbol)
                        if ticker:
                            market_info.current_price = ticker.get('last', 0)
                            market_info.volume_24h = ticker.get('quoteVolume', 0)
                    except Exception as e:
                        logger.debug(f"获取 {symbol} 价格失败: {e}")
            
            # 2. 获取市场分析
            if self.market_analyzer:
                try:
                    analysis = await self.market_analyzer.analyze_market_sentiment(symbol)
                    if analysis:
                        market_info.sentiment_score = analysis.sentiment_score if hasattr(analysis, 'sentiment_score') else 0
                        market_info.fear_greed_index = analysis.fear_greed_index if hasattr(analysis, 'fear_greed_index') else 50
                        market_info.market_mood = analysis.sentiment if hasattr(analysis, 'sentiment') else "neutral"
                except Exception as e:
                    logger.debug(f"分析 {symbol} 市场情绪失败: {e}")
            
            # 3. 获取情感分析
            if self.sentiment_analyzer:
                try:
                    # 这里可以添加情感分析逻辑
                    market_info.twitter_sentiment = 0.0
                    market_info.reddit_sentiment = 0.0
                    market_info.news_sentiment = 0.0
                except Exception as e:
                    logger.debug(f"获取 {symbol} 情感分析失败: {e}")
            
            # 4. 计算数据质量分数
            market_info.sources_count = sum([
                1 if self.realtime_collector else 0,
                1 if self.market_analyzer else 0,
                1 if self.sentiment_analyzer else 0,
                1 if self.onchain_integrator else 0
            ])
            market_info.data_quality_score = min(market_info.sources_count / 4.0, 1.0)
            
            # 更新缓存
            self._market_info_cache[symbol] = market_info
            self._last_update[symbol] = datetime.now()
            
            # 触发回调
            await self._trigger_callbacks(market_info)
            
            return market_info
            
        except Exception as e:
            logger.error(f"更新 {symbol} 市场信息失败: {e}")
            return None
    
    async def _trigger_callbacks(self, market_info: MarketInfo):
        """触发回调函数"""
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(market_info)
                else:
                    callback(market_info)
            except Exception as e:
                logger.error(f"回调函数执行失败: {e}")
    
    def add_callback(self, callback: Callable):
        """添加回调函数"""
        self._callbacks.append(callback)
    
    def get_market_info(self, symbol: str) -> Optional[MarketInfo]:
        """
        获取缓存的市场信息
        
        Args:
            symbol: 交易对符号
        
        Returns:
            MarketInfo: 市场信息对象
        """
        return self._market_info_cache.get(symbol)
    
    def get_all_market_info(self) -> Dict[str, MarketInfo]:
        """获取所有缓存的市场信息"""
        return self._market_info_cache.copy()
    
    async def get_comprehensive_report(self, symbol: str) -> Dict[str, Any]:
        """
        生成综合分析报告
        
        Args:
            symbol: 交易对符号
        
        Returns:
            Dict: 综合报告
        """
        market_info = self.get_market_info(symbol)
        if not market_info:
            return {"error": "No data available"}
        
        report = {
            "symbol": symbol,
            "timestamp": market_info.timestamp.isoformat(),
            "price": {
                "current": market_info.current_price,
                "change_24h": market_info.price_change_24h,
                "volume_24h": market_info.volume_24h
            },
            "sentiment": {
                "score": market_info.sentiment_score,
                "fear_greed_index": market_info.fear_greed_index,
                "mood": market_info.market_mood
            },
            "technical": {
                "rsi": market_info.rsi,
                "macd_signal": market_info.macd_signal,
                "trend": market_info.trend
            },
            "social": {
                "twitter": market_info.twitter_sentiment,
                "reddit": market_info.reddit_sentiment,
                "news": market_info.news_sentiment
            },
            "quality": {
                "score": market_info.data_quality_score,
                "sources": market_info.sources_count
            }
        }
        
        return report
    
    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._running
    
    def get_status(self) -> Dict[str, Any]:
        """获取状态信息"""
        return {
            "running": self._running,
            "realtime_collector": self.realtime_collector is not None,
            "market_analyzer": self.market_analyzer is not None,
            "sentiment_analyzer": self.sentiment_analyzer is not None,
            "onchain_integrator": self.onchain_integrator is not None,
            "cached_symbols": len(self._market_info_cache),
            "monitored_symbols": self.config.symbols
        }
