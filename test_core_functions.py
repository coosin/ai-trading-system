#!/usr/bin/env python3
"""
测试核心功能模块
"""

import asyncio
import logging
import sys

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

async def test_machine_learning():
    """测试机器学习模型管理器"""
    try:
        from src.modules.intelligence.machine_learning.model_manager import ModelManager, ModelType
        logger.info("测试机器学习模型管理器...")
        config = {
            "models": {
                "lstm": {
                    "hidden_size": 64,
                    "num_layers": 2,
                    "dropout": 0.2
                },
                "gru": {
                    "hidden_size": 64,
                    "num_layers": 2,
                    "dropout": 0.2
                },
                "transformer": {
                    "hidden_size": 64,
                    "num_layers": 2,
                    "nhead": 2
                }
            }
        }
        model_manager = ModelManager(config)
        await model_manager.initialize()
        logger.info("机器学习模型管理器初始化成功")
        await model_manager.shutdown()
        return True
    except Exception as e:
        logger.error(f"测试机器学习模型管理器失败: {e}")
        return False

async def test_data_fusion():
    """测试数据融合系统"""
    try:
        from src.modules.core.data_fusion import DataFusionSystem
        logger.info("测试数据融合系统...")
        config = {
            "data_sources": {
                "market": True,
                "on_chain": True,
                "social": True,
                "news": True,
                "macro": True
            }
        }
        data_fusion = DataFusionSystem(config)
        await data_fusion.initialize()
        logger.info("数据融合系统初始化成功")
        await data_fusion.shutdown()
        return True
    except Exception as e:
        logger.error(f"测试数据融合系统失败: {e}")
        return False

async def test_risk_manager():
    """测试高级风险管理系统"""
    try:
        from src.modules.core.risk_manager import RiskManager
        logger.info("测试高级风险管理系统...")
        config = {
            "risk_thresholds": {
                "low": 0.2,
                "medium": 0.4,
                "high": 0.7,
                "extreme": 1.0
            },
            "var_confidence": 0.95,
            "var_horizon": 1,
            "max_position_size": 0.1,
            "max_leverage": 3,
            "max_drawdown": 0.2
        }
        risk_manager = AdvancedRiskManager(None, config)
        await risk_manager.initialize()
        logger.info("高级风险管理系统初始化成功")
        await risk_manager.shutdown()
        return True
    except Exception as e:
        logger.error(f"测试高级风险管理系统失败: {e}")
        return False

async def test_fund_manager():
    """测试智能资金管理系统"""
    try:
        from src.modules.core.risk_manager import RiskManager
        from src.modules.core.intelligent_fund_manager import IntelligentFundManager
        logger.info("测试智能资金管理系统...")
        risk_config = {
            "risk_thresholds": {
                "low": 0.2,
                "medium": 0.4,
                "high": 0.7,
                "extreme": 1.0
            }
        }
        fund_config = {
            "initial_funds": 10000,
            "risk_per_trade": 0.02,
            "max_leverage": 3
        }
        risk_manager = AdvancedRiskManager(None, risk_config)
        await risk_manager.initialize()
        fund_manager = IntelligentFundManager(None, risk_manager, fund_config)
        await fund_manager.initialize()
        logger.info("智能资金管理系统初始化成功")
        await fund_manager.shutdown()
        await risk_manager.shutdown()
        return True
    except Exception as e:
        logger.error(f"测试智能资金管理系统失败: {e}")
        return False

async def test_large_model_interface():
    """测试大模型接口"""
    try:
        from src.modules.intelligence.large_model_interface import LargeModelInterface
        logger.info("测试大模型接口...")
        config = {
            "default_provider": "openai",
            "default_model": "gpt-4-turbo",
            "api_keys": {
                "openai": "test_key"
            }
        }
        model_interface = LargeModelInterface(config)
        await model_interface.initialize()
        logger.info("大模型接口初始化成功")
        await model_interface.shutdown()
        return True
    except Exception as e:
        logger.error(f"测试大模型接口失败: {e}")
        return False

async def test_real_time_processor():
    """测试实时数据处理器"""
    try:
        from src.modules.core.real_time_processor import RealTimeProcessor, LowLatencyDecisionEngine
        logger.info("测试实时数据处理器...")
        config = {
            "processing_rate": 100,
            "max_latency": 100,
            "max_cache_size": 1000
        }
        processor = RealTimeProcessor(config)
        processor.initialize()
        logger.info("实时数据处理器初始化成功")
        processor.shutdown()
        
        # 测试低延迟决策引擎
        engine = LowLatencyDecisionEngine(config)
        await engine.initialize()
        logger.info("低延迟决策引擎初始化成功")
        await engine.shutdown()
        return True
    except Exception as e:
        logger.error(f"测试实时数据处理器失败: {e}")
        return False

async def test_multi_strategy_framework():
    """测试多策略框架"""
    try:
        from src.modules.strategy.multi_strategy_framework import MultiStrategyFramework
        logger.info("测试多策略框架...")
        config = {
            "strategies": {
                "trend_following": {
                    "enabled": True
                },
                "mean_reversion": {
                    "enabled": True
                },
                "breakout": {
                    "enabled": True
                }
            }
        }
        framework = MultiStrategyFramework(config)
        await framework.initialize()
        logger.info("多策略框架初始化成功")
        await framework.shutdown()
        return True
    except Exception as e:
        logger.error(f"测试多策略框架失败: {e}")
        return False

async def test_advanced_backtester():
    """测试高级回测系统"""
    try:
        from src.modules.backtest.advanced_backtester import AdvancedBacktester, BacktestConfig
        from src.modules.strategy.multi_strategy_framework import StrategyType
        logger.info("测试高级回测系统...")
        config = {
            "risk_manager": {},
            "fund_manager": {}
        }
        backtester = AdvancedBacktester(config)
        await backtester.initialize()
        logger.info("高级回测系统初始化成功")
        await backtester.shutdown()
        return True
    except Exception as e:
        logger.error(f"测试高级回测系统失败: {e}")
        return False

async def main():
    """主测试函数"""
    logger.info("开始测试核心功能模块...")
    
    tests = [
        test_machine_learning,
        test_data_fusion,
        test_risk_manager,
        test_fund_manager,
        test_large_model_interface,
        test_real_time_processor,
        test_multi_strategy_framework,
        test_advanced_backtester
    ]
    
    results = []
    for test in tests:
        result = await test()
        results.append(result)
    
    logger.info("测试完成!")
    logger.info(f"测试结果: {sum(results)}/{len(results)} 成功")
    
    if all(results):
        logger.info("所有测试通过!")
        return 0
    else:
        logger.error("部分测试失败!")
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
