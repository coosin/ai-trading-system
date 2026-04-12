"""
OKX v5 WebSocket 适配（公共 tickers + 私有 positions），与官方文档对齐：
- 公共：wss://ws.okx.com:8443/ws/v5/public（模拟盘 wspap）
- 私有：/ws/v5/private，login 签名 timestamp + 'GET' + '/users/self/verify'
- 模拟盘连接头：x-simulated-trading: 1

REST 仍为主路径；WS 用于降低行情轮询压力并预热持仓推送（positions 仅缓存，供后续扩展）。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import aiohttp

if TYPE_CHECKING:
    from src.modules.exchanges.okx import OKXExchange

logger = logging.getLogger(__name__)


class OKXWebSocketHub:
    """管理 OKX WebSocket 连接与轻量缓存。"""

    def __init__(self, exchange: "OKXExchange") -> None:
        self._ex = exchange
        self._tasks: List[asyncio.Task] = []
        self._stop = asyncio.Event()
        self._ticker_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

    def ws_private_url(self) -> str:
        if self._ex.testnet:
            return "wss://wspap.okx.com:8443/ws/v5/private"
        return "wss://ws.okx.com:8443/ws/v5/private"

    def _ws_headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {}
        if getattr(self._ex, "testnet", False):
            h["x-simulated-trading"] = "1"
        return h

    def build_login_arg(self) -> Dict[str, str]:
        ts = str(int(time.time()))
        msg = ts + "GET" + "/users/self/verify"
        mac = hmac.new(
            (self._ex.api_secret or "").encode("utf-8"),
            msg.encode("utf-8"),
            digestmod=hashlib.sha256,
        )
        sign = base64.b64encode(mac.digest()).decode("utf-8")
        return {
            "apiKey": self._ex.api_key or "",
            "passphrase": self._ex.api_passphrase or "",
            "timestamp": ts,
            "sign": sign,
        }

    async def _ws_send_periodic_ping(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """OKX 建议周期性 ping，降低中间设备空闲断连概率。"""
        interval = float(os.getenv("OPENCLAW_OKX_WS_PING_INTERVAL_SEC", "20") or "20")
        interval = max(8.0, min(interval, 120.0))
        while not self._stop.is_set():
            await asyncio.sleep(interval)
            try:
                await ws.send_str(json.dumps({"op": "ping"}, separators=(",", ":")))
            except Exception:
                return

    def get_cached_ticker(self, inst_id: str, max_age_ms: float) -> Optional[Dict[str, Any]]:
        row = self._ticker_cache.get(inst_id)
        if not row:
            return None
        ts, data = row
        if (time.time() - ts) * 1000.0 > max_age_ms:
            return None
        return data

    async def start(self) -> None:
        raw = os.getenv("OPENCLAW_OKX_WS_TICKER_INSTIDS", "BTC-USDT-SWAP,ETH-USDT-SWAP")
        instids = [x.strip() for x in raw.split(",") if x.strip()]
        self._stop.clear()
        self._tasks.append(asyncio.create_task(self._public_tickers_loop(instids), name="okx-ws-public-tickers"))
        if self._ex.api_key and self._ex.api_secret:
            self._tasks.append(asyncio.create_task(self._private_positions_loop(), name="okx-ws-private-positions"))

    async def stop(self) -> None:
        self._stop.set()
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
        self._tasks.clear()

    async def _public_tickers_loop(self, inst_ids: List[str]) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                sess = self._ex._session
                if sess is None or getattr(sess, "closed", True):
                    await asyncio.sleep(1.0)
                    continue
                if self._ex._proxy_only and not self._ex._proxy_url:
                    logger.warning("OKX WS 公共频道跳过：OPENCLAW_OKX_PROXY_ONLY=1 且无代理")
                    await asyncio.sleep(30.0)
                    continue

                args = [{"channel": "tickers", "instId": iid} for iid in inst_ids]
                kwargs: Dict[str, Any] = {"headers": self._ws_headers()}
                if self._ex._proxy_url:
                    kwargs["proxy"] = self._ex._proxy_url

                async with sess.ws_connect(self._ex.ws_url, **kwargs) as ws:
                    await ws.send_str(json.dumps({"op": "subscribe", "args": args}, separators=(",", ":")))
                    logger.info("OKX WS 已订阅 tickers: %s", ",".join(inst_ids))
                    backoff = 1.0
                    ping_task = asyncio.create_task(self._ws_send_periodic_ping(ws))
                    try:
                        while not self._stop.is_set():
                            msg = await asyncio.wait_for(ws.receive(), timeout=35.0)
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    data = json.loads(msg.data)
                                except Exception:
                                    continue
                                if data.get("event") == "pong":
                                    continue
                                if data.get("arg", {}).get("channel") == "tickers" and isinstance(
                                    data.get("data"), list
                                ):
                                    for row in data["data"]:
                                        if not isinstance(row, dict):
                                            continue
                                        iid = row.get("instId")
                                        if iid:
                                            self._ticker_cache[str(iid)] = (time.time(), row)
                                ev = data.get("event")
                                if ev == "error":
                                    logger.warning("OKX WS 公共频道错误: %s", data)
                            elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                                break
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                break
                    finally:
                        ping_task.cancel()
                        try:
                            await ping_task
                        except asyncio.CancelledError:
                            pass
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("OKX WS 公共频道异常，%.1fs 后重连: %s", backoff, e)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.8, 45.0)

    async def _private_positions_loop(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                sess = self._ex._session
                if sess is None or getattr(sess, "closed", True):
                    await asyncio.sleep(1.0)
                    continue
                if self._ex._proxy_only and not self._ex._proxy_url:
                    await asyncio.sleep(30.0)
                    continue

                kwargs: Dict[str, Any] = {"headers": self._ws_headers()}
                if self._ex._proxy_url:
                    kwargs["proxy"] = self._ex._proxy_url

                async with sess.ws_connect(self.ws_private_url(), **kwargs) as ws:
                    login_payload = {"op": "login", "args": [self.build_login_arg()]}
                    await ws.send_str(json.dumps(login_payload, separators=(",", ":")))
                    logged_in = False
                    for _ in range(20):
                        msg = await asyncio.wait_for(ws.receive(), timeout=15.0)
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue
                        try:
                            data = json.loads(msg.data)
                        except Exception:
                            continue
                        if data.get("event") == "login":
                            if str(data.get("code")) == "0":
                                logged_in = True
                            else:
                                logger.error("OKX WS 登录失败: %s", data)
                            break
                    if not logged_in:
                        raise RuntimeError("OKX WS private login failed or timeout")

                    sub = {"op": "subscribe", "args": [{"channel": "positions", "instType": "SWAP"}]}
                    await ws.send_str(json.dumps(sub, separators=(",", ":")))
                    logger.info("OKX WS 已订阅 positions SWAP（私有）")
                    backoff = 1.0
                    ping_task = asyncio.create_task(self._ws_send_periodic_ping(ws))
                    try:
                        while not self._stop.is_set():
                            msg = await asyncio.wait_for(ws.receive(), timeout=35.0)
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    data = json.loads(msg.data)
                                except Exception:
                                    continue
                                if data.get("event") == "pong":
                                    continue
                                if data.get("event") == "subscribe" and str(data.get("code")) != "0":
                                    logger.warning("OKX WS positions 订阅响应: %s", data)
                                if data.get("arg", {}).get("channel") == "positions":
                                    # 预留：后续可将 data["data"] 写入 exchange 级缓存供 get_positions 快路径
                                    pass
                                if data.get("event") == "error":
                                    logger.warning("OKX WS 私有频道错误: %s", data)
                            elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                                break
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                break
                    finally:
                        ping_task.cancel()
                        try:
                            await ping_task
                        except asyncio.CancelledError:
                            pass
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("OKX WS 私有频道异常，%.1fs 后重连: %s", backoff, e)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.8, 45.0)
