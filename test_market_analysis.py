#!/usr/bin/env python3
"""
测试市场分析功能
"""

import asyncio
import logging
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)

# 导入市场分析相关模块
from src.modules.intelligence.sentiment_analyzer.analyzer import SentimentAnalyzer, SentimentType
from src.modules.core.database_manager import DatabaseManager


async def test_market_analysis():
    """测试市场分析功能"""
    logger.info("🧪 测试市场分析功能...")
    logger.info("=" * 50)
    
    # 1. 测试初始化情感分析器
    logger.info("1. 初始化情感分析器")
    db_manager = DatabaseManager(None)
    await db_manager.initialize()
    
    config = {
        "sources": ["twitter", "reddit", "news", "telegram"],
        "model_config": {
            "threshold": 0.3,
            "window_size": 60,
            "min_confidence": 0.5
        }
    }
    
    sentiment_analyzer = SentimentAnalyzer(db_manager, config)
    initialized = await sentiment_analyzer.initialize()
    logger.info(f"✅ 情感分析器初始化: {'成功' if initialized else '失败'}")
    assert initialized, "情感分析器初始化失败"
    
    # 2. 测试文本情感分析
    logger.info("2. 测试文本情感分析")
    test_texts = [
        ("Bitcoin is going to the moon!", "twitter"),
        ("The market is crashing", "news"),
        ("Market is stable today", "reddit"),
        ("Great buying opportunity", "telegram")
    ]
    
    for text, source in test_texts:
        result = await sentiment_analyzer.analyze_text(text, source)
        if result:
            logger.info(f"✅ 文本: '{text}' -> 情感: {result.sentiment.value}, 得分: {result.score:.2f}, 置信度: {result.confidence:.2f}")
        else:
            logger.warning(f"❌ 文本分析失败: {text}")
    
    # 3. 测试批量情感分析
    logger.info("3. 测试批量情感分析")
    batch_results = await sentiment_analyzer.analyze_batch(test_texts)
    logger.info(f"✅ 批量分析完成，处理了 {len(batch_results)} 条文本")
    assert len(batch_results) > 0, "批量分析失败"
    
    # 4. 测试情感趋势分析
    logger.info("4. 测试情感趋势分析")
    trend = await sentiment_analyzer.get_sentiment_trend()
    logger.info(f"✅ 情感趋势: 平均得分={trend.get('average_score', 0):.2f}, 主导情感={trend.get('dominant_sentiment', 'unknown')}, 趋势={trend.get('trend', 'unknown')}")
    
    # 5. 测试按来源的情感趋势
    logger.info("5. 测试按来源的情感趋势")
    for source in config["sources"]:
        source_trend = await sentiment_analyzer.get_sentiment_trend(source=source)
        if source_trend:
            logger.info(f"✅ 来源 {source}: 平均得分={source_trend.get('average_score', 0):.2f}, 主导情感={source_trend.get('dominant_sentiment', 'unknown')}")
    
    # 6. 测试市场整体情感
    logger.info("6. 测试市场整体情感")
    market_sentiment = await sentiment_analyzer.get_market_sentiment()
    logger.info(f"✅ 市场整体情感: 得分={market_sentiment.get('overall', 0):.2f}, 主导情感={market_sentiment.get('dominant', 'unknown')}, 置信度={market_sentiment.get('confidence', 0):.2f}")
    
    # 7. 测试健康状态检查
    logger.info("7. 测试健康状态检查")
    is_healthy = sentiment_analyzer.is_healthy()
    logger.info(f"✅ 健康状态: {'健康' if is_healthy else '异常'}")
    assert is_healthy, "健康状态检查失败"
    
    # 8. 测试关闭情感分析器
    logger.info("8. 测试关闭情感分析器")
    shutdown = await sentiment_analyzer.shutdown()
    logger.info(f"✅ 情感分析器关闭: {'成功' if shutdown else '失败'}")
    assert shutdown, "情感分析器关闭失败"
    
    # 清理数据库管理器
    await db_manager.cleanup()
    
    logger.info("=" * 50)
    logger.info("🎉 市场分析功能测试完成！")
    logger.info("✅ 所有测试通过")
    
    return True


if __name__ == "__main__":
    try:
        asyncio.run(test_market_analysis())
    except KeyboardInterrupt:
        print("\n👋 测试已停止")
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
