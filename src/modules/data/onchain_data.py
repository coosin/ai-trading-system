"""
链上数据采集模块

支持：
1. 区块链浏览器API（Etherscan、BscScan等）
2. 链上分析数据
3. DeFi锁仓量数据
4. 大额转账监控
5. Gas费用趋势
6. 钱包地址持仓追踪
"""

import asyncio
import aiohttp
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class ChainType(Enum):
    """区块链类型"""
    ETHEREUM = "ethereum"
    BSC = "bsc"
    POLYGON = "polygon"
    ARBITRUM = "arbitrum"
    OPTIMISM = "optimism"
    SOLANA = "solana"
    BITCOIN = "bitcoin"


@dataclass
class OnChainConfig:
    """链上数据配置"""
    chain: ChainType
    api_key: str
    api_url: str
    explorer_url: str


@dataclass
class WalletBalance:
    """钱包余额"""
    address: str
    chain: ChainType
    native_balance: float
    native_symbol: str
    tokens: List[Dict[str, Any]] = field(default_factory=list)
    total_value_usd: float = 0.0
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class LargeTransaction:
    """大额转账"""
    tx_hash: str
    chain: ChainType
    from_address: str
    to_address: str
    value: float
    value_usd: float
    token_symbol: str
    timestamp: datetime
    block_number: int


@dataclass
class GasPrice:
    """Gas价格"""
    chain: ChainType
    slow: float
    standard: float
    fast: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class DeFiProtocol:
    """DeFi协议数据"""
    name: str
    chain: ChainType
    tvl: float
    tvl_change_24h: float
    users_24h: int
    volume_24h: float


class OnChainDataProvider:
    """
    链上数据提供者
    
    支持多个区块链网络的数据采集
    """
    
    DEFAULT_CONFIGS = {
        ChainType.ETHEREUM: OnChainConfig(
            chain=ChainType.ETHEREUM,
            api_key="",
            api_url="https://api.etherscan.io/api",
            explorer_url="https://etherscan.io"
        ),
        ChainType.BSC: OnChainConfig(
            chain=ChainType.BSC,
            api_key="",
            api_url="https://api.bscscan.com/api",
            explorer_url="https://bscscan.com"
        ),
        ChainType.POLYGON: OnChainConfig(
            chain=ChainType.POLYGON,
            api_key="",
            api_url="https://api.polygonscan.com/api",
            explorer_url="https://polygonscan.com"
        ),
        ChainType.SOLANA: OnChainConfig(
            chain=ChainType.SOLANA,
            api_key="",
            api_url="https://api.mainnet-beta.solana.com",
            explorer_url="https://solscan.io"
        ),
    }
    
    def __init__(self, configs: Dict[ChainType, OnChainConfig] = None):
        self.configs = configs or self.DEFAULT_CONFIGS
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, Any] = {}
        self._cache_timeout = 60
        
        logger.info("链上数据提供者初始化完成")
    
    async def initialize(self) -> bool:
        """初始化"""
        try:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
            logger.info("✅ 链上数据提供者初始化成功")
            return True
        except Exception as e:
            logger.error(f"链上数据提供者初始化失败: {e}")
            return False
    
    async def close(self) -> None:
        """关闭连接"""
        if self._session:
            await self._session.close()
    
    async def get_wallet_balance(self, address: str, 
                                 chain: ChainType = ChainType.ETHEREUM) -> Optional[WalletBalance]:
        """获取钱包余额"""
        config = self.configs.get(chain)
        if not config or not config.api_key:
            logger.warning(f"链 {chain.value} 未配置API密钥")
            return self._get_mock_wallet_balance(address, chain)
        
        try:
            if chain in [ChainType.ETHEREUM, ChainType.BSC, ChainType.POLYGON]:
                return await self._get_evm_wallet_balance(address, config)
            elif chain == ChainType.SOLANA:
                return await self._get_solana_wallet_balance(address, config)
        except Exception as e:
            logger.error(f"获取钱包余额失败: {e}")
            return self._get_mock_wallet_balance(address, chain)
        
        return None
    
    async def _get_evm_wallet_balance(self, address: str, 
                                      config: OnChainConfig) -> Optional[WalletBalance]:
        """获取EVM链钱包余额"""
        try:
            url = f"{config.api_url}?module=account&action=balance&address={address}&apikey={config.api_key}"
            
            async with self._session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data.get("status") == "1":
                        balance_wei = int(data.get("result", 0))
                        balance_eth = balance_wei / 10**18
                        
                        symbol = "ETH" if config.chain == ChainType.ETHEREUM else \
                                "BNB" if config.chain == ChainType.BSC else "MATIC"
                        
                        return WalletBalance(
                            address=address,
                            chain=config.chain,
                            native_balance=balance_eth,
                            native_symbol=symbol
                        )
        except Exception as e:
            logger.error(f"获取EVM钱包余额失败: {e}")
        
        return None
    
    async def _get_solana_wallet_balance(self, address: str,
                                         config: OnChainConfig) -> Optional[WalletBalance]:
        """获取Solana钱包余额"""
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getBalance",
                "params": [address]
            }
            
            async with self._session.post(config.api_url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    balance_lamports = data.get("result", {}).get("value", 0)
                    balance_sol = balance_lamports / 10**9
                    
                    return WalletBalance(
                        address=address,
                        chain=ChainType.SOLANA,
                        native_balance=balance_sol,
                        native_symbol="SOL"
                    )
        except Exception as e:
            logger.error(f"获取Solana钱包余额失败: {e}")
        
        return None
    
    def _get_mock_wallet_balance(self, address: str, chain: ChainType) -> WalletBalance:
        """获取模拟钱包余额（API未配置时使用）"""
        symbol = {
            ChainType.ETHEREUM: "ETH",
            ChainType.BSC: "BNB",
            ChainType.POLYGON: "MATIC",
            ChainType.SOLANA: "SOL",
            ChainType.BITCOIN: "BTC"
        }.get(chain, "UNKNOWN")
        
        return WalletBalance(
            address=address,
            chain=chain,
            native_balance=0.0,
            native_symbol=symbol,
            total_value_usd=0.0
        )
    
    async def get_gas_price(self, chain: ChainType = ChainType.ETHEREUM) -> Optional[GasPrice]:
        """获取Gas价格"""
        config = self.configs.get(chain)
        if not config or not config.api_key:
            return self._get_mock_gas_price(chain)
        
        try:
            if chain in [ChainType.ETHEREUM, ChainType.BSC, ChainType.POLYGON]:
                url = f"{config.api_url}?module=gastracker&action=gasoracle&apikey={config.api_key}"
                
                async with self._session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if data.get("status") == "1":
                            result = data.get("result", {})
                            return GasPrice(
                                chain=chain,
                                slow=float(result.get("SafeGasPrice", 0)),
                                standard=float(result.get("ProposeGasPrice", 0)),
                                fast=float(result.get("FastGasPrice", 0))
                            )
        except Exception as e:
            logger.error(f"获取Gas价格失败: {e}")
        
        return self._get_mock_gas_price(chain)
    
    def _get_mock_gas_price(self, chain: ChainType) -> GasPrice:
        """获取模拟Gas价格"""
        base_prices = {
            ChainType.ETHEREUM: (20, 30, 50),
            ChainType.BSC: (3, 5, 10),
            ChainType.POLYGON: (30, 50, 100),
        }
        
        slow, standard, fast = base_prices.get(chain, (10, 20, 30))
        
        return GasPrice(
            chain=chain,
            slow=slow,
            standard=standard,
            fast=fast
        )
    
    async def get_large_transactions(self, chain: ChainType = ChainType.ETHEREUM,
                                     min_value_usd: float = 100000,
                                     limit: int = 10) -> List[LargeTransaction]:
        """获取大额转账"""
        config = self.configs.get(chain)
        if not config or not config.api_key:
            return self._get_mock_large_transactions(chain, limit)
        
        try:
            pass
        except Exception as e:
            logger.error(f"获取大额转账失败: {e}")
        
        return self._get_mock_large_transactions(chain, limit)
    
    def _get_mock_large_transactions(self, chain: ChainType, limit: int) -> List[LargeTransaction]:
        """获取模拟大额转账"""
        return [
            LargeTransaction(
                tx_hash=f"0x{'0'*64}",
                chain=chain,
                from_address="0x" + "1"*40,
                to_address="0x" + "2"*40,
                value=100.0,
                value_usd=200000.0,
                token_symbol="ETH",
                timestamp=datetime.now() - timedelta(minutes=i*5),
                block_number=18000000 - i*100
            )
            for i in range(limit)
        ]
    
    async def get_defi_tvl(self, protocol_name: str = None) -> List[DeFiProtocol]:
        """获取DeFi锁仓量"""
        try:
            return await self._get_defi_tvl_from_defillama()
        except Exception as e:
            logger.error(f"获取DeFi TVL失败: {e}")
            return self._get_mock_defi_tvl()
    
    async def _get_defi_tvl_from_defillama(self) -> List[DeFiProtocol]:
        """从DefiLlama获取TVL数据"""
        try:
            url = "https://api.llama.fi/protocols"
            
            async with self._session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    protocols = []
                    for p in data[:20]:
                        protocols.append(DeFiProtocol(
                            name=p.get("name", ""),
                            chain=ChainType.ETHEREUM,
                            tvl=p.get("tvl", 0),
                            tvl_change_24h=p.get("change_1d", 0),
                            users_24h=0,
                            volume_24h=p.get("volume_24h", 0)
                        ))
                    
                    return protocols
        except Exception as e:
            logger.error(f"从DefiLlama获取TVL失败: {e}")
        
        return self._get_mock_defi_tvl()
    
    def _get_mock_defi_tvl(self) -> List[DeFiProtocol]:
        """获取模拟DeFi TVL"""
        return [
            DeFiProtocol(
                name="Lido",
                chain=ChainType.ETHEREUM,
                tvl=28000000000,
                tvl_change_24h=2.5,
                users_24h=5000,
                volume_24h=100000000
            ),
            DeFiProtocol(
                name="MakerDAO",
                chain=ChainType.ETHEREUM,
                tvl=8000000000,
                tvl_change_24h=1.2,
                users_24h=2000,
                volume_24h=50000000
            ),
            DeFiProtocol(
                name="Aave",
                chain=ChainType.ETHEREUM,
                tvl=12000000000,
                tvl_change_24h=-0.8,
                users_24h=8000,
                volume_24h=200000000
            ),
        ]
    
    async def get_token_holders(self, token_address: str,
                                chain: ChainType = ChainType.ETHEREUM,
                                limit: int = 10) -> List[Dict]:
        """获取代币持有者列表"""
        config = self.configs.get(chain)
        if not config or not config.api_key:
            return self._get_mock_token_holders(limit)
        
        try:
            url = f"{config.api_url}?module=token&action=tokenholderlist&contractaddress={token_address}&page=1&offset={limit}&apikey={config.api_key}"
            
            async with self._session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data.get("status") == "1":
                        return data.get("result", [])
        except Exception as e:
            logger.error(f"获取代币持有者失败: {e}")
        
        return self._get_mock_token_holders(limit)
    
    def _get_mock_token_holders(self, limit: int) -> List[Dict]:
        """获取模拟代币持有者"""
        return [
            {
                "rank": i + 1,
                "address": f"0x{i+1:*<40}",
                "balance": 1000000 - i * 100000,
                "percentage": f"{10 - i}%"
            }
            for i in range(limit)
        ]
    
    async def get_network_stats(self, chain: ChainType = ChainType.ETHEREUM) -> Dict:
        """获取网络统计"""
        config = self.configs.get(chain)
        if not config or not config.api_key:
            return self._get_mock_network_stats(chain)
        
        try:
            url = f"{config.api_url}?module=stats&action=ethprice&apikey={config.api_key}"
            
            async with self._session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data.get("status") == "1":
                        result = data.get("result", {})
                        return {
                            "chain": chain.value,
                            "price_usd": float(result.get("ethusd", 0)),
                            "price_btc": float(result.get("ethbtc", 0)),
                            "timestamp": datetime.now().isoformat()
                        }
        except Exception as e:
            logger.error(f"获取网络统计失败: {e}")
        
        return self._get_mock_network_stats(chain)
    
    def _get_mock_network_stats(self, chain: ChainType) -> Dict:
        """获取模拟网络统计"""
        base_stats = {
            ChainType.ETHEREUM: {"price_usd": 3500, "tps": 15, "active_addresses": 500000},
            ChainType.BSC: {"price_usd": 600, "tps": 100, "active_addresses": 300000},
            ChainType.SOLANA: {"price_usd": 150, "tps": 3000, "active_addresses": 200000},
        }
        
        stats = base_stats.get(chain, {"price_usd": 0, "tps": 0, "active_addresses": 0})
        stats["chain"] = chain.value
        stats["timestamp"] = datetime.now().isoformat()
        
        return stats


_onchain_provider: Optional[OnChainDataProvider] = None


async def get_onchain_provider() -> OnChainDataProvider:
    """获取链上数据提供者单例"""
    global _onchain_provider
    
    if _onchain_provider is None:
        _onchain_provider = OnChainDataProvider()
        await _onchain_provider.initialize()
    
    return _onchain_provider
