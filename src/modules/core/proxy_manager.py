"""
代理管理器 - 支持 HTTP/HTTPS/SOCKS 代理

功能：
1. 支持 HTTP/HTTPS/SOCKS5 代理
2. 自动代理切换和故障转移
3. 代理健康检查
4. 代理池管理
5. 代理认证支持
"""

import asyncio
import logging
import socket
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ProxyType(Enum):
    """代理类型"""
    HTTP = "http"
    HTTPS = "https"
    SOCKS5 = "socks5"
    SOCKS4 = "socks4"


class ProxyStatus(Enum):
    """代理状态"""
    ACTIVE = "active"           # 活跃可用
    INACTIVE = "inactive"       # 未激活
    ERROR = "error"             # 错误状态
    CHECKING = "checking"       # 检查中


@dataclass
class ProxyConfig:
    """代理配置"""
    name: str
    proxy_type: ProxyType
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    enabled: bool = True
    priority: int = 0           # 优先级，数字越小优先级越高
    timeout: int = 30           # 超时时间（秒）
    retry_count: int = 3        # 重试次数
    health_check_url: str = "http://www.google.com"  # 健康检查URL
    
    def __post_init__(self):
        if isinstance(self.proxy_type, str):
            self.proxy_type = ProxyType(self.proxy_type.lower())
    
    @property
    def url(self) -> str:
        """获取代理 URL"""
        auth = ""
        if self.username and self.password:
            auth = f"{self.username}:{self.password}@"
        return f"{self.proxy_type.value}://{auth}{self.host}:{self.port}"
    
    @property
    def dict(self) -> Dict[str, str]:
        """转换为字典格式（用于 requests/aiohttp）"""
        return {
            "http": self.url,
            "https": self.url
        }


@dataclass
class ProxyStats:
    """代理统计信息"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_response_time: float = 0.0
    last_used: Optional[float] = None
    last_error: Optional[str] = None
    error_count: int = 0
    consecutive_errors: int = 0
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests
    
    @property
    def avg_response_time(self) -> float:
        """平均响应时间"""
        if self.successful_requests == 0:
            return 0.0
        return self.total_response_time / self.successful_requests


class ProxyManager:
    """
    代理管理器
    
    功能：
    1. 管理多个代理配置
    2. 自动代理选择和切换
    3. 代理健康检查
    4. 代理统计和监控
    """
    
    def __init__(self):
        self.proxies: Dict[str, ProxyConfig] = {}
        self.proxy_stats: Dict[str, ProxyStats] = {}
        self.proxy_status: Dict[str, ProxyStatus] = {}
        self.current_proxy: Optional[str] = None
        self._lock = asyncio.Lock()
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False
        
        # 全局代理设置
        self.global_proxy: Optional[ProxyConfig] = None
        self.use_global_proxy: bool = False
        
        # 代理白名单/黑名单
        self.whitelist_domains: List[str] = []
        self.blacklist_domains: List[str] = []
        
        # 回调函数
        self.on_proxy_change: Optional[Callable] = None
        self.on_proxy_error: Optional[Callable] = None
    
    async def initialize(self, config: Dict[str, Any] = None):
        """初始化代理管理器"""
        logger.info("初始化代理管理器...")
        
        if config:
            # 加载全局代理设置
            global_config = config.get("global_proxy")
            if global_config:
                self.global_proxy = ProxyConfig(**global_config)
                self.use_global_proxy = config.get("use_global_proxy", False)
                logger.info(f"配置全局代理: {self.global_proxy.url}")
            
            # 加载代理列表
            proxies_config = config.get("proxies", [])
            for proxy_conf in proxies_config:
                await self.add_proxy(ProxyConfig(**proxy_conf))
            
            # 加载黑白名单
            self.whitelist_domains = config.get("whitelist_domains", [])
            self.blacklist_domains = config.get("blacklist_domains", [])
        
        self._running = True
        
        # 启动健康检查任务
        self._health_check_task = asyncio.create_task(self._health_check_worker())
        
        logger.info("代理管理器初始化完成")
    
    async def cleanup(self):
        """清理资源"""
        logger.info("清理代理管理器...")
        self._running = False
        
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        logger.info("代理管理器清理完成")
    
    async def add_proxy(self, proxy_config: ProxyConfig) -> bool:
        """添加代理"""
        async with self._lock:
            self.proxies[proxy_config.name] = proxy_config
            self.proxy_stats[proxy_config.name] = ProxyStats()
            self.proxy_status[proxy_config.name] = ProxyStatus.INACTIVE
            
            # 如果是第一个代理，设为当前代理
            if self.current_proxy is None and proxy_config.enabled:
                self.current_proxy = proxy_config.name
                self.proxy_status[proxy_config.name] = ProxyStatus.ACTIVE
            
            logger.info(f"添加代理: {proxy_config.name} ({proxy_config.url})")
            return True
    
    async def remove_proxy(self, name: str) -> bool:
        """移除代理"""
        async with self._lock:
            if name not in self.proxies:
                return False
            
            del self.proxies[name]
            del self.proxy_stats[name]
            del self.proxy_status[name]
            
            # 如果移除的是当前代理，切换到其他可用代理
            if self.current_proxy == name:
                self.current_proxy = None
                for proxy_name, proxy in self.proxies.items():
                    if proxy.enabled:
                        self.current_proxy = proxy_name
                        self.proxy_status[proxy_name] = ProxyStatus.ACTIVE
                        break
            
            logger.info(f"移除代理: {name}")
            return True
    
    async def get_proxy(self, domain: str = None) -> Optional[ProxyConfig]:
        """
        获取代理配置
        
        Args:
            domain: 目标域名，用于判断是否使用代理
        
        Returns:
            代理配置或 None
        """
        # 检查是否需要使用代理
        if domain:
            if self.whitelist_domains and domain not in self.whitelist_domains:
                return None
            if domain in self.blacklist_domains:
                return None
        
        # 如果使用全局代理
        if self.use_global_proxy and self.global_proxy:
            return self.global_proxy
        
        # 返回当前选中的代理
        async with self._lock:
            if self.current_proxy and self.current_proxy in self.proxies:
                proxy = self.proxies[self.current_proxy]
                if proxy.enabled and self.proxy_status[self.current_proxy] == ProxyStatus.ACTIVE:
                    return proxy
            
            # 如果当前代理不可用，尝试找一个可用的
            for name, proxy in sorted(self.proxies.items(), key=lambda x: x[1].priority):
                if proxy.enabled and self.proxy_status[name] == ProxyStatus.ACTIVE:
                    self.current_proxy = name
                    return proxy
        
        return None
    
    async def get_proxy_dict(self, domain: str = None) -> Optional[Dict[str, str]]:
        """获取代理字典（用于 requests）"""
        proxy = await self.get_proxy(domain)
        if proxy:
            return proxy.dict
        return None
    
    async def switch_proxy(self, name: Optional[str] = None) -> bool:
        """
        切换代理
        
        Args:
            name: 代理名称，如果为 None 则自动选择最佳代理
        
        Returns:
            是否切换成功
        """
        async with self._lock:
            if name:
                if name not in self.proxies:
                    logger.error(f"代理不存在: {name}")
                    return False
                
                if not self.proxies[name].enabled:
                    logger.error(f"代理未启用: {name}")
                    return False
                
                old_proxy = self.current_proxy
                self.current_proxy = name
                
                # 更新状态
                for proxy_name in self.proxy_status:
                    if proxy_name == name:
                        self.proxy_status[proxy_name] = ProxyStatus.ACTIVE
                    else:
                        self.proxy_status[proxy_name] = ProxyStatus.INACTIVE
                
                logger.info(f"切换到代理: {name}")
                
                # 触发回调
                if self.on_proxy_change:
                    await self.on_proxy_change(old_proxy, name)
                
                return True
            else:
                # 自动选择最佳代理
                best_proxy = None
                best_score = -1
                
                for proxy_name, proxy in self.proxies.items():
                    if not proxy.enabled:
                        continue
                    
                    stats = self.proxy_stats[proxy_name]
                    # 计算代理得分（成功率 * 100 - 平均响应时间 - 优先级 * 10）
                    score = stats.success_rate * 100 - stats.avg_response_time - proxy.priority * 10
                    
                    if score > best_score:
                        best_score = score
                        best_proxy = proxy_name
                
                if best_proxy:
                    return await self.switch_proxy(best_proxy)
                
                return False
    
    async def report_proxy_error(self, name: str, error: str):
        """报告代理错误"""
        async with self._lock:
            if name in self.proxy_stats:
                stats = self.proxy_stats[name]
                stats.failed_requests += 1
                stats.error_count += 1
                stats.consecutive_errors += 1
                stats.last_error = error
                
                # 如果连续错误超过阈值，标记为错误状态
                proxy = self.proxies.get(name)
                if proxy and stats.consecutive_errors >= proxy.retry_count:
                    self.proxy_status[name] = ProxyStatus.ERROR
                    logger.warning(f"代理 {name} 标记为错误状态")
                    
                    # 触发回调
                    if self.on_proxy_error:
                        await self.on_proxy_error(name, error)
                    
                    # 如果当前代理出错，自动切换
                    if self.current_proxy == name:
                        await self.switch_proxy()
    
    async def report_proxy_success(self, name: str, response_time: float):
        """报告代理成功"""
        async with self._lock:
            if name in self.proxy_stats:
                stats = self.proxy_stats[name]
                stats.successful_requests += 1
                stats.total_response_time += response_time
                stats.consecutive_errors = 0
                stats.last_used = time.time()
                
                # 如果之前是错误状态，恢复为活跃
                if self.proxy_status[name] == ProxyStatus.ERROR:
                    self.proxy_status[name] = ProxyStatus.ACTIVE
                    logger.info(f"代理 {name} 恢复为活跃状态")
    
    async def check_proxy_health(self, name: str) -> bool:
        """检查代理健康状态"""
        if name not in self.proxies:
            return False
        
        proxy = self.proxies[name]
        
        try:
            # 简单的 TCP 连接测试
            start_time = time.time()
            
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(proxy.host, proxy.port),
                timeout=proxy.timeout
            )
            writer.close()
            await writer.wait_closed()
            
            response_time = time.time() - start_time
            
            # 更新统计
            await self.report_proxy_success(name, response_time)
            
            return True
            
        except Exception as e:
            await self.report_proxy_error(name, str(e))
            return False
    
    async def _health_check_worker(self):
        """健康检查工作线程"""
        logger.info("启动代理健康检查任务")
        
        while self._running:
            try:
                # 每 60 秒检查一次
                await asyncio.sleep(60)
                
                for name, proxy in self.proxies.items():
                    if not proxy.enabled:
                        continue
                    
                    self.proxy_status[name] = ProxyStatus.CHECKING
                    is_healthy = await self.check_proxy_health(name)
                    
                    if is_healthy:
                        logger.debug(f"代理 {name} 健康检查通过")
                    else:
                        logger.warning(f"代理 {name} 健康检查失败")
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查任务出错: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取代理统计信息"""
        return {
            name: {
                "total_requests": stats.total_requests,
                "successful_requests": stats.successful_requests,
                "failed_requests": stats.failed_requests,
                "success_rate": stats.success_rate,
                "avg_response_time": stats.avg_response_time,
                "last_used": stats.last_used,
                "error_count": stats.error_count,
                "status": self.proxy_status.get(name, ProxyStatus.INACTIVE).value
            }
            for name, stats in self.proxy_stats.items()
        }
    
    def get_config(self) -> Dict[str, Any]:
        """获取配置信息"""
        return {
            "global_proxy": {
                "name": self.global_proxy.name,
                "proxy_type": self.global_proxy.proxy_type.value,
                "host": self.global_proxy.host,
                "port": self.global_proxy.port,
                "username": self.global_proxy.username,
                "enabled": self.global_proxy.enabled
            } if self.global_proxy else None,
            "use_global_proxy": self.use_global_proxy,
            "current_proxy": self.current_proxy,
            "proxies": [
                {
                    "name": proxy.name,
                    "proxy_type": proxy.proxy_type.value,
                    "host": proxy.host,
                    "port": proxy.port,
                    "enabled": proxy.enabled,
                    "priority": proxy.priority
                }
                for proxy in self.proxies.values()
            ],
            "whitelist_domains": self.whitelist_domains,
            "blacklist_domains": self.blacklist_domains
        }


# 全局代理管理器实例
_proxy_manager: Optional[ProxyManager] = None


async def get_proxy_manager() -> ProxyManager:
    """获取代理管理器实例"""
    global _proxy_manager
    if _proxy_manager is None:
        _proxy_manager = ProxyManager()
    return _proxy_manager


async def set_global_proxy(proxy_config: ProxyConfig):
    """设置全局代理"""
    manager = await get_proxy_manager()
    manager.global_proxy = proxy_config
    manager.use_global_proxy = True
    logger.info(f"设置全局代理: {proxy_config.url}")


async def clear_global_proxy():
    """清除全局代理"""
    manager = await get_proxy_manager()
    manager.use_global_proxy = False
    logger.info("清除全局代理设置")
