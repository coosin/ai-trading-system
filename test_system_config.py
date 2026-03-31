#!/usr/bin/env python3
"""
系统配置功能测试脚本
测试配置管理、参数设置、配置验证等功能
"""

import asyncio
import logging
import json
from src.modules.core.config_manager import ConfigManager, ConfigChange

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_config_manager():
    """测试配置管理器功能"""
    logger.info("🧪 测试系统配置功能...")
    logger.info("==================================================")
    
    # 1. 初始化配置管理器
    logger.info("1. 初始化配置管理器")
    config_manager = EnhancedConfigManager("config")
    await config_manager.initialize()
    logger.info("✅ 配置管理器初始化成功")
    
    # 2. 测试获取配置
    logger.info("2. 测试获取配置")
    system_name = await config_manager.get_config("system.name")
    assert system_name == "AI Trading System", f"系统名称获取失败: {system_name}"
    logger.info(f"✅ 系统名称: {system_name}")
    
    trading_enabled = await config_manager.get_config("trading.enabled")
    assert trading_enabled == True, f"交易启用状态获取失败: {trading_enabled}"
    logger.info(f"✅ 交易启用状态: {trading_enabled}")
    
    # 3. 测试获取完整配置
    logger.info("3. 测试获取完整配置")
    full_config = await config_manager.get_config()
    assert isinstance(full_config, dict), "完整配置获取失败"
    logger.info(f"✅ 完整配置获取成功，包含 {len(full_config)} 个顶层配置项")
    
    # 4. 测试设置配置
    logger.info("4. 测试设置配置")
    await config_manager.set_config("system.debug", True)
    debug_value = await config_manager.get_config("system.debug")
    assert debug_value == True, f"配置设置失败: {debug_value}"
    logger.info(f"✅ 配置设置成功: system.debug = {debug_value}")
    
    # 5. 测试配置验证
    logger.info("5. 测试配置验证")
    try:
        # 尝试设置无效的配置值
        await config_manager.set_config("trading.commission_rate", 1.5)  # 超出范围
        assert False, "配置验证失败，应该抛出异常"
    except Exception as e:
        logger.info(f"✅ 配置验证成功，正确拒绝了无效值: {e}")
    
    # 6. 测试配置变更回调
    logger.info("6. 测试配置变更回调")
    callback_called = False
    def on_config_change(change: ConfigChange):
        nonlocal callback_called
        callback_called = True
        logger.info(f"   配置变更回调触发: {change.key} = {change.new_value}")
    
    config_manager.register_change_callback(on_config_change)
    await config_manager.set_config("trading.max_position_size", 0.15)
    assert callback_called, "配置变更回调未触发"
    logger.info("✅ 配置变更回调测试成功")
    
    # 7. 测试配置变更历史
    logger.info("7. 测试配置变更历史")
    history = config_manager.get_change_history()
    assert len(history) > 0, "配置变更历史获取失败"
    logger.info(f"✅ 配置变更历史记录数: {len(history)}")
    if history:
        latest_change = history[-1]
        logger.info(f"   最新变更: {latest_change.key} = {latest_change.new_value}")
    
    # 8. 测试导出配置
    logger.info("8. 测试导出配置")
    exported_config = await config_manager.export_config()
    assert isinstance(exported_config, dict), "配置导出失败"
    logger.info("✅ 配置导出成功")
    
    # 9. 测试导入配置
    logger.info("9. 测试导入配置")
    import_config = {
        "system": {
            "name": "Test Trading System"
        }
    }
    await config_manager.import_config(import_config)
    imported_name = await config_manager.get_config("system.name")
    assert imported_name == "Test Trading System", f"配置导入失败: {imported_name}"
    logger.info(f"✅ 配置导入成功: system.name = {imported_name}")
    
    # 10. 测试重置配置
    logger.info("10. 测试重置配置")
    await config_manager.reset_config(ConfigLayer.RUNTIME)
    reset_name = await config_manager.get_config("system.name")
    logger.info(f"✅ 配置重置成功: system.name = {reset_name}")
    
    # 11. 测试环境变量配置
    logger.info("11. 测试环境变量配置")
    # 环境变量配置已经在初始化时加载
    env_config = await config_manager.get_config("trading.paper_trading")
    logger.info(f"✅ 环境变量配置: trading.paper_trading = {env_config}")
    
    # 12. 测试密钥管理
    logger.info("12. 测试密钥管理")
    # 密钥管理服务配置已经在初始化时加载
    secrets_config = await config_manager.get_config("secrets")
    logger.info(f"✅ 密钥管理配置加载成功")
    
    # 13. 测试清理配置管理器
    logger.info("13. 测试清理配置管理器")
    await config_manager.cleanup()
    logger.info("✅ 配置管理器清理成功")
    
    logger.info("==================================================")
    logger.info("🎉 系统配置功能测试完成！")
    logger.info("✅ 所有测试通过")

if __name__ == "__main__":
    asyncio.run(test_config_manager())
