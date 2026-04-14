"""
统一代理工具
为所有网络请求提供统一的代理支持

支持：
1. Clash代理自动检测
2. 环境变量代理配置
3. 配置文件代理设置
4. 代理故障自动切换
"""
import asyncio
import logging
import os
from typing import Optional, Dict, Any
from dataclasses import dataclass
from pathlib import Path
import json

logger = logging.getLogger(__name__)


@dataclass
class ProxySettings:
    """代理设置"""
    enabled: bool = False
    http_proxy: str = ""
    https_proxy: str = ""
    socks5_proxy: str = ""
    
    @property
    def proxy_url(self) -> Optional[str]:
        """获取代理URL"""
        if self.https_proxy:
            return self.https_proxy
        if self.http_proxy:
            return self.http_proxy
        if self.socks5_proxy:
            return self.socks5_proxy
        return None


class UnifiedProxyManager:
    """
    统一代理管理器
    
    代理优先级：
    1. 环境变量 HTTP_PROXY/HTTPS_PROXY
    2. Clash配置文件
    3. 系统配置文件
    """
    
    DEFAULT_CLASH_PORT = 7890
    DEFAULT_CLASH_API_PORT = 9090
    
    def __init__(self):
        self.settings = ProxySettings()
        self._initialized = False
        self._clash_running = False
        
    async def initialize(self, config: Dict[str, Any] = None):
        """初始化代理管理器"""
        logger.info("初始化统一代理管理器...")
        
        await self._detect_from_env()
        
        if not self.settings.enabled:
            await self._detect_clash()
        
        if config and not self.settings.enabled:
            await self._load_from_config(config)
        
        self._initialized = True
        
        if self.settings.enabled:
            logger.info(f"✅ 代理已启用: {self.settings.proxy_url}")
        else:
            logger.info("ℹ️ 代理未启用，使用直连")
    
    async def _detect_from_env(self):
        """从环境变量检测代理"""
        # 优先读取应用专用变量，避免宿主机的 HTTP_PROXY 意外污染容器运行（常导致 127.0.0.1:7890 不可达）
        http_proxy = os.getenv("OPENCLAW_HTTP_PROXY") or ""
        https_proxy = os.getenv("OPENCLAW_HTTPS_PROXY") or ""
        all_proxy = os.getenv("OPENCLAW_ALL_PROXY") or ""

        if not (http_proxy or https_proxy or all_proxy):
            # 兼容：如用户确实希望使用系统变量，可直接设置 OPENCLAW_* 或把系统变量注入容器
            http_proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy") or ""
            https_proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or ""
            all_proxy = os.getenv("ALL_PROXY") or os.getenv("all_proxy") or ""
        
        if http_proxy or https_proxy or all_proxy:
            self.settings.enabled = True
            self.settings.http_proxy = http_proxy or all_proxy or ""
            self.settings.https_proxy = https_proxy or all_proxy or ""
            logger.info(f"从环境变量检测到代理: {self.settings.https_proxy or self.settings.http_proxy}")
    
    async def _detect_clash(self):
        """检测Clash代理"""
        try:
            clash_config_paths = [
                Path.home() / ".config" / "clash" / "config.yaml",
                Path.home() / ".config" / "clash" / "profiles" / "config.yaml",
                Path("/etc/clash/config.yaml"),
            ]
            
            clash_running = False
            for config_path in clash_config_paths:
                if config_path.exists():
                    logger.debug(f"发现Clash配置文件: {config_path}")
                    clash_running = True
                    break
            
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', self.DEFAULT_CLASH_PORT))
            sock.close()
            
            if result == 0:
                clash_running = True
                logger.debug(f"Clash端口 {self.DEFAULT_CLASH_PORT} 可访问")
            
            if clash_running:
                self.settings.enabled = True
                self.settings.http_proxy = f"http://127.0.0.1:{self.DEFAULT_CLASH_PORT}"
                self.settings.https_proxy = f"http://127.0.0.1:{self.DEFAULT_CLASH_PORT}"
                self.settings.socks5_proxy = f"socks5://127.0.0.1:7891"
                self._clash_running = True
                logger.info(f"✅ 检测到Clash代理: http://127.0.0.1:{self.DEFAULT_CLASH_PORT}")
                
        except Exception as e:
            logger.debug(f"Clash检测失败: {e}")
    
    async def _load_from_config(self, config: Dict[str, Any]):
        """从配置文件加载代理设置"""
        if not config:
            return
        
        proxy_config = config.get("proxy", {})
        
        if not proxy_config.get("enabled", False):
            return
        
        global_proxy = proxy_config.get("global_proxy", {})
        if global_proxy.get("enabled", False):
            proxy_type = global_proxy.get("proxy_type", "http")
            host = global_proxy.get("host", "127.0.0.1")
            port = global_proxy.get("port", 7890)
            
            username = os.getenv(global_proxy.get("username_env", ""), "")
            password = os.getenv(global_proxy.get("password_env", ""), "")
            
            auth = ""
            if username and password:
                auth = f"{username}:{password}@"
            
            proxy_url = f"{proxy_type}://{auth}{host}:{port}"
            
            self.settings.enabled = True
            if proxy_type in ["http", "https"]:
                self.settings.http_proxy = proxy_url
                self.settings.https_proxy = proxy_url
            elif proxy_type == "socks5":
                self.settings.socks5_proxy = proxy_url
            
            logger.info(f"从配置文件加载代理: {proxy_url}")
    
    def get_proxy(self, url: str = None) -> Optional[str]:
        """
        获取代理URL
        
        Args:
            url: 目标URL（用于未来可能的域名特定代理）
        
        Returns:
            代理URL或None
        """
        if not self.settings.enabled:
            return None
        
        if url and url.startswith("https://"):
            return self.settings.https_proxy or self.settings.http_proxy
        
        return self.settings.proxy_url
    
    def get_aiohttp_proxy(self, url: str = None) -> Optional[str]:
        """获取aiohttp格式的代理"""
        return self.get_proxy(url)
    
    def get_requests_proxies(self) -> Optional[Dict[str, str]]:
        """获取requests格式的代理字典"""
        if not self.settings.enabled:
            return None
        
        proxy = self.settings.proxy_url
        if proxy:
            return {
                "http": proxy,
                "https": proxy
            }
        return None
    
    async def test_proxy(self) -> bool:
        """测试代理是否可用"""
        if not self.settings.enabled:
            return True
        
        import aiohttp
        
        proxy = self.get_proxy()
        test_urls = [
            "https://api.ipify.org?format=json",
            "https://api.github.com",
            "https://www.google.com"
        ]
        
        for url in test_urls:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, proxy=proxy, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            logger.info(f"✅ 代理测试成功: {url}")
                            return True
            except Exception as e:
                logger.debug(f"代理测试失败 {url}: {e}")
        
        logger.warning("⚠️ 代理测试失败，可能无法正常访问外网")
        return False
    
    def is_enabled(self) -> bool:
        """检查代理是否启用"""
        return self.settings.enabled
    
    def is_clash(self) -> bool:
        """检查是否使用Clash代理"""
        return self._clash_running
    
    def get_settings(self) -> Dict[str, Any]:
        """获取代理设置"""
        return {
            "enabled": self.settings.enabled,
            "http_proxy": self.settings.http_proxy,
            "https_proxy": self.settings.https_proxy,
            "socks5_proxy": self.settings.socks5_proxy,
            "proxy_url": self.settings.proxy_url,
            "is_clash": self._clash_running
        }


_unified_proxy: Optional[UnifiedProxyManager] = None


async def get_unified_proxy() -> UnifiedProxyManager:
    """获取统一代理管理器实例"""
    global _unified_proxy
    if _unified_proxy is None:
        _unified_proxy = UnifiedProxyManager()
        await _unified_proxy.initialize()
    return _unified_proxy


async def get_proxy_url(url: str = None) -> Optional[str]:
    """快速获取代理URL"""
    proxy = await get_unified_proxy()
    return proxy.get_proxy(url)


async def init_proxy_from_config(config: Dict[str, Any] = None):
    """从配置初始化代理"""
    global _unified_proxy
    _unified_proxy = UnifiedProxyManager()
    await _unified_proxy.initialize(config)
    return _unified_proxy
