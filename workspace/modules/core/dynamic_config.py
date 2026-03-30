#!/usr/bin/env python3
"""
动态配置管理模块
支持配置热重载，无需重启系统
"""

import asyncio
import json
import os
import time
import threading
import copy
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime
import yaml
import toml
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

@dataclass
class ConfigChangeEvent:
    """配置变更事件"""
    timestamp: datetime
    config_type: str
    changes: Dict[str, Any]
    old_value: Any = None
    new_value: Any = None

class ConfigWatcher:
    """配置文件监控器"""
    
    def __init__(self, config_dir: str):
        self.config_dir = Path(config_dir)
        self.observer = Observer()
        self.event_handler = ConfigFileHandler(self)
        self.callbacks: List[Callable] = []
        
    def start(self):
        """启动文件监控"""
        if not self.config_dir.exists():
            self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.observer.schedule(
            self.event_handler, 
            str(self.config_dir), 
            recursive=True
        )
        self.observer.start()
        
    def stop(self):
        """停止文件监控"""
        self.observer.stop()
        self.observer.join()
        
    def register_callback(self, callback: Callable):
        """注册变更回调"""
        self.callbacks.append(callback)
        
    def notify_change(self, file_path: str):
        """通知配置变更"""
        for callback in self.callbacks:
            try:
                callback(file_path)
            except Exception as e:
                print(f"配置变更回调失败: {e}")

class ConfigFileHandler(FileSystemEventHandler):
    """配置文件事件处理器"""
    
    def __init__(self, watcher: ConfigWatcher):
        self.watcher = watcher
        
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory and event.src_path.endswith(('.json', '.yaml', '.yml', '.toml')):
            print(f"配置文件变更: {event.src_path}")
            self.watcher.notify_change(event.src_path)
            
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory and event.src_path.endswith(('.json', '.yaml', '.yml', '.toml')):
            print(f"配置文件创建: {event.src_path}")
            self.watcher.notify_change(event.src_path)

class DynamicConfigManager:
    """动态配置管理器"""
    
    def __init__(self, base_config_path: str = None):
        # 配置存储
        self._config_store: Dict[str, Any] = {}
        self._default_config: Dict[str, Any] = {}
        self._config_history: List[ConfigChangeEvent] = []
        
        # 配置路径
        if base_config_path:
            self.base_config_path = Path(base_config_path)
        else:
            self.base_config_path = Path.home() / '.openclaw-trading' / 'config'
        
        # 配置文件路径
        self.config_files = {
            'system': self.base_config_path / 'system.json',
            'trading': self.base_config_path / 'trading.json',
            'risk': self.base_config_path / 'risk.json',
            'data_sources': self.base_config_path / 'data_sources.json',
            'ai_models': self.base_config_path / 'ai_models.json'
        }
        
        # 配置变更回调
        self.change_callbacks: Dict[str, List[Callable]] = {}
        
        # 配置监控器
        self.watcher = ConfigWatcher(str(self.base_config_path))
        self.watcher.register_callback(self._on_config_file_changed)
        
        # 加载初始配置
        self._load_all_configs()
        
    def start(self):
        """启动配置管理器"""
        # 确保配置目录存在
        self.base_config_path.mkdir(parents=True, exist_ok=True)
        
        # 创建默认配置文件（如果不存在）
        self._create_default_configs()
        
        # 启动文件监控
        self.watcher.start()
        
        # 启动配置同步任务
        asyncio.create_task(self._config_sync_task())
        
        print(f"✅ 动态配置管理器已启动，监控目录: {self.base_config_path}")
        
    async def stop(self):
        """停止配置管理器"""
        self.watcher.stop()
        
    async def _config_sync_task(self):
        """配置同步任务"""
        while True:
            try:
                # 定期检查配置一致性
                await self._check_config_consistency()
                await asyncio.sleep(60)  # 每分钟检查一次
            except Exception as e:
                print(f"配置同步任务出错: {e}")
                await asyncio.sleep(30)
    
    def _load_all_configs(self):
        """加载所有配置文件"""
        for config_type, config_file in self.config_files.items():
            try:
                if config_file.exists():
                    self._load_config(config_type, config_file)
                else:
                    # 使用默认配置
                    self._config_store[config_type] = self._get_default_config(config_type)
            except Exception as e:
                print(f"加载配置文件 {config_type} 失败: {e}")
                self._config_store[config_type] = self._get_default_config(config_type)
    
    def _load_config(self, config_type: str, config_file: Path):
        """加载单个配置文件"""
        
        if not config_file.exists():
            return
        
        try:
            # 根据文件类型使用不同的加载器
            if config_file.suffix == '.json':
                with open(config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
            elif config_file.suffix in ['.yaml', '.yml']:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config_data = yaml.safe_load(f)
            elif config_file.suffix == '.toml':
                with open(config_file, 'r', encoding='utf-8') as f:
                    config_data = toml.load(f)
            else:
                print(f"不支持的配置文件格式: {config_file.suffix}")
                return
            
            # 保存旧配置用于比较
            old_config = self._config_store.get(config_type, {})
            
            # 更新配置
            self._config_store[config_type] = config_data
            
            # 记录配置变更
            self._record_config_change(config_type, old_config, config_data)
            
            print(f"✅ 加载配置文件: {config_file}")
            
        except Exception as e:
            print(f"加载配置文件 {config_file} 失败: {e}")
    
    def _create_default_configs(self):
        """创建默认配置文件"""
        
        for config_type, config_file in self.config_files.items():
            if not config_file.exists():
                default_config = self._get_default_config(config_type)
                self._save_config(config_type, default_config)
                print(f"📝 创建默认配置文件: {config_file}")
    
    def _get_default_config(self, config_type: str) -> Dict[str, Any]:
        """获取默认配置"""
        
        default_configs = {
            'system': {
                'name': '全智能量化交易系统',
                'version': '1.0.0',
                'mode': 'paper_trading',  # paper_trading, live_trading, backtesting
                'log_level': 'INFO',      # DEBUG, INFO, WARNING, ERROR
                'max_memory_mb': 2048,
                'max_cpu_percent': 80,
                'auto_restart': True,
                'restart_on_error': True,
                'health_check_interval': 60,  # 秒
                'performance_monitoring': True
            },
            'trading': {
                'enabled': True,
                'symbols': ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'],
                'max_positions': 5,
                'max_position_size_percent': 20.0,
                'max_daily_loss_percent': 5.0,
                'max_total_loss_percent': 20.0,
                'take_profit_percent': 10.0,
                'stop_loss_percent': 5.0,
                'trailing_stop_percent': 3.0,
                'slippage_tolerance_percent': 1.0,
                'min_trade_amount': 10.0,  # USDT
                'commission_rate': 0.001,  # 0.1%
                'tax_rate': 0.0,
                'trading_hours': {
                    'start': '00:00',
                    'end': '23:59',
                    'timezone': 'UTC'
                },
                'order_types': ['LIMIT', 'MARKET'],
                'time_in_force': ['GTC', 'IOC']
            },
            'risk': {
                'max_leverage': 3.0,
                'max_correlation': 0.7,
                'var_confidence': 0.95,
                'var_period_days': 30,
                'stress_test_scenarios': ['crash_30', 'flash_crash', 'slow_drain'],
                'risk_limits': {
                    'daily': 2.0,
                    'weekly': 5.0,
                    'monthly': 10.0
                },
                'liquidity_requirements': {
                    'min_volume_usd': 1000000,
                    'min_market_cap_usd': 10000000
                },
                'blacklist': [],  # 禁止交易的币种
                'whitelist': []   # 允许交易的币种（如果设置则只允许这些）
            },
            'data_sources': {
                'market_data': {
                    'binance': {
                        'enabled': True,
                        'api_key': '',
                        'api_secret': '',
                        'testnet': True,
                        'rate_limit_requests': 1200,
                        'rate_limit_period': 60
                    },
                    'coinbase': {
                        'enabled': False,
                        'api_key': '',
                        'api_secret': ''
                    }
                },
                'onchain_data': {
                    'glassnode': {
                        'enabled': True,
                        'api_key': ''
                    },
                    'cryptoquant': {
                        'enabled': True,
                        'api_key': ''
                    }
                },
                'sentiment_data': {
                    'twitter': {
                        'enabled': True,
                        'bearer_token': ''
                    },
                    'reddit': {
                        'enabled': True,
                        'client_id': '',
                        'client_secret': ''
                    }
                },
                'cache_settings': {
                    'enabled': True,
                    'ttl_seconds': 300,
                    'max_size_mb': 100,
                    'redis_enabled': False,
                    'redis_host': 'localhost',
                    'redis_port': 6379
                }
            },
            'ai_models': {
                'technical_analysis': {
                    'enabled': True,
                    'indicators': ['RSI', 'MACD', 'BB', 'ATR', 'OBV'],
                    'timeframes': ['1h', '4h', '1d'],
                    'lookback_periods': [14, 20, 50, 200]
                },
                'onchain_analysis': {
                    'enabled': True,
                    'metrics': ['exchange_flow', 'active_addresses', 'mvrv', 'sopr'],
                    'update_interval_minutes': 60
                },
                'sentiment_analysis': {
                    'enabled': True,
                    'sources': ['twitter', 'reddit'],
                    'update_interval_minutes': 30,
                    'sentiment_threshold': 0.6
                },
                'ml_models': {
                    'lstm_enabled': True,
                    'transformer_enabled': False,
                    'training_interval_hours': 24,
                    'prediction_horizon_hours': 24
                },
                'fusion_weights': {
                    'technical': 0.35,
                    'onchain': 0.35,
                    'sentiment': 0.20,
                    'market_structure': 0.10
                }
            }
        }
        
        return default_configs.get(config_type, {})
    
    def _save_config(self, config_type: str, config_data: Dict[str, Any]):
        """保存配置到文件"""
        
        config_file = self.config_files.get(config_type)
        if not config_file:
            print(f"未知的配置类型: {config_type}")
            return
        
        try:
            # 确保目录存在
            config_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 根据文件类型保存
            if config_file.suffix == '.json':
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, indent=2, ensure_ascii=False)
            elif config_file.suffix in ['.yaml', '.yml']:
                with open(config_file, 'w', encoding='utf-8') as f:
                    yaml.dump(config_data, f, allow_unicode=True)
            elif config_file.suffix == '.toml':
                with open(config_file, 'w', encoding='utf-8') as f:
                    toml.dump(config_data, f)
            
            print(f"✅ 保存配置文件: {config_file}")
            
        except Exception as e:
            print(f"保存配置文件 {config_file} 失败: {e}")
    
    def _on_config_file_changed(self, file_path: str):
        """配置文件变更处理"""
        
        try:
            # 找出是哪个配置类型的文件
            config_type = None
            for ct, cf in self.config_files.items():
                if str(cf) == file_path:
                    config_type = ct
                    break
            
            if config_type:
                # 重新加载配置
                old_config = self._config_store.get(config_type, {})
                self._load_config(config_type, Path(file_path))
                
                # 触发变更回调
                self._trigger_change_callbacks(config_type, old_config, self._config_store[config_type])
                
        except Exception as e:
            print(f"配置文件变更处理失败: {e}")
    
    def _record_config_change(self, config_type: str, old_config: Dict, new_config: Dict):
        """记录配置变更"""
        
        # 找出变更的字段
        changes = self._find_config_changes(old_config, new_config)
        
        if changes:
            event = ConfigChangeEvent(
                timestamp=datetime.now(),
                config_type=config_type,
                changes=changes,
                old_value=old_config,
                new_value=new_config
            )
            
            self._config_history.append(event)
            
            # 保持历史记录长度
            if len(self._config_history) > 1000:
                self._config_history = self._config_history[-1000:]
            
            # 记录日志
            print(f"📝 配置变更: {config_type}, 变更字段: {list(changes.keys())}")
    
    def _find_config_changes(self, old_config: Dict, new_config: Dict) -> Dict[str, Any]:
        """找出配置变更"""
        
        changes = {}
        
        # 比较所有键
        all_keys = set(old_config.keys()) | set(new_config.keys())
        
        for key in all_keys:
            old_value = old_config.get(key)
            new_value = new_config.get(key)
            
            if old_value != new_value:
                changes[key] = {
                    'old': old_value,
                    'new': new_value
                }
        
        return changes
    
    def _trigger_change_callbacks(self, config_type: str, old_config: Dict, new_config: Dict):
        """触发变更回调"""
        
        if config_type in self.change_callbacks:
            for callback in self.change_callbacks[config_type]:
                try:
                    callback(config_type, old_config, new_config)
                except Exception as e:
                    print(f"配置变更回调执行失败: {e}")
    
    async def _check_config_consistency(self):
        """检查配置一致性"""
        
        for config_type, config_file in self.config_files.items():
            try:
                if config_file.exists():
                    # 重新加载文件检查一致性
                    with open(config_file, 'r', encoding='utf-8') as f:
                        if config_file.suffix == '.json':
                            file_content = json.load(f)
                        elif config_file.suffix in ['.yaml', '.yml']:
                            file_content = yaml.safe_load(f)
                        elif config_file.suffix == '.toml':
                            file_content = toml.load(f)
                        else:
                            continue
                    
                    # 检查内存中的配置与文件是否一致
                    memory_config = self._config_store.get(config_type, {})
                    
                    if memory_config != file_content:
                        print(f"⚠️ 配置不一致: {config_type}，重新加载...")
                        self._load_config(config_type, config_file)
                        
            except Exception as e:
                print(f"检查配置一致性失败 ({config_type}): {e}")
    
    # 公共接口
    
    def get_config(self, config_type: str, key: str = None, default: Any = None) -> Any:
        """获取配置值"""
        
        config = self._config_store.get(config_type, {})
        
        if key is None:
            return config
        
        # 支持点分隔的嵌套键
        keys = key.split('.')
        value = config
        
        try:
            for k in keys:
                if isinstance(value, dict):
                    value = value.get(k)
                else:
                    return default
        except (KeyError, AttributeError):
            return default
        
        return value if value is not None else default
    
    def set_config(self, config_type: str, key: str, value: Any):
        """设置配置值"""
        
        if config_type not in self._config_store:
            self._config_store[config_type] = {}
        
        # 获取旧值
        old_value = self.get_config(config_type, key)
        
        # 设置新值
        config = self._config_store[config_type]
        keys = key.split('.')
        
        # 遍历嵌套字典
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        # 设置最终值
        config[keys[-1]] = value
        
        # 保存到文件
        self._save_config(config_type, self._config_store[config_type])
        
        # 触发变更回调
        if old_value != value:
            self._trigger_change_callbacks(
                config_type, 
                {key: old_value}, 
                {key: value}
            )
    
    def update_config(self, config_type: str, updates: Dict[str, Any]):
        """批量更新配置"""
        
        for key, value in updates.items():
            self.set_config(config_type, key, value)
    
    def register_change_callback(self, config_type: str, callback: Callable):
        """注册配置变更回调"""
        
        if config_type not in self.change_callbacks:
            self.change_callbacks[config_type] = []
        
        self.change_callbacks[config_type].append(callback)
    
    def get_config_history(self, config_type: str = None, limit: int = 50) -> List[ConfigChangeEvent]:
        """获取配置变更历史"""
        
        if config_type:
            filtered = [event for event in self._config_history 
                       if event.config_type == config_type]
        else:
            filtered = self._config_history
        
        return filtered[-limit:]
    
    def export_config(self, config_type: str = None, format: str = 'json') -> str:
        """导出配置"""
        
        if config_type:
            config_data = self._config_store.get(config_type, {})
        else:
            config_data = self._config_store
        
        if format == 'json':
            return json.dumps(config_data, indent=2, ensure_ascii=False)
        elif format == 'yaml':
            return yaml.dump(config_data, allow_unicode=True)
        elif format == 'toml':
            return toml.dumps(config_data)
        else:
            raise ValueError(f"不支持的格式: {format}")
    
    def validate_config(self, config_type: str) -> List[str]:
        """验证配置"""
        
        config = self._config_store.get(config_type, {})
        errors = []
        
        # 基础验证规则
        validation_rules = {
            'system': self._validate_system_config,
            'trading': self._validate_trading_config,
            'risk': self._validate_risk_config,
            'data_sources': self._validate_data_sources_config,
            'ai_models': self._validate_ai_models_config
        }
        
        if config_type in validation_rules:
            errors = validation_rules[config_type](config)
        
        return errors
    
    def _validate_system_config(self, config: Dict) -> List[str]:
        """验证系统配置"""
        
        errors = []
        
        if 'mode' not in config:
            errors.append("缺少 mode 配置")
        elif config['mode'] not in ['paper_trading', 'live_trading', 'backtesting']:
            errors.append(f"无效的 mode: {config['mode']}")
        
        if 'log_level' in config and config['log_level'] not in ['DEBUG', 'INFO', 'WARNING', 'ERROR']:
            errors.append(f"无效的 log_level: {config['log_level']}")
        
        return errors
    
    def _validate_trading_config(self, config: Dict) -> List[str]:
        """验证交易配置"""
        
        errors = []
        
        if 'max_position_size_percent' in config:
            if config['max_position_size_percent'] <= 0 or config['max_position_size_percent'] > 100:
                errors.append(f"无效的 max_position_size_percent: {config['max_position_size_percent']}")
        
        if 'max_daily_loss_percent' in config:
            if config['max_daily_loss_percent'] <= 0 or config['max_daily_loss_percent'] > 100:
                errors.append(f"无效的 max_daily_loss_percent: {config['max_daily_loss_percent']}")
        
        return errors
    
    def _validate_risk_config(self, config: Dict) -> List[str]:
        """验证风险配置"""
        
        errors = []
        
        if 'max_leverage' in config and config['max_leverage'] < 1:
            errors.append(f"无效的 max_leverage: {config['max_leverage']}")
        
        return errors
    
    def _validate_data_sources_config(self, config: Dict) -> List[str]:
        """验证数据源配置"""
        
        errors = []
        
        # 这里可以添加具体的数据源验证逻辑
        return errors
    
    def _validate_ai_models_config(self, config: Dict) -> List[str]:
        """验证AI模型配置"""
        
        errors = []
        
        if 'fusion_weights' in config:
            weights = config['fusion_weights']
            total_weight = sum(weights.values()) if isinstance(weights, dict) else 0
            
            if abs(total_weight - 1.0) > 0.01:
                errors.append(f"融合权重总和不为1: {total_weight}")
        
        return errors

# 单例实例
_config_manager = None

def get_dynamic_config_manager(base_config_path: str = None) -> DynamicConfigManager:
    """获取动态配置管理器单例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = DynamicConfigManager(base_config_path)
    return _config_manager

async def test_dynamic_config():
    """测试动态配置"""
    
    config_manager = get_dynamic_config_manager()
    config_manager.start()
    
    try:
        # 获取配置
        system_mode = config_manager.get_config('system', 'mode')
        print(f"当前系统模式: {system_mode}")
        
        # 修改配置
        config_manager.set_config('system', 'log_level', 'DEBUG')
        
        # 注册变更回调
        def on_system_change(config_type, old_config, new_config):
            print(f"系统配置变更: {config_type}")
            if 'log_level' in new_config:
                print(f"日志级别从 {old_config.get('log_level')} 变为 {new_config.get('log_level')}")
        
        config_manager.register_change_callback('system', on_system_change)
        
        # 保持运行
        await asyncio.sleep(3600)
        
    finally:
        await config_manager.stop()

if __name__ == "__main__":
    asyncio.run(test_dynamic_config())