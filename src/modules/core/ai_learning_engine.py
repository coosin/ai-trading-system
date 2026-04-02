"""
AI自我学习和经验总结模块

核心功能：
1. 自动总结交易经验教训
2. 识别交易模式
3. 生成学习报告
4. 自动优化决策规则
"""

import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

logger = logging.getLogger(__name__)


class LessonType(Enum):
    """经验类型"""
    SUCCESS_PATTERN = "success_pattern"      # 成功模式
    FAILURE_PATTERN = "failure_pattern"      # 失败模式
    MARKET_INSIGHT = "market_insight"        # 市场洞察
    RISK_LESSON = "risk_lesson"              # 风险教训
    TIMING_LESSON = "timing_lesson"          # 时序教训
    STRATEGY_ADJUSTMENT = "strategy_adjustment"  # 策略调整


@dataclass
class TradingLesson:
    """交易经验"""
    id: str
    lesson_type: LessonType
    title: str
    content: str
    context: Dict[str, Any]
    impact_score: float  # -1 to 1, 正值表示正面经验，负值表示负面教训
    confidence: float   # 0 to 1
    timestamp: datetime = field(default_factory=datetime.now)
    times_applied: int = 0
    effectiveness: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "lesson_type": self.lesson_type.value,
            "title": self.title,
            "content": self.content,
            "context": self.context,
            "impact_score": self.impact_score,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
            "times_applied": self.times_applied,
            "effectiveness": self.effectiveness
        }


@dataclass
class LearningReport:
    """学习报告"""
    period_start: datetime
    period_end: datetime
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    lessons_learned: List[TradingLesson]
    key_insights: List[str]
    recommendations: List[str]
    next_steps: List[str]


class AILearningEngine:
    """
    AI自我学习引擎
    
    功能：
    1. 分析交易历史，自动提取经验教训
    2. 识别成功和失败的模式
    3. 生成学习报告
    4. 将经验应用到未来的交易决策中
    """
    
    def __init__(self, memory_manager=None, llm_integration=None):
        self.memory_manager = memory_manager
        self.llm_integration = llm_integration
        
        self.lessons: List[TradingLesson] = []
        self.learning_reports: List[LearningReport] = []
        
        self.pattern_cache: Dict[str, List[Dict]] = defaultdict(list)
        
        self.config = {
            "min_trades_for_learning": 5,
            "learning_interval_hours": 6,
            "max_lessons_kept": 200,
            "min_confidence_for_application": 0.7,
            "pattern_similarity_threshold": 0.8
        }
        
        self._running = False
        self._learning_task = None
        
        logger.info("✅ AI学习引擎初始化完成")
    
    async def start(self) -> None:
        """启动学习引擎"""
        self._running = True
        self._learning_task = asyncio.create_task(self._learning_loop())
        logger.info("✅ AI学习引擎已启动")
    
    async def stop(self) -> None:
        """停止学习引擎"""
        self._running = False
        if self._learning_task:
            self._learning_task.cancel()
        logger.info("AI学习引擎已停止")
    
    async def _learning_loop(self) -> None:
        """学习循环"""
        while self._running:
            try:
                await asyncio.sleep(self.config["learning_interval_hours"] * 3600)
                
                logger.info("🧠 开始AI自动学习...")
                
                await self._analyze_and_learn()
                
                await self._generate_learning_report()
                
                await self._optimize_decision_rules()
                
                logger.info("✅ AI学习周期完成")
                
            except Exception as e:
                logger.error(f"学习循环错误: {e}")
                await asyncio.sleep(300)
    
    async def record_trade_result(self, trade: Dict[str, Any]) -> None:
        """记录交易结果用于学习"""
        try:
            symbol = trade.get("symbol", "unknown")
            pnl = trade.get("pnl", 0)
            is_profitable = pnl > 0
            
            trade_context = {
                "symbol": symbol,
                "side": trade.get("side", "long"),
                "entry_price": trade.get("entry_price", 0),
                "exit_price": trade.get("exit_price", 0),
                "pnl": pnl,
                "pnl_percent": trade.get("pnl_percent", 0),
                "hold_duration": trade.get("hold_duration", ""),
                "strategy": trade.get("strategy", "unknown"),
                "reason": trade.get("reason", ""),
                "market_condition": trade.get("market_condition", {}),
                "timestamp": trade.get("timestamp", datetime.now().isoformat()),
                "is_profitable": is_profitable
            }
            
            self.pattern_cache[symbol].append(trade_context)
            
            if len(self.pattern_cache[symbol]) > 100:
                self.pattern_cache[symbol] = self.pattern_cache[symbol][-100:]
            
            if len([t for t in self.pattern_cache[symbol]]) >= self.config["min_trades_for_learning"]:
                lessons = await self._extract_lessons_from_trade(trade_context)
                for lesson in lessons:
                    self._add_lesson(lesson)
                    
        except Exception as e:
            logger.error(f"记录交易结果失败: {e}")
    
    async def _analyze_and_learn(self) -> None:
        """分析和学习"""
        if not self.memory_manager:
            return
        
        try:
            close_trades = []
            
            if hasattr(self.memory_manager, 'enhanced_memory') and self.memory_manager.enhanced_memory:
                close_trades = [
                    m for m in self.memory_manager.enhanced_memory.long_term_memory 
                    if hasattr(m, 'category') and str(m.category.value) == "trade_close"
                    and m.created_at >= datetime.now() - timedelta(hours=self.config["learning_interval_hours"])
                ]
            
            if not close_trades or len(close_trades) < self.config["min_trades_for_learning"]:
                logger.info(f"交易数量不足，跳过学习 (需要{self.config['min_trades_for_learning']}笔，当前{len(close_trades)}笔)")
                return
            
            profitable_trades = [t for t in close_trades if t.metadata.get("is_profitable", False)]
            losing_trades = [t for t in close_trades if not t.metadata.get("is_profitable", False)]
            
            if profitable_trades:
                success_lessons = await self._analyze_successful_trades(profitable_trades)
                for lesson in success_lessons:
                    self._add_lesson(lesson)
            
            if losing_trades:
                failure_lessons = await self._analyze_failed_trades(losing_trades)
                for lesson in failure_lessons:
                    self._add_lesson(lesson)
            
            logger.info(f"📚 学习完成: 成功模式{len(profitable_trades)}笔, 失败模式{len(losing_trades)}笔")
            
        except Exception as e:
            logger.error(f"分析学习失败: {e}")
    
    async def _extract_lessons_from_trade(self, trade_context: Dict) -> List[TradingLesson]:
        """从单笔交易中提取经验"""
        lessons = []
        
        try:
            pnl_percent = trade_context.get("pnl_percent", 0)
            abs_pnl = abs(pnl_percent)
            
            if abs_pnl > 5:
                lesson_type = LessonType.SUCCESS_PATTERN if pnl_percent > 0 else LessonType.FAILURE_PATTERN
                
                direction = "盈利" if pnl_percent > 0 else "亏损"
                
                lesson = TradingLesson(
                    id=f"lesson_{datetime.now().timestamp()}",
                    lesson_type=lesson_type,
                    title=f"{trade_context['symbol']} {direction}{abs_pnl:.1f}%交易",
                    content=self._generate_lesson_content(trade_context),
                    context=trade_context,
                    impact_score=pnl_percent / 10,
                    confidence=min(abs_pnl / 10, 1.0)
                )
                
                lessons.append(lesson)
                
        except Exception as e:
            logger.error(f"提取经验失败: {e}")
        
        return lessons
    
    async def _analyze_successful_trades(self, trades: List) -> List[TradingLesson]:
        """分析成功交易"""
        lessons = []
        
        try:
            patterns = defaultdict(list)
            
            for trade in trades:
                meta = trade.metadata if hasattr(trade, 'metadata') else {}
                strategy = meta.get('strategy', 'unknown')
                patterns[strategy].append(meta)
            
            for strategy, strategy_trades in patterns.items():
                avg_pnl = sum(t.get('pnl', 0) for t in strategy_trades) / len(strategy_trades)
                
                if avg_pnl > 0 and len(strategy_trades) >= 2:
                    common_factors = self._find_common_factors(strategy_trades)
                    
                    lesson = TradingLesson(
                        id=f"success_{datetime.now().timestamp()}",
                        lesson_type=LessonType.SUCCESS_PATTERN,
                        title=f"策略'{strategy}'成功模式",
                        content=f"使用{strategy}策略在{len(strategy_trades)}笔交易中平均盈利{avg_pnl:+.2f} USDT。"
                               f"共同因素: {', '.join(common_factors[:3])}",
                        context={"strategy": strategy, "avg_pnl": avg_pnl, "trade_count": len(strategy_trades)},
                        impact_score=min(avg_pnl / 100, 1.0),
                        confidence=0.8
                    )
                    
                    lessons.append(lesson)
                    
        except Exception as e:
            logger.error(f"分析成功交易失败: {e}")
        
        return lessons
    
    async def _analyze_failed_trades(self, trades: List) -> List[TradingLesson]:
        """分析失败交易"""
        lessons = []
        
        try:
            loss_patterns = defaultdict(int)
            timing_issues = 0
            risk_issues = 0
            
            for trade in trades:
                meta = trade.metadata if hasattr(trade, 'metadata') else {}
                reason = meta.get('reason', '')
                pnl = meta.get('pnl', 0)
                
                if '止损' in reason or 'stop' in reason.lower():
                    risk_issues += 1
                    loss_patterns['触发止损'] += 1
                elif '市场反转' in reason or '趋势改变' in reason:
                    timing_issues += 1
                    loss_patterns['时机不当'] += 1
                elif pnl < -50:
                    loss_patterns['大额亏损'] += 1
            
            if risk_issues >= 2:
                lesson = TradingLesson(
                    id=f"risk_{datetime.now().timestamp()}",
                    lesson_type=LessonType.RISK_LESSON,
                    title="风险控制不足",
                    content=f"近期{risk_issues}笔交易因触发止损而亏损。建议: "
                           f"1. 更严格的入场筛选; 2. 减少仓位大小; 3. 更宽的止损距离",
                    context={"issue_count": risk_issues},
                    impact_score=-0.7,
                    confidence=0.85
                )
                lessons.append(lesson)
            
            if timing_issues >= 2:
                lesson = TradingLesson(
                    id=f"timing_{datetime.now().timestamp()}",
                    lesson_type=LessonType.TIMING_LESSON,
                    title="入场/出场时机问题",
                    content=f"近期{timing_issues}笔交易因市场反转而亏损。建议: "
                           f"1. 等待更明确的信号; 2. 使用多时间框架确认; 3. 关注市场情绪变化",
                    context={"issue_count": timing_issues},
                    impact_score=-0.6,
                    confidence=0.75
                )
                lessons.append(lesson)
                
        except Exception as e:
            logger.error(f"分析失败交易失败: {e}")
        
        return lessons
    
    def _find_common_factors(self, trades: List[Dict]) -> List[str]:
        """找出交易的共同因素"""
        factors = []
        
        try:
            symbols = set()
            timeframes = set()
            
            for trade in trades:
                symbol = trade.get('symbol', '')
                if symbol:
                    symbols.add(symbol)
                
                timestamp = trade.get('timestamp', '')
                if timestamp:
                    hour = datetime.fromisoformat(timestamp).hour if isinstance(timestamp, str) else timestamp.hour
                    if 9 <= hour <= 11:
                        timeframes.add("亚洲早盘")
                    elif 14 <= hour <= 17:
                        timeframes.add("欧洲盘")
                    elif 20 <= hour <= 23:
                        timeframes.add("美盘")
            
            if len(symbols) == 1:
                factors.append(f"专注交易{symbols.pop()}")
            
            if len(timeframes) == 1:
                factors.append(f"主要在{timeframes.pop()}交易")
                
        except Exception as e:
            logger.error(f"查找共同因素失败: {e}")
        
        return factors
    
    def _generate_lesson_content(self, trade: Dict) -> str:
        """生成经验内容"""
        pnl = trade.get("pnl_percent", 0)
        symbol = trade.get("symbol", "")
        strategy = trade.get("strategy", "")
        reason = trade.get("reason", "")
        
        direction = "盈利" if pnl > 0 else "亏损"
        
        content = f"{symbol} {direction}{abs(pnl):.2f}%"
        
        if strategy:
            content += f"，使用{strategy}策略"
        
        if reason:
            content += f"，原因: {reason}"
        
        if abs(pnl) > 10:
            content += "。这是一笔大额交易，需要特别关注。"
        
        return content
    
    def _add_lesson(self, lesson: TradingLesson) -> None:
        """添加经验"""
        existing = [l for l in self.lessons if l.content == lesson.content]
        
        if existing:
            existing[0].times_applied += 1
            existing[0].confidence = min(existing[0].confidence + 0.05, 1.0)
        else:
            self.lessons.append(lesson)
            
            if len(self.lessons) > self.config["max_lessons_kept"]:
                self.lessons.sort(key=lambda x: (x.confidence * x.times_applied), reverse=True)
                self.lessons = self.lessons[:self.config["max_lessons_kept"]]
        
        logger.info(f"💡 新经验: [{lesson.lesson_type.value}] {lesson.title}")
    
    async def _generate_learning_report(self) -> Optional[LearningReport]:
        """生成学习报告"""
        try:
            now = datetime.now()
            period_start = now - timedelta(hours=self.config["learning_interval_hours"])
            
            recent_lessons = [l for l in self.lessons if l.timestamp >= period_start]
            
            if not recent_lessons:
                return None
            
            total_pnl = sum(l.context.get("pnl", 0) for l in recent_lessons if l.context.get("pnl"))
            positive_lessons = [l for l in recent_lessons if l.impact_score > 0]
            negative_lessons = [l for l in recent_lessons if l.impact_score < 0]
            
            key_insights = [
                f"本周期共学习{len(recent_lessons)}条经验",
                f"其中{len(positive_lessons)}条正面经验, {len(negative_lessons)}条教训",
                f"总盈亏影响: {total_pnl:+.2f} USDT"
            ]
            
            recommendations = []
            
            if len(negative_lessons) > len(positive_lessons):
                recommendations.append("建议提高交易筛选标准，减少低质量交易")
            
            risk_lessons = [l for l in negative_lessons if l.lesson_type == LessonType.RISK_LESSON]
            if risk_lessons:
                recommendations.append("需要加强风险管理，考虑降低单笔交易风险敞口")
            
            timing_lessons = [l for l in negative_lessons if l.lesson_type == LessonType.TIMING_LESSON]
            if timing_lessons:
                recommendations.append("建议优化入场时机判断，等待更强的确认信号")
            
            next_steps = [
                "继续监控交易表现",
                "应用已学习的经验到未来交易",
                "定期回顾和更新交易规则"
            ]
            
            report = LearningReport(
                period_start=period_start,
                period_end=now,
                total_trades=len(recent_lessons),
                winning_trades=len(positive_lessons),
                losing_trades=len(negative_lessons),
                win_rate=len(positive_lessons) / len(recent_lessons) if recent_lessons else 0,
                total_pnl=total_pnl,
                lessons_learned=recent_lessons[-10:],
                key_insights=key_insights,
                recommendations=recommendations,
                next_steps=next_steps
            )
            
            self.learning_reports.append(report)
            
            if self.memory_manager and hasattr(self.memory_manager, 'enhanced_memory'):
                self.memory_manager.enhanced_memory.save_strategy_optimization(
                    strategy_name="AI自我学习",
                    optimization_type="knowledge",
                    old_params={},
                    new_params={"lessons_learned": len(recent_lessons)},
                    reason=f"学习周期完成: {key_insights[0]}",
                    expected_improvement="应用经验提升交易质量"
                )
            
            logger.info(f"📝 学习报告已生成: 胜率={report.win_rate:.1%}, 盈亏={report.total_pnl:+.2f}")
            
            return report
            
        except Exception as e:
            logger.error(f"生成学习报告失败: {e}")
            return None
    
    async def _optimize_decision_rules(self) -> None:
        """基于学习结果优化决策规则"""
        try:
            recent_lessons = [
                l for l in self.lessons 
                if l.timestamp >= datetime.now() - timedelta(days=1)
                and l.confidence >= self.config["min_confidence_for_application"]
            ]
            
            if not recent_lessons:
                return
            
            risk_lessons = [l for l in recent_lessons if l.lesson_type == LessonType.RISK_LESSON]
            timing_lessons = [l for l in recent_lessons if l.lesson_type == LessonType.TIMING_LESSON]
            
            optimizations = []
            
            if len(risk_lessons) >= 3:
                optimizations.append({
                    "rule": "risk_management",
                    "action": "reduce_position_size",
                    "reason": f"近期{len(risk_lessons)}条风险教训",
                    "expected_impact": "降低最大回撤"
                })
            
            if len(timing_lessons) >= 3:
                optimizations.append({
                    "rule": "entry_timing",
                    "action": "require_stronger_signal",
                    "reason": f"近期{len(timing_lessons)}条时序教训",
                    "expected_impact": "提高胜率"
                })
            
            if optimizations and self.memory_manager:
                for opt in optimizations:
                    self.memory_manager.enhanced_memory.save_strategy_optimization(
                        strategy_name="决策规则优化",
                        optimization_type=opt["rule"],
                        old_params={},
                        new_params={opt["action"]: True},
                        reason=opt["reason"],
                        expected_improvement=opt["expected_impact"]
                    )
                
                logger.info(f"🔧 决策规则优化: {len(optimizations)}项")
                
        except Exception as e:
            logger.error(f"优化决策规则失败: {e}")
    
    def get_relevant_lessons(self, context: Dict[str, Any], limit: int = 5) -> List[TradingLesson]:
        """获取相关的经验"""
        scored_lessons = []
        
        for lesson in self.lessons:
            score = 0
            
            if context.get("symbol") == lesson.context.get("symbol"):
                score += 3
            
            if context.get("strategy") == lesson.context.get("strategy"):
                score += 2
            
            if lesson.impact_score > 0 and context.get("looking_for") == "success":
                score += 2
            elif lesson.impact_score < 0 and context.get("looking_for") == "avoid":
                score += 2
            
            score += lesson.confidence * 2
            score += lesson.times_applied * 0.5
            
            if score > 0:
                scored_lessons.append((score, lesson))
        
        scored_lessons.sort(key=lambda x: x[0], reverse=True)
        
        result = [lesson for _, lesson in scored_lessons[:limit]]
        
        for lesson in result:
            lesson.times_applied += 1
        
        return result
    
    def get_status(self) -> Dict:
        """获取状态"""
        return {
            "running": self._running,
            "total_lessons": len(self.lessons),
            "reports_generated": len(self.learning_reports),
            "recent_lessons": [
                {"type": l.lesson_type.value, "title": l.title, "impact": l.impact_score}
                for l in self.lessons[-5:]
            ],
            "config": self.config
        }
