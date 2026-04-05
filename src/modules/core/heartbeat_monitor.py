"""
心跳监控机制 - 主动式系统监控和任务执行
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable, List
from pathlib import Path

logger = logging.getLogger(__name__)


class HeartbeatMonitor:

    async def initialize(self) -> bool:
        """初始化模块"""
        return True

    """心跳监控器"""
    
    def __init__(
        self,
        trading_engine,
        skill_manager,
        memory_manager,
        notification_handler: Optional[Callable] = None,
        interval: int = 1800  # 30分钟
    ):
        self.trading_engine = trading_engine
        self.skill_manager = skill_manager
        self.memory_manager = memory_manager
        self.notification_handler = notification_handler
        self.interval = interval
        
        self._running = False
        self._last_heartbeat: Optional[datetime] = None
        self.heartbeat_count = 0
        self.heartbeat_history: List[Dict[str, Any]] = []
        
        self.tasks = [
            self._check_system_health,
            self._check_positions_risk,
            self._analyze_market_opportunities,
            self._update_memories,
            self._generate_reports,
            self._optimize_system
        ]
        
        logger.info(f"心跳监控器初始化完成，间隔: {interval}秒")
    
    async def start(self):
        """启动心跳监控"""
        self._running = True
        logger.info("💓 心跳监控启动")
        
        while self._running:
            try:
                await self._execute_heartbeat()
                await asyncio.sleep(self.interval)
            except Exception as e:
                logger.error(f"心跳执行错误: {e}", exc_info=True)
                await asyncio.sleep(60)
    
    def stop(self):
        """停止心跳监控"""
        self._running = False
        logger.info("💔 心跳监控停止")
    
    async def _execute_heartbeat(self):
        """执行心跳任务"""
        self.heartbeat_count += 1
        self._last_heartbeat = datetime.now()
        
        logger.info(f"💓 心跳 #{self.heartbeat_count} - {self._last_heartbeat.strftime('%H:%M:%S')}")
        
        context = await self._build_context()
        
        for task in self.tasks:
            try:
                await task(context)
            except Exception as e:
                logger.error(f"心跳任务执行失败 {task.__name__}: {e}")
        
        self._record_heartbeat()
    
    async def _build_context(self) -> Dict[str, Any]:
        """构建执行上下文"""
        return {
            "trading_engine": self.trading_engine,
            "skill_manager": self.skill_manager,
            "memory_manager": self.memory_manager,
            "timestamp": datetime.now().isoformat(),
            "heartbeat_count": self.heartbeat_count
        }
    
    async def _check_system_health(self, context: Dict[str, Any]):
        """检查系统健康"""
        logger.info("🏥 检查系统健康...")
        
        health_report = await self.skill_manager.run_health_check(context)
        
        if health_report["status"] == "critical":
            await self._send_notification(
                "🚨 系统健康检查",
                f"发现严重问题！\n{health_report['summary']}",
                priority="high"
            )
        elif health_report["status"] == "warning":
            await self._send_notification(
                "⚠️ 系统健康检查",
                f"发现警告\n{health_report['summary']}",
                priority="medium"
            )
    
    async def _check_positions_risk(self, context: Dict[str, Any]):
        """检查持仓风险"""
        logger.info("📊 检查持仓风险...")
        
        result = await self.skill_manager.execute_skill("risk_assessment", context)
        
        if result and result.status.value == "failed":
            await self._send_notification(
                "🚨 风险预警",
                result.message,
                priority="critical"
            )
    
    async def _analyze_market_opportunities(self, context: Dict[str, Any]):
        """分析市场机会"""
        logger.info("📈 分析市场机会...")
        
        trading_engine = context.get("trading_engine")
        if not trading_engine:
            return
        
        positions = getattr(trading_engine, 'positions', {})
        
        if len(positions) < 3:
            await self._send_notification(
                "💡 市场机会",
                "当前持仓较少，可以关注新的交易机会",
                priority="low"
            )
    
    async def _update_memories(self, context: Dict[str, Any]):
        """更新记忆系统"""
        logger.info("🧠 更新记忆系统...")
        
        if self.heartbeat_count % 48 == 0:  # 每24小时（48个30分钟）
            logger.info("📚 整理长期记忆...")
            await self.memory_manager.consolidate_memories()
        
        if self.heartbeat_count % 2 == 0:  # 每小时
            await self._save_daily_summary(context)
    
    async def _generate_reports(self, context: Dict[str, Any]):
        """生成报告"""
        logger.info("📝 生成报告...")
        
        if self.heartbeat_count % 48 == 0:  # 每24小时
            await self._generate_daily_report(context)
    
    async def _optimize_system(self, context: Dict[str, Any]):
        """优化系统"""
        logger.info("⚡ 优化系统...")
        
        if self.heartbeat_count % 6 == 0:  # 每3小时
            result = await self.skill_manager.execute_skill("auto_repair", context)
            if result and result.data.get("fixed"):
                logger.info(f"✅ 自动修复了 {len(result.data['fixed'])} 个问题")
    
    async def _save_daily_summary(self, context: Dict[str, Any]):
        """保存每日总结"""
        trading_engine = context.get("trading_engine")
        if not trading_engine:
            return
        
        positions = getattr(trading_engine, 'positions', {})
        balance = getattr(trading_engine, 'balance', 0)
        
        summary = f"""# 交易总结 - {datetime.now().strftime('%Y-%m-%d %H:%M')}

## 账户状态
- 余额: {balance:.2f} USDT
- 持仓数: {len(positions)}

## 持仓详情
"""
        for symbol, pos in positions.items():
            if isinstance(pos, dict):
                summary += f"- {symbol}: {pos.get('side', 'unknown')} {pos.get('quantity', 0)} @ {pos.get('current_price', 0)}\n"
        
        await self.memory_manager.save_daily_memory(summary)
    
    async def _generate_daily_report(self, context: Dict[str, Any]):
        """生成每日报告"""
        result = await self.skill_manager.execute_skill("performance_analysis", context)
        
        if result:
            report = f"""📊 每日交易报告 - {datetime.now().strftime('%Y-%m-%d')}

{result.message}

## 性能指标
- 胜率: {result.data.get('trading', {}).get('win_rate', 0):.1%}
- 盈亏比: {result.data.get('trading', {}).get('profit_factor', 0):.2f}
- 最大回撤: {result.data.get('trading', {}).get('max_drawdown', 0):.1%}

## 建议
{chr(10).join(result.recommendations) if result.recommendations else '暂无'}
"""
            
            await self._send_notification(
                "📊 每日报告",
                report,
                priority="medium"
            )
    
    async def _send_notification(self, title: str, message: str, priority: str = "medium"):
        """发送通知"""
        if self.notification_handler:
            try:
                await self.notification_handler(title, message, priority)
            except Exception as e:
                logger.error(f"发送通知失败: {e}")
        else:
            logger.info(f"📢 [{priority.upper()}] {title}: {message}")
    
    def _record_heartbeat(self):
        """记录心跳"""
        record = {
            "count": self.heartbeat_count,
            "timestamp": self._last_heartbeat.isoformat(),
            "status": "success"
        }
        
        self.heartbeat_history.append(record)
        
        if len(self.heartbeat_history) > 100:
            self.heartbeat_history = self.heartbeat_history[-100:]
    
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        return {
            "running": self._running,
            "heartbeat_count": self.heartbeat_count,
            "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
            "interval": self.interval,
            "history_size": len(self.heartbeat_history)
        }


    async def cleanup(self):
        """清理资源"""
        pass
