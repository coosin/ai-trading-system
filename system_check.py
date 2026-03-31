#!/usr/bin/env python3
"""
系统全面检查 - AI智能对接和数据同步验证
"""

import asyncio
import sys
import yaml
import json
from datetime import datetime

sys.path.insert(0, '/home/cool/.openclaw-trading')

# 设置日志
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SystemChecker:
    def __init__(self):
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "checks": {},
            "summary": {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "warnings": 0
            }
        }
    
    def add_result(self, category, name, status, details=None):
        """添加检查结果"""
        if category not in self.results["checks"]:
            self.results["checks"][category] = []
        
        self.results["checks"][category].append({
            "name": name,
            "status": status,
            "details": details or {}
        })
        
        self.results["summary"]["total"] += 1
        if status == "✅ PASS":
            self.results["summary"]["passed"] += 1
        elif status == "❌ FAIL":
            self.results["summary"]["failed"] += 1
        elif status == "⚠️ WARN":
            self.results["summary"]["warnings"] += 1
    
    async def check_ai_models(self):
        """检查AI模型对接"""
        print("\n" + "="*70)
        print("🤖 检查 AI 模型对接")
        print("="*70)
        
        from src.modules.core.enhanced_llm_manager import EnhancedLLMManager
        
        try:
            llm_manager = EnhancedLLMManager()
            await llm_manager.initialize({})
            
            # 检查已配置的模型
            models = llm_manager.models
            print(f"\n已配置模型数量: {len(models)}")
            
            for model_id, config in models.items():
                print(f"  - {model_id}: {config.get('name', 'N/A')} ({config.get('provider', 'N/A')})")
            
            # 检查讯飞模型
            if "astron-code-latest" in models:
                self.add_result("AI模型", "讯飞 astron-code-latest", "✅ PASS", 
                    {"provider": models["astron-code-latest"].get("provider")})
            else:
                self.add_result("AI模型", "讯飞 astron-code-latest", "❌ FAIL", 
                    {"error": "模型未配置"})
            
            # 测试AI调用
            print("\n测试 AI 调用...")
            try:
                response = await llm_manager.chat(
                    "你好，请回复'测试成功'",
                    model="astron-code-latest"
                )
                if "error" not in response:
                    self.add_result("AI模型", "AI调用测试", "✅ PASS", 
                        {"response": response.get("content", "")[:50]})
                else:
                    self.add_result("AI模型", "AI调用测试", "❌ FAIL", 
                        {"error": response.get("error")})
            except Exception as e:
                self.add_result("AI模型", "AI调用测试", "❌ FAIL", 
                    {"error": str(e)})
            
            await llm_manager.cleanup()
            
        except Exception as e:
            self.add_result("AI模型", "初始化", "❌ FAIL", {"error": str(e)})
    
    async def check_exchanges(self):
        """检查交易所对接"""
        print("\n" + "="*70)
        print("🏦 检查交易所对接")
        print("="*70)
        
        from src.modules.exchanges.exchange_factory import ExchangeFactory
        
        try:
            # 读取配置
            with open('/home/cool/.openclaw-trading/data/config/default.yml', 'r') as f:
                config = yaml.safe_load(f)
            
            exchanges_config = config.get('exchanges', {})
            
            print(f"\n已配置交易所:")
            for name, ex_config in exchanges_config.items():
                enabled = ex_config.get('enabled', False)
                status = "✅ 已启用" if enabled else "⚠️ 未启用"
                print(f"  - {name.upper()}: {status}")
                
                if enabled:
                    self.add_result("交易所", f"{name.upper()} 配置", "✅ PASS")
                else:
                    self.add_result("交易所", f"{name.upper()} 配置", "⚠️ WARN", 
                        {"message": "交易所未启用"})
            
            # 测试OKX连接
            okx_config = exchanges_config.get('okx', {})
            if okx_config.get('enabled'):
                print("\n测试 OKX 连接...")
                try:
                    factory = ExchangeFactory()
                    exchange = factory.create_exchange("okx", {
                        "api_key": okx_config.get('api_key'),
                        "api_secret": okx_config.get('api_secret'),
                        "passphrase": okx_config.get('passphrase'),
                        "sandbox": okx_config.get('sandbox', False)
                    })
                    
                    success = await exchange.initialize()
                    if success:
                        self.add_result("交易所", "OKX 连接", "✅ PASS")
                        
                        # 测试获取余额
                        try:
                            balance = await exchange.get_balance()
                            self.add_result("交易所", "OKX 余额获取", "✅ PASS", 
                                {"assets": list(balance.keys())[:5]})
                        except Exception as e:
                            self.add_result("交易所", "OKX 余额获取", "⚠️ WARN", 
                                {"error": str(e)})
                        
                        # 测试获取行情
                        try:
                            ticker = await exchange.get_ticker("BTC/USDT")
                            self.add_result("交易所", "OKX 行情获取", "✅ PASS", 
                                {"price": ticker.get('last')})
                        except Exception as e:
                            self.add_result("交易所", "OKX 行情获取", "⚠️ WARN", 
                                {"error": str(e)})
                        
                        await exchange.cleanup()
                    else:
                        self.add_result("交易所", "OKX 连接", "❌ FAIL", 
                            {"error": "初始化失败"})
                except Exception as e:
                    self.add_result("交易所", "OKX 连接", "❌ FAIL", {"error": str(e)})
            
        except Exception as e:
            self.add_result("交易所", "配置检查", "❌ FAIL", {"error": str(e)})
    
    async def check_data_sources(self):
        """检查数据源对接"""
        print("\n" + "="*70)
        print("📊 检查数据源对接")
        print("="*70)
        
        from src.modules.data.data_integration import (
            DataIntegrator, BinanceDataSource, CoinGeckoDataSource,
            CoinbaseDataSource, KrakenDataSource
        )
        
        integrator = DataIntegrator()
        
        # 检查数据源配置
        data_sources = [
            ("Binance", BinanceDataSource),
            ("CoinGecko", CoinGeckoDataSource),
            ("Coinbase", CoinbaseDataSource),
            ("Kraken", KrakenDataSource)
        ]
        
        print("\n数据源状态:")
        for name, source_class in data_sources:
            try:
                source = source_class()
                integrator.register_data_source(name.lower(), source)
                print(f"  ✅ {name}: 已注册")
                self.add_result("数据源", f"{name} 注册", "✅ PASS")
            except Exception as e:
                print(f"  ❌ {name}: {e}")
                self.add_result("数据源", f"{name} 注册", "❌ FAIL", {"error": str(e)})
        
        # 测试数据获取
        print("\n测试数据获取...")
        try:
            # 尝试获取Binance数据
            data = await integrator.fetch_data("binance", symbol="BTCUSDT", interval="1h", limit=10)
            if not data.empty:
                print(f"  ✅ Binance 数据: {len(data)} 条记录")
                self.add_result("数据源", "Binance 数据获取", "✅ PASS", 
                    {"records": len(data)})
            else:
                print("  ⚠️ Binance 数据为空")
                self.add_result("数据源", "Binance 数据获取", "⚠️ WARN")
        except Exception as e:
            print(f"  ❌ Binance 数据获取失败: {e}")
            self.add_result("数据源", "Binance 数据获取", "⚠️ WARN", {"error": str(e)})
        
        try:
            # 尝试获取CoinGecko数据
            data = await integrator.fetch_data("coingecko", coin_id="bitcoin", vs_currency="usd", days=7)
            if not data.empty:
                print(f"  ✅ CoinGecko 数据: {len(data)} 条记录")
                self.add_result("数据源", "CoinGecko 数据获取", "✅ PASS", 
                    {"records": len(data)})
            else:
                print("  ⚠️ CoinGecko 数据为空")
                self.add_result("数据源", "CoinGecko 数据获取", "⚠️ WARN")
        except Exception as e:
            print(f"  ❌ CoinGecko 数据获取失败: {e}")
            self.add_result("数据源", "CoinGecko 数据获取", "⚠️ WARN", {"error": str(e)})
    
    async def check_contract_simulator(self):
        """检查模拟合约交易"""
        print("\n" + "="*70)
        print("📈 检查模拟合约交易")
        print("="*70)
        
        from src.modules.simulation.contract_simulator import ContractSimulator
        
        try:
            # 读取配置
            with open('/home/cool/.openclaw-trading/data/config/default.yml', 'r') as f:
                config = yaml.safe_load(f)
            
            trading_config = config.get('trading', {})
            mode = trading_config.get('mode', 'unknown')
            
            print(f"\n交易模式: {mode}")
            
            if mode == 'simulation':
                sim_config = trading_config.get('simulation', {})
                print(f"  初始资金: {sim_config.get('initial_capital')} USDT")
                print(f"  杠杆: {sim_config.get('leverage')}x")
                print(f"  保证金模式: {sim_config.get('margin_mode')}")
                
                self.add_result("合约交易", "模拟模式配置", "✅ PASS", {
                    "initial_capital": sim_config.get('initial_capital'),
                    "leverage": sim_config.get('leverage'),
                    "margin_mode": sim_config.get('margin_mode')
                })
                
                # 初始化模拟器
                simulator = ContractSimulator(sim_config)
                await simulator.initialize()
                
                account = simulator.get_account_info()
                print(f"\n  账户总权益: {account['total_equity']:.2f} USDT")
                print(f"  可用余额: {account['available_balance']:.2f} USDT")
                
                self.add_result("合约交易", "模拟器初始化", "✅ PASS", account)
                
                await simulator.cleanup()
            else:
                self.add_result("合约交易", "模拟模式配置", "⚠️ WARN", 
                    {"message": f"当前模式为 {mode}，不是模拟模式"})
        
        except Exception as e:
            self.add_result("合约交易", "配置检查", "❌ FAIL", {"error": str(e)})
    
    async def check_llm_integration(self):
        """检查LLM集成功能"""
        print("\n" + "="*70)
        print("🧠 检查 LLM 集成功能")
        print("="*70)
        
        from src.modules.core.llm_integration import EnhancedLLMIntegration
        from src.modules.core.enhanced_llm_manager import EnhancedLLMManager
        
        try:
            llm_manager = EnhancedLLMManager()
            await llm_manager.initialize({})
            
            llm_integration = EnhancedLLMIntegration()
            llm_integration.set_llm_manager(llm_manager)
            
            print("\n测试 AI 功能...")
            
            # 测试市场分析
            market_data = {
                "symbol": "BTC/USDT",
                "price": 67750.0,
                "indicators": {"rsi": 65, "macd": "bullish"}
            }
            
            try:
                analysis = await llm_integration.analyze_market(market_data, provider="astron-code-latest")
                if "error" not in analysis:
                    print("  ✅ AI 市场分析: 成功")
                    self.add_result("LLM集成", "市场分析", "✅ PASS")
                else:
                    print(f"  ⚠️ AI 市场分析: {analysis.get('error')}")
                    self.add_result("LLM集成", "市场分析", "⚠️ WARN")
            except Exception as e:
                print(f"  ❌ AI 市场分析: {e}")
                self.add_result("LLM集成", "市场分析", "⚠️ WARN")
            
            # 测试交易信号生成
            try:
                signal = await llm_integration.generate_trading_signal(market_data, provider="astron-code-latest")
                if "error" not in signal:
                    print("  ✅ AI 信号生成: 成功")
                    self.add_result("LLM集成", "信号生成", "✅ PASS")
                else:
                    print(f"  ⚠️ AI 信号生成: {signal.get('error')}")
                    self.add_result("LLM集成", "信号生成", "⚠️ WARN")
            except Exception as e:
                print(f"  ❌ AI 信号生成: {e}")
                self.add_result("LLM集成", "信号生成", "⚠️ WARN")
            
            await llm_integration.cleanup()
            await llm_manager.cleanup()
            
        except Exception as e:
            self.add_result("LLM集成", "初始化", "❌ FAIL", {"error": str(e)})
    
    async def check_api_endpoints(self):
        """检查API端点"""
        print("\n" + "="*70)
        print("🌐 检查 API 端点")
        print("="*70)
        
        import aiohttp
        
        base_url = "http://localhost:8000"
        endpoints = [
            ("/health", "GET", "健康检查"),
            ("/api/v1/system/status", "GET", "系统状态"),
            ("/api/v1/ai-models", "GET", "AI模型列表"),
            ("/api/v1/market/ticker/BTC/USDT", "GET", "市场行情"),
        ]
        
        print("\n测试 API 端点...")
        
        async with aiohttp.ClientSession() as session:
            for endpoint, method, name in endpoints:
                try:
                    if method == "GET":
                        async with session.get(f"{base_url}{endpoint}", timeout=5) as resp:
                            if resp.status == 200:
                                print(f"  ✅ {name}: OK")
                                self.add_result("API端点", name, "✅ PASS")
                            else:
                                print(f"  ⚠️ {name}: HTTP {resp.status}")
                                self.add_result("API端点", name, "⚠️ WARN", 
                                    {"status": resp.status})
                except Exception as e:
                    print(f"  ❌ {name}: {e}")
                    self.add_result("API端点", name, "❌ FAIL", {"error": str(e)})
    
    async def check_onchain_data(self):
        """检查链上数据配置"""
        print("\n" + "="*70)
        print("🔗 检查链上数据配置")
        print("="*70)
        
        try:
            with open('/home/cool/.openclaw-trading/data/config/default.yml', 'r') as f:
                config = yaml.safe_load(f)
            
            etherscan_config = config.get('etherscan', {})
            api_key = etherscan_config.get('api_key')
            
            if api_key:
                print("  ✅ Etherscan API Key: 已配置")
                self.add_result("链上数据", "Etherscan配置", "✅ PASS")
            else:
                print("  ⚠️ Etherscan API Key: 未配置")
                self.add_result("链上数据", "Etherscan配置", "⚠️ WARN", 
                    {"message": "未配置API Key"})
        
        except Exception as e:
            self.add_result("链上数据", "配置检查", "❌ FAIL", {"error": str(e)})
    
    async def check_social_media(self):
        """检查社交媒体配置"""
        print("\n" + "="*70)
        print("📱 检查社交媒体配置")
        print("="*70)
        
        try:
            with open('/home/cool/.openclaw-trading/data/config/default.yml', 'r') as f:
                config = yaml.safe_load(f)
            
            twitter_config = config.get('twitter', {})
            newsapi_config = config.get('newsapi', {})
            
            if twitter_config.get('bearer_token'):
                print("  ✅ Twitter Bearer Token: 已配置")
                self.add_result("社交媒体", "Twitter配置", "✅ PASS")
            else:
                print("  ⚠️ Twitter Bearer Token: 未配置")
                self.add_result("社交媒体", "Twitter配置", "⚠️ WARN")
            
            if newsapi_config.get('api_key'):
                print("  ✅ NewsAPI Key: 已配置")
                self.add_result("社交媒体", "NewsAPI配置", "✅ PASS")
            else:
                print("  ⚠️ NewsAPI Key: 未配置")
                self.add_result("社交媒体", "NewsAPI配置", "⚠️ WARN")
        
        except Exception as e:
            self.add_result("社交媒体", "配置检查", "❌ FAIL", {"error": str(e)})
    
    def print_summary(self):
        """打印检查摘要"""
        print("\n" + "="*70)
        print("📋 检查摘要")
        print("="*70)
        
        summary = self.results["summary"]
        print(f"\n总计检查项: {summary['total']}")
        print(f"  ✅ 通过: {summary['passed']}")
        print(f"  ❌ 失败: {summary['failed']}")
        print(f"  ⚠️  警告: {summary['warnings']}")
        
        # 计算通过率
        if summary['total'] > 0:
            pass_rate = (summary['passed'] / summary['total']) * 100
            print(f"\n通过率: {pass_rate:.1f}%")
        
        # 保存详细报告
        report_file = f"/home/cool/.openclaw-trading/system_check_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"\n详细报告已保存: {report_file}")
    
    async def run_all_checks(self):
        """运行所有检查"""
        print("\n" + "="*70)
        print("🔍 系统全面检查开始")
        print("="*70)
        print(f"检查时间: {datetime.now().isoformat()}")
        
        await self.check_ai_models()
        await self.check_exchanges()
        await self.check_data_sources()
        await self.check_contract_simulator()
        await self.check_llm_integration()
        await self.check_api_endpoints()
        await self.check_onchain_data()
        await self.check_social_media()
        
        self.print_summary()


async def main():
    checker = SystemChecker()
    await checker.run_all_checks()


if __name__ == "__main__":
    asyncio.run(main())
