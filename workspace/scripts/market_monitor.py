#!/usr/bin/env python3
"""
加密货币市场监控脚本
实时监控主要加密货币价格变化
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

import aiohttp

# 添加工作空间目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class MarketMonitor:
    """市场监控类"""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "crypto-config", "market_config.json"
        )
        self.config = self.load_config()
        self.prices: Dict[str, float] = {}
        self.alerts: List[str] = []

    def load_config(self) -> Dict:
        """加载配置文件"""
        default_config = {
            "monitoring": {
                "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT", "DOTUSDT"],
                "alert_threshold_percent": 5.0,
                "update_interval_seconds": 60,
                "price_history_days": 7,
            },
            "apis": {
                "binance": "https://api.binance.com/api/v3/ticker/price",
                "coinbase": "https://api.coinbase.com/v2/prices/{}-USD/spot",
                "coingecko": "https://api.coingecko.com/api/v3/simple/price",
            },
        }

        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r") as f:
                    return json.load(f)
        except Exception as e:
            print(f"配置文件加载失败，使用默认配置: {e}")

        return default_config

    async def fetch_price(self, session: aiohttp.ClientSession, symbol: str) -> Optional[float]:
        """获取单个币种价格"""
        try:
            url = f"{self.config['apis']['binance']}?symbol={symbol}"
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return float(data["price"])
        except Exception as e:
            print(f"获取 {symbol} 价格失败: {e}")
        return None

    async def update_prices(self):
        """更新所有监控币种的价格"""
        async with aiohttp.ClientSession() as session:
            tasks = []
            for symbol in self.config["monitoring"]["symbols"]:
                tasks.append(self.fetch_price(session, symbol))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, symbol in enumerate(self.config["monitoring"]["symbols"]):
                price = results[i]
                if isinstance(price, (int, float)):
                    old_price = self.prices.get(symbol)
                    self.prices[symbol] = price

                    # 检查价格变化是否超过阈值
                    if old_price:
                        change_percent = abs((price - old_price) / old_price * 100)
                        if change_percent >= self.config["monitoring"]["alert_threshold_percent"]:
                            alert_msg = (
                                f"🚨 价格预警: {symbol}\n"
                                f"价格变化: {change_percent:.2f}%\n"
                                f"旧价格: ${old_price:.2f}\n"
                                f"新价格: ${price:.2f}\n"
                                f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                            )
                            self.alerts.append(alert_msg)
                            print(alert_msg)

    def generate_report(self) -> str:
        """生成市场报告"""
        if not self.prices:
            return "暂无市场数据"

        report_lines = ["📊 加密货币市场报告"]
        report_lines.append(f"更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("=" * 40)

        for symbol, price in sorted(self.prices.items()):
            report_lines.append(f"{symbol}: ${price:.2f}")

        report_lines.append("=" * 40)

        if self.alerts:
            report_lines.append("🔔 最新预警:")
            for alert in self.alerts[-3:]:  # 显示最近3个预警
                report_lines.append(f"- {alert.split('时间:')[0].strip()}")

        return "\n".join(report_lines)

    async def run(self, duration_hours: int = 24):
        """运行监控"""
        print("🚀 启动加密货币市场监控系统")
        print(f"监控币种: {', '.join(self.config['monitoring']['symbols'])}")
        print(f"更新间隔: {self.config['monitoring']['update_interval_seconds']}秒")
        print(f"预警阈值: {self.config['monitoring']['alert_threshold_percent']}%")
        print("=" * 50)

        start_time = time.time()
        end_time = start_time + duration_hours * 3600

        while time.time() < end_time:
            try:
                await self.update_prices()
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 价格更新完成")

                # 每小时生成一次完整报告
                if int(time.time() - start_time) % 3600 < 60:
                    report = self.generate_report()
                    print("\n" + report + "\n")

                    # 保存报告到文件
                    report_file = os.path.join(
                        os.path.dirname(os.path.dirname(__file__)),
                        "logs",
                        f'market_report_{datetime.now().strftime("%Y%m%d_%H%M")}.txt',
                    )
                    with open(report_file, "w") as f:
                        f.write(report)

                await asyncio.sleep(self.config["monitoring"]["update_interval_seconds"])

            except KeyboardInterrupt:
                print("\n🛑 监控系统被用户中断")
                break
            except Exception as e:
                print(f"监控循环出错: {e}")
                await asyncio.sleep(30)  # 出错后等待30秒重试

        # 最终报告
        final_report = self.generate_report()
        print("\n" + "=" * 50)
        print("📋 最终市场报告")
        print(final_report)

        return final_report


def main():
    """主函数"""
    monitor = MarketMonitor()

    # 创建日志目录
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)

    try:
        # 运行监控24小时
        asyncio.run(monitor.run(duration_hours=24))
    except KeyboardInterrupt:
        print("\n👋 监控系统已停止")
    except Exception as e:
        print(f"系统错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
