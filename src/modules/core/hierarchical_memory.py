"""
层次化记忆管理器 - 赋予交易系统记忆和智慧积累能力

记忆层次：
1. 短期记忆 - 当前会话上下文
2. 中期记忆 - 每日/每周交易总结
3. 长期记忆 - 交易经验教训、市场规律
4. 核心认知 - 系统自我认知和用户画像
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
import aiofiles
import asyncio

logger = logging.getLogger(__name__)

from src.modules.memory.memory_schema import base_metadata, kind_tag, symbol_tag, tags


class MemoryLevel:

    async def initialize(self) -> bool:
        """初始化模块"""
        return True

    """记忆层次"""
    SHORT_TERM = "short_term"      # 短期记忆（会话级）
    DAILY = "daily"                # 每日记忆
    WEEKLY = "weekly"              # 每周记忆
    LESSONS = "lessons"            # 经验教训
    INSIGHTS = "insights"          # 市场洞察
    CORE = "core"                  # 核心认知


class HierarchicalMemoryManager:
    """层次化记忆管理器"""
    
    def __init__(self, base_path: str = None, config_manager: Any = None, memory_gateway: Any = None):
        if base_path is None:
            base_path = (
                config_manager.get_path_sync("memory_path", None) if config_manager else None
                or "/app/workspace/memory"
            )
        self.base_path = Path(base_path)
        try:
            self.base_path.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            self.base_path = Path("/tmp/openclaw_memory")
            self.base_path.mkdir(parents=True, exist_ok=True)
            logger.warning(f"使用备用记忆路径: {self.base_path}")
        
        self.daily_path = self.base_path / "daily"
        self.weekly_path = self.base_path / "weekly"
        self.lessons_path = self.base_path / "lessons"
        self.insights_path = self.base_path / "insights"
        
        for path in [self.daily_path, self.weekly_path, self.lessons_path, self.insights_path]:
            try:
                path.mkdir(exist_ok=True)
            except PermissionError:
                logger.warning(f"无法创建目录 {path}")
        
        self.session_context: Dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self.memory_gateway = memory_gateway
        
        logger.info(f"层次化记忆管理器初始化完成，路径: {self.base_path}")
    
    async def save_daily_memory(self, content: str, date: Optional[datetime] = None):
        """保存每日交易记忆"""
        if date is None:
            date = datetime.now()

        # Migrate-to-gateway mode: store as structured memories (single source)
        if self.memory_gateway is not None:
            d = date.strftime("%Y-%m-%d")
            try:
                await self.memory_gateway.add_memory(
                    memory_type="daily_summary",
                    content=str(content or "").strip(),
                    summary=f"每日摘要 {d}",
                    metadata=base_metadata(
                        source_module="hierarchical_memory",
                        kind="daily_summary",
                        extra={"date": d},
                    ),
                    importance=0.7,
                    source_module="hierarchical_memory",
                    tags=tags(kind_tag("summary"), kind_tag("daily")),
                )
                return
            except Exception as e:
                logger.debug(f"写入 daily_summary 到 MemoryGateway 失败，回退写文件: {e}")
        
        filename = f"{date.strftime('%Y-%m-%d')}.md"
        filepath = self.daily_path / filename
        
        async with self._lock:
            async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
                await f.write(content)
        
        logger.info(f"保存每日记忆: {filename}")
    
    async def load_recent_memories(self, days: int = 2) -> List[str]:
        """加载最近几天的记忆"""
        memories = []
        
        for i in range(days):
            date = datetime.now() - timedelta(days=i)
            filename = f"{date.strftime('%Y-%m-%d')}.md"
            filepath = self.daily_path / filename
            
            if filepath.exists():
                async with aiofiles.open(filepath, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    memories.append(content)
        
        return memories
    
    async def save_lesson_learned(self, lesson_type: str, lesson: str, context: str):
        """保存经验教训"""
        if self.memory_gateway is not None:
            try:
                await self.memory_gateway.add_memory(
                    memory_type="lesson_learned",
                    content=f"[{lesson_type}] {lesson}\n上下文: {context}".strip(),
                    summary=f"经验教训 {lesson_type}",
                    metadata=base_metadata(
                        source_module="hierarchical_memory",
                        kind="lesson_learned",
                        extra={"lesson_type": lesson_type, "context": context},
                    ),
                    importance=0.78,
                    source_module="hierarchical_memory",
                    tags=tags(kind_tag("lesson"), kind_tag(lesson_type)),
                )
                return
            except Exception as e:
                logger.debug(f"写入 lesson_learned 到 MemoryGateway 失败，回退写文件: {e}")

        filename = f"{lesson_type}.md"
        filepath = self.lessons_path / filename
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        entry = f"\n## [{timestamp}]\n{context}\n\n**教训**: {lesson}\n"
        
        async with self._lock:
            if not filepath.exists():
                async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
                    await f.write(f"# {lesson_type.replace('_', ' ').title()}\n\n")
            
            async with aiofiles.open(filepath, 'a', encoding='utf-8') as f:
                await f.write(entry)
        
        logger.info(f"保存经验教训: {lesson_type}")
    
    async def save_market_insight(self, symbol: str, insight: str, confidence: float):
        """保存市场洞察"""
        if self.memory_gateway is not None:
            try:
                await self.memory_gateway.add_memory(
                    memory_type="market_observation",
                    content=f"洞察: {symbol} conf={confidence:.2f} {insight}".strip(),
                    summary=f"市场洞察 {symbol}",
                    metadata=base_metadata(
                        source_module="hierarchical_memory",
                        kind="market_insight",
                        symbol=symbol,
                        extra={"confidence": float(confidence)},
                    ),
                    importance=0.6 + 0.3 * float(confidence),
                    source_module="hierarchical_memory",
                    tags=tags(kind_tag("insight"), symbol_tag(symbol)),
                )
                return
            except Exception as e:
                logger.debug(f"写入 market_observation 到 MemoryGateway 失败，回退写文件: {e}")

        filename = f"{symbol.replace('/', '_')}.md"
        filepath = self.insights_path / filename
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        entry = f"\n## [{timestamp}] 置信度: {confidence:.0%}\n{insight}\n"
        
        async with self._lock:
            if not filepath.exists():
                async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
                    await f.write(f"# {symbol} 市场洞察\n\n")
            
            async with aiofiles.open(filepath, 'a', encoding='utf-8') as f:
                await f.write(entry)
        
        logger.info(f"保存市场洞察: {symbol}")
    
    async def consolidate_memories(self):
        """整理记忆 - 从每日记忆中提炼长期记忆"""
        logger.info("开始整理记忆...")
        
        recent_memories = await self.load_recent_memories(7)
        
        if not recent_memories:
            logger.info("没有近期记忆需要整理")
            return
        
        all_content = "\n\n---\n\n".join(recent_memories)
        
        lessons = self._extract_lessons(all_content)
        for lesson_type, lesson, context in lessons:
            await self.save_lesson_learned(lesson_type, lesson, context)
        
        logger.info(f"记忆整理完成，提取了 {len(lessons)} 条经验教训")
    
    def _extract_lessons(self, content: str) -> List[tuple]:
        """从内容中提取经验教训"""
        lessons = []
        
        keywords = {
            "trading_mistakes": ["错误", "失败", "亏损", "止损"],
            "successful_patterns": ["成功", "盈利", "正确", "机会"],
            "risk_management": ["风险", "强平", "爆仓", "仓位"],
            "market_patterns": ["规律", "模式", "趋势", "周期"]
        }
        
        lines = content.split('\n')
        for i, line in enumerate(lines):
            for lesson_type, words in keywords.items():
                if any(word in line for word in words):
                    context_start = max(0, i - 2)
                    context_end = min(len(lines), i + 3)
                    context = '\n'.join(lines[context_start:context_end])
                    lessons.append((lesson_type, line, context))
                    break
        
        return lessons
    
    async def get_memory_summary(self) -> Dict[str, Any]:
        """获取记忆摘要"""
        daily_files = list(self.daily_path.glob("*.md"))
        lesson_files = list(self.lessons_path.glob("*.md"))
        insight_files = list(self.insights_path.glob("*.md"))
        
        return {
            "daily_memories": len(daily_files),
            "lessons_learned": len(lesson_files),
            "market_insights": len(insight_files),
            "latest_memory": daily_files[-1].name if daily_files else None,
            "memory_categories": [f.stem for f in lesson_files]
        }
    
    def set_session_context(self, key: str, value: Any):
        """设置会话上下文"""
        self.session_context[key] = value
    
    def get_session_context(self, key: str) -> Optional[Any]:
        """获取会话上下文"""
        return self.session_context.get(key)
    
    def clear_session_context(self):
        """清除会话上下文"""
        self.session_context.clear()

    # ==================== 交易记录专用方法 ====================
    
    async def save_trade_open(
        self,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        reason: str = "",
        stop_loss: float = None,
        take_profit: float = None,
        strategy: str = ""
    ):
        """保存开仓记录到记忆"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        trade_record = (
            f"\n## [{timestamp}] 开仓\n"
            f"- **交易对**: {symbol}\n"
            f"- **方向**: {'做多' if side == 'long' else '做空'}\n"
            f"- **价格**: {price}\n"
            f"- **数量**: {quantity}\n"
            f"- **策略**: {strategy or 'AI智能决策'}\n"
            f"- **原因**: {reason or '市场分析驱动'}\n"
        )
        
        if stop_loss:
            trade_record += f"- **止损**: {stop_loss}\n"
        if take_profit:
            trade_record += f"- **止盈**: {take_profit}\n"
        
        # 保存到每日记忆
        today = datetime.now()
        existing_memories = await self.load_recent_memories(days=1)
        
        if existing_memories:
            updated_content = existing_memories[0] + trade_record
        else:
            updated_content = f"# {today.strftime('%Y-%m-%d')} 交易记录\n\n{trade_record}"
        
        await self.save_daily_memory(updated_content, today)
        
        logger.info(f"✓ 开仓记录已保存到记忆: {symbol} {'多' if side == 'long' else '空'}")
    
    async def save_trade_close(
        self,
        symbol: str,
        side: str,
        open_price: float,
        close_price: float,
        quantity: float,
        pnl: float = 0,
        pnl_percent: float = 0,
        reason: str = ""
    ):
        """保存平仓记录到记忆"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        result_emoji = "✅ 盈利" if pnl > 0 else "❌ 亏损" if pnl < 0 else "➖ 平局"
        
        trade_record = (
            f"\n## [{timestamp}] 平仓 {result_emoji}\n"
            f"- **交易对**: {symbol}\n"
            f"- **方向**: {'做多' if side == 'long' else '做空'}\n"
            f"- **开仓价**: {open_price}\n"
            f"- **平仓价**: {close_price}\n"
            f"- **数量**: {quantity}\n"
            f"- **盈亏**: {pnl:.4f} ({pnl_percent:.2f}%)\n"
            f"- **原因**: {reason or '触发止盈止损或AI决策'}\n"
        )
        
        # 保存到每日记忆
        today = datetime.now()
        existing_memories = await self.load_recent_memories(days=1)
        
        if existing_memories:
            updated_content = existing_memories[0] + trade_record
        else:
            updated_content = f"# {today.strftime('%Y-%m-%d')} 交易记录\n\n{trade_record}"
        
        await self.save_daily_memory(updated_content, today)
        
        # 同时保存经验教训
        if abs(pnl) > 0:
            if pnl > 0:
                lesson_type = "successful_patterns"
                lesson = f"{symbol}盈利交易：{'做多' if side == 'long' else '做空'}，从{open_price}到{close_price}，盈利{pnl:.4f}"
                context = f"成功交易案例 - {symbol} {side}"
            else:
                lesson_type = "trading_mistakes"
                lesson = f"{symbol}亏损交易：{'做多' if side == 'long' else '做空'}，从{open_price}到{close_price}，亏损{abs(pnl):.4f}"
                context = f"亏损交易反思 - {symbol} {side}"
            
            await self.save_lesson_learned(lesson_type, lesson, context)
        
        logger.info(f"✓ 平仓记录已保存到记忆: {symbol} {result_emoji}")
    
    async def get_trade_history_summary(self, days: int = 7) -> str:
        """
        获取交易历史摘要（用于对话上下文）
        
        从每日记忆中提取交易记录并生成摘要
        """
        memories = await self.load_recent_memories(days=days)
        
        if not memories:
            return "暂无近期交易记录。"
        
        summary_parts = [
            f"# 📊 近 {days} 天交易摘要",
            "",
            "## 交易时间线",
            ""
        ]
        
        total_trades = 0
        wins = 0
        losses = 0
        
        for memory in memories:
            # 简单统计开仓和平仓次数
            total_trades += memory.count("开仓") + memory.count("平仓")
            if "✅ 盈利" in memory:
                wins += memory.count("✅ 盈利")
            if "❌ 亏损" in memory:
                losses += memory.count("❌ 亏损")
        
        win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
        
        summary_parts.extend([
            f"**总交易数**: 约 {total_trades // 2} 笔",
            f"**胜率**: {win_rate:.1f}%",
            f"**盈利笔数**: {wins}",
            f"**亏损笔数**: {losses}",
            "",
            "---",
            "",
            "## 详细记录",
            ""
        ])
        
        # 添加最近3天的详细记录
        for i, memory in enumerate(memories[:3], 1):
            date_match = memory.split('\n')[0] if memory.startswith('#') else f"第{i}天"
            summary_parts.append(f"### {date_match}")
            summary_parts.append("")
            
            # 提取交易记录部分
            lines = memory.split('\n')
            in_trade_section = False
            
            for line in lines:
                if '## [' in line and ('开仓' in line or '平仓' in line):
                    in_trade_section = True
                
                if in_trade_section:
                    summary_parts.append(line)
                    
                    # 一个交易块结束
                    if line.strip() == '' and in_trade_section:
                        in_trade_section = False
            
            summary_parts.append("")
        
        return "\n".join(summary_parts)
    
    async def save_trading_session_summary(
        self,
        session_stats: Dict[str, Any],
        insights: List[str] = None
    ):
        """
        保存交易会话总结
        
        在每个交易日结束时调用，生成当日总结
        """
        today = datetime.now()
        date_str = today.strftime('%Y-%m-%d')
        
        summary = f"# {date_str} 交易日总结\n\n"
        
        summary += "## 📈 今日表现\n\n"
        summary += f"- **总交易次数**: {session_stats.get('total_trades', 0)}\n"
        summary += f"- **胜率**: {session_stats.get('win_rate', 0)}%\n"
        summary += f"- **总盈亏**: {session_stats.get('total_pnl', 0)} USDT\n"
        summary += f"- **最佳交易**: {session_stats.get('best_trade', 0)} USDT\n"
        summary += f"- **最差交易**: {session_stats.get('worst_trade', 0)} USDT\n"
        
        if session_stats.get('max_drawdown'):
            summary += f"- **最大回撤**: {session_stats['max_drawdown']} USDT\n"
        
        summary += "\n## 💡 关键洞察\n\n"
        
        if insights:
            for i, insight in enumerate(insights, 1):
                summary += f"{i}. {insight}\n"
        else:
            summary += "*(待补充)*\n"
        
        summary += "\n## 🎯 明日计划\n\n"
        summary += "*(基于今日表现调整策略)*\n"
        
        # 保存为每日记忆（覆盖或追加）
        await self.save_daily_memory(summary, today)
        
        # 如果有重要教训，也保存到长期记忆
        if session_stats.get('total_pnl', 0) < 0:
            lesson = f"{date_str} 亏损日总结：总亏损{abs(session_stats['total_pnl'])}，需分析原因并调整策略"
            context = f"亏损日 - {date_str} | 交易{session_stats.get('total_trades', 0)}笔"
            await self.save_lesson_learned("trading_mistakes", lesson, context)
        elif session_stats.get('total_pnl', 0) > 0:
            lesson = f"{date_str} 盈利日总结：总盈利{session_stats['total_pnl']}，成功因素值得保持"
            context = f"盈利日 - {date_str} | 胜率{session_stats.get('win_rate', 0)}%"
            await self.save_lesson_learned("successful_patterns", lesson, context)
        
        logger.info(f"✓ 交易日总结已保存: {date_str}")
    
    async def get_relevant_lessons_for_symbol(self, symbol: str) -> List[str]:
        """获取与特定币种相关的经验教训"""
        relevant_lessons = []
        
        lessons_path = self.lessons_path
        
        if not lessons_path.exists():
            return []
        
        for lesson_file in lessons_path.glob("*.md"):
            try:
                content = lesson_file.read_text(encoding='utf-8')
                
                if symbol.replace('/', '_') in content or symbol in content:
                    # 提取相关的教训条目
                    lines = content.split('\n')
                    for i, line in enumerate(lines):
                        if symbol in line or symbol.replace('/', '_') in line:
                            context_start = max(0, i - 1)
                            context_end = min(len(lines), i + 2)
                            relevant_lessons.append('\n'.join(lines[context_start:context_end]))
            except Exception as e:
                logger.warning(f"读取教训文件失败 {lesson_file}: {e}")
        
        return relevant_lessons[-10:]  # 返回最近10条相关教训


    async def cleanup(self):
        """清理资源"""
        pass
