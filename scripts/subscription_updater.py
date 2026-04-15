#!/usr/bin/env python3
"""
Clash订阅更新器
自动从订阅URL获取代理节点并更新clash配置
"""

import asyncio
import httpx
import yaml
import logging
import os
from urllib.parse import urlparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Set

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


class SubscriptionUpdater:
    def __init__(self, config_path: str = None):
        self.config_dir = Path(config_path or "/home/cool/.openclaw-trading/config")
        self.subscription_file = self.config_dir / "subscription.yaml"
        self.clash_config_file = self.config_dir / "clash_config.yaml"
        self.subscriptions: Dict[str, Any] = {}
        self.proxies: List[Dict] = []
        self.settings: Dict[str, Any] = {}
        
    async def load_subscription_config(self) -> bool:
        try:
            if not self.subscription_file.exists():
                logger.warning(f"订阅配置文件不存在: {self.subscription_file}")
                return False
                
            with open(self.subscription_file, 'r', encoding='utf-8') as f:
                self.subscriptions = yaml.safe_load(f) or {}
            self.settings = self.subscriptions.get('settings', {}) or {}
            
            logger.info(f"加载订阅配置: {len(self.subscriptions.get('subscriptions', []))} 个订阅")
            return True
        except Exception as e:
            logger.error(f"加载订阅配置失败: {e}")
            return False
    
    async def fetch_subscription(self, url: str, timeout: int = 30, use_system_proxy: bool = True) -> Optional[str]:
        try:
            if use_system_proxy:
                # Prefer HTTP(S)_PROXY for compatibility; some hosts export ALL_PROXY=socks5
                # but runtime may not have socks extras installed.
                old_all_proxy = os.environ.pop("ALL_PROXY", None)
                old_all_proxy_lc = os.environ.pop("all_proxy", None)
                try:
                    async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
                        response = await client.get(url)
                        response.raise_for_status()
                        return response.text
                finally:
                    if old_all_proxy is not None:
                        os.environ["ALL_PROXY"] = old_all_proxy
                    if old_all_proxy_lc is not None:
                        os.environ["all_proxy"] = old_all_proxy_lc

            proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']
            old_values: Dict[str, Optional[str]] = {}
            for var in proxy_vars:
                old_values[var] = os.environ.pop(var, None)
            try:
                async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    return response.text
            finally:
                for var, val in old_values.items():
                    if val is not None:
                        os.environ[var] = val
        except Exception as e:
            logger.error(f"获取订阅失败: {url} - {e}")
            return None
    
    def parse_clash_config(self, content: str) -> List[Dict]:
        try:
            config = yaml.safe_load(content)
            if config and 'proxies' in config:
                return config['proxies']
        except Exception as e:
            logger.error(f"解析Clash配置失败: {e}")
        return []
    
    async def update_subscriptions(self) -> int:
        total_proxies = 0
        timeout = int(self.settings.get('timeout', 30))
        fetch_via_proxy = bool(self.settings.get('fetch_via_system_proxy', True))
        
        for sub in self.subscriptions.get('subscriptions', []):
            if not sub.get('enabled', True):
                continue
                
            name = sub.get('name', 'Unknown')
            url = sub.get('url')
            
            if not url:
                continue
            
            logger.info(f"更新订阅: {name}")
            logger.info(f"URL: {self._mask_url(url)}")
            
            sub_timeout = int(sub.get('timeout', timeout))
            sub_use_proxy = bool(sub.get('fetch_via_system_proxy', fetch_via_proxy))
            content = await self.fetch_subscription(url, timeout=sub_timeout, use_system_proxy=sub_use_proxy)
            if content:
                proxies = self.parse_clash_config(content)
                if proxies:
                    logger.info(f"获取到 {len(proxies)} 个代理节点")
                    self.proxies.extend(proxies)
                    total_proxies += len(proxies)
                    sub['last_update'] = datetime.now().isoformat()
                else:
                    logger.warning(f"订阅 {name} 没有有效的代理节点")
        
        return total_proxies

    def _filter_and_deduplicate_proxies(self, proxies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not proxies:
            return []

        deduplicate = bool(self.settings.get("deduplicate_proxies", True))
        require_tls = bool(self.settings.get("require_tls", False))
        allowed_ports = self.settings.get("allowed_ports", [])
        allowed_types = self.settings.get("allowed_types", [])

        allowed_ports_set: Set[int] = set()
        for p in allowed_ports:
            try:
                allowed_ports_set.add(int(p))
            except Exception:
                continue
        allowed_types_set = {str(t).strip().lower() for t in allowed_types if str(t).strip()}

        result: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for proxy in proxies:
            p_type = str(proxy.get("type", "")).lower()
            p_port = proxy.get("port")
            p_server = str(proxy.get("server", "")).strip().lower()
            p_name = str(proxy.get("name", "")).strip()

            if require_tls and not bool(proxy.get("tls", False)):
                continue
            if allowed_ports_set:
                try:
                    if int(p_port) not in allowed_ports_set:
                        continue
                except Exception:
                    continue
            if allowed_types_set and p_type not in allowed_types_set:
                continue

            if deduplicate:
                dedup_key = f"{p_type}|{p_server}|{p_port}|{proxy.get('uuid','')}|{proxy.get('network','')}"
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

            if not p_name:
                proxy["name"] = f"{proxy.get('type','proxy')}-{p_server}:{p_port}"
            result.append(proxy)
        return result

    @staticmethod
    def _mask_url(url: str) -> str:
        try:
            p = urlparse(url or "")
            host = p.netloc or "unknown-host"
            return f"{p.scheme}://{host}/***"
        except Exception:
            return "***"
    
    def generate_clash_config(self) -> Dict[str, Any]:
        existing_config = {}
        
        if self.clash_config_file.exists():
            with open(self.clash_config_file, 'r', encoding='utf-8') as f:
                existing_config = yaml.safe_load(f) or {}
        
        optimized_proxies = self._filter_and_deduplicate_proxies(self.proxies)
        proxy_names = [p.get('name', f'proxy-{i}') for i, p in enumerate(optimized_proxies)]
        url_test_url = self.settings.get('url_test_url', 'http://www.gstatic.com/generate_204')
        url_test_interval = int(self.settings.get('url_test_interval', 300))
        
        config = {
            'mixed-port': existing_config.get('mixed-port', 7890),
            'allow-lan': existing_config.get('allow-lan', True),
            'mode': existing_config.get('mode', 'rule'),
            'log-level': existing_config.get('log-level', 'info'),
            'proxies': optimized_proxies,
            'proxy-groups': [
                {
                    'name': '🚀 节点选择',
                    'type': 'select',
                    'proxies': ['♻️ 自动选择'] + proxy_names + ['🎯 全球直连']
                },
                {
                    'name': '♻️ 自动选择',
                    'type': 'url-test',
                    'proxies': proxy_names,
                    'url': url_test_url,
                    'interval': url_test_interval
                },
                {
                    'name': '🎯 全球直连',
                    'type': 'select',
                    'proxies': ['DIRECT']
                },
                {
                    'name': '🛑 全球拦截',
                    'type': 'select',
                    'proxies': ['REJECT']
                }
            ],
            'rules': existing_config.get('rules', [
                'DOMAIN-SUFFIX,local,🎯 全球直连',
                'IP-CIDR,127.0.0.0/8,🎯 全球直连',
                'IP-CIDR,172.16.0.0/12,🎯 全球直连',
                'IP-CIDR,192.168.0.0/16,🎯 全球直连',
                'IP-CIDR,10.0.0.0/8,🎯 全球直连',
                'GEOIP,CN,🎯 全球直连',
                'MATCH,🚀 节点选择'
            ])
        }
        
        return config
    
    async def save_clash_config(self) -> bool:
        try:
            config = self.generate_clash_config()
            
            with open(self.clash_config_file, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
            
            logger.info(f"Clash配置已保存: {self.clash_config_file}")
            return True
        except Exception as e:
            logger.error(f"保存Clash配置失败: {e}")
            return False
    
    async def save_subscription_config(self) -> bool:
        try:
            with open(self.subscription_file, 'w', encoding='utf-8') as f:
                yaml.dump(self.subscriptions, f, allow_unicode=True, default_flow_style=False)
            return True
        except Exception as e:
            logger.error(f"保存订阅配置失败: {e}")
            return False
    
    async def run(self) -> bool:
        logger.info("=" * 50)
        logger.info("Clash订阅更新器启动")
        logger.info("=" * 50)
        
        if not await self.load_subscription_config():
            return False
        
        total = await self.update_subscriptions()
        
        if total > 0:
            await self.save_clash_config()
            await self.save_subscription_config()
            logger.info(f"✅ 更新完成，共 {total} 个代理节点")
            return True
        else:
            logger.warning("⚠️ 没有获取到任何代理节点")
            return False


async def main():
    updater = SubscriptionUpdater()
    await updater.run()


if __name__ == "__main__":
    asyncio.run(main())
