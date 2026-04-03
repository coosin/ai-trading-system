"""
AiCoin 数据源集成模块
临时对接AiCoin API获取特色数据
API文档: https://docs.aicoin.com/apis/features
"""

import asyncio
import aiohttp
import hmac
import hashlib
import base64
import time
import json
import logging
import websockets
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AiCoinConfig:
    """AiCoin配置"""
    access_key_id: str
    secret_key: str
    base_url: str = "https://open-api.aicoin.com"
    ws_url: str = "wss://open-ws.aicoin.com/ws"
    timeout: int = 30
    proxy: str = None


@dataclass
class LongShortRatio:
    """多空比数据"""
    current: float
    last_day: float
    last_week: float
    timestamp: datetime


@dataclass
class LiquidationData:
    """爆仓数据"""
    liq_1h: float
    liq_long_1h: float
    liq_short_1h: float
    liq_24h: float
    liq_long_24h: float
    liq_short_24h: float
    max_liq: float
    timestamp: datetime


@dataclass
class BigOrder:
    """主力大单数据"""
    id: str
    symbol: str
    start_time: datetime
    depth_price: float
    depth_type: str
    depth_amount: float
    depth_turnover: float
    trade_amount: float
    trade_turnover: float


@dataclass
class ChangeSignal:
    """异动信号"""
    id: str
    symbol: str
    signal_type: str
    price: float
    trade_amount: float
    degree_24h: float
    created_at: datetime


class AiCoinDataSource:
    """AiCoin数据源"""
    
    SIGNAL_TYPES = {
        "1": "放量上攻",
        "2": "放量下探",
        "3": "盘中大涨",
        "4": "盘中大跌",
        "5": "快速反弹",
        "6": "高台跳水",
        "7": "近期新高",
        "8": "近期新低",
        "9": "极速拉升",
        "10": "极速下跌",
        "11": "大单买入",
        "12": "大单卖出",
        "17": "快速流入",
        "18": "快速流出",
        "23": "大额爆仓(多单)",
        "24": "大额爆仓(空单)"
    }
    
    def __init__(self, config: AiCoinConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        
    async def initialize(self):
        """初始化"""
        connector = None
        if self.config.proxy:
            connector = aiohttp.TCPConnector()
        self.session = aiohttp.ClientSession(connector=connector)
        logger.info("✅ AiCoin数据源初始化完成")
        
    async def close(self):
        """关闭连接"""
        self._running = False
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()
        logger.info("AiCoin数据源已关闭")
    
    def _generate_signature(self, timestamp: str, nonce: str) -> str:
        """生成签名"""
        message = f"{self.config.access_key_id}{timestamp}{nonce}"
        signature = hmac.new(
            self.config.secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha1
        )
        return base64.b64encode(signature.digest()).decode('utf-8')
    
    def _build_params(self) -> Dict[str, str]:
        """构建请求参数"""
        timestamp = str(int(time.time()))
        nonce = str(int(time.time() * 1000000))
        signature = self._generate_signature(timestamp, nonce)
        
        return {
            "AccessKeyId": self.config.access_key_id,
            "Timestamp": timestamp,
            "SignatureNonce": nonce,
            "Signature": signature
        }
    
    async def _request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """发送请求"""
        if not self.session:
            await self.initialize()
        
        full_params = self._build_params()
        if params:
            full_params.update(params)
        
        url = f"{self.config.base_url}{endpoint}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
        }
        
        try:
            proxy = self.config.proxy if self.config.proxy else None
            async with self.session.get(url, params=full_params, headers=headers, timeout=self.config.timeout, proxy=proxy) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("success"):
                        return data.get("data")
                    else:
                        logger.debug(f"AiCoin API错误: {data.get('error')}")
                        return None
                elif response.status == 530:
                    logger.debug(f"AiCoin API服务暂时不可用 (530)")
                    return None
                elif response.status == 429:
                    logger.debug(f"AiCoin API频率限制")
                    return None
                else:
                    logger.debug(f"AiCoin API请求失败: {response.status}")
                    return None
        except asyncio.TimeoutError:
            logger.debug(f"AiCoin API超时: {endpoint}")
            return None
        except Exception as e:
            logger.debug(f"AiCoin API请求异常: {e}")
            return None
    
    async def get_long_short_ratio(self) -> Optional[LongShortRatio]:
        """获取多空比数据"""
        data = await self._request("/v2/mix/ls-ratio")
        if data and "detail" in data:
            detail = data["detail"]
            return LongShortRatio(
                current=float(detail.get("last", 0) or 0),
                last_day=float(detail.get("last_day", 0) or 0),
                last_week=float(detail.get("last_week", 0) or 0),
                timestamp=datetime.now()
            )
        return None
    
    async def get_liquidation_data(self, currency: str = "usd") -> Optional[LiquidationData]:
        """获取爆仓数据"""
        data = await self._request("/v2/mix/liq", {"currency": currency})
        if data and "detail" in data:
            detail = data["detail"]
            return LiquidationData(
                liq_1h=float(detail.get("liq1h", 0) or 0),
                liq_long_1h=float(detail.get("liqLong1h", 0) or 0),
                liq_short_1h=float(detail.get("liqShort1h", 0) or 0),
                liq_24h=float(detail.get("liq24h", 0) or 0),
                liq_long_24h=float(detail.get("liqLong24h", 0) or 0),
                liq_short_24h=float(detail.get("liqShort24h", 0) or 0),
                max_liq=float(detail.get("maxLiq", 0) or 0),
                timestamp=datetime.now()
            )
        return None
    
    async def get_big_orders(self, symbol: str) -> List[BigOrder]:
        """获取主力大单数据"""
        data = await self._request("/v2/order/bigOrder", {"symbol": symbol})
        orders = []
        if data and "list" in data:
            for item in data["list"]:
                try:
                    orders.append(BigOrder(
                        id=str(item.get("id", "")),
                        symbol=symbol,
                        start_time=datetime.fromtimestamp(item.get("start_time", 0) / 1000),
                        depth_price=float(item.get("depth_price", 0) or 0),
                        depth_type=item.get("depth_type", ""),
                        depth_amount=float(item.get("depth_amount", 0) or 0),
                        depth_turnover=float(item.get("depth_turnover", 0) or 0),
                        trade_amount=float(item.get("trade_amount", 0) or 0),
                        trade_turnover=float(item.get("trade_turnover", 0) or 0)
                    ))
                except Exception as e:
                    logger.debug(f"解析大单数据失败: {e}")
        return orders
    
    async def get_change_signals(self, signal_type: str = None) -> List[ChangeSignal]:
        """获取异动信号"""
        params = {}
        if signal_type:
            params["type"] = signal_type
        
        data = await self._request("/v2/signal/changeSignal", params)
        signals = []
        if data and "list" in data:
            for item in data["list"]:
                try:
                    signals.append(ChangeSignal(
                        id=str(item.get("id", "")),
                        symbol=item.get("key", ""),
                        signal_type=self.SIGNAL_TYPES.get(str(item.get("type", "")), "未知"),
                        price=float(item.get("price", 0) or 0),
                        trade_amount=float(item.get("trade", 0) or 0),
                        degree_24h=float(item.get("degree_24h", 0) or 0),
                        created_at=datetime.now()
                    ))
                except Exception as e:
                    logger.debug(f"解析异动信号失败: {e}")
        return signals
    
    async def get_ticker(self, symbols: List[str]) -> Dict[str, Dict]:
        """获取行情数据"""
        data = await self._request("/v2/trading-pair/ticker", {
            "key_list": ",".join(symbols)
        })
        result = {}
        if data:
            for item in data:
                key = item.get("key", "")
                result[key] = {
                    "last": float(item.get("last_usd", 0) or 0),
                    "high_24h": float(item.get("high24h_usd", 0) or 0),
                    "low_24h": float(item.get("low24h_usd", 0) or 0),
                }
        return result
    
    async def get_market_summary(self) -> Dict[str, Any]:
        """获取市场概况 - 综合数据"""
        ls_ratio = await self.get_long_short_ratio()
        liq_data = await self.get_liquidation_data()
        signals = await self.get_change_signals()
        
        return {
            "long_short_ratio": {
                "current": ls_ratio.current if ls_ratio else 0,
                "last_day": ls_ratio.last_day if ls_ratio else 0,
                "last_week": ls_ratio.last_week if ls_ratio else 0,
            } if ls_ratio else {},
            "liquidation": {
                "1h": liq_data.liq_1h if liq_data else 0,
                "24h": liq_data.liq_24h if liq_data else 0,
                "long_1h": liq_data.liq_long_1h if liq_data else 0,
                "short_1h": liq_data.liq_short_1h if liq_data else 0,
            } if liq_data else {},
            "change_signals": [
                {
                    "symbol": s.symbol,
                    "type": s.signal_type,
                    "price": s.price,
                    "amount": s.trade_amount
                }
                for s in signals[:10]
            ],
            "timestamp": datetime.now().isoformat()
        }
    
    async def _build_ws_params(self) -> Dict[str, str]:
        """构建WebSocket认证参数"""
        timestamp = str(int(time.time()))
        nonce = str(int(time.time() * 1000000))
        signature = self._generate_signature(timestamp, nonce)
        
        return {
            "AccessKeyId": self.config.access_key_id,
            "Timestamp": timestamp,
            "SignatureNonce": nonce,
            "Signature": signature
        }
    
    async def subscribe_big_orders(self, symbols: List[str], callback):
        """订阅主力大单数据"""
        await self._connect_ws()
        
        params = self._build_ws_params()
        subscribe_msg = {
            "op": "sub",
            "type": "bigorders",
            "params": symbols,
            **params
        }
        
        await self.ws.send(json.dumps(subscribe_msg))
        logger.info(f"📡 订阅主力大单: {symbols}")
        
        self._running = True
        await self._listen_ws(callback)
    
    async def subscribe_change_signals(self, signal_types: List[str], callback):
        """订阅异动信号"""
        await self._connect_ws()
        
        params = self._build_ws_params()
        subscribe_msg = {
            "op": "sub",
            "type": "changeSignal",
            "params": signal_types,
            **params
        }
        
        await self.ws.send(json.dumps(subscribe_msg))
        logger.info(f"📡 订阅异动信号: {signal_types}")
        
        self._running = True
        await self._listen_ws(callback)
    
    async def _connect_ws(self):
        """连接WebSocket"""
        if not self.ws or self.ws.closed:
            self.ws = await websockets.connect(self.config.ws_url)
            logger.info("✅ AiCoin WebSocket已连接")
    
    async def _listen_ws(self, callback):
        """监听WebSocket消息"""
        try:
            while self._running:
                message = await self.ws.recv()
                data = json.loads(message)
                await callback(data)
        except websockets.ConnectionClosed:
            logger.warning("AiCoin WebSocket连接关闭")
        except Exception as e:
            logger.error(f"AiCoin WebSocket错误: {e}")


ai_coin_data_source: Optional[AiCoinDataSource] = None


async def get_ai_coin_source() -> Optional[AiCoinDataSource]:
    """获取AiCoin数据源实例"""
    global ai_coin_data_source
    
    if ai_coin_data_source is None:
        import os
        access_key = os.environ.get("AICOIN_ACCESS_KEY", "")
        secret_key = os.environ.get("AICOIN_SECRET_KEY", "")
        proxy = os.environ.get("AICOIN_PROXY", "http://127.0.0.1:7890")  # 默认使用本地代理
        
        if access_key and secret_key:
            config = AiCoinConfig(
                access_key_id=access_key,
                secret_key=secret_key,
                proxy=proxy
            )
            ai_coin_data_source = AiCoinDataSource(config)
            await ai_coin_data_source.initialize()
        else:
            logger.warning("AiCoin API密钥未配置")
    
    return ai_coin_data_source
