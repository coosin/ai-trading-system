"""
配置管理器模块

负责统一配置加载、管理、验证和热重载。
支持多格式配置（JSON/YAML/Env）、配置验证和默认值设置。
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# 容错导入
try:
    import yaml
except ImportError:
    yaml = None
    logging.warning("yaml模块未安装，跳过YAML配置文件")

try:
    from pydantic import BaseModel, ValidationError
except ImportError:
    BaseModel = None
    ValidationError = None
    logging.warning("pydantic模块未安装，使用简化的配置验证")

logger = logging.getLogger(__name__)

_TRADING_PREFIX_DEPRECATION_LOGGED = False


class ConfigValidationError(Exception):
    """配置验证错误"""

    pass


class ConfigNotFoundError(Exception):
    """配置未找到错误"""

    pass


@dataclass
class ConfigChange:
    """配置变更记录"""

    section: str
    key: str
    old_value: Any
    new_value: Any
    timestamp: float


class ConfigSchema:
    """配置模式基类"""

    pass

if BaseModel:
    class ConfigSchema(BaseModel):
        """配置模式基类"""

        pass


class ConfigManager:
    """
    配置管理器

    特性：
    1. 统一配置加载和管理
    2. 多格式配置支持 (JSON/YAML/Env)
    3. 配置验证和默认值设置
    4. 配置热重载支持
    5. 配置变更通知机制
    6. 多路径配置查找（支持data/config和config目录）
    """

    DEFAULT_CONFIG_PATHS = [
        "data/config",
        "config",
        "/app/data/config",
        "/app/config"
    ]

    # Minimal built-in defaults to reduce config scattering. File configs and env
    # overrides will take precedence.
    DEFAULT_CONFIG: Dict[str, Dict[str, Any]] = {
        "system": {
            "environment": "development",
            "debug": False,
        },
        "controller": {
            "auto_restart_modules": True,
            "max_restart_attempts": 3,
            "health_check_interval": 30,
            "event_history_limit": 1000,
        },
        "ai_brain": {
            # single brain arbitration: ai_core | ai_trading_engine
            "primary_controller": "ai_core",
            # keep secondary loop disabled by default to avoid dual-dispatch
            "enable_secondary_controller": False,
            # enable autonomous executor supervision loop by default
            "enable_autonomous_executor": True,
        },
        "api": {
            "host": "0.0.0.0",
            "port": 8000,
            "enable_cors": True,
            "enable_swagger": True,
        },
        "paths": {
            "base_path": "/app",
            "data_path": "/app/data",
            "log_path": "/app/logs",
            "workspace_path": "/app/workspace",
            "trade_history_path": "data/trade_history",
            "templates_dir": "/app/templates",
            "models_path": "/app/data/models",
            "memory_path": "/app/workspace/memory",
            "trading_path": "/app",
        },
        "timing": {
            "config_watch_interval": 30,
        },
        "active_trader": {
            "min_trade_interval": 300,
            "contract_config": {
                "leverage_min": 10,
                "leverage_max": 50,
                "default_leverage": 20,
                "max_positions": 5,
                "min_positions": 3,
                "margin_mode": "cross",
            },
        },
        "proactive_scanner": {
            "scan_interval": 30,
            "deep_scan_interval": 300,
            "default_symbols": [
                "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",
                "XRP/USDT", "DOGE/USDT", "ADA/USDT", "AVAX/USDT",
                "DOT/USDT", "MATIC/USDT", "LINK/USDT", "ATOM/USDT",
            ],
        },
        "system_maintenance": {
            "health_thresholds": {
                "cpu_warning": 70,
                "cpu_critical": 90,
                "memory_warning": 75,
                "memory_critical": 90,
                "disk_warning": 80,
                "disk_critical": 95,
                "error_rate_warning": 0.05,
                "error_rate_critical": 0.15,
            },
        },
        "ai_trading": {
            "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"],
            "contract_config": {
                "enabled": True,
                "trade_type": "swap",
                "leverage_min": 10,
                "leverage_max": 50,
                "default_leverage": 20,
                "max_positions": 5,
                "min_positions": 1,
                "margin_mode": "cross",
                "grid_trading": False,
                "grid_levels": 5,
                "grid_spacing": 0.02,
            },
            "ai_config": {
                "enabled": True,
                "model_id": "astron-code-latest",
                "analysis_interval": 120,
                "min_confidence": 0.75,
                "max_positions": 5,
                "risk_per_trade": 0.01,
                "trade_mode": "real",
                "auto_risk_management": True,
                "critical_risk_auto_close": True,
                "max_loss_per_position": 0.05,
                "daily_loss_limit": 0.10,
                "max_drawdown_limit": 0.15,
            },
        },
        "proactive_ai": {
            "scan_interval": 30,
            "deep_scan_interval": 300,
            "collect_interval": 300,
            "action_cooldown": 60,
        },
        "system_monitor": {},
        "intelligent_monitoring": {},
        "enhanced_monitoring": {},
        "unified_data_manager": {},
        "unified_strategy_system": {},
        "unified_trade_system": {},
        "unified_risk_system": {},
        "memory": {
            "provider": "native",
            "default_scope": "global",
            "scopes": {
                "enabled": True,
            },
            "dual_layer": {
                "structured_enabled": True,
                "workspace_markdown_enabled": True,
            },
            "retrieval": {
                "mode": "hybrid",
                "vector_weight": 0.7,
                "bm25_weight": 0.3,
                "min_score": 0.3,
                "max_results": 10,
                "rerank": {
                    "enabled": False,
                    "candidate_pool_size": 12,
                    "min_score": 0.0,
                },
            },
            "auto_capture": {
                "enabled": True,
                "policy": {
                    # If a memory is tagged as noise, skip it.
                    "deny_tags": ["noise", "low_value"],
                    # Skip known low-value categories.
                    "deny_categories": ["notification_hint", "market_opportunity_hint"],
                    # Simple content deny patterns (case-insensitive contains)
                    "deny_content_contains": [
                        "当前持仓较少",
                        "市场机会",
                    ],
                    # Only store conversation automatically above this importance
                    "min_importance_by_category": {
                        "conversation": 0.2,
                        "config": 0.5,
                        "strategy": 0.6,
                        "risk_setting": 0.6,
                    },
                },
            },
            "auto_recall": {
                "enabled": True,
            },
        },
        "notifications": {
            "enabled": True,
            "smart": {
                "quiet_hours_start": "23:00",
                "quiet_hours_end": "07:00",
                "batch_interval_sec": 3600,
                "rate_limits_per_hour": {
                    "low": 10,
                    "medium": 20,
                    "high": 50,
                    "critical": 100,
                },
                "dedup_windows_sec": {
                    "critical": 60,
                    "high": 600,
                    "medium": 3600,
                    "low": 21600,
                },
                "dedup_max_keys": 2000,
            },
            "telegram": {
                # repeated send failures (chat_id/proxy) log suppression window
                "failure_dedup_window_sec": 1800,
            },
        },
        "heartbeat": {
            "enabled": True,
            "interval_sec": 1800,
            "market_opportunity_notice_cooldown_sec": 21600,
        },
        "research": {
            "enabled": True,
            "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"],
            "timeframe": "1h",
            "lookback_days": 30,
            "gates": {
                "min_sharpe": 0.8,
                "max_drawdown": 0.25,
                "min_trades": 8,
            },
            "cost_model": {
                # applied in walk-forward scoring
                "fee_rate": 0.0005,
                "slippage_rate": 0.0003,
            },
            "walk_forward": {
                "enabled": True,
                "folds": 3,
                "train_ratio": 0.7,
            },
        },
    }

    def __init__(self, config_dir: str = None, watch_interval: int = 30):
        """
        初始化配置管理器

        Args:
            config_dir: 配置文件目录（如果为None，自动查找）
            watch_interval: 配置监控间隔（秒）
        """
        self.watch_interval = watch_interval
        self._config: Dict[str, Dict[str, Any]] = {}
        self._schemas: Dict[str, ConfigSchema] = {}
        self._watchers: Dict[str, List[Callable]] = {}
        self._file_timestamps: Dict[str, float] = {}
        self._change_history: List[ConfigChange] = []
        self._lock = asyncio.Lock()
        self._watch_task: Optional[asyncio.Task] = None
        self._initialized = False
        self._config_dirs: List[Path] = []

        if config_dir:
            self.config_dir = Path(config_dir)
            self._config_dirs = [self.config_dir]
        else:
            self.config_dir = self._find_config_dir()
            self._config_dirs = self._find_all_config_dirs()

        for d in self._config_dirs:
            d.mkdir(parents=True, exist_ok=True)

    def _deep_update(self, base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively merge dictionaries (updates win)."""
        for k, v in (updates or {}).items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                base[k] = self._deep_update(base[k], v)
            else:
                base[k] = v
        return base

    def _find_config_dir(self) -> Path:
        """查找第一个存在的配置目录"""
        for path in self.DEFAULT_CONFIG_PATHS:
            p = Path(path)
            if p.exists():
                logger.info(f"使用配置目录: {p}")
                return p
        default = Path("data/config")
        default.mkdir(parents=True, exist_ok=True)
        logger.info(f"使用默认配置目录: {default}")
        return default

    def _find_all_config_dirs(self) -> List[Path]:
        """查找所有存在的配置目录"""
        dirs = []
        for path in self.DEFAULT_CONFIG_PATHS:
            p = Path(path)
            if p.exists():
                dirs.append(p)
        if not dirs:
            default = Path("data/config")
            default.mkdir(parents=True, exist_ok=True)
            dirs.append(default)
        logger.info(f"配置搜索路径: {[str(d) for d in dirs]}")
        return dirs

    async def initialize(self) -> None:
        """
        初始化配置管理器

        加载所有配置文件并启动监控任务
        """
        if self._initialized:
            return

        logger.info("初始化配置管理器...")

        # 加载配置文件
        await self._load_all_configs()

        # 启动配置监控
        if self.watch_interval > 0:
            self._watch_task = asyncio.create_task(self._watch_config_files())

        self._initialized = True
        logger.info("配置管理器初始化完成")

    async def cleanup(self) -> None:
        """
        清理配置管理器

        停止监控任务
        """
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
            finally:
                self._watch_task = None

        self._initialized = False
        logger.info("配置管理器已清理")

    async def get_config(self, section: str, key: Any = None, default: Any = None) -> Any:
        """
        获取配置值

        Args:
            section: 配置段名
            key: 配置键名（可选）
            default: 默认值（如果配置不存在）

        Returns:
            配置值
        """
        async with self._lock:
            # 如果只传递了两个参数，第二个参数作为default
            if key is not None and not isinstance(key, str):
                default = key
                key = None
            
            if key:
                section_config = self._config.get(section, {})
                value = section_config.get(key)

                if value is None and default is not None:
                    return default

                return value
            else:
                # 如果没有指定key，返回整个section
                return self._config.get(section, default)

    def get_config_sync(self, section: str, key: Optional[str] = None, default: Any = None) -> Any:
        """
        同步读取配置快照（只读）。

        适用于 sync 方法/构造函数等无法 await 的场景。该方法不加锁，
        返回的是当前内存配置快照；热重载时可能短暂读到旧值，但不会抛错。
        """
        try:
            if key:
                section_config = self._config.get(section, {})
                if isinstance(section_config, dict):
                    value = section_config.get(key)
                    return default if value is None else value
                return default
            return self._config.get(section, default)
        except Exception:
            return default

    def get_path_sync(self, key: str, default: Optional[str] = None) -> str:
        """同步读取 `paths.<key>`，用于统一路径配置入口。"""
        value = self.get_config_sync("paths", key, default)
        return value if isinstance(value, str) and value else (default or "")

    async def set_config(self, section: str, key: str, value: Any, validate: bool = True) -> bool:
        """
        设置配置值

        Args:
            section: 配置段名
            key: 配置键名
            value: 配置值
            validate: 是否验证配置

        Returns:
            是否设置成功
        """
        async with self._lock:
            # 获取旧值
            old_value = None
            if section in self._config and key in self._config[section]:
                old_value = self._config[section][key]

            # 验证配置（如果启用了验证）
            if validate:
                if BaseModel and section in self._schemas:
                    try:
                        schema = self._schemas[section]
                        # 使用“现有 section 配置 + 本次更新”进行验证
                        section_config = self._config.get(section, {})
                        temp_config = dict(section_config) if isinstance(section_config, dict) else {}
                        temp_config[key] = value
                        schema(**temp_config)
                    except ValidationError as e:
                        logger.error(f"配置验证失败: {e}")
                        return False
                else:
                    # 简化验证（不依赖pydantic）
                    if not self._validate_value(value):
                        logger.error(f"配置验证失败: 值类型无效")
                        return False

            # 更新配置
            if section not in self._config:
                self._config[section] = {}

            self._config[section][key] = value

            # 记录变更
            change = ConfigChange(
                section=section,
                key=key,
                old_value=old_value,
                new_value=value,
                timestamp=asyncio.get_event_loop().time(),
            )
            self._change_history.append(change)

            # 保存到文件
            await self._save_section_to_file(section)

            # 通知观察者
            await self._notify_watchers(section, key, old_value, value)

            logger.info(f"配置已更新: {section}.{key} = {value}")
            return True

    async def set_config_path(self, path: str, value: Any, validate: bool = True) -> bool:
        """
        Set nested config with dotted path, e.g. "notifications.smart.dedup_windows_sec.high".
        This updates the corresponding top-level section dict and persists it.
        """
        parts = [p for p in (path or "").split(".") if p]
        if len(parts) < 2:
            return False
        section = parts[0]
        nested = parts[1:]
        async with self._lock:
            section_cfg = self._config.get(section)
            if not isinstance(section_cfg, dict):
                section_cfg = {}
                self._config[section] = section_cfg

            old_value = None
            cur = section_cfg
            for k in nested[:-1]:
                if k not in cur or not isinstance(cur.get(k), dict):
                    cur[k] = {}
                cur = cur[k]
            leaf = nested[-1]
            if isinstance(cur, dict) and leaf in cur:
                old_value = cur.get(leaf)
            cur[leaf] = value

            # record as ConfigChange using the full nested key
            change = ConfigChange(
                section=section,
                key=".".join(nested),
                old_value=old_value,
                new_value=value,
                timestamp=asyncio.get_event_loop().time(),
            )
            self._change_history.append(change)
            await self._save_section_to_file(section)
            await self._notify_watchers(section, ".".join(nested), old_value, value)
            logger.info(f"配置已更新: {section}.{'.'.join(nested)} = {value}")
            return True

    def get_config_path_sync(self, path: str, default: Any = None) -> Any:
        parts = [p for p in (path or "").split(".") if p]
        if not parts:
            return default
        section = parts[0]
        keys = parts[1:]
        cur: Any = self.get_config_sync(section, None, default if not keys else {})
        for k in keys:
            if not isinstance(cur, dict):
                return default
            cur = cur.get(k)
            if cur is None:
                return default
        return cur

    def _validate_value(self, value: Any) -> bool:
        """简化验证"""
        # 允许所有基本类型
        return True

    async def watch_config(self, section: str, key: str, callback: Callable) -> None:
        """
        监听配置变更

        Args:
            section: 配置段名
            key: 配置键名
            callback: 回调函数，接收(section, key, old_value, new_value)
        """
        watch_key = f"{section}.{key}"
        if watch_key not in self._watchers:
            self._watchers[watch_key] = []

        self._watchers[watch_key].append(callback)
        logger.debug(f"已注册配置监听器: {watch_key}")

    async def unwatch_config(self, section: str, key: str, callback: Callable) -> None:
        """
        取消监听配置变更

        Args:
            section: 配置段名
            key: 配置键名
            callback: 要移除的回调函数
        """
        watch_key = f"{section}.{key}"
        if watch_key in self._watchers and callback in self._watchers[watch_key]:
            self._watchers[watch_key].remove(callback)
            logger.debug(f"已移除配置监听器: {watch_key}")

    async def reload(self) -> None:
        """
        重新加载所有配置文件
        """
        async with self._lock:
            logger.info("重新加载配置文件...")
            await self._load_all_configs()
            logger.info("配置文件重载完成")

    def register_schema(self, section: str, schema: ConfigSchema) -> None:
        """
        注册配置模式

        Args:
            section: 配置段名
            schema: 配置模式类
        """
        self._schemas[section] = schema
        logger.debug(f"已注册配置模式: {section}")

    async def get_all_configs(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有配置

        Returns:
            所有配置的字典
        """
        async with self._lock:
            return self._config.copy()

    async def get_change_history(self, limit: int = 100) -> List[ConfigChange]:
        """
        获取配置变更历史

        Args:
            limit: 返回的最大记录数

        Returns:
            配置变更历史列表
        """
        async with self._lock:
            return self._change_history[-limit:]

    @asynccontextmanager
    async def transaction(self):
        """
        配置事务上下文管理器

        用法：
        async with config_manager.transaction() as transaction:
            await transaction.set_config('section', 'key1', 'value1')
            await transaction.set_config('section', 'key2', 'value2')
            # 所有变更在退出上下文时一起应用
        """
        transaction = ConfigTransaction(self)
        try:
            yield transaction
            await transaction.commit()
        except Exception as e:
            await transaction.rollback()
            raise e

    # 私有方法

    async def _load_all_configs(self) -> None:
        """加载所有配置文件（从多个配置目录）"""
        # Start from built-in defaults every time (reload-safe)
        self._config = {}
        self._deep_update(self._config, self.DEFAULT_CONFIG)

        loaded_files = set()
        
        for config_dir in self._config_dirs:
            # Deterministic priority: default.* first, then other files sorted.
            config_files: List[Path] = []
            default_candidates: List[Path] = []
            other_candidates: List[Path] = []

            default_candidates.extend(sorted(config_dir.glob("default.json")))
            if yaml:
                default_candidates.extend(sorted(config_dir.glob("default.yaml")))
                default_candidates.extend(sorted(config_dir.glob("default.yml")))

            other_candidates.extend(sorted(config_dir.glob("*.json")))
            if yaml:
                other_candidates.extend(sorted(config_dir.glob("*.yaml")))
                other_candidates.extend(sorted(config_dir.glob("*.yml")))

            # Remove defaults from other_candidates to avoid double load
            default_set = {p.resolve() for p in default_candidates}
            other_candidates = [p for p in other_candidates if p.resolve() not in default_set]

            config_files.extend(default_candidates)
            config_files.extend(other_candidates)
            
            for config_file in config_files:
                file_key = f"{config_dir.name}/{config_file.name}"
                if file_key not in loaded_files:
                    await self._load_config_file(config_file)
                    loaded_files.add(file_key)
        
        await self._load_environment_configs()
        logger.info(f"已加载 {len(loaded_files)} 个配置文件")

    async def _load_config_file(self, config_file: Path) -> None:
        """加载配置文件"""
        try:
            # 记录文件时间戳
            self._file_timestamps[str(config_file)] = config_file.stat().st_mtime

            # 根据文件扩展名解析
            if config_file.suffix == ".json":
                with open(config_file, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
            elif config_file.suffix in [".yaml", ".yml"]:
                if yaml:
                    with open(config_file, "r", encoding="utf-8") as f:
                        config_data = yaml.safe_load(f)
                else:
                    logger.warning(f"无法加载YAML文件，缺少yaml模块: {config_file}")
                    return
            else:
                logger.warning(f"不支持的配置文件格式: {config_file}")
                return

            # 合并配置
            for section, values in config_data.items():
                if not isinstance(values, dict):
                    self._config[section] = values
                    continue

                if section not in self._config:
                    self._config[section] = {}

                # Deep merge to avoid losing nested defaults
                self._deep_update(self._config[section], values)

            logger.info(f"已加载配置文件: {config_file}")

        except Exception as e:
            logger.error(f"加载配置文件失败 {config_file}: {e}")

    async def _load_environment_configs(self) -> None:
        """加载环境变量配置"""
        # Supported prefixes (backward compatible)
        prefixes = ("OPENCLAW_", "TRADING_")

        def parse_value(raw: str) -> Any:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, ValueError, TypeError):
                return raw

        def set_nested(cfg: Dict[str, Any], path: List[str], value: Any) -> None:
            cur = cfg
            for part in path[:-1]:
                if part not in cur or not isinstance(cur[part], dict):
                    cur[part] = {}
                cur = cur[part]
            cur[path[-1]] = value

        for env_key, raw_value in os.environ.items():
            prefix = next((p for p in prefixes if env_key.startswith(p)), None)
            if not prefix:
                continue
            if prefix == "TRADING_":
                global _TRADING_PREFIX_DEPRECATION_LOGGED
                if not _TRADING_PREFIX_DEPRECATION_LOGGED:
                    logger.warning(
                        "环境变量前缀 TRADING_ 已弃用，建议迁移到 OPENCLAW__section__key 形式。"
                    )
                    _TRADING_PREFIX_DEPRECATION_LOGGED = True

            remainder = env_key[len(prefix) :]
            if not remainder:
                continue

            # Prefer explicit nesting with "__": OPENCLAW__section__key__subkey
            if remainder.startswith("__"):
                parts = [p for p in remainder.split("__") if p]
                parts = [p.lower() for p in parts]
                if len(parts) >= 2:
                    set_nested(self._config, parts, parse_value(raw_value))
                continue

            # Fallback: PREFIX_SECTION_KEY -> section.key (1-level)
            parts = remainder.split("_", 1)
            if len(parts) != 2:
                continue
            section = parts[0].lower()
            config_key = parts[1].lower()
            if section not in self._config:
                self._config[section] = {}
            if isinstance(self._config[section], dict):
                self._config[section][config_key] = parse_value(raw_value)

        logger.debug("已加载环境变量配置")

    async def _save_section_to_file(self, section: str) -> None:
        """保存配置段到文件"""
        config_file = self.config_dir / f"{section}.json"

        try:
            section_config = self._config.get(section, {})

            # 如果配置为空，删除文件
            if not section_config and config_file.exists():
                config_file.unlink()
                return

            # 保存到文件
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(section_config, f, indent=2, ensure_ascii=False)

            # 更新文件时间戳
            self._file_timestamps[str(config_file)] = config_file.stat().st_mtime

            logger.debug(f"已保存配置到文件: {config_file}")

        except Exception as e:
            logger.error(f"保存配置文件失败 {config_file}: {e}")

    async def _watch_config_files(self) -> None:
        """监控配置文件变化"""
        logger.info(f"开始监控配置文件，间隔: {self.watch_interval}秒")

        while True:
            try:
                await asyncio.sleep(self.watch_interval)

                changed_files = []
                for file_path_str, last_mtime in self._file_timestamps.items():
                    file_path = Path(file_path_str)
                    if file_path.exists():
                        current_mtime = file_path.stat().st_mtime
                        if current_mtime > last_mtime:
                            changed_files.append(file_path)
                            self._file_timestamps[file_path_str] = current_mtime

                if changed_files:
                    logger.info(f"检测到配置文件变化: {changed_files}")
                    await self.reload()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"配置文件监控出错: {e}")

    async def _notify_watchers(
        self, section: str, key: str, old_value: Any, new_value: Any
    ) -> None:
        """通知配置观察者"""
        watch_key = f"{section}.{key}"

        if watch_key in self._watchers:
            for callback in self._watchers[watch_key]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(section, key, old_value, new_value)
                    else:
                        callback(section, key, old_value, new_value)
                except Exception as e:
                    logger.error(f"配置回调函数执行失败: {e}")


class ConfigTransaction:
    """配置事务"""

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.changes: List[tuple] = []  # (section, key, value)
        self.committed = False

    async def set_config(self, section: str, key: str, value: Any) -> None:
        """在事务中设置配置"""
        self.changes.append((section, key, value))

    async def commit(self) -> None:
        """提交事务"""
        if self.committed:
            return

        for section, key, value in self.changes:
            await self.config_manager.set_config(section, key, value, validate=False)

        self.committed = True

    async def rollback(self) -> None:
        """回滚事务"""
        self.changes.clear()


# 默认配置管理器实例
_default_config_manager: Optional[ConfigManager] = None


async def get_config_manager() -> ConfigManager:
    """获取默认配置管理器实例"""
    global _default_config_manager

    if _default_config_manager is None:
        _default_config_manager = ConfigManager()
        await _default_config_manager.initialize()

    return _default_config_manager


async def cleanup_config_manager() -> None:
    """清理默认配置管理器"""
    global _default_config_manager

    if _default_config_manager:
        await _default_config_manager.cleanup()
        _default_config_manager = None


# 示例使用
if __name__ == "__main__":
    import asyncio

    async def example():
        # 创建配置管理器
        config = ConfigManager()
        await config.initialize()

        # 设置配置
        await config.set_config("database", "host", "localhost")
        await config.set_config("database", "port", 5432)
        await config.set_config("database", "username", "trader")

        # 获取配置
        host = await config.get_config("database", "host")
        port = await config.get_config("database", "port")
        logger.info(f"数据库配置: {host}:{port}")

        # 监听配置变更
        async def on_database_change(section, key, old_value, new_value):
            logger.info(f"数据库配置变更: {section}.{key} = {old_value} -> {new_value}")

        await config.watch_config("database", "host", on_database_change)

        # 修改配置（会触发监听器）
        await config.set_config("database", "host", "127.0.0.1")

        # 使用事务
        async with config.transaction() as transaction:
            await transaction.set_config("redis", "host", "localhost")
            await transaction.set_config("redis", "port", 6379)

        # 获取所有配置
        all_configs = await config.get_all_configs()
        logger.info("所有配置:", json.dumps(all_configs, indent=2))

        # 清理
        await config.cleanup()

    asyncio.run(example())
