"""
环境变量配置加载工具

提供安全的环境变量加载和验证功能
"""

import os
import logging
from typing import Any, Dict, List, Optional, Union
from pathlib import Path

logger = logging.getLogger(__name__)


class EnvConfig:
    """环境变量配置加载器"""
    
    @staticmethod
    def load_env_file(env_file: str = ".env") -> None:
        """
        加载.env文件到环境变量
        
        Args:
            env_file: .env文件路径
        """
        env_path = Path(env_file)
        
        if not env_path.exists():
            logger.warning(f"环境变量文件不存在: {env_file}")
            return
        
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    
                    # 跳过注释和空行
                    if not line or line.startswith('#'):
                        continue
                    
                    # 解析键值对
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # 移除引号
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]
                        
                        # 设置环境变量(如果不存在)
                        if key not in os.environ:
                            os.environ[key] = value
            
            logger.info(f"✅ 已加载环境变量文件: {env_file}")
            
        except Exception as e:
            logger.error(f"加载环境变量文件失败: {e}")
    
    @staticmethod
    def get(key: str, default: Any = None, required: bool = False) -> Optional[str]:
        """
        获取环境变量
        
        Args:
            key: 环境变量名
            default: 默认值
            required: 是否必需
        
        Returns:
            环境变量值
        
        Raises:
            ValueError: 如果required=True但环境变量不存在
        """
        value = os.getenv(key, default)
        
        if required and not value:
            raise ValueError(f"必需的环境变量 {key} 未设置")
        
        return value
    
    @staticmethod
    def get_int(key: str, default: int = 0, required: bool = False) -> int:
        """获取整数类型环境变量"""
        value = EnvConfig.get(key, required=required)
        
        if value is None:
            return default
        
        try:
            return int(value)
        except ValueError:
            logger.warning(f"环境变量 {key}={value} 不是有效的整数,使用默认值 {default}")
            return default
    
    @staticmethod
    def get_float(key: str, default: float = 0.0, required: bool = False) -> float:
        """获取浮点数类型环境变量"""
        value = EnvConfig.get(key, required=required)
        
        if value is None:
            return default
        
        try:
            return float(value)
        except ValueError:
            logger.warning(f"环境变量 {key}={value} 不是有效的浮点数,使用默认值 {default}")
            return default
    
    @staticmethod
    def get_bool(key: str, default: bool = False, required: bool = False) -> bool:
        """获取布尔类型环境变量"""
        value = EnvConfig.get(key, required=required)
        
        if value is None:
            return default
        
        return value.lower() in ('true', '1', 'yes', 'on', 'enabled')
    
    @staticmethod
    def get_list(key: str, separator: str = ',', default: List[str] = None, 
                 required: bool = False) -> List[str]:
        """获取列表类型环境变量"""
        value = EnvConfig.get(key, required=required)
        
        if value is None:
            return default or []
        
        return [item.strip() for item in value.split(separator) if item.strip()]
    
    @staticmethod
    def get_dict(prefix: str, required_keys: List[str] = None) -> Dict[str, str]:
        """
        获取带前缀的环境变量字典
        
        Args:
            prefix: 环境变量前缀
            required_keys: 必需的键列表
        
        Returns:
            环境变量字典
        
        Example:
            # 环境变量: DB_HOST=localhost, DB_PORT=5432
            config = EnvConfig.get_dict("DB")
            # 返回: {"HOST": "localhost", "PORT": "5432"}
        """
        result = {}
        
        # 遍历所有环境变量
        for key, value in os.environ.items():
            if key.startswith(prefix + '_'):
                # 移除前缀
                config_key = key[len(prefix) + 1:]
                result[config_key] = value
        
        # 验证必需的键
        if required_keys:
            missing_keys = [key for key in required_keys if key not in result]
            if missing_keys:
                raise ValueError(f"缺少必需的环境变量: {[prefix + '_' + key for key in missing_keys]}")
        
        return result
    
    @staticmethod
    def validate_required_keys(keys: List[str]) -> List[str]:
        """
        验证必需的环境变量
        
        Args:
            keys: 环境变量名列表
        
        Returns:
            缺失的环境变量名列表
        """
        missing = []
        
        for key in keys:
            if not os.getenv(key):
                missing.append(key)
        
        return missing
    
    @staticmethod
    def mask_sensitive_value(key: str, value: str, show_length: int = 4) -> str:
        """
        遮蔽敏感值
        
        Args:
            key: 环境变量名
            value: 环境变量值
            show_length: 显示的字符数
        
        Returns:
            遮蔽后的值
        """
        sensitive_keywords = [
            'KEY', 'SECRET', 'PASSWORD', 'TOKEN', 'PASSPHRASE',
            'API_KEY', 'PRIVATE', 'CREDENTIAL'
        ]
        
        is_sensitive = any(keyword in key.upper() for keyword in sensitive_keywords)
        
        if is_sensitive and value and len(value) > show_length:
            return value[:show_length] + '*' * (len(value) - show_length)
        
        return value
    
    @staticmethod
    def print_env_summary(sensitive_keys: List[str] = None) -> None:
        """
        打印环境变量摘要
        
        Args:
            sensitive_keys: 敏感键列表
        """
        logger.info("=" * 60)
        logger.info("环境变量配置摘要:")
        logger.info("=" * 60)
        
        # 按前缀分组
        groups = {}
        for key in sorted(os.environ.keys()):
            # 跳过系统环境变量
            if key.startswith(('_', 'PATH', 'HOME', 'USER', 'SHELL', 'TERM')):
                continue
            
            # 分组
            prefix = key.split('_')[0] if '_' in key else 'OTHER'
            
            if prefix not in groups:
                groups[prefix] = []
            
            value = os.getenv(key)
            
            # 遮蔽敏感值
            if sensitive_keys and key in sensitive_keys:
                value = EnvConfig.mask_sensitive_value(key, value)
            elif any(keyword in key.upper() for keyword in ['KEY', 'SECRET', 'PASSWORD', 'TOKEN']):
                value = EnvConfig.mask_sensitive_value(key, value)
            
            groups[prefix].append((key, value))
        
        # 打印分组
        for prefix, items in sorted(groups.items()):
            logger.info(f"\n[{prefix}]")
            for key, value in items:
                logger.info(f"  {key}={value}")
        
        logger.info("=" * 60)


def load_environment(env_file: str = ".env") -> None:
    """
    加载环境变量的便捷函数
    
    Args:
        env_file: .env文件路径
    """
    # 尝试从多个位置加载.env文件
    possible_paths = [
        env_file,
        Path.cwd() / ".env",
        Path(__file__).parent.parent.parent.parent / ".env",
        Path.home() / ".openclaw-trading" / ".env"
    ]
    
    for path in possible_paths:
        if Path(path).exists():
            EnvConfig.load_env_file(str(path))
            return
    
    logger.warning("未找到.env文件,使用系统环境变量")


# 使用示例
if __name__ == "__main__":
    # 加载环境变量
    load_environment()
    
    # 打印环境变量摘要
    EnvConfig.print_env_summary()
    
    # 获取配置
    logger.info(f"XUNFEI_API_KEY: {EnvConfig.get('XUNFEI_API_KEY', 'not_set')}")
    logger.info(f"OKX_API_KEY: {EnvConfig.get('OKX_API_KEY', 'not_set')}")
    logger.info(f"TRADING_SYMBOLS: {EnvConfig.get_list('TRADING_SYMBOLS', default=['BTC/USDT'])}")
