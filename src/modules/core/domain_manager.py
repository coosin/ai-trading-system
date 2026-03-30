"""
域名管理器 - 域名绑定和 SSL/TLS 配置

功能：
1. 多域名管理
2. SSL/TLS 证书管理
3. 自动证书申请和续期（Let's Encrypt）
4. 域名健康检查
5. 反向代理配置生成
"""

import asyncio
import logging
import ssl
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import os

logger = logging.getLogger(__name__)


class DomainStatus(Enum):
    """域名状态"""
    ACTIVE = "active"           # 活跃可用
    INACTIVE = "inactive"       # 未激活
    ERROR = "error"             # 错误状态
    PENDING = "pending"         # 待处理
    EXPIRED = "expired"         # 证书过期


class CertificateSource(Enum):
    """证书来源"""
    LETS_ENCRYPT = "letsencrypt"    # Let's Encrypt
    CUSTOM = "custom"               # 自定义证书
    SELF_SIGNED = "self_signed"     # 自签名证书
    AUTO = "auto"                   # 自动选择


@dataclass
class SSLCertificate:
    """SSL 证书配置"""
    domain: str
    cert_path: Optional[str] = None
    key_path: Optional[str] = None
    ca_path: Optional[str] = None
    source: CertificateSource = CertificateSource.AUTO
    auto_renew: bool = True
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    last_renewed: Optional[datetime] = None
    renew_days_before: int = 30     # 到期前多少天续期
    
    def is_expired(self) -> bool:
        """检查证书是否过期"""
        if not self.expires_at:
            return True
        return datetime.now() > self.expires_at
    
    def needs_renewal(self) -> bool:
        """检查是否需要续期"""
        if not self.expires_at:
            return True
        if not self.auto_renew:
            return False
        renewal_date = self.expires_at - timedelta(days=self.renew_days_before)
        return datetime.now() >= renewal_date
    
    def days_until_expiry(self) -> Optional[int]:
        """距离过期还有多少天"""
        if not self.expires_at:
            return None
        delta = self.expires_at - datetime.now()
        return max(0, delta.days)


@dataclass
class DomainConfig:
    """域名配置"""
    domain: str
    enabled: bool = True
    status: DomainStatus = DomainStatus.PENDING
    
    # 后端配置
    backend_host: str = "localhost"
    backend_port: int = 8000
    backend_protocol: str = "http"
    
    # SSL 配置
    ssl_enabled: bool = False
    ssl_certificate: Optional[SSLCertificate] = None
    force_https: bool = False      # 强制 HTTPS
    hsts_enabled: bool = False     # HTTP Strict Transport Security
    
    # 性能配置
    caching_enabled: bool = True
    cache_duration: int = 3600     # 缓存时间（秒）
    compression_enabled: bool = True
    
    # 安全配置
    rate_limiting_enabled: bool = True
    rate_limit_requests: int = 100  # 每分钟请求数
    ip_whitelist: List[str] = field(default_factory=list)
    ip_blacklist: List[str] = field(default_factory=list)
    
    # 监控配置
    health_check_enabled: bool = True
    health_check_path: str = "/health"
    health_check_interval: int = 60
    
    # 元数据
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "domain": self.domain,
            "enabled": self.enabled,
            "status": self.status.value,
            "backend_host": self.backend_host,
            "backend_port": self.backend_port,
            "backend_protocol": self.backend_protocol,
            "ssl_enabled": self.ssl_enabled,
            "ssl_certificate": {
                "domain": self.ssl_certificate.domain,
                "source": self.ssl_certificate.source.value,
                "auto_renew": self.ssl_certificate.auto_renew,
                "expires_at": self.ssl_certificate.expires_at.isoformat() if self.ssl_certificate.expires_at else None,
                "days_until_expiry": self.ssl_certificate.days_until_expiry()
            } if self.ssl_certificate else None,
            "force_https": self.force_https,
            "hsts_enabled": self.hsts_enabled,
            "caching_enabled": self.caching_enabled,
            "rate_limiting_enabled": self.rate_limiting_enabled,
            "health_check_enabled": self.health_check_enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


class DomainManager:
    """
    域名管理器
    
    功能：
    1. 管理多个域名配置
    2. SSL 证书自动申请和续期
    3. 生成 Nginx/Apache 配置
    4. 域名健康检查
    """
    
    def __init__(self, config_dir: str = "data/domains"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.domains: Dict[str, DomainConfig] = {}
        self._lock = asyncio.Lock()
        self._initialized = False
        self._renewal_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Let's Encrypt 配置
        self.letsencrypt_email: Optional[str] = None
        self.letsencrypt_staging: bool = False  # 使用测试环境
        
        # 证书存储路径
        self.cert_dir = Path("data/certs")
        self.cert_dir.mkdir(parents=True, exist_ok=True)
    
    async def initialize(self, config: Dict[str, Any] = None):
        """初始化域名管理器"""
        logger.info("初始化域名管理器...")
        
        if config:
            # 加载 Let's Encrypt 配置
            le_config = config.get("letsencrypt", {})
            self.letsencrypt_email = le_config.get("email")
            self.letsencrypt_staging = le_config.get("staging", False)
            
            # 加载域名配置
            domains_config = config.get("domains", [])
            for domain_conf in domains_config:
                await self.add_domain(self._dict_to_domain_config(domain_conf))
        
        self._running = True
        
        # 启动证书续期任务
        self._renewal_task = asyncio.create_task(self._certificate_renewal_worker())
        
        self._initialized = True
        logger.info("域名管理器初始化完成")
    
    async def cleanup(self):
        """清理资源"""
        logger.info("清理域名管理器...")
        self._running = False
        
        if self._renewal_task:
            self._renewal_task.cancel()
            try:
                await self._renewal_task
            except asyncio.CancelledError:
                pass
        
        logger.info("域名管理器清理完成")
    
    def _dict_to_domain_config(self, data: Dict[str, Any]) -> DomainConfig:
        """从字典创建域名配置"""
        ssl_cert = None
        if data.get("ssl_certificate"):
            cert_data = data["ssl_certificate"]
            ssl_cert = SSLCertificate(
                domain=cert_data.get("domain", data["domain"]),
                cert_path=cert_data.get("cert_path"),
                key_path=cert_data.get("key_path"),
                ca_path=cert_data.get("ca_path"),
                source=CertificateSource(cert_data.get("source", "auto")),
                auto_renew=cert_data.get("auto_renew", True),
                renew_days_before=cert_data.get("renew_days_before", 30)
            )
        
        return DomainConfig(
            domain=data["domain"],
            enabled=data.get("enabled", True),
            backend_host=data.get("backend_host", "localhost"),
            backend_port=data.get("backend_port", 8000),
            backend_protocol=data.get("backend_protocol", "http"),
            ssl_enabled=data.get("ssl_enabled", False),
            ssl_certificate=ssl_cert,
            force_https=data.get("force_https", False),
            hsts_enabled=data.get("hsts_enabled", False),
            caching_enabled=data.get("caching_enabled", True),
            rate_limiting_enabled=data.get("rate_limiting_enabled", True),
            ip_whitelist=data.get("ip_whitelist", []),
            ip_blacklist=data.get("ip_blacklist", [])
        )
    
    async def add_domain(self, config: DomainConfig) -> bool:
        """添加域名"""
        async with self._lock:
            self.domains[config.domain] = config
            
            # 如果启用 SSL 但没有证书，自动申请
            if config.ssl_enabled and config.ssl_certificate is None:
                success = await self._obtain_certificate(config)
                if success:
                    config.status = DomainStatus.ACTIVE
                else:
                    config.status = DomainStatus.ERROR
            else:
                config.status = DomainStatus.ACTIVE if config.enabled else DomainStatus.INACTIVE
            
            logger.info(f"添加域名: {config.domain} (状态: {config.status.value})")
            return True
    
    async def remove_domain(self, domain: str) -> bool:
        """移除域名"""
        async with self._lock:
            if domain not in self.domains:
                return False
            
            del self.domains[domain]
            logger.info(f"移除域名: {domain}")
            return True
    
    async def get_domain(self, domain: str) -> Optional[DomainConfig]:
        """获取域名配置"""
        return self.domains.get(domain)
    
    async def update_domain(self, domain: str, updates: Dict[str, Any]) -> bool:
        """更新域名配置"""
        async with self._lock:
            if domain not in self.domains:
                return False
            
            config = self.domains[domain]
            
            # 更新字段
            for key, value in updates.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            
            config.updated_at = datetime.now()
            logger.info(f"更新域名配置: {domain}")
            return True
    
    async def enable_ssl(self, domain: str, force_https: bool = True) -> bool:
        """为域名启用 SSL"""
        config = await self.get_domain(domain)
        if not config:
            logger.error(f"域名不存在: {domain}")
            return False
        
        config.ssl_enabled = True
        config.force_https = force_https
        
        # 申请证书
        success = await self._obtain_certificate(config)
        if success:
            config.status = DomainStatus.ACTIVE
            logger.info(f"已为 {domain} 启用 SSL")
        else:
            config.status = DomainStatus.ERROR
            logger.error(f"为 {domain} 启用 SSL 失败")
        
        return success
    
    async def disable_ssl(self, domain: str) -> bool:
        """禁用域名 SSL"""
        config = await self.get_domain(domain)
        if not config:
            return False
        
        config.ssl_enabled = False
        config.force_https = False
        logger.info(f"已禁用 {domain} 的 SSL")
        return True
    
    async def _obtain_certificate(self, config: DomainConfig) -> bool:
        """申请 SSL 证书"""
        if not self.letsencrypt_email:
            logger.error("未配置 Let's Encrypt 邮箱")
            return False
        
        try:
            logger.info(f"正在为 {config.domain} 申请证书...")
            
            # 使用 certbot 申请证书
            cmd = [
                "certbot", "certonly",
                "--standalone",
                "--agree-tos",
                "--non-interactive",
                "--email", self.letsencrypt_email,
                "-d", config.domain
            ]
            
            if self.letsencrypt_staging:
                cmd.append("--staging")
            
            # 执行 certbot 命令
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()
            
            if result.returncode == 0:
                # 证书申请成功
                cert_path = f"/etc/letsencrypt/live/{config.domain}/fullchain.pem"
                key_path = f"/etc/letsencrypt/live/{config.domain}/privkey.pem"
                
                config.ssl_certificate = SSLCertificate(
                    domain=config.domain,
                    cert_path=cert_path,
                    key_path=key_path,
                    source=CertificateSource.LETS_ENCRYPT,
                    auto_renew=True,
                    created_at=datetime.now(),
                    expires_at=datetime.now() + timedelta(days=90)
                )
                
                logger.info(f"证书申请成功: {config.domain}")
                return True
            else:
                logger.error(f"证书申请失败: {stderr.decode()}")
                return False
                
        except Exception as e:
            logger.error(f"申请证书时出错: {e}")
            return False
    
    async def _renew_certificate(self, config: DomainConfig) -> bool:
        """续期 SSL 证书"""
        if not config.ssl_certificate or not config.ssl_certificate.auto_renew:
            return False
        
        try:
            logger.info(f"正在续期 {config.domain} 的证书...")
            
            # 使用 certbot 续期
            cmd = ["certbot", "renew", "--non-interactive"]
            
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()
            
            if result.returncode == 0:
                config.ssl_certificate.last_renewed = datetime.now()
                config.ssl_certificate.expires_at = datetime.now() + timedelta(days=90)
                logger.info(f"证书续期成功: {config.domain}")
                return True
            else:
                logger.error(f"证书续期失败: {stderr.decode()}")
                return False
                
        except Exception as e:
            logger.error(f"续期证书时出错: {e}")
            return False
    
    async def _certificate_renewal_worker(self):
        """证书续期工作线程"""
        logger.info("启动证书续期任务")
        
        while self._running:
            try:
                # 每天检查一次
                await asyncio.sleep(86400)
                
                for domain, config in self.domains.items():
                    if not config.ssl_enabled:
                        continue
                    
                    if config.ssl_certificate and config.ssl_certificate.needs_renewal():
                        logger.info(f"证书需要续期: {domain}")
                        await self._renew_certificate(config)
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"证书续期任务出错: {e}")
    
    def generate_nginx_config(self, domain: str) -> Optional[str]:
        """生成 Nginx 配置"""
        config = self.domains.get(domain)
        if not config:
            return None
        
        # HTTP 配置
        http_config = f"""
server {{
    listen 80;
    server_name {domain};
    
    {"return 301 https://$server_name$request_uri;" if config.force_https else ""}
    
    {"#" if config.force_https else ""}location / {{
    {"#" if config.force_https else ""}    proxy_pass {config.backend_protocol}://{config.backend_host}:{config.backend_port};
    {"#" if config.force_https else ""}    proxy_set_header Host $host;
    {"#" if config.force_https else ""}    proxy_set_header X-Real-IP $remote_addr;
    {"#" if config.force_https else ""}    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    {"#" if config.force_https else ""}    proxy_set_header X-Forwarded-Proto $scheme;
    {"#" if config.force_https else ""}}}
}}
"""
        
        # HTTPS 配置
        https_config = ""
        if config.ssl_enabled and config.ssl_certificate:
            https_config = f"""
server {{
    listen 443 ssl http2;
    server_name {domain};
    
    ssl_certificate {config.ssl_certificate.cert_path};
    ssl_certificate_key {config.ssl_certificate.key_path};
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    
    {"add_header Strict-Transport-Security \"max-age=31536000; includeSubDomains\" always;" if config.hsts_enabled else ""}
    
    {"# 缓存配置" if config.caching_enabled else "# 缓存已禁用"}
    {"location ~* \\.(js|css|png|jpg|jpeg|gif|ico|svg)$ {" if config.caching_enabled else ""}
    {"    expires 1h;" if config.caching_enabled else ""}
    {"    add_header Cache-Control \"public, immutable\";" if config.caching_enabled else ""}
    {"}" if config.caching_enabled else ""}
    
    location / {{
        proxy_pass {config.backend_protocol}://{config.backend_host}:{config.backend_port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        {"# 限流配置" if config.rate_limiting_enabled else "# 限流已禁用"}
        {"limit_req zone=one burst=10 nodelay;" if config.rate_limiting_enabled else ""}
    }}
}}
"""
        
        return http_config + https_config
    
    async def save_nginx_config(self, domain: str, output_path: str = None) -> bool:
        """保存 Nginx 配置到文件"""
        config = self.domains.get(domain)
        if not config:
            return False
        
        nginx_config = self.generate_nginx_config(domain)
        if not nginx_config:
            return False
        
        if output_path is None:
            output_path = f"/etc/nginx/sites-available/{domain}"
        
        try:
            with open(output_path, 'w') as f:
                f.write(nginx_config)
            
            logger.info(f"Nginx 配置已保存: {output_path}")
            return True
        except Exception as e:
            logger.error(f"保存 Nginx 配置失败: {e}")
            return False
    
    async def check_domain_health(self, domain: str) -> Dict[str, Any]:
        """检查域名健康状态"""
        config = self.domains.get(domain)
        if not config:
            return {"error": "Domain not found"}
        
        result = {
            "domain": domain,
            "timestamp": datetime.now().isoformat(),
            "status": config.status.value,
            "checks": {}
        }
        
        # 检查 DNS 解析
        try:
            import socket
            ip = socket.gethostbyname(domain)
            result["checks"]["dns"] = {"status": "ok", "ip": ip}
        except Exception as e:
            result["checks"]["dns"] = {"status": "error", "error": str(e)}
        
        # 检查 HTTP 响应
        try:
            import urllib.request
            url = f"http://{domain}{config.health_check_path}"
            response = urllib.request.urlopen(url, timeout=10)
            result["checks"]["http"] = {
                "status": "ok",
                "code": response.getcode()
            }
        except Exception as e:
            result["checks"]["http"] = {"status": "error", "error": str(e)}
        
        # 检查 HTTPS（如果启用）
        if config.ssl_enabled:
            try:
                import urllib.request
                url = f"https://{domain}{config.health_check_path}"
                response = urllib.request.urlopen(url, timeout=10)
                result["checks"]["https"] = {
                    "status": "ok",
                    "code": response.getcode()
                }
            except Exception as e:
                result["checks"]["https"] = {"status": "error", "error": str(e)}
            
            # 检查证书状态
            if config.ssl_certificate:
                result["checks"]["certificate"] = {
                    "status": "ok" if not config.ssl_certificate.is_expired() else "expired",
                    "expires_at": config.ssl_certificate.expires_at.isoformat() if config.ssl_certificate.expires_at else None,
                    "days_until_expiry": config.ssl_certificate.days_until_expiry()
                }
        
        return result
    
    def get_all_domains(self) -> List[Dict[str, Any]]:
        """获取所有域名配置"""
        return [config.to_dict() for config in self.domains.values()]
    
    def get_config(self) -> Dict[str, Any]:
        """获取配置信息"""
        return {
            "letsencrypt": {
                "email": self.letsencrypt_email,
                "staging": self.letsencrypt_staging
            },
            "domains": self.get_all_domains(),
            "total_domains": len(self.domains),
            "ssl_enabled_domains": sum(1 for d in self.domains.values() if d.ssl_enabled)
        }


# 全局域名管理器实例
_domain_manager: Optional[DomainManager] = None


async def get_domain_manager() -> DomainManager:
    """获取域名管理器实例"""
    global _domain_manager
    if _domain_manager is None:
        _domain_manager = DomainManager()
    return _domain_manager
