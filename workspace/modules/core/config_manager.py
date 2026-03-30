#!/usr/bin/env python3
"""
配置管理模块
统一管理全系统配置
"""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


@dataclass
class SystemConfig:
    """系统基础配置"""

    name: str = "全智能量化交易系统"
    version: str = "1.0.0"
    mode: str = "production"  # production, backtest, paper_trading
    timezone: str = "UTC"


@dataclass
class TradingConfig:
    """交易配置"""

    base_currency: str = "USDT"
    max_position_percent: float = 30.0
    max_daily_loss_percent: float = 2.0
    stop_loss_percent: float = 5.0
    take_profit_percent: float = 15.0
    max_leverage: float = 3.0


@dataclass
class RiskConfig:
    """风险配置"""

    volatility_threshold: float = 0.05
    correlation_threshold: float = 0.7
    max_drawdown_percent: float = 20.0
    var_confidence: float = 0.95
    stress_test_scenarios: list = None

    def __post_init__(self):
        if self.stress_test_scenarios is None:
            self.stress_test_scenarios = ["black_swan", "flash_crash", "liquidity_crisis"]


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_dir: str = None):
        self.config_dir = config_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "crypto-config"
        )

        # 默认配置
        self.system = SystemConfig()
        self.trading = TradingConfig()
        self.risk = RiskConfig()

        # 加载现有配置
        self.load_configs()

    def load_configs(self):
        """加载所有配置文件"""
        config_files = {
            "system": "system_config.json",
            "trading": "trading_config.json",
            "risk": "risk_config.json",
            "market": "market_config.json",
            "strategies": "strategies_config.json",
        }

        for config_type, filename in config_files.items():
            config_path = os.path.join(self.config_dir, filename)
            if os.path.exists(config_path):
                self._load_single_config(config_type, config_path)

    def _load_single_config(self, config_type: str, filepath: str):
        """加载单个配置文件"""
        try:
            with open(filepath, "r") as f:
                data = json.load(f)

                if config_type == "system":
                    for key, value in data.items():
                        if hasattr(self.system, key):
                            setattr(self.system, key, value)
                elif config_type == "trading":
                    for key, value in data.items():
                        if hasattr(self.trading, key):
                            setattr(self.trading, key, value)
                elif config_type == "risk":
                    for key, value in data.items():
                        if hasattr(self.risk, key):
                            setattr(self.risk, key, value)

        except Exception as e:
            print(f"加载配置文件 {filepath} 失败: {e}")

    def save_config(self, config_type: str, data: Dict[str, Any]):
        """保存配置"""
        config_path = os.path.join(self.config_dir, f"{config_type}_config.json")

        try:
            with open(config_path, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"保存配置文件失败: {e}")
            return False

    def get_config(self, config_type: str) -> Dict[str, Any]:
        """获取配置字典"""
        if config_type == "system":
            return asdict(self.system)
        elif config_type == "trading":
            return asdict(self.trading)
        elif config_type == "risk":
            return asdict(self.risk)
        else:
            return {}

    def update_config(self, config_type: str, updates: Dict[str, Any]):
        """更新配置"""
        if config_type == "system":
            target = self.system
        elif config_type == "trading":
            target = self.trading
        elif config_type == "risk":
            target = self.risk
        else:
            raise ValueError(f"未知的配置类型: {config_type}")

        for key, value in updates.items():
            if hasattr(target, key):
                setattr(target, key, value)

        # 保存到文件
        self.save_config(config_type, asdict(target))

    def validate_config(self) -> tuple[bool, list]:
        """验证配置有效性"""
        errors = []

        # 验证交易配置
        if self.trading.max_position_percent > 100:
            errors.append("最大仓位比例不能超过100%")
        if self.trading.max_daily_loss_percent > 100:
            errors.append("最大日亏损不能超过100%")
        if self.trading.max_leverage > 10:
            errors.append("杠杆倍数过高，请谨慎设置")

        # 验证风险配置
        if self.risk.volatility_threshold <= 0:
            errors.append("波动率阈值必须大于0")
        if not 0 <= self.risk.var_confidence <= 1:
            errors.append("VaR置信度必须在0-1之间")

        return len(errors) == 0, errors

    def create_default_configs(self):
        """创建默认配置文件"""
        os.makedirs(self.config_dir, exist_ok=True)

        configs = {
            "system": self.get_config("system"),
            "trading": self.get_config("trading"),
            "risk": self.get_config("risk"),
        }

        for config_type, config_data in configs.items():
            config_path = os.path.join(self.config_dir, f"{config_type}_config.json")
            if not os.path.exists(config_path):
                self.save_config(config_type, config_data)
                print(f"创建默认配置文件: {config_path}")

    def export_to_env(self):
        """导出配置到环境变量"""
        env_vars = {}

        # 系统配置
        env_vars["TRADING_SYSTEM_NAME"] = self.system.name
        env_vars["TRADING_SYSTEM_MODE"] = self.system.mode

        # 交易配置
        env_vars["BASE_CURRENCY"] = self.trading.base_currency
        env_vars["MAX_POSITION_PERCENT"] = str(self.trading.max_position_percent)
        env_vars["MAX_DAILY_LOSS_PERCENT"] = str(self.trading.max_daily_loss_percent)
        env_vars["STOP_LOSS_PERCENT"] = str(self.trading.stop_loss_percent)
        env_vars["TAKE_PROFIT_PERCENT"] = str(self.trading.take_profit_percent)

        # 风险配置
        env_vars["VOLATILITY_THRESHOLD"] = str(self.risk.volatility_threshold)
        env_vars["MAX_DRAWDOWN_PERCENT"] = str(self.risk.max_drawdown_percent)

        return env_vars


# 单例实例
_config_manager = None


def get_config_manager() -> ConfigManager:
    """获取配置管理器单例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager
