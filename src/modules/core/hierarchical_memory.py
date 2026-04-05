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
    
    def __init__(self, base_path: str = None):
        if base_path is None:
            base_path = os.environ.get("OPENCLAW_MEMORY_PATH", "/app/workspace/memory")
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
        
        logger.info(f"层次化记忆管理器初始化完成，路径: {self.base_path}")
    
    async def save_daily_memory(self, content: str, date: Optional[datetime] = None):
        """保存每日交易记忆"""
        if date is None:
            date = datetime.now()
        
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


    async def cleanup(self):
        """清理资源"""
        pass
