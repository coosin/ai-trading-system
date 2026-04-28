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
    
    def __init__(self, memory_manager=None, llm_integration=None, *, config_manager=None):
        self.memory_manager = memory_manager
        self.llm_integration = llm_integration
        self.config_manager = config_manager
        
        self.lessons: List[TradingLesson] = []
        self.learning_reports: List[LearningReport] = []
        
        self.pattern_cache: Dict[str, List[Dict]] = defaultdict(list)
        
        self.config = {
            "min_trades_for_learning": 5,
            "learning_interval_hours": 6,
            "max_lessons_kept": 200,
            "min_confidence_for_application": 0.7,
            "pattern_similarity_threshold": 0.8,
            # Extract lesson when absolute pnl percent reaches this threshold (in percentage points).
            "min_abs_pnl_percent_for_lesson": 0.6,
        }
        
        self._running = False
        self._learning_task = None
        self._trace_feedback_summary: Dict[str, Any] = {
            "sample_size": 0,
            "guard_rejected": 0,
            "execution_failed": 0,
            "reconciliation_blocked": 0,
            "top_guard_reason": None,
            "top_execution_failure": None,
            "top_reconciliation_block": None,
            "recommendations": [],
            "updated_at": None,
        }
        
        logger.info("✅ AI学习引擎初始化完成")

    async def _load_runtime_config(self) -> None:
        """从正式配置入口加载学习引擎阈值，避免仅靠硬编码默认值。"""
        cm = self.config_manager
        if cm is None or not hasattr(cm, "get_config"):
            return
        try:
            cfg = await cm.get_config("ai_learning", {})
            if not isinstance(cfg, dict):
                return
            for k in (
                "min_trades_for_learning",
                "learning_interval_hours",
                "max_lessons_kept",
                "min_confidence_for_application",
                "pattern_similarity_threshold",
                "min_abs_pnl_percent_for_lesson",
            ):
                if cfg.get(k) is not None:
                    self.config[k] = cfg.get(k)
        except Exception as e:
            logger.debug("加载 AI 学习配置失败: %s", e)
    
    async def start(self) -> None:
        """启动学习引擎"""
        await self._load_runtime_config()
        self._running = True
        self._learning_task = asyncio.create_task(self._learning_loop())
        logger.info("✅ AI学习引擎已启动")
    
    async def stop(self) -> None:
        """停止学习引擎"""
        self._running = False
        if self._learning_task:
            self._learning_task.cancel()
            try:
                await self._learning_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning("停止学习任务时出现异常: %s", e)
            finally:
                self._learning_task = None
        logger.info("AI学习引擎已停止")
    
    async def _learning_loop(self) -> None:
        """学习循环"""
        first = True
        interval_sec = float(self.config["learning_interval_hours"]) * 3600.0
        while self._running:
            try:
                # 首周期短等待，便于验收与排障；之后按 learning_interval_hours
                wait = min(120.0, max(45.0, interval_sec)) if first else interval_sec
                first = False
                await asyncio.sleep(wait)

                logger.info(
                    "🧠 开始AI自动学习... (间隔=%.0fs, min_trades=%s)",
                    wait,
                    self.config.get("min_trades_for_learning", 5),
                )

                await self._analyze_and_learn()
                await self._analyze_decision_traces()

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
            pnl_percent = trade.get("pnl_percent", 0)
            try:
                pnl_percent = float(pnl_percent or 0)
            except Exception:
                pnl_percent = 0.0
            # Normalize common formats:
            # - 0.012 => 1.2%
            # - 6.0   => 6.0%
            pnl_percent_norm = pnl_percent * 100.0 if abs(pnl_percent) <= 1.0 else pnl_percent
            
            trade_context = {
                "symbol": symbol,
                "side": trade.get("side", "long"),
                "entry_price": trade.get("entry_price", 0),
                "exit_price": trade.get("exit_price", 0),
                "pnl": pnl,
                "pnl_percent": pnl_percent_norm,
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
            
            # Fast path: capture large enough per-trade lessons immediately.
            direct_lessons = await self._extract_lessons_from_trade(trade_context)
            for lesson in direct_lessons:
                self._add_lesson(lesson)

            if len([t for t in self.pattern_cache[symbol]]) >= self.config["min_trades_for_learning"]:
                lessons = await self._extract_lessons_from_trade(trade_context)
                for lesson in lessons:
                    self._add_lesson(lesson)
                    
        except Exception as e:
            logger.error(f"记录交易结果失败: {e}")

    async def _analyze_decision_traces(self) -> None:
        """分析最近的 decision traces，提取 guard/执行/保护层面的学习反馈。"""
        try:
            mm = self.memory_manager
            mc = getattr(mm, "main_controller", None) if mm is not None else None
            if mc is None:
                mc = getattr(self, "main_controller", None)
            store = getattr(mc, "decision_trace_store", None) if mc is not None else None
            if not store or not hasattr(store, "analyze_recent"):
                return

            analysis = store.analyze_recent(limit=80)
            sm = analysis.get("summary") if isinstance(analysis.get("summary"), dict) else {}
            sample_size = int(sm.get("sample_size", 0) or 0)
            if sample_size <= 0:
                self._trace_feedback_summary = {
                    "sample_size": 0,
                    "guard_rejected": 0,
                    "execution_failed": 0,
                    "reconciliation_blocked": 0,
                    "top_guard_reason": None,
                    "top_execution_failure": None,
                    "top_reconciliation_block": None,
                    "recommendations": [],
                    "updated_at": datetime.now().isoformat(),
                }
                return

            top_guard = ((analysis.get("top_guard_reasons") or [None])[0] if isinstance(analysis.get("top_guard_reasons"), list) and (analysis.get("top_guard_reasons") or []) else None)
            top_exec = ((analysis.get("top_execution_failures") or [None])[0] if isinstance(analysis.get("top_execution_failures"), list) and (analysis.get("top_execution_failures") or []) else None)
            top_rec = ((analysis.get("top_reconciliation_blocks") or [None])[0] if isinstance(analysis.get("top_reconciliation_blocks"), list) and (analysis.get("top_reconciliation_blocks") or []) else None)

            recommendations: List[str] = []
            guard_rejected = int(sm.get("guard_rejected", 0) or 0)
            execution_failed = int(sm.get("execution_failed", 0) or 0)
            reconciliation_blocked = int(sm.get("reconciliation_blocked", 0) or 0)

            if guard_rejected >= max(5, sample_size // 3):
                recommendations.append("近期 guard_rejected 占比较高，建议复核开仓门槛是否过严，特别是 top_guard_reason。")
            if execution_failed >= max(3, sample_size // 5):
                recommendations.append("近期 execution_failed 偏高，建议优先优化执行层/交易所链路，而不是直接放松 AI 开仓条件。")
            if reconciliation_blocked >= max(3, sample_size // 5):
                recommendations.append("近期 reconciliation_blocked 偏高，建议优先处理本地状态一致性与孤儿订单问题。")

            if isinstance(top_guard, dict) and str(top_guard.get("key") or "").startswith("loss_streak_cooldown"):
                recommendations.append("连亏冷静期是主要拒绝原因，说明近期策略环境不稳定，应先降频而不是强行提高开仓率。")
            if isinstance(top_rec, dict) and "side_mismatch" in str(top_rec.get("key") or ""):
                recommendations.append("对账保护主要拦截 side_mismatch，说明 AI 依赖的本地持仓状态仍需进一步稳固。")

            self._trace_feedback_summary = {
                "sample_size": sample_size,
                "guard_rejected": guard_rejected,
                "execution_failed": execution_failed,
                "reconciliation_blocked": reconciliation_blocked,
                "top_guard_reason": top_guard,
                "top_execution_failure": top_exec,
                "top_reconciliation_block": top_rec,
                "recommendations": recommendations[:6],
                "updated_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"分析 decision traces 失败: {e}")
    
    def _collect_recent_close_trades(self) -> List[Any]:
        """
        统一收集「平仓」记忆：兼容旧版 enhanced_memory，以及当前 MemoryGateway→OptimizedMemorySystem。
        返回对象需具备 .metadata (dict) 与 .created_at (datetime)；供 _analyze_successful_trades 使用。
        """
        from types import SimpleNamespace

        window_h = int(self.config.get("learning_interval_hours", 6) or 6)
        cutoff = datetime.now() - timedelta(hours=max(1, window_h))
        out: List[Any] = []
        mm = self.memory_manager
        if mm is None:
            return out

        # --- 旧路径：LLM 集成里挂的 enhanced_memory + long_term_memory ---
        em = getattr(mm, "enhanced_memory", None)
        if em is not None:
            ltm = getattr(em, "long_term_memory", None)
            if ltm:
                for m in ltm:
                    try:
                        cat_v = getattr(getattr(m, "category", None), "value", m.category)
                        if str(cat_v) != "trade_close":
                            continue
                        ca = getattr(m, "created_at", None)
                        if ca is not None and ca < cutoff:
                            continue
                        out.append(m)
                    except Exception:
                        continue
                if out:
                    return out

        # --- 现网：MemoryGateway.memory_backend._memories，metadata.kind == trade_close ---
        try:
            from src.modules.core.optimized_memory_system import MemoryCategory

            backend = getattr(mm, "memory_backend", None)
            memories = getattr(backend, "_memories", None) if backend is not None else None
            if isinstance(memories, dict):
                for entry in memories.values():
                    try:
                        if getattr(entry, "category", None) != MemoryCategory.TRADE_RECORD:
                            continue
                        md_raw = getattr(entry, "metadata", None) or {}
                        md = dict(md_raw)
                        if str(md.get("kind", "")).lower() != "trade_close":
                            continue
                        created = getattr(entry, "created_at", None)
                        if created is None:
                            continue
                        if created < cutoff:
                            continue
                        pnl = float(md.get("pnl", 0) or 0)
                        if "is_profitable" not in md:
                            md["is_profitable"] = pnl > 0
                        if "pnl" not in md:
                            md["pnl"] = pnl
                        out.append(
                            SimpleNamespace(
                                metadata=md,
                                created_at=created,
                                content=getattr(entry, "content", ""),
                            )
                        )
                    except Exception:
                        continue
        except Exception:
            pass

        return out

    async def _analyze_and_learn(self) -> None:
        """分析和学习"""
        if not self.memory_manager:
            return
        
        try:
            close_trades = self._collect_recent_close_trades()
            
            if not close_trades or len(close_trades) < self.config["min_trades_for_learning"]:
                logger.info(f"交易数量不足，跳过学习 (需要{self.config['min_trades_for_learning']}笔，当前{len(close_trades)}笔)")
                return
            
            def _is_win(t: Any) -> bool:
                md = getattr(t, "metadata", None) or {}
                if not isinstance(md, dict):
                    return False
                if "is_profitable" in md:
                    return bool(md.get("is_profitable"))
                try:
                    return float(md.get("pnl", 0) or 0) > 0
                except (TypeError, ValueError):
                    return False

            profitable_trades = [t for t in close_trades if _is_win(t)]
            losing_trades = [t for t in close_trades if not _is_win(t)]
            
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
            pnl_percent = float(trade_context.get("pnl_percent", 0) or 0)
            abs_pnl = abs(pnl_percent)
            min_abs_pct = float(self.config.get("min_abs_pnl_percent_for_lesson", 0.6) or 0.6)

            if abs_pnl >= min_abs_pct:
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

            # 写回策略：优先写到 ConfigManager（可热更新+持久化），其次再落到记忆里做审计。
            applied: List[Dict[str, Any]] = []
            cm = self.config_manager
            if optimizations and cm is not None and hasattr(cm, "set_config"):
                try:
                    # --- 风险教训：降低进场频率/减少噪音单、略微降低仓位预算 ---
                    if len(risk_lessons) >= 3:
                        cur = await cm.get_config("ai_core_runtime", {}) if hasattr(cm, "get_config") else {}
                        try:
                            cur_open_c = float((cur or {}).get("ai_core_min_confidence_to_open", 0.72) or 0.72)
                        except Exception:
                            cur_open_c = 0.72
                        new_open_c = min(0.86, max(0.65, cur_open_c + 0.02))
                        await cm.set_config("ai_core_runtime", "ai_core_min_confidence_to_open", float(new_open_c))
                        applied.append(
                            {
                                "section": "ai_core_runtime",
                                "key": "ai_core_min_confidence_to_open",
                                "old": cur_open_c,
                                "new": new_open_c,
                                "reason": f"risk_lessons={len(risk_lessons)}",
                            }
                        )

                        # 降低可用保证金比例（保守且有边界）
                        try:
                            cur_mf = float((cur or {}).get("default_max_margin_fraction", 0.30) or 0.30)
                        except Exception:
                            cur_mf = 0.30
                        new_mf = min(0.55, max(0.08, cur_mf * 0.90))
                        await cm.set_config("ai_core_runtime", "default_max_margin_fraction", float(new_mf))
                        applied.append(
                            {
                                "section": "ai_core_runtime",
                                "key": "default_max_margin_fraction",
                                "old": cur_mf,
                                "new": new_mf,
                                "reason": f"risk_lessons={len(risk_lessons)}",
                            }
                        )

                    # --- 时机教训：提高净边际/盈亏比门槛，减少“挣得少、亏得多”的单子 ---
                    if len(timing_lessons) >= 3:
                        cur = await cm.get_config("ai_core_runtime", {}) if hasattr(cm, "get_config") else {}
                        try:
                            cur_rr = float((cur or {}).get("min_rr_to_trade", 1.2) or 1.2)
                        except Exception:
                            cur_rr = 1.2
                        new_rr = min(2.10, max(0.9, cur_rr + 0.05))
                        await cm.set_config("ai_core_runtime", "min_rr_to_trade", float(new_rr))
                        applied.append(
                            {"section": "ai_core_runtime", "key": "min_rr_to_trade", "old": cur_rr, "new": new_rr, "reason": f"timing_lessons={len(timing_lessons)}"}
                        )

                        try:
                            cur_edge = float((cur or {}).get("edge_min_net_reward_pct", 0.003) or 0.003)
                        except Exception:
                            cur_edge = 0.003
                        new_edge = min(0.012, max(0.0015, cur_edge + 0.001))
                        await cm.set_config("ai_core_runtime", "edge_min_net_reward_pct", float(new_edge))
                        applied.append(
                            {"section": "ai_core_runtime", "key": "edge_min_net_reward_pct", "old": cur_edge, "new": new_edge, "reason": f"timing_lessons={len(timing_lessons)}"}
                        )
                except Exception as e:
                    logger.error(f"写回配置失败（将仅记录优化建议）: {e}")

            if optimizations and self.memory_manager and getattr(self.memory_manager, "enhanced_memory", None):
                try:
                    for opt in optimizations:
                        self.memory_manager.enhanced_memory.save_strategy_optimization(
                            strategy_name="决策规则优化",
                            optimization_type=opt["rule"],
                            old_params={},
                            new_params={opt["action"]: True},
                            reason=opt["reason"],
                            expected_improvement=opt["expected_impact"]
                        )
                except Exception:
                    pass

            if optimizations:
                logger.info("🔧 决策规则优化: %s项 applied=%s", len(optimizations), len(applied))
                
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
            "trace_feedback": dict(self._trace_feedback_summary),
            "config": self.config
        }


    async def cleanup(self):
        """清理资源"""
        pass
