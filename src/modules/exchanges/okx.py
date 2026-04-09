"""
OKX交易所实现

基于ExchangeBase抽象类实现OKX API调用
"""

import asyncio
import base64
import hmac
import json
import logging
import os
import ssl
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from functools import wraps
from urllib.parse import urlencode

import aiohttp
import certifi

from .exchange_base import ExchangeBase, MarketData, OrderBook, Order, Balance, ExchangeInfo

logger = logging.getLogger(__name__)


def retry_on_error(max_retries=3, delay=1.0, backoff=2.0, allowed_exceptions=(Exception,)):
    """
    重试装饰器
    
    Args:
        max_retries: 最大重试次数
        delay: 初始延迟时间（秒）
        backoff: 延迟时间的增长因子
        allowed_exceptions: 允许重试的异常类型
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except allowed_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(f"⚠️ {func.__name__} 失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
                        logger.info(f"⏳ 等待 {current_delay:.1f} 秒后重试...")
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"❌ {func.__name__} 失败，已达到最大重试次数")
                        raise
            
            raise last_exception
        return wrapper
    return decorator


class OKXExchange(ExchangeBase):
    """OKX交易所实现"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_url = "https://www.okx.com" if not self.testnet else "https://www.okx.com"
        self.ws_url = "wss://ws.okx.com:8443" if not self.testnet else "wss://wspap.okx.com:8443"
        self._session = None
        self._ws_connections = {}
        req_concurrency = int(os.getenv("OPENCLAW_OKX_MAX_CONCURRENCY", "4") or "4")
        self._request_semaphore = asyncio.Semaphore(max(1, req_concurrency))  # 限制并发请求数
        self._last_request_time = 0
        self._min_request_interval = float(os.getenv("OPENCLAW_OKX_MIN_REQUEST_INTERVAL", "0.2") or "0.2")
        self._request_max_retries = int(os.getenv("OPENCLAW_OKX_MAX_RETRIES", "3") or "3")
        self._timeout_total = float(os.getenv("OPENCLAW_OKX_TIMEOUT_TOTAL", "30") or "30")
        self._timeout_connect = float(os.getenv("OPENCLAW_OKX_TIMEOUT_CONNECT", "10") or "10")
        self._timeout_sock_read = float(os.getenv("OPENCLAW_OKX_TIMEOUT_SOCK_READ", "20") or "20")
        self._base_min_request_interval = self._min_request_interval
        self._adaptive_min_request_interval = self._min_request_interval
        self._max_adaptive_interval = float(
            os.getenv("OPENCLAW_OKX_MAX_ADAPTIVE_INTERVAL", "1.2") or "1.2"
        )
        # 代理/直连自愈：代理不可用时自动降级为直连，避免实盘全链路失败
        self._proxy_mode: str = "unknown"  # unknown|direct|http|socks
        self._proxy_url: Optional[str] = None
        self._proxy_from_env: bool = False
        self._proxy_disabled_until: float = 0.0
        self._session_recreate_lock = asyncio.Lock()
        # 网络自愈：连续失败后主动重建会话/切换代理源
        self._network_consecutive_failures: int = 0
        self._network_failure_threshold: int = 5
        self._last_recover_ts: float = 0.0
        self._recover_cooldown_s: float = float(
            os.getenv("OPENCLAW_OKX_RECOVER_COOLDOWN", "60") or "60"
        )
        # instruments 缓存（公开接口），用于下单前的最小张数/步进预检
        self._instrument_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._instrument_cache_ttl_s: float = 300.0
        # Payload recorder: runtime channel-field matrix from live responses
        self._payload_recorder_enabled: bool = str(
            os.getenv("OPENCLAW_OKX_PAYLOAD_RECORDER", "1")
        ).strip().lower() not in ("0", "false", "no", "off")
        self._payload_sample_limit: int = max(
            1, int(os.getenv("OPENCLAW_OKX_PAYLOAD_SAMPLE_LIMIT", "30") or "30")
        )
        self._payload_flush_interval_s: float = float(
            os.getenv("OPENCLAW_OKX_PAYLOAD_FLUSH_INTERVAL", "120") or "120"
        )
        self._payload_output_dir: Path = Path(
            os.getenv("OPENCLAW_OKX_PAYLOAD_DIR", "logs/okx_payload_matrix")
        )
        self._payload_channel_fields: Dict[str, set] = defaultdict(set)
        self._payload_channel_samples: Dict[str, int] = defaultdict(int)
        self._payload_last_flush_ts: float = 0.0
        self._payload_expected_fields: Dict[str, List[str]] = {
            "books": ["instId", "bids", "asks", "ts"],
            "tickers": ["instId", "last", "bidPx", "askPx", "vol24h", "ts"],
            "funding-rate": ["instId", "fundingRate", "nextFundingTime"],
            "mark-price": ["instId", "markPx", "ts"],
            "positions": ["instId", "pos", "avgPx", "markPx", "upl", "liqPx", "lever"],
            "candles": ["0", "1", "2", "3", "4", "5"],
            "open-interest": ["instId", "oi", "ts"],
            "order": ["ordId", "instId", "side", "ordType", "state", "accFillSz"],
            "account-balance": ["details", "ccy", "eq", "availEq"],
        }

    def _build_ssl_context(self) -> ssl.SSLContext:
        """
        统一TLS上下文：
        - 使用 certifi/system CA，避免证书链不一致
        - 仅允许 TLS1.2+，提升兼容与安全性
        """
        ctx = ssl.create_default_context(cafile=certifi.where())
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        return ctx

    def _proxy_temporarily_disabled(self) -> bool:
        return time.time() < float(self._proxy_disabled_until or 0.0)

    async def _mark_request_success(self) -> None:
        self._network_consecutive_failures = 0
        self._adaptive_min_request_interval = max(
            self._base_min_request_interval,
            float(self._adaptive_min_request_interval) * 0.9,
        )

    async def _mark_request_failure(self, reason: str) -> None:
        self._network_consecutive_failures += 1
        self._adaptive_min_request_interval = min(
            self._max_adaptive_interval,
            max(self._base_min_request_interval, float(self._adaptive_min_request_interval) * 1.2),
        )
        if self._network_consecutive_failures >= self._network_failure_threshold:
            logger.warning(
                "⚠️ OKX网络连续失败达到阈值(%s)，触发自愈恢复: %s",
                self._network_consecutive_failures,
                reason,
            )
            await self._attempt_network_recovery(reason)

    async def _attempt_network_recovery(self, reason: str) -> None:
        now = time.time()
        if now - self._last_recover_ts < self._recover_cooldown_s:
            return
        self._last_recover_ts = now

        # 若代理来源于 ProxyManager，优先请求切换代理，再重建会话
        if not self._proxy_from_env:
            try:
                from src.modules.core.proxy_manager import get_proxy_manager

                proxy_manager = await get_proxy_manager()
                if getattr(proxy_manager, "_running", False):
                    switched = await proxy_manager.switch_proxy()
                    if switched:
                        proxy = await proxy_manager.get_proxy("www.okx.com")
                        if proxy:
                            self._proxy_url = proxy.url
                            self._proxy_mode = "socks" if proxy.proxy_type.value in ("socks5", "socks4") else "http"
                            logger.info("✅ OKX自愈已切换代理: %s", self._proxy_url)
            except Exception as e:
                logger.debug("OKX自愈切换代理失败，继续重建会话: %s", e)

        # 始终重建一次会话，清理潜在坏连接
        await self._rebuild_session(reason)
        self._network_consecutive_failures = 0

    async def _rebuild_session(self, reason: str) -> None:
        async with self._session_recreate_lock:
            old = self._session
            connector = aiohttp.TCPConnector(ssl=self._build_ssl_context())
            self._session = aiohttp.ClientSession(connector=connector, connector_owner=True)
            if old:
                try:
                    await old.close()
                except Exception:
                    pass
            logger.info("♻️ OKX会话已重建: %s", reason)

    async def _switch_to_direct_session(self, reason: str) -> None:
        """
        代理链路异常时切换为直连会话。
        说明：不要求用户改配置；只在运行时降级，尽量保证 OKX API 可达。
        """
        async with self._session_recreate_lock:
            # 双重检查，避免重复重建
            if self._proxy_mode == "direct":
                return
            logger.warning("⚠️ OKX代理链路异常，切换为直连: %s (mode=%s url=%s)", reason, self._proxy_mode, self._proxy_url)
            self._proxy_disabled_until = time.time() + 300  # 5 分钟内不再尝试代理
            self._proxy_mode = "direct"
            self._proxy_url = None

            try:
                ssl_context = self._build_ssl_context()
                connector = aiohttp.TCPConnector(ssl=ssl_context)
                new_session = aiohttp.ClientSession(connector=connector, connector_owner=True)
            except Exception as e:
                logger.error("直连会话重建失败: %s", e)
                return

            old = self._session
            self._session = new_session
            if old:
                try:
                    await old.close()
                except Exception:
                    pass
    
    def _generate_signature(self, timestamp: str, method: str, endpoint: str, body: str = "") -> str:
        """生成OKX API签名"""
        message = timestamp + method.upper() + endpoint + body
        mac = hmac.new(self.api_secret.encode('utf-8'), message.encode('utf-8'), digestmod='sha256')
        return base64.b64encode(mac.digest()).decode('utf-8')
    
    def _get_headers(self, method: str, endpoint: str, body: str = "") -> Dict[str, str]:
        """获取请求头"""
        # 使用 UTC 时间戳（ISO 8601 格式）
        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        signature = self._generate_signature(timestamp, method, endpoint, body)
        
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.api_passphrase or "",
            "Content-Type": "application/json"
        }
        return headers

    def _build_request_path(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> str:
        """
        OKX 签名的 requestPath 对 GET 需要包含 query string。
        这里使用排序后的 urlencode，确保签名稳定一致。
        """
        if not params:
            return endpoint
        items: List[Tuple[str, str]] = []
        for k in sorted(params.keys()):
            v = params.get(k)
            if v is None:
                continue
            items.append((str(k), str(v)))
        if not items:
            return endpoint
        return endpoint + "?" + urlencode(items)

    def _infer_channel_from_endpoint(self, endpoint: str) -> str:
        ep = str(endpoint or "")
        if "market/books" in ep:
            return "books"
        if "market/ticker" in ep:
            return "tickers"
        if "public/funding-rate" in ep:
            return "funding-rate"
        if "public/mark-price" in ep:
            return "mark-price"
        if "account/positions" in ep:
            return "positions"
        if "market/candles" in ep:
            return "candles"
        if "public/open-interest" in ep:
            return "open-interest"
        if "trade/order" in ep:
            return "order"
        if "account/balance" in ep:
            return "account-balance"
        return "unknown"

    def _flatten_fields(self, payload: Any, prefix: str = "") -> set:
        fields: set = set()
        if isinstance(payload, dict):
            for k, v in payload.items():
                key = f"{prefix}.{k}" if prefix else str(k)
                fields.add(key)
                fields.update(self._flatten_fields(v, key))
        elif isinstance(payload, list):
            for idx, item in enumerate(payload[:3]):
                key = f"{prefix}[{idx}]" if prefix else str(idx)
                fields.add(key)
                fields.update(self._flatten_fields(item, key))
        return fields

    async def _record_payload_sample(self, endpoint: str, data: Any) -> None:
        if not self._payload_recorder_enabled:
            return
        channel = self._infer_channel_from_endpoint(endpoint)
        if self._payload_channel_samples[channel] >= self._payload_sample_limit:
            return
        fields = self._flatten_fields(data)
        if not fields:
            return
        self._payload_channel_fields[channel].update(fields)
        self._payload_channel_samples[channel] += 1
        await self._flush_payload_matrix(force=False)

    def _build_payload_matrix_markdown(self) -> str:
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        lines = [
            "# OKX Payload Field Matrix",
            "",
            f"- generated_at: {now}",
            f"- sample_limit_per_channel: {self._payload_sample_limit}",
            "",
            "## Channels",
            "",
            "| channel | samples | observed_fields | missing_expected |",
            "|---|---:|---:|---:|",
        ]
        for channel in sorted(self._payload_channel_fields.keys()):
            observed = self._payload_channel_fields.get(channel, set())
            expected = self._payload_expected_fields.get(channel, [])
            missing = [
                e for e in expected if not any(f == e or f.endswith(f".{e}") for f in observed)
            ]
            lines.append(
                f"| {channel} | {self._payload_channel_samples.get(channel, 0)} | "
                f"{len(observed)} | {len(missing)} |"
            )
        lines.extend(["", "## Detailed Fields", ""])
        for channel in sorted(self._payload_channel_fields.keys()):
            lines.append(f"### {channel}")
            expected = self._payload_expected_fields.get(channel, [])
            observed = sorted(self._payload_channel_fields.get(channel, set()))
            missing = [
                e for e in expected if not any(f == e or f.endswith(f".{e}") for f in observed)
            ]
            lines.append(f"- missing_expected: {', '.join(missing) if missing else 'none'}")
            lines.append("- observed_fields:")
            for field in observed[:300]:
                lines.append(f"  - {field}")
            if len(observed) > 300:
                lines.append(f"  - ... ({len(observed) - 300} more)")
            lines.append("")
        return "\n".join(lines) + "\n"

    def _log_missing_fields_warnings(self) -> None:
        for channel, expected in self._payload_expected_fields.items():
            observed = self._payload_channel_fields.get(channel, set())
            if not observed:
                continue
            missing = [
                e for e in expected if not any(f == e or f.endswith(f".{e}") for f in observed)
            ]
            if missing:
                logger.warning(
                    "OKX payload字段缺口: channel=%s missing=%s",
                    channel,
                    ",".join(missing),
                )

    async def _flush_payload_matrix(self, force: bool = False) -> None:
        if not self._payload_recorder_enabled:
            return
        now = time.time()
        if not force and (now - self._payload_last_flush_ts) < self._payload_flush_interval_s:
            return
        self._payload_last_flush_ts = now
        try:
            self._payload_output_dir.mkdir(parents=True, exist_ok=True)
            md_path = self._payload_output_dir / "okx_payload_field_matrix.md"
            json_path = self._payload_output_dir / "okx_payload_field_matrix.json"
            md_path.write_text(self._build_payload_matrix_markdown(), encoding="utf-8")
            payload = {
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "sample_limit_per_channel": self._payload_sample_limit,
                "channels": {
                    ch: {
                        "samples": int(self._payload_channel_samples.get(ch, 0)),
                        "observed_fields": sorted(list(self._payload_channel_fields.get(ch, set()))),
                        "expected_fields": self._payload_expected_fields.get(ch, []),
                    }
                    for ch in sorted(self._payload_channel_fields.keys())
                },
            }
            json_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._log_missing_fields_warnings()
        except Exception as e:
            logger.debug("OKX payload matrix flush failed: %s", e)

    def _to_okx_inst_id(self, symbol: str, default_type: str = "SPOT") -> str:
        """
        将系统内 symbol 统一转换为 OKX instId。
        - BTC/USDT/SWAP -> BTC-USDT-SWAP
        - BTC/USDT      -> BTC-USDT （默认 SPOT）
        """
        s = str(symbol or "").strip()
        s_up = s.upper()
        # 已经是 OKX instId（例如 BTC-USDT-SWAP / BTC-USDT）则直接返回
        if "-" in s and "/" not in s:
            return s
        if "/SWAP" in s_up or s_up.endswith("SWAP"):
            okx_symbol = s.replace("/SWAP", "").replace("/swap", "").replace("/", "-")
            if not okx_symbol.upper().endswith("-SWAP"):
                okx_symbol = okx_symbol + "-SWAP"
            return okx_symbol
        okx_symbol = s.replace("/", "-")
        if default_type.upper() == "SWAP" and not okx_symbol.upper().endswith("-SWAP"):
            okx_symbol = okx_symbol + "-SWAP"
        return okx_symbol

    def _build_request_profile(self, method: str, endpoint: str) -> Dict[str, float]:
        """
        分级请求策略：
        - critical_exec: 下单/平仓/账户关键同步，优先成功率
        - account_sync: 账户/持仓同步，平衡成功率与时延
        - market_fast: 实时行情，控制抖动扩散
        - analytics_bg: 背景分析类，优先降压
        """
        ep = str(endpoint or "")
        m = str(method or "").upper()

        profile = {
            "name": "default",
            "max_retries": float(self._request_max_retries),
            "timeout_total": float(self._timeout_total),
            "timeout_connect": float(self._timeout_connect),
            "timeout_sock_read": float(self._timeout_sock_read),
            "retry_delay": 1.0,
            "retry_backoff": 1.6,
            "interval_multiplier": 1.0,
        }

        if ep.startswith("/api/v5/trade/") or ep in (
            "/api/v5/account/positions",
            "/api/v5/account/balance",
            "/api/v5/account/config",
            "/api/v5/account/set-leverage",
        ):
            profile.update(
                {
                    "name": "critical_exec",
                    "max_retries": float(max(self._request_max_retries + 1, 4)),
                    "timeout_total": min(float(self._timeout_total), 22.0),
                    "timeout_connect": min(float(self._timeout_connect), 7.0),
                    "timeout_sock_read": min(float(self._timeout_sock_read), 12.0),
                    "retry_delay": 0.8,
                    "retry_backoff": 1.5,
                    "interval_multiplier": 1.0,
                }
            )
        elif ep.startswith("/api/v5/market/") and m == "GET":
            profile.update(
                {
                    "name": "market_fast",
                    "max_retries": float(max(1, self._request_max_retries - 1)),
                    "timeout_total": min(float(self._timeout_total), 12.0),
                    "timeout_connect": min(float(self._timeout_connect), 4.5),
                    "timeout_sock_read": min(float(self._timeout_sock_read), 7.0),
                    "retry_delay": 0.6,
                    "retry_backoff": 1.45,
                    "interval_multiplier": 1.25,
                }
            )
        elif ep.startswith("/api/v5/public/") and m == "GET":
            profile.update(
                {
                    "name": "analytics_bg",
                    "max_retries": float(max(1, self._request_max_retries - 1)),
                    "timeout_total": min(float(self._timeout_total), 10.0),
                    "timeout_connect": min(float(self._timeout_connect), 4.0),
                    "timeout_sock_read": min(float(self._timeout_sock_read), 6.0),
                    "retry_delay": 0.5,
                    "retry_backoff": 1.35,
                    "interval_multiplier": 1.5,
                }
            )
        return profile
    
    async def _make_request(self, method: str, endpoint: str, params: Dict[str, Any] = None, body: Dict[str, Any] = None) -> Any:
        """发送请求到OKX API - 带重试和限流机制"""
        async with self._request_semaphore:
            profile = self._build_request_profile(method, endpoint)
            current_time = time.time()
            time_since_last = current_time - self._last_request_time
            effective_interval = max(
                self._min_request_interval,
                self._adaptive_min_request_interval,
            ) * float(profile.get("interval_multiplier", 1.0) or 1.0)
            if time_since_last < effective_interval:
                await asyncio.sleep(effective_interval - time_since_last)
            
            self._last_request_time = time.time()
            
            url = self.api_url + endpoint
            body_str = json.dumps(body, separators=(',', ':')) if body else ""

            request_path = self._build_request_path(endpoint, params if str(method).upper() == "GET" else None)
            headers = self._get_headers(method, request_path, body_str)
            request_params = params
            if str(method).upper() == "GET" and request_path != endpoint:
                # Ensure signature query and actual query are byte-consistent.
                # Using full URL with request_path avoids potential params re-encoding mismatch.
                url = self.api_url + request_path
                request_params = None
            
            logger.debug(f"📤 OKX请求: {method} {endpoint}")
            logger.debug(f"📤 Body: {body_str}")
            logger.debug(f"📤 Headers: OK-ACCESS-KEY={headers.get('OK-ACCESS-KEY')[:8]}..., TIMESTAMP={headers.get('OK-ACCESS-TIMESTAMP')}")
            
            max_retries = int(profile.get("max_retries", self._request_max_retries) or self._request_max_retries)
            retry_delay = float(profile.get("retry_delay", 1.0) or 1.0)
            retry_backoff = float(profile.get("retry_backoff", 1.6) or 1.6)
            
            proxy = getattr(self, '_proxy_url', None)
            if proxy and not self._proxy_temporarily_disabled():
                logger.debug(f"📤 使用代理: {proxy}")
            else:
                proxy = None
            
            for attempt in range(max_retries + 1):
                try:
                    timeout = aiohttp.ClientTimeout(
                        total=float(profile.get("timeout_total", self._timeout_total) or self._timeout_total),
                        connect=float(profile.get("timeout_connect", self._timeout_connect) or self._timeout_connect),
                        sock_read=float(profile.get("timeout_sock_read", self._timeout_sock_read) or self._timeout_sock_read),
                    )
                    
                    if method == "GET":
                        async with self._session.get(url, headers=headers, params=request_params, timeout=timeout, proxy=proxy) as response:
                            if response.status == 429:  # Rate limit
                                logger.warning(f"⚠️ OKX API 限流，等待 {retry_delay} 秒后重试...")
                                await asyncio.sleep(retry_delay)
                                retry_delay *= retry_backoff
                                continue
                            
                            data = await response.json()
                            if data.get("code") == "0":
                                await self._record_payload_sample(endpoint, data.get("data", []))
                                await self._mark_request_success()
                                return data.get("data", [])
                            else:
                                error_code = data.get('code', '')
                                error_msg = data.get('msg', '') or error_code or 'unknown'
                                if error_code == "51001":
                                    logger.debug(f"OKX API交易对不存在: {method} {endpoint} - {error_msg}")
                                else:
                                    logger.error(f"OKX API返回错误: {method} {endpoint} - code={error_code}, msg={error_msg}")
                                raise Exception(f"OKX API错误: {error_msg}")
                                
                    elif method == "POST":
                        async with self._session.post(url, headers=headers, data=body_str, timeout=timeout, proxy=proxy) as response:
                            if response.status == 429:  # Rate limit
                                logger.warning(f"⚠️ OKX API 限流，等待 {retry_delay} 秒后重试...")
                                await asyncio.sleep(retry_delay)
                                retry_delay *= retry_backoff
                                continue
                            
                            data = await response.json()
                            logger.debug(f"📥 OKX响应: {data}")
                            if data.get("code") == "0":
                                await self._record_payload_sample(endpoint, data.get("data", []))
                                await self._mark_request_success()
                                return data.get("data", [])
                            else:
                                error_msg = data.get('msg', '') or data.get('code', 'unknown')
                                logger.error(f"OKX API返回错误: {method} {endpoint} - code={data.get('code')}, msg={data.get('msg')}")
                                raise Exception(f"OKX API错误: {error_msg}")
                                
                    elif method == "DELETE":
                        async with self._session.delete(url, headers=headers, json=body, timeout=timeout, proxy=proxy) as response:
                            if response.status == 429:  # Rate limit
                                logger.warning(f"⚠️ OKX API 限流，等待 {retry_delay} 秒后重试...")
                                await asyncio.sleep(retry_delay)
                                retry_delay *= retry_backoff
                                continue
                            
                            data = await response.json()
                            if data.get("code") == "0":
                                await self._record_payload_sample(endpoint, data.get("data", []))
                                await self._mark_request_success()
                                return data.get("data", [])
                            else:
                                error_code = data.get('code', '')
                                error_msg = data.get('msg', '') or error_code or 'unknown'
                                if error_code == "51001":
                                    logger.debug(f"OKX API交易对不存在: {method} {endpoint}")
                                else:
                                    logger.error(f"OKX API返回错误: {method} {endpoint} - code={error_code}, msg={error_msg}")
                                raise Exception(f"OKX API错误: {error_msg}")
                                
                except asyncio.TimeoutError as e:
                    await self._mark_request_failure(f"timeout {method} {endpoint}")
                    if attempt < max_retries:
                        logger.warning(f"⚠️ OKX API 超时 (尝试 {attempt + 1}/{max_retries + 1}): {method} {endpoint}")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= max(1.2, retry_backoff - 0.2)
                        continue
                    else:
                        logger.error(f"❌ OKX API 超时，已达到最大重试次数: {method} {endpoint}")
                        raise
                        
                except aiohttp.ClientConnectorError as e:
                    await self._mark_request_failure(f"connector {method} {endpoint}: {e}")
                    if attempt < max_retries:
                        logger.warning(f"⚠️ OKX API 连接失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= retry_backoff
                        continue
                    else:
                        logger.error(f"❌ OKX API 连接失败，已达到最大重试次数: {e}")
                        raise
                        
                except aiohttp.ClientError as e:
                    await self._mark_request_failure(f"client {method} {endpoint}: {e}")
                    # 代理/网络链路错误：若当前在用代理，自动降级直连并重试
                    err_s = str(e)
                    proxy_related = any(
                        k in err_s.lower()
                        for k in (
                            "proxy",
                            "all operations failed",
                            "cannot connect to host",
                            "connection refused",
                            "connection reset",
                            "connect call failed",
                        )
                    )
                    if proxy_related and (getattr(self, "_proxy_mode", "") in ("http", "socks") or getattr(self, "_proxy_url", None)):
                        if attempt < max_retries:
                            await self._switch_to_direct_session(f"{type(e).__name__}: {err_s}")
                            proxy = None
                            await asyncio.sleep(min(1.0, retry_delay))
                            continue
                    if attempt < max_retries and "SSL" in err_s:
                        logger.warning(f"⚠️ OKX API SSL错误 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= retry_backoff
                        continue
                    else:
                        logger.error(f"OKX API网络错误: {method} {endpoint} - {type(e).__name__}: {e}")
                        raise
                        
                except Exception as e:
                    await self._mark_request_failure(f"unknown {method} {endpoint}: {e}")
                    error_str = str(e)
                    # 代理链路导致的“全失败”常见报错，自动降级直连再试
                    if "All operations failed" in error_str and (getattr(self, "_proxy_mode", "") in ("http", "socks") or getattr(self, "_proxy_url", None)):
                        if attempt < max_retries:
                            await self._switch_to_direct_session(error_str)
                            proxy = None
                            await asyncio.sleep(min(1.0, retry_delay))
                            continue
                    if "51001" in error_str or "doesn't exist" in error_str:
                        logger.debug(f"OKX API交易对不存在: {method} {endpoint}")
                    else:
                        logger.error(f"OKX API请求失败: {method} {endpoint} - {type(e).__name__}: {e}")
                    raise
    
    async def initialize(self) -> bool:
        """初始化交易所连接"""
        try:
            connector = None
            ssl_context = None
            
            try:
                # 优先使用容器环境变量代理，保证与部署配置一致
                env_proxy = (
                    os.getenv("OPENCLAW_HTTPS_PROXY")
                    or os.getenv("OPENCLAW_HTTP_PROXY")
                    or os.getenv("HTTPS_PROXY")
                    or os.getenv("HTTP_PROXY")
                )
                if env_proxy:
                    ssl_context = self._build_ssl_context()
                    connector = aiohttp.TCPConnector(ssl=ssl_context)
                    self._proxy_url = env_proxy
                    self._proxy_mode = "http"
                    self._proxy_from_env = True
                    logger.info(f"✅ OKX使用环境代理: {env_proxy}")
                else:
                    logger.info("ℹ️ 未检测到环境代理，尝试通过proxy_manager获取")

                    from src.modules.core.proxy_manager import get_proxy_manager
                    proxy_manager = await get_proxy_manager()
                
                    if not proxy_manager._running:
                        if hasattr(self, '_config_manager') and self._config_manager:
                            config_manager = self._config_manager
                        else:
                            from src.modules.core.config_manager import get_config_manager
                            config_manager = await get_config_manager()
                        
                        proxy_config = await config_manager.get_config("proxy", {})
                        logger.info(f"📋 加载代理配置: {proxy_config}")
                        await proxy_manager.initialize(proxy_config)
                    else:
                        logger.info(f"📋 proxy_manager已初始化, global_proxy={proxy_manager.global_proxy}, use_global_proxy={proxy_manager.use_global_proxy}")
                    
                    proxy = await proxy_manager.get_proxy("www.okx.com")
                    
                    if proxy:
                        logger.info(f"✅ 使用代理: {proxy.url}")
                        if proxy.proxy_type.value in ["socks5", "socks4"]:
                            from aiohttp_socks import ProxyConnector
                            connector = ProxyConnector.from_url(proxy.url, ssl=self._build_ssl_context())
                            self._proxy_mode = "socks"
                            self._proxy_url = proxy.url
                            self._proxy_from_env = False
                        else:
                            ssl_context = self._build_ssl_context()
                            connector = aiohttp.TCPConnector(ssl=ssl_context)
                            self._proxy_url = proxy.url
                            self._proxy_mode = "http"
                            self._proxy_from_env = False
                    else:
                        logger.warning("⚠️ 未找到可用代理，使用直连")
                        ssl_context = self._build_ssl_context()
                        connector = aiohttp.TCPConnector(ssl=ssl_context)
                        self._proxy_mode = "direct"
                        self._proxy_from_env = False
            except Exception as proxy_error:
                logger.warning(f"⚠️ 加载代理配置失败: {proxy_error}，使用直连")
                import traceback
                traceback.print_exc()
                ssl_context = self._build_ssl_context()
                connector = aiohttp.TCPConnector(ssl=ssl_context)
                self._proxy_mode = "direct"
                self._proxy_from_env = False
            
            self._session = aiohttp.ClientSession(connector=connector, connector_owner=True)
            await self.get_exchange_info()
            self._running = True
            if self._payload_recorder_enabled:
                logger.info(
                    "OKX payload recorder enabled: dir=%s, sample_limit=%s",
                    str(self._payload_output_dir),
                    self._payload_sample_limit,
                )
            logger.info(f"OKX交易所初始化成功")
            return True
        except Exception as e:
            logger.error(f"OKX交易所初始化失败: {e}")
            return False
    
    async def cleanup(self) -> None:
        """清理资源"""
        try:
            await self._flush_payload_matrix(force=True)
            if self._session:
                await self._session.close()
            # 关闭所有WebSocket连接
            for conn in self._ws_connections.values():
                if not conn.closed:
                    await conn.close()
            self._running = False
            logger.info(f"OKX交易所清理完成")
        except Exception as e:
            logger.error(f"OKX交易所清理失败: {e}")
    
    async def get_market_data(self, symbol: str, interval: str = "1m") -> MarketData:
        """获取市场数据"""
        interval_map = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "1h": "1H",
            "4h": "4H",
            "1d": "1D"
        }
        okx_interval = interval_map.get(interval, "1m")
        
        endpoint = "/api/v5/market/candles"
        
        if "/SWAP" in symbol or symbol.endswith("SWAP"):
            okx_symbol = symbol.replace("/SWAP", "").replace("/", "-")
            if not okx_symbol.endswith("-SWAP"):
                okx_symbol = okx_symbol + "-SWAP"
        else:
            okx_symbol = symbol.replace("/", "-") + "-SWAP"
        
        params = {
            "instId": okx_symbol,
            "bar": okx_interval,
            "limit": 1
        }
        
        try:
            data = await self._make_request("GET", endpoint, params)
            if data and len(data) > 0:
                candle = data[0]
                return MarketData(
                    symbol=symbol,
                    timestamp=datetime.fromtimestamp(int(candle[0]) / 1000),
                    open=float(candle[1]),
                    high=float(candle[2]),
                    low=float(candle[3]),
                    close=float(candle[4]),
                    volume=float(candle[5]),
                    quote_volume=float(candle[7])
                )
        except Exception as e:
            logger.debug(f"获取OKX市场数据失败: {symbol} -> {okx_symbol}: {e}")
        return None
    
    async def get_klines(self, symbol: str, interval: str = "1h", limit: int = 100) -> List[Dict[str, any]]:
        """
        获取K线数据
        
        Args:
            symbol: 交易对，如 BTC/USDT
            interval: 时间周期，支持 1m, 5m, 15m, 1h, 4h, 1d
            limit: 返回数量，最大300
            
        Returns:
            K线数据列表
        """
        # OKX的时间间隔格式转换
        interval_map = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "1h": "1H",
            "4h": "4H",
            "1d": "1D"
        }
        okx_interval = interval_map.get(interval, "1H")
        
        endpoint = "/api/v5/market/candles"
        
        if "/SWAP" in symbol or symbol.endswith("SWAP"):
            okx_symbol = symbol.replace("/SWAP", "").replace("/", "-")
            if not okx_symbol.endswith("-SWAP"):
                okx_symbol = okx_symbol + "-SWAP"
        else:
            okx_symbol = symbol.replace("/", "-") + "-SWAP"
        
        params = {
            "instId": okx_symbol,
            "bar": okx_interval,
            "limit": min(limit, 300)
        }
        
        try:
            data = await self._make_request("GET", endpoint, params)
            if data:
                klines = []
                for candle in data:
                    klines.append({
                        "timestamp": int(candle[0]),
                        "open": float(candle[1]),
                        "high": float(candle[2]),
                        "low": float(candle[3]),
                        "close": float(candle[4]),
                        "volume": float(candle[5]),
                        "quote_volume": float(candle[7])
                    })
                return klines
        except Exception as e:
            logger.debug(f"获取OKX K线数据失败: {symbol} -> {okx_symbol}: {e}")
        return []
    
    async def get_multi_timeframe_klines(self, symbol: str, timeframes: List[str] = None) -> Dict[str, List[Dict]]:
        """
        获取多时间周期K线数据
        
        Args:
            symbol: 交易对
            timeframes: 时间周期列表，默认 ["1m", "5m", "15m", "1h", "4h", "1d"]
            
        Returns:
            字典，key为时间周期，value为K线数据列表
        """
        if timeframes is None:
            timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]
        
        result = {}
        
        for tf in timeframes:
            try:
                klines = await self.get_klines(symbol, tf, limit=100)
                if klines:
                    result[tf] = klines
                    logger.info(f"获取 {symbol} {tf} K线数据成功，共 {len(klines)} 条")
            except Exception as e:
                logger.error(f"获取 {symbol} {tf} K线数据失败: {e}")
                result[tf] = []
        
        return result
    
    async def get_order_book(self, symbol: str, depth: int = 10) -> OrderBook:
        """获取订单簿"""
        endpoint = "/api/v5/market/books"

        # 行情订单簿：若 symbol 未明确 SWAP，则按现货 instId 请求，避免 “Instrument ID does not exist” 噪音。
        okx_symbol = self._to_okx_inst_id(symbol, default_type="SPOT")
        
        params = {
            "instId": okx_symbol,
            "sz": depth
        }
        
        try:
            data = await self._make_request("GET", endpoint, params)
            if data and len(data) > 0:
                order_book = data[0]
                asks = [(float(price), float(quantity)) for price, quantity, _, _ in order_book.get("asks", [])]
                bids = [(float(price), float(quantity)) for price, quantity, _, _ in order_book.get("bids", [])]
                return OrderBook(
                    symbol=symbol,
                    timestamp=datetime.fromtimestamp(int(order_book["ts"]) / 1000),
                    asks=asks,
                    bids=bids
                )
        except Exception as e:
            logger.debug(f"获取OKX订单簿失败: {symbol} -> {okx_symbol}: {e}")
        return None
    
    async def place_order(self, order: Order) -> Dict[str, Any]:
        """下单
        
        支持永续合约交易：
        - symbol格式: BTC/USDT/SWAP 或 BTC/USDT
        - 自动转换为OKX格式: BTC-USDT-SWAP
        """
        endpoint = "/api/v5/trade/order"
        
        # 交易对格式转换
        symbol = order.symbol
        if "/SWAP" in symbol or symbol.endswith("SWAP"):
            okx_symbol = symbol.replace("/SWAP", "").replace("/", "-")
            if not okx_symbol.endswith("-SWAP"):
                okx_symbol = okx_symbol + "-SWAP"
        else:
            # 默认使用永续合约
            okx_symbol = symbol.replace("/", "-") + "-SWAP"
        
        # 判断是开仓还是平仓
        is_close = hasattr(order, 'metadata') and order.metadata and order.metadata.get('is_close', False)
        
        # OKX的订单方向转换
        # 对于永续合约：
        # - 开多: side=buy, posSide=long
        # - 开空: side=sell, posSide=short
        # - 平多: side=sell, posSide=long
        # - 平空: side=buy, posSide=short
        side_map = {"buy": "buy", "sell": "sell"}
        ord_type_map = {"market": "market", "limit": "limit"}
        
        body = {
            "instId": okx_symbol,
            "tdMode": "cross",  # 全仓模式
            "side": side_map.get(order.side, "buy"),
            "ordType": ord_type_map.get(order.order_type, "market"),
            "sz": str(order.quantity)
        }
        
        # 永续合约需要指定posSide
        if "-SWAP" in okx_symbol:
            if hasattr(order, 'metadata') and order.metadata:
                pos_side = order.metadata.get('posSide', 'net')
                if pos_side in ['long', 'short']:
                    body["posSide"] = pos_side
            elif is_close:
                # 平仓时根据side推断posSide
                if order.side == "buy":
                    body["posSide"] = "short"  # 平空
                else:
                    body["posSide"] = "long"   # 平多
        
        if order.order_type == "limit" and order.price:
            body["px"] = str(order.price)
        
        if order.client_order_id:
            body["clOrdId"] = order.client_order_id
        
        logger.info(f"📤 OKX下单请求: {body}")
        
        try:
            data = await self._make_request("POST", endpoint, body=body)
            if data and len(data) > 0:
                result = data[0]
                return {
                    "order_id": result.get("ordId"),
                    "client_order_id": result.get("clOrdId"),
                    "status": "success",
                    "result": result
                }
        except Exception as e:
            logger.error(f"OKX下单失败: {e}")
            return {"status": "error", "message": str(e)}
    
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """取消订单"""
        endpoint = "/api/v5/trade/cancel-order"
        okx_symbol = symbol.replace("/", "-")
        
        body = {
            "instId": okx_symbol,
            "ordId": order_id
        }
        
        try:
            await self._make_request("POST", endpoint, body=body)
            return True
        except Exception as e:
            logger.error(f"OKX取消订单失败: {e}")
            return False
    
    async def get_order(self, order_id: str, symbol: str) -> Order:
        """获取订单信息"""
        endpoint = "/api/v5/trade/order"
        okx_symbol = symbol.replace("/", "-")
        
        params = {
            "instId": okx_symbol,
            "ordId": order_id
        }
        
        try:
            data = await self._make_request("GET", endpoint, params)
            if data and len(data) > 0:
                order_data = data[0]
                
                # 状态映射
                status_map = {
                    "live": "open",
                    "partially_filled": "partial",
                    "filled": "closed",
                    "cancelled": "cancelled"
                }
                
                return Order(
                    order_id=order_data["ordId"],
                    symbol=symbol,
                    side=order_data["side"],
                    order_type=order_data["ordType"],
                    quantity=float(order_data["sz"]),
                    price=float(order_data["px"]) if order_data.get("px") else None,
                    status=status_map.get(order_data["state"], "unknown"),
                    executed_quantity=float(order_data["accFillSz"]),
                    avg_price=float(order_data["avgPx"]) if order_data.get("avgPx") else 0.0,
                    timestamp=datetime.fromtimestamp(int(order_data["cTime"]) / 1000),
                    client_order_id=order_data.get("clOrdId")
                )
        except Exception as e:
            logger.error(f"获取OKX订单信息失败: {e}")
        return None
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """获取未成交订单"""
        endpoint = "/api/v5/trade/orders-pending"
        
        params = {"instType": "SPOT"}
        if symbol:
            params["instId"] = self._to_okx_inst_id(symbol, default_type="SPOT")
        
        try:
            data = await self._make_request("GET", endpoint, params)
            orders = []
            
            for order_data in data:
                status_map = {
                    "live": "open",
                    "partially_filled": "partial",
                    "filled": "closed",
                    "cancelled": "cancelled"
                }
                
                orders.append(Order(
                    order_id=order_data["ordId"],
                    symbol=order_data["instId"].replace("-", "/"),
                    side=order_data["side"],
                    order_type=order_data["ordType"],
                    quantity=float(order_data["sz"]),
                    price=float(order_data["px"]) if order_data.get("px") else None,
                    status=status_map.get(order_data["state"], "unknown"),
                    executed_quantity=float(order_data["accFillSz"]),
                    avg_price=float(order_data["avgPx"]) if order_data.get("avgPx") else 0.0,
                    timestamp=datetime.fromtimestamp(int(order_data["cTime"]) / 1000),
                    client_order_id=order_data.get("clOrdId")
                ))
            
            return orders
        except Exception as e:
            logger.error(f"获取OKX未成交订单失败: {e}")
            return []

    async def get_open_orders_strict(self, symbol: Optional[str] = None) -> List[Order]:
        """
        严格模式获取未成交订单：
        - 与 get_open_orders 相同语义
        - 任何上游业务错误/签名错误都会抛出异常，便于健康度统计与诊断
        """
        endpoint = "/api/v5/trade/orders-pending"
        params = {"instType": "SPOT"}
        if symbol:
            params["instId"] = self._to_okx_inst_id(symbol, default_type="SPOT")
        data = await self._make_request("GET", endpoint, params)
        orders: List[Order] = []
        for order_data in data or []:
            status_map = {
                "live": "open",
                "partially_filled": "partial",
                "filled": "closed",
                "cancelled": "cancelled",
            }
            orders.append(
                Order(
                    order_id=order_data["ordId"],
                    symbol=order_data["instId"].replace("-", "/"),
                    side=order_data["side"],
                    order_type=order_data["ordType"],
                    quantity=float(order_data["sz"]),
                    price=float(order_data["px"]) if order_data.get("px") else None,
                    status=status_map.get(order_data["state"], "unknown"),
                    executed_quantity=float(order_data["accFillSz"]),
                    avg_price=float(order_data["avgPx"]) if order_data.get("avgPx") else 0.0,
                    timestamp=datetime.fromtimestamp(int(order_data["cTime"]) / 1000),
                    client_order_id=order_data.get("clOrdId"),
                )
            )
        return orders
    
    async def get_balances(self) -> List[Balance]:
        """获取资产余额"""
        endpoint = "/api/v5/account/balance"
        
        try:
            data = await self._make_request("GET", endpoint)
            balances = []
            
            if data and len(data) > 0:
                for balance_data in data[0].get("details", []):
                    balances.append(Balance(
                        asset=balance_data["ccy"],
                        free=float(balance_data["availEq"]),
                        locked=float(balance_data["frozenBal"]),
                        total=float(balance_data["eq"])
                    ))
            
            return balances
        except Exception as e:
            logger.error(f"获取OKX资产余额失败: {e}")
            return []
    
    async def get_positions(self) -> List[Dict[str, Any]]:
        """
        获取持仓：合并多类 instType 查询，避免只拉「全量」时漏掉 SWAP/FUTURES；
        支持 net 单向持仓（方向由 pos 正负决定）。
        """
        endpoint = "/api/v5/account/positions"

        def _parse_row(pos_data: Dict[str, Any]) -> Dict[str, Any]:
            inst_id = pos_data.get("instId", "") or ""
            try:
                pos_val = float(pos_data.get("pos", 0) or 0)
            except (TypeError, ValueError):
                pos_val = 0.0
            ps = (pos_data.get("posSide") or "").strip().lower()
            if ps == "long":
                side = "long"
            elif ps == "short":
                side = "short"
            elif ps == "net":
                if pos_val > 0:
                    side = "long"
                elif pos_val < 0:
                    side = "short"
                else:
                    side = "long"
            else:
                side = "long" if pos_val >= 0 else "short"
            size_abs = abs(pos_val)
            entry = float(pos_data.get("avgPx", 0) or 0)
            mark_px = float(pos_data.get("markPx", 0) or 0)
            return {
                "instId": inst_id,
                "symbol": inst_id.replace("-", "/") if inst_id else "",
                "posSide_raw": str(pos_data.get("posSide") or ""),
                "side": side,
                "raw_pos": pos_val,
                "size": size_abs,
                "entry_price": entry,
                "mark_px": mark_px,
                "unrealized_pnl": float(pos_data.get("upl", 0) or 0),
                "leverage": float(pos_data.get("lever", 1) or 1),
                "margin": float(pos_data.get("margin", 0) or 0),
                "liquidation_price": float(pos_data.get("liqPx", 0) or 0),
                "timestamp": int(pos_data.get("cTime", 0) or 0),
            }

        def _ingest_rows(rows: Any, bucket: Dict[str, Dict[str, Any]]) -> None:
            for pos_data in rows or []:
                if not isinstance(pos_data, dict):
                    continue
                parsed = _parse_row(pos_data)
                if parsed["size"] <= 1e-12:
                    continue
                key = f"{parsed['instId']}|{parsed.get('posSide_raw', '')}|{parsed['side']}"
                prev = bucket.get(key)
                if prev is None or parsed["size"] > prev["size"]:
                    bucket[key] = parsed

        last_error: Optional[Exception] = None

        # 关键：不能先把「全量 positions」与 SWAP 再合并。
        # OKX 全量接口有时仍带已平仓合约的陈旧行；若 SWAP 侧已无该 instId，
        # 合并后会留下「幽灵仓位」（用户看到的 ETH 等假持仓）。
        # 原则：U 本位永续以 instType=SWAP 为唯一真相源；仅当 SWAP 请求失败时再降级。

        swap_bucket: Dict[str, Dict[str, Any]] = {}
        try:
            data = await self._make_request("GET", endpoint, params={"instType": "SWAP"})
            _ingest_rows(data, swap_bucket)
            out = list(swap_bucket.values())
            logger.info("OKX 持仓(SWAP 权威): 非零 %d 条", len(out))
            return out
        except Exception as e:
            last_error = e
            logger.warning(f"OKX get_positions SWAP 失败，尝试降级: {e}")

        fallback: Dict[str, Dict[str, Any]] = {}
        for pv in ({"instType": "FUTURES"}, None):
            try:
                data = await self._make_request("GET", endpoint, params=pv)
                _ingest_rows(data, fallback)
            except Exception as e2:
                last_error = e2
                logger.debug(f"OKX get_positions 降级子查询失败 params={pv}: {e2}")
                continue

        if fallback:
            out = list(fallback.values())
            logger.info("OKX 持仓(降级合并 FUTURES/全量): 非零 %d 条", len(out))
            return out
        if last_error:
            logger.error(f"获取OKX持仓信息失败: {last_error}")
        return []
    
    async def get_exchange_info(self) -> ExchangeInfo:
        """获取交易所信息"""
        endpoint = "/api/v5/public/instruments"
        params = {"instType": "SPOT"}
        
        try:
            data = await self._make_request("GET", endpoint, params)
            
            supported_symbols = []
            for inst in data:
                supported_symbols.append(inst["instId"].replace("-", "/"))
            
            return ExchangeInfo(
                exchange_id="okx",
                name="OKX",
                api_url=self.api_url,
                ws_url=self.ws_url,
                rate_limit=20,
                supported_symbols=supported_symbols,
                fee_structure={
                    "maker": 0.001,
                    "taker": 0.0015
                }
            )
        except Exception as e:
            logger.error(f"获取OKX交易所信息失败: {e}")
            # 返回默认信息
            return ExchangeInfo(
                exchange_id="okx",
                name="OKX",
                api_url=self.api_url,
                ws_url=self.ws_url,
                rate_limit=20,
                supported_symbols=[],
                fee_structure={}
            )
    
    async def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        """获取交易对信息"""
        endpoint = "/api/v5/public/instruments"
        okx_symbol = symbol.replace("/", "-")
        params = {
            "instType": "SPOT",
            "instId": okx_symbol
        }
        
        try:
            data = await self._make_request("GET", endpoint, params)
            if data and len(data) > 0:
                inst = data[0]
                return {
                    "symbol": symbol,
                    "base_currency": inst.get("baseCcy", ""),
                    "quote_currency": inst.get("quoteCcy", ""),
                    "min_order_size": float(inst.get("minSz", 0)),
                    "max_order_size": float(inst.get("maxSz", 0)),
                    "tick_size": float(inst.get("tickSz", 0)),
                    "price_precision": len(inst.get("tickSz", "0").split(".")[1]) if "." in inst.get("tickSz", "") else 0
                }
        except Exception as e:
            logger.error(f"获取OKX交易对信息失败: {e}")
        return {}

    async def get_swap_symbol_info(self, symbol: str) -> Dict[str, Any]:
        """
        获取永续合约交易对信息（SWAP instruments）

        返回字段尽量包含：
        - minSz / maxSz: 最小/最大下单张数
        - lotSz: 下单张数步进
        - ctVal / ctValCcy: 合约面值
        - tickSz: 价格最小变动
        """
        # 归一 instId：BTC/USDT -> BTC-USDT-SWAP
        base = symbol.replace("/SWAP", "").replace("SWAP", "").replace("/", "-").strip()
        if not base.endswith("-SWAP"):
            base = base + "-SWAP"
        okx_inst_id = base.replace("--", "-")

        now = time.time()
        cached = self._instrument_cache.get(okx_inst_id)
        if cached:
            ts, payload = cached
            if (now - ts) < float(self._instrument_cache_ttl_s):
                return payload

        endpoint = "/api/v5/public/instruments"
        params = {"instType": "SWAP", "instId": okx_inst_id}
        payload: Dict[str, Any] = {}
        try:
            data = await self._make_request("GET", endpoint, params)
            if data and len(data) > 0:
                inst = data[0]
                payload = {
                    "instId": inst.get("instId", okx_inst_id),
                    "symbol": symbol,
                    "minSz": float(inst.get("minSz", 0) or 0),
                    "maxSz": float(inst.get("maxSz", 0) or 0),
                    "lotSz": float(inst.get("lotSz", 0) or 0),
                    "tickSz": inst.get("tickSz"),
                    "ctVal": inst.get("ctVal"),
                    "ctValCcy": inst.get("ctValCcy"),
                    "uly": inst.get("uly"),
                    "state": inst.get("state"),
                }
        except Exception as e:
            logger.warning(f"获取OKX合约交易对信息失败: {okx_inst_id} - {e}")

        self._instrument_cache[okx_inst_id] = (now, payload)
        return payload
    
    async def subscribe_market_data(self, symbol: str, callback: Any) -> bool:
        """订阅市场数据"""
        # 暂时使用轮询方式，WebSocket实现可以后续添加
        logger.info(f"OKX订阅市场数据: {symbol}")
        return True
    
    async def unsubscribe_market_data(self, symbol: str) -> bool:
        """取消订阅市场数据"""
        logger.info(f"OKX取消订阅市场数据: {symbol}")
        return True
    
    async def get_balance(self) -> Dict[str, float]:
        """获取账户余额（便捷方法）"""
        balances = await self.get_balances()
        return {b.asset: b.free for b in balances if b.free > 0}
    
    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """获取行情数据（便捷方法）
        
        自动识别现货和永续合约：
        - 现货: BTC/USDT -> BTC-USDT (需要指定 instType=SP)
        - 永续合约: BTC/USDT/SWAP 或 BTC/USDT -> BTC-USDT-SWAP (默认)
        """
        endpoint = "/api/v5/market/ticker"
        
        if "/SWAP" in symbol or symbol.endswith("SWAP"):
            okx_symbol = symbol.replace("/SWAP", "").replace("/", "-")
            if not okx_symbol.endswith("-SWAP"):
                okx_symbol = okx_symbol + "-SWAP"
        else:
            okx_symbol = symbol.replace("/", "-") + "-SWAP"
        
        params = {"instId": okx_symbol}
        
        try:
            data = await self._make_request("GET", endpoint, params)
            if data and len(data) > 0:
                ticker = data[0]
                return {
                    "symbol": symbol,
                    "last": float(ticker.get("last", 0)),
                    "bid": float(ticker.get("bidPx", 0)),
                    "ask": float(ticker.get("askPx", 0)),
                    "high": float(ticker.get("high24h", 0)),
                    "low": float(ticker.get("low24h", 0)),
                    "volume": float(ticker.get("vol24h", 0)),
                    "change": float(ticker.get("change24h", 0)),
                    "timestamp": int(ticker.get("ts", 0))
                }
        except Exception as e:
            error_str = str(e)
            if "51001" in error_str or "doesn't exist" in error_str:
                logger.debug(f"交易对 {okx_symbol} 不存在，尝试现货...")
                try:
                    spot_symbol = symbol.replace("/SWAP", "").replace("/", "-")
                    params["instId"] = spot_symbol
                    data = await self._make_request("GET", endpoint, params)
                    if data and len(data) > 0:
                        ticker = data[0]
                        return {
                            "symbol": symbol,
                            "last": float(ticker.get("last", 0)),
                            "bid": float(ticker.get("bidPx", 0)),
                            "ask": float(ticker.get("askPx", 0)),
                            "high": float(ticker.get("high24h", 0)),
                            "low": float(ticker.get("low24h", 0)),
                            "volume": float(ticker.get("vol24h", 0)),
                            "change": float(ticker.get("change24h", 0)),
                            "timestamp": int(ticker.get("ts", 0))
                        }
                except Exception as e2:
                    logger.debug(f"交易对 {symbol} 行情获取失败: {e2}")
            else:
                logger.debug(f"获取OKX行情失败: {e}")
        return {}
    
    async def set_leverage(self, symbol: str, leverage: int, margin_mode: str = "cross") -> Dict[str, Any]:
        """设置杠杆倍数
        
        Args:
            symbol: 交易对，如 BTC/USDT
            leverage: 杠杆倍数
            margin_mode: 保证金模式 cross(全仓) 或 isolated(逐仓)
        """
        endpoint = "/api/v5/account/set-leverage"
        okx_symbol = symbol.replace("/", "-") + "-SWAP"
        
        body = {
            "instId": okx_symbol,
            "lever": str(leverage),
            "mgnMode": margin_mode
        }
        
        try:
            data = await self._make_request("POST", endpoint, body=body)
            logger.info(f"✅ 设置杠杆成功: {symbol} {leverage}x ({margin_mode})")
            return {
                "success": True,
                "symbol": symbol,
                "leverage": leverage,
                "margin_mode": margin_mode,
                "data": data
            }
        except Exception as e:
            logger.error(f"设置杠杆失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def open_swap_position(self, symbol: str, side: str, size: float, 
                                  leverage: int = 20, price: float = None,
                                  margin_mode: str = "cross") -> Dict[str, Any]:
        """开永续合约仓位
        
        Args:
            symbol: 交易对，如 BTC/USDT
            side: 方向 long/short
            size: 仓位大小（张数或币数）
            leverage: 杠杆倍数
            price: 限价单价格，None为市价单
            margin_mode: 保证金模式 cross/isolated
        """
        okx_symbol = symbol.replace("/", "-") + "-SWAP"
        if "--" in okx_symbol:
            okx_symbol = okx_symbol.replace("--", "-")
        
        await self.set_leverage(symbol, leverage, margin_mode)
        
        order_type = "market" if price is None else "limit"
        
        pos_side = await self._get_position_side(side)
        
        body = {
            "instId": okx_symbol,
            "tdMode": margin_mode,
            "side": "buy" if side == "long" else "sell",
            "posSide": pos_side,
            "ordType": order_type,
            "sz": str(size)
        }
        
        if price:
            body["px"] = str(price)
        
        endpoint = "/api/v5/trade/order"
        
        logger.info(f"📤 发送订单请求: {body}")
        
        try:
            data = await self._make_request("POST", endpoint, body=body)
            order_data = data[0] if isinstance(data, list) and len(data) > 0 else data
            logger.info(f"✅ 开仓成功: {symbol} {side} {size} @ {leverage}x")
            return {
                "success": True,
                "orderId": order_data.get("ordId"),
                "symbol": symbol,
                "side": side,
                "size": size,
                "leverage": leverage,
                "data": data
            }
        except Exception as e:
            logger.error(f"开仓失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def _get_position_side(self, side: str) -> str:
        """获取持仓方向 - 适配单向/双向持仓模式"""
        try:
            account_config = await self._get_account_config()
            pos_mode = account_config.get("posMode", "long_short_mode")
            
            if pos_mode == "net_mode":
                return "net"
            else:
                return side
        except Exception as e:
            logger.warning(f"获取持仓模式失败，使用默认: {e}")
            return side
    
    async def _get_account_config(self) -> Dict[str, Any]:
        """获取账户配置"""
        endpoint = "/api/v5/account/config"
        try:
            data = await self._make_request("GET", endpoint)
            if isinstance(data, list) and len(data) > 0:
                return data[0]
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.error(f"获取账户配置失败: {e}")
            return {}
    
    def _normalize_pair_symbol(self, symbol: str) -> str:
        """Normalize instId (e.g. BTC-USDT-SWAP) or mixed formats to BTC/USDT."""
        s = (symbol or "").strip()
        if not s:
            return s
        s = s.replace("-SWAP", "").replace("--", "-")
        if "/" in s:
            return s
        parts = [p for p in s.split("-") if p]
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
        return s

    async def close_position(self, symbol: str, side: str, size: float = None) -> Dict[str, Any]:
        """
        Compatibility shim for ai_core / legacy callers using instId or pair strings.
        Delegates to close_swap_position with normalized BTC/USDT style symbol.
        """
        pair = self._normalize_pair_symbol(symbol)
        return await self.close_swap_position(pair, side, size)

    async def close_swap_position(self, symbol: str, side: str, size: float = None) -> Dict[str, Any]:
        """平永续合约仓位
        
        Args:
            symbol: 交易对
            side: 方向 long/short
            size: 平仓数量，None为全部平仓
        """
        okx_symbol = symbol.replace("/", "-") + "-SWAP"
        
        if size is None:
            positions = await self.get_positions()
            for pos in positions:
                if pos["symbol"].replace("/USDT", "") == symbol.replace("/USDT", ""):
                    size = abs(float(pos["size"]))
                    break
        
        if size is None or size <= 0:
            return {"success": False, "error": "未找到持仓或数量为0"}
        
        pos_side = await self._get_position_side(side)
        
        body = {
            "instId": okx_symbol,
            "tdMode": "cross",
            "side": "sell" if side == "long" else "buy",
            "posSide": pos_side,
            "ordType": "market",
            "sz": str(size)
        }
        
        endpoint = "/api/v5/trade/order"
        
        try:
            data = await self._make_request("POST", endpoint, body=body)
            logger.info(f"✅ 平仓成功: {symbol} {side} {size}")
            return {
                "success": True,
                "orderId": data.get("ordId") if isinstance(data, dict) else data[0].get("ordId") if isinstance(data, list) else None,
                "symbol": symbol,
                "side": side,
                "size": size,
                "data": data
            }
        except Exception as e:
            logger.error(f"平仓失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_swap_ticker(self, symbol: str) -> Dict[str, Any]:
        """获取永续合约行情"""
        endpoint = "/api/v5/market/ticker"
        okx_symbol = symbol.replace("/", "-") + "-SWAP"
        params = {"instId": okx_symbol}
        
        try:
            data = await self._make_request("GET", endpoint, params)
            if data and len(data) > 0:
                ticker = data[0]
                return {
                    "symbol": symbol,
                    "last": float(ticker.get("last", 0)),
                    "bid": float(ticker.get("bidPx", 0)),
                    "ask": float(ticker.get("askPx", 0)),
                    "high": float(ticker.get("high24h", 0)),
                    "low": float(ticker.get("low24h", 0)),
                    "volume": float(ticker.get("vol24h", 0)),
                    "change": float(ticker.get("change24h", 0)),
                    "funding_rate": float(ticker.get("fundingRate", 0)),
                    "timestamp": int(ticker.get("ts", 0))
                }
        except Exception as e:
            logger.error(f"获取永续合约行情失败: {e}")
        return {}
    
    async def get_swap_klines(self, symbol: str, interval: str = "1H", limit: int = 100) -> List[Dict[str, Any]]:
        """获取永续合约K线数据"""
        endpoint = "/api/v5/market/candles"
        okx_symbol = symbol.replace("/", "-") + "-SWAP"
        
        interval_map = {
            "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
            "1H": "1H", "4H": "4H", "1D": "1D", "1W": "1W"
        }
        bar = interval_map.get(interval, "1H")
        
        params = {
            "instId": okx_symbol,
            "bar": bar,
            "limit": str(limit)
        }
        
        try:
            data = await self._make_request("GET", endpoint, params)
            klines = []
            
            for candle in data:
                klines.append({
                    "timestamp": int(candle[0]),
                    "open": float(candle[1]),
                    "high": float(candle[2]),
                    "low": float(candle[3]),
                    "close": float(candle[4]),
                    "volume": float(candle[5])
                })
            
            return list(reversed(klines))
        except Exception as e:
            logger.error(f"获取永续合约K线失败: {e}")
            return []
    
    async def create_grid_order(self, symbol: str, grid_levels: int = 10, 
                                 grid_spacing: float = 0.01, total_size: float = 1.0,
                                 leverage: int = 20, side: str = "long") -> Dict[str, Any]:
        """创建网格交易订单
        
        Args:
            symbol: 交易对
            grid_levels: 网格层数
            grid_spacing: 网格间距（百分比）
            total_size: 总仓位大小
            leverage: 杠杆倍数
            side: 方向 long/short
        """
        ticker = await self.get_swap_ticker(symbol)
        if not ticker:
            return {"success": False, "error": "无法获取行情"}
        
        current_price = ticker["last"]
        size_per_grid = total_size / grid_levels
        
        orders = []
        
        for i in range(1, grid_levels + 1):
            if side == "long":
                price = current_price * (1 - grid_spacing * i)
            else:
                price = current_price * (1 + grid_spacing * i)
            
            result = await self.open_swap_position(
                symbol=symbol,
                side=side,
                size=size_per_grid,
                leverage=leverage,
                price=round(price, 2),
                margin_mode="cross"
            )
            
            orders.append({
                "level": i,
                "price": price,
                "size": size_per_grid,
                "result": result
            })
        
        logger.info(f"✅ 创建网格订单: {symbol} {grid_levels}层 间距{grid_spacing*100}%")
        return {
            "success": True,
            "symbol": symbol,
            "current_price": current_price,
            "grid_levels": grid_levels,
            "grid_spacing": grid_spacing,
            "orders": orders
        }
    
    async def get_open_interest(self, symbol: str) -> Optional[Dict[str, float]]:
        """获取持仓量"""
        endpoint = "/api/v5/public/open-interest"
        okx_symbol = self._to_okx_inst_id(symbol, default_type="SWAP")
        params = {"instId": okx_symbol}
        
        try:
            data = await self._make_request("GET", endpoint, params)
            item = data[0] if isinstance(data, list) and data else (data or {})
            if item:
                oi = float(item.get("oi", 0) or 0)
                vol24h = float(item.get("vol24h", 0) or 0)
                return {
                    "open_interest": oi,
                    "volume_24h": vol24h
                }
            return None
        except Exception as e:
            logger.error(f"获取持仓量失败: {e}")
        return None
    
    async def get_funding_rate(self, symbol: str) -> Optional[float]:
        """获取资金费率"""
        endpoint = "/api/v5/public/funding-rate"
        okx_symbol = self._to_okx_inst_id(symbol, default_type="SWAP")
        params = {"instId": okx_symbol}
        
        try:
            data = await self._make_request("GET", endpoint, params)
            item = data[0] if isinstance(data, list) and data else (data or {})
            if item:
                return float(item.get("fundingRate", 0) or 0)
            return None
        except Exception as e:
            logger.error(f"获取资金费率失败: {e}")
        return None
    
    async def get_long_short_ratio(self, symbol: str) -> Optional[Dict[str, float]]:
        """获取多空比 - 使用订单簿数据计算"""
        try:
            okx_inst_id = self._to_okx_inst_id(symbol, default_type="SWAP")
            order_book = await self.get_order_book(okx_inst_id, depth=20)
            
            if not order_book:
                return None
            
            bids = order_book.bids if hasattr(order_book, 'bids') else []
            asks = order_book.asks if hasattr(order_book, 'asks') else []
            
            if not bids or not asks:
                return None
            
            bid_volume = sum(float(b[1]) if len(b) > 1 else 0 for b in bids)
            ask_volume = sum(float(a[1]) if len(a) > 1 else 0 for a in asks)
            
            total = bid_volume + ask_volume
            if total == 0:
                return None
            
            long_ratio = bid_volume / total
            short_ratio = ask_volume / total
            
            return {
                "long": long_ratio,
                "short": short_ratio,
                "long_short_ratio": long_ratio / short_ratio if short_ratio > 0 else 1,
                "source": "order_book"
            }
        except Exception as e:
            logger.debug(f"获取多空比失败: {e}")
        return None

    async def get_realtime_market_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        增强实时行情快照（主通道）：
        - 并行拉取 ticker/order_book/funding_rate/open_interest
        - 与现有 get_ticker 兼容，失败时由上层自动回退
        """
        started = time.time()
        try:
            ticker_task = self.get_ticker(symbol)
            ob_task = self.get_order_book(symbol, depth=5)
            fr_task = self.get_funding_rate(symbol)
            oi_task = self.get_open_interest(symbol)
            ticker, order_book, funding_rate, open_interest = await asyncio.gather(
                ticker_task,
                ob_task,
                fr_task,
                oi_task,
                return_exceptions=True,
            )

            if isinstance(ticker, Exception) or not ticker:
                return None

            price = float(ticker.get("last") or ticker.get("close") or 0.0)
            if price <= 0:
                return None
            high = float(ticker.get("high") or price)
            low = float(ticker.get("low") or price)
            open_price = float(ticker.get("open") or price)
            volume = float(ticker.get("quoteVolume") or ticker.get("volume") or 0.0)

            spread_bps = None
            best_bid = float(ticker.get("bid") or 0.0)
            best_ask = float(ticker.get("ask") or 0.0)
            if best_bid > 0 and best_ask > 0 and price > 0:
                spread_bps = ((best_ask - best_bid) / price) * 10000

            quality_score = 0.35
            if volume > 0:
                quality_score += 0.2
            if isinstance(order_book, OrderBook) and order_book.bids and order_book.asks:
                quality_score += 0.2
            if not isinstance(funding_rate, Exception) and funding_rate is not None:
                quality_score += 0.15
            if not isinstance(open_interest, Exception) and open_interest:
                quality_score += 0.1
            quality_score = min(1.0, max(0.0, quality_score))

            return {
                "symbol": symbol,
                "timestamp": datetime.now(),
                "open": open_price,
                "high": max(high, low, price),
                "low": min(high, low, price),
                "close": price,
                "volume": max(0.0, volume),
                "is_live": True,
                "route_channel": "primary_enhanced",
                "route_fallback": False,
                "latency_ms": int((time.time() - started) * 1000),
                "quality_score": quality_score,
                "market_extras": {
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "spread_bps": spread_bps,
                    "funding_rate": None if isinstance(funding_rate, Exception) else funding_rate,
                    "open_interest": None if isinstance(open_interest, Exception) else open_interest,
                    "orderbook_depth5": (
                        {
                            "bids": order_book.bids[:5],
                            "asks": order_book.asks[:5],
                        }
                        if isinstance(order_book, OrderBook)
                        else None
                    ),
                },
            }
        except Exception as e:
            logger.debug(f"OKX增强实时快照失败 {symbol}: {e}")
            return None
