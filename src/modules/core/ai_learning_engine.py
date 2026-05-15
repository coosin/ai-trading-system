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
from pathlib import Path

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

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TradingLesson":
        raw_type = str(data.get("lesson_type") or LessonType.MARKET_INSIGHT.value)
        try:
            lesson_type = LessonType(raw_type)
        except Exception:
            lesson_type = LessonType.MARKET_INSIGHT
        ts = data.get("timestamp")
        try:
            timestamp = datetime.fromisoformat(str(ts)) if ts else datetime.now()
        except Exception:
            timestamp = datetime.now()
        return cls(
            id=str(data.get("id") or f"lesson_{datetime.now().timestamp()}"),
            lesson_type=lesson_type,
            title=str(data.get("title") or ""),
            content=str(data.get("content") or ""),
            context=dict(data.get("context") or {}),
            impact_score=float(data.get("impact_score", 0.0) or 0.0),
            confidence=float(data.get("confidence", 0.0) or 0.0),
            timestamp=timestamp,
            times_applied=int(data.get("times_applied", 0) or 0),
            effectiveness=float(data.get("effectiveness", 0.0) or 0.0),
        )


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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "total_pnl": self.total_pnl,
            "lessons_learned": [l.to_dict() for l in self.lessons_learned],
            "key_insights": list(self.key_insights or []),
            "recommendations": list(self.recommendations or []),
            "next_steps": list(self.next_steps or []),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LearningReport":
        def _dt(key: str) -> datetime:
            try:
                return datetime.fromisoformat(str(data.get(key)))
            except Exception:
                return datetime.now()

        lessons = []
        for item in list(data.get("lessons_learned") or []):
            if isinstance(item, dict):
                try:
                    lessons.append(TradingLesson.from_dict(item))
                except Exception:
                    continue
        return cls(
            period_start=_dt("period_start"),
            period_end=_dt("period_end"),
            total_trades=int(data.get("total_trades", 0) or 0),
            winning_trades=int(data.get("winning_trades", 0) or 0),
            losing_trades=int(data.get("losing_trades", 0) or 0),
            win_rate=float(data.get("win_rate", 0.0) or 0.0),
            total_pnl=float(data.get("total_pnl", 0.0) or 0.0),
            lessons_learned=lessons,
            key_insights=list(data.get("key_insights") or []),
            recommendations=list(data.get("recommendations") or []),
            next_steps=list(data.get("next_steps") or []),
        )


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
            "top_workflow_stage": None,
            "top_workflow_status": None,
            "recommendations": [],
            "updated_at": None,
        }
        self._self_review_summary: Dict[str, Any] = {
            "lesson_summary": None,
            "mistake_tags": [],
            "self_review_score": None,
            "updated_at": None,
        }
        self._last_tuning_summary: Dict[str, Any] = {
            "applied": [],
            "pending": [],
            "rejected": [],
            "updated_at": None,
        }
        self._weekly_review_summary: Dict[str, Any] = {
            "week_key": None,
            "review_markdown": None,
            "generated_at": None,
        }
        self._learning_analytics_summary: Dict[str, Any] = {
            "study_modules": {},
            "retrieval_accuracy": 0.0,
            "research_conversion_rate": 0.0,
            "review_completion_score": 0.0,
            "updated_at": None,
        }
        self._retrieval_deck_summary: Dict[str, Any] = {
            "generated_at": None,
            "cards": [],
        }
        self._state_file = self._resolve_state_file()
        
        logger.info("✅ AI学习引擎初始化完成")

    def _resolve_state_file(self) -> Path:
        try:
            cm = self.config_manager
            if cm is not None and hasattr(cm, "get_config_sync"):
                base = cm.get_config_sync("paths", "learning_path", None)
                if base:
                    return Path(str(base)) / "learning_state.json"
        except Exception:
            pass
        return Path("data/learning/learning_state.json")

    def _serialize_state(self) -> Dict[str, Any]:
        max_lessons = int(self.config.get("max_lessons_kept", 200) or 200)
        return {
            "version": 1,
            "saved_at": datetime.now().isoformat(),
            "lessons": [lesson.to_dict() for lesson in self.lessons[-max_lessons:]],
            "learning_reports": [report.to_dict() for report in self.learning_reports[-30:]],
            "trace_feedback": dict(self._trace_feedback_summary or {}),
            "self_review": dict(self._self_review_summary or {}),
            "tuning_governance": dict(self._last_tuning_summary or {}),
            "weekly_review": dict(self._weekly_review_summary or {}),
            "learning_analytics": dict(self._learning_analytics_summary or {}),
            "retrieval_deck": dict(self._retrieval_deck_summary or {}),
        }

    def _persist_learning_state_sync(self) -> None:
        try:
            path = self._state_file
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(self._serialize_state(), ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
        except Exception as e:
            logger.debug("持久化 AI 学习状态失败: %s", e)

    async def _load_persisted_learning_state(self) -> None:
        path = self._state_file
        try:
            if not path.is_file():
                return
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return

            loaded_lessons: List[TradingLesson] = []
            seen_ids = set()
            for item in list(payload.get("lessons") or []):
                if not isinstance(item, dict):
                    continue
                try:
                    lesson = TradingLesson.from_dict(item)
                except Exception:
                    continue
                if lesson.id in seen_ids:
                    continue
                seen_ids.add(lesson.id)
                loaded_lessons.append(lesson)
            max_lessons = int(self.config.get("max_lessons_kept", 200) or 200)
            self.lessons = sorted(loaded_lessons, key=lambda l: l.timestamp)[-max_lessons:]

            loaded_reports: List[LearningReport] = []
            for item in list(payload.get("learning_reports") or []):
                if isinstance(item, dict):
                    try:
                        loaded_reports.append(LearningReport.from_dict(item))
                    except Exception:
                        continue
            self.learning_reports = sorted(loaded_reports, key=lambda r: r.period_end)[-30:]

            for attr, key in (
                ("_trace_feedback_summary", "trace_feedback"),
                ("_self_review_summary", "self_review"),
                ("_last_tuning_summary", "tuning_governance"),
                ("_weekly_review_summary", "weekly_review"),
                ("_learning_analytics_summary", "learning_analytics"),
                ("_retrieval_deck_summary", "retrieval_deck"),
            ):
                value = payload.get(key)
                if isinstance(value, dict):
                    setattr(self, attr, value)
            if self.learning_reports and not (self._learning_analytics_summary or {}).get("updated_at"):
                self._learning_analytics_summary = self._build_learning_analytics(self.learning_reports[-1])
            logger.info("✅ 已恢复 AI 学习状态: lessons=%s reports=%s path=%s", len(self.lessons), len(self.learning_reports), path)
        except Exception as e:
            logger.warning("恢复 AI 学习状态失败: %s", e)

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
        await self._load_persisted_learning_state()
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
        self._persist_learning_state_sync()
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
                await self._update_strategy_learning_governance()
                await self.generate_weekly_research_review()
                await self.generate_retrieval_practice_deck()

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
                    "top_workflow_stage": None,
                    "top_workflow_status": None,
                    "recommendations": [],
                    "updated_at": datetime.now().isoformat(),
                }
                return

            top_guard = ((analysis.get("top_guard_reasons") or [None])[0] if isinstance(analysis.get("top_guard_reasons"), list) and (analysis.get("top_guard_reasons") or []) else None)
            top_exec = ((analysis.get("top_execution_failures") or [None])[0] if isinstance(analysis.get("top_execution_failures"), list) and (analysis.get("top_execution_failures") or []) else None)
            top_rec = ((analysis.get("top_reconciliation_blocks") or [None])[0] if isinstance(analysis.get("top_reconciliation_blocks"), list) and (analysis.get("top_reconciliation_blocks") or []) else None)
            top_stage = ((analysis.get("top_workflow_stages") or [None])[0] if isinstance(analysis.get("top_workflow_stages"), list) and (analysis.get("top_workflow_stages") or []) else None)
            top_status = ((analysis.get("top_workflow_statuses") or [None])[0] if isinstance(analysis.get("top_workflow_statuses"), list) and (analysis.get("top_workflow_statuses") or []) else None)

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
            if isinstance(top_stage, dict) and str(top_stage.get("key") or "") == "reconciliation":
                recommendations.append("近期决策经常停在 reconciliation 阶段，优先修复本地持仓同步和孤儿订单清理，再考虑放宽策略动作。")
            if isinstance(top_status, dict) and str(top_status.get("key") or "") in {"reconcile_blocked", "blocked"}:
                recommendations.append("workflow 主要卡在 blocked/reconcile_blocked，说明当前问题偏执行治理而不是策略信号不足。")

            self._trace_feedback_summary = {
                "sample_size": sample_size,
                "guard_rejected": guard_rejected,
                "execution_failed": execution_failed,
                "reconciliation_blocked": reconciliation_blocked,
                "top_guard_reason": top_guard,
                "top_execution_failure": top_exec,
                "top_reconciliation_block": top_rec,
                "top_workflow_stage": top_stage,
                "top_workflow_status": top_status,
                "recommendations": recommendations[:6],
                "updated_at": datetime.now().isoformat(),
            }
            self._self_review_summary = {
                "lesson_summary": self._build_trace_lesson_summary(sample_size, top_guard, top_exec, top_rec, top_stage, top_status),
                "mistake_tags": self._build_trace_mistake_tags(top_guard, top_exec, top_rec, top_stage, top_status),
                "self_review_score": round(max(0.0, 1.0 - ((guard_rejected + execution_failed + reconciliation_blocked) / max(sample_size, 1))), 4),
                "updated_at": datetime.now().isoformat(),
            }
            await self._persist_trace_learning_snapshot()
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
        
        self._persist_learning_state_sync()
        logger.info(f"💡 新经验: [{lesson.lesson_type.value}] {lesson.title}")

    def _build_trace_lesson_summary(
        self,
        sample_size: int,
        top_guard: Optional[Dict[str, Any]],
        top_exec: Optional[Dict[str, Any]],
        top_rec: Optional[Dict[str, Any]],
        top_stage: Optional[Dict[str, Any]],
        top_status: Optional[Dict[str, Any]],
    ) -> str:
        parts = [f"最近 {sample_size} 条决策样本已复盘"]
        if isinstance(top_guard, dict) and top_guard.get("key"):
            parts.append(f"主要门控原因是 {top_guard.get('key')}")
        if isinstance(top_exec, dict) and top_exec.get("key"):
            parts.append(f"主要执行失败是 {top_exec.get('key')}")
        if isinstance(top_rec, dict) and top_rec.get("key"):
            parts.append(f"主要对账阻断是 {top_rec.get('key')}")
        if isinstance(top_stage, dict) and top_stage.get("key"):
            parts.append(f"主要停留阶段是 {top_stage.get('key')}")
        if isinstance(top_status, dict) and top_status.get("key"):
            parts.append(f"主要 workflow 状态是 {top_status.get('key')}")
        return "；".join(parts)

    def _build_trace_mistake_tags(
        self,
        top_guard: Optional[Dict[str, Any]],
        top_exec: Optional[Dict[str, Any]],
        top_rec: Optional[Dict[str, Any]],
        top_stage: Optional[Dict[str, Any]],
        top_status: Optional[Dict[str, Any]],
    ) -> List[str]:
        tags: List[str] = []
        for item in (top_guard, top_exec, top_rec, top_stage, top_status):
            if isinstance(item, dict):
                key = str(item.get("key") or "").strip()
                if key:
                    tags.append(key)
        return tags[:8]

    async def _persist_trace_learning_snapshot(self) -> None:
        mm = self.memory_manager
        if mm is None or not hasattr(mm, "add_memory"):
            return
        summary = str((self._self_review_summary or {}).get("lesson_summary") or "").strip()
        if not summary:
            return
        await mm.add_memory(
            memory_type="weekly_lesson",
            content=summary,
            source_module="ai_learning_engine",
            importance=0.78,
            metadata={
                "kind": "trace_learning_snapshot",
                "mistake_tags": list((self._self_review_summary or {}).get("mistake_tags") or []),
                "self_review_score": (self._self_review_summary or {}).get("self_review_score"),
            },
        )
    
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
            self._learning_analytics_summary = self._build_learning_analytics(report)
            self._persist_learning_state_sync()
            
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
            if self.memory_manager and hasattr(self.memory_manager, "add_memory"):
                await self.memory_manager.add_memory(
                    memory_type="weekly_lesson",
                    content="\n".join(report.key_insights + report.recommendations[:3]),
                    source_module="ai_learning_engine",
                    importance=0.8,
                    metadata={
                        "kind": "learning_report",
                        "period_start": period_start.isoformat(),
                        "period_end": now.isoformat(),
                        "total_trades": report.total_trades,
                        "win_rate": report.win_rate,
                        "total_pnl": report.total_pnl,
                    },
                )
            if self.memory_manager and hasattr(self.memory_manager, "save_knowledge_document"):
                await self.memory_manager.save_knowledge_document(
                    title=f"Learning Report {now.strftime('%Y-%m-%d %H:%M')}",
                    content="\n".join(report.key_insights + report.recommendations + report.next_steps),
                    knowledge_type="learning_report",
                    metadata={
                        "period_start": period_start.isoformat(),
                        "period_end": now.isoformat(),
                        "win_rate": report.win_rate,
                        "total_pnl": report.total_pnl,
                    },
                )
            
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

            suggestions: List[Dict[str, Any]] = []
            cm = self.config_manager
            cur = await cm.get_config("ai_core_runtime", {}) if (cm is not None and hasattr(cm, "get_config")) else {}
            if len(risk_lessons) >= 3:
                cur_open_c = float((cur or {}).get("ai_core_min_confidence_to_open", 0.72) or 0.72)
                cur_mf = float((cur or {}).get("default_max_margin_fraction", 0.30) or 0.30)
                suggestions.extend(
                    [
                        {
                            "section": "ai_core_runtime",
                            "key": "ai_core_min_confidence_to_open",
                            "old": cur_open_c,
                            "new": min(0.86, max(0.65, cur_open_c + 0.02)),
                            "reason": f"risk_lessons={len(risk_lessons)}",
                            "expected_impact": "降低低质量开仓",
                        },
                        {
                            "section": "ai_core_runtime",
                            "key": "default_max_margin_fraction",
                            "old": cur_mf,
                            "new": min(0.55, max(0.08, cur_mf * 0.90)),
                            "reason": f"risk_lessons={len(risk_lessons)}",
                            "expected_impact": "降低保证金暴露",
                        },
                    ]
                )
            if len(timing_lessons) >= 3:
                cur_rr = float((cur or {}).get("min_rr_to_trade", 1.2) or 1.2)
                cur_edge = float((cur or {}).get("edge_min_net_reward_pct", 0.003) or 0.003)
                suggestions.extend(
                    [
                        {
                            "section": "ai_core_runtime",
                            "key": "min_rr_to_trade",
                            "old": cur_rr,
                            "new": min(2.10, max(0.9, cur_rr + 0.05)),
                            "reason": f"timing_lessons={len(timing_lessons)}",
                            "expected_impact": "提高盈亏比要求",
                        },
                        {
                            "section": "ai_core_runtime",
                            "key": "edge_min_net_reward_pct",
                            "old": cur_edge,
                            "new": min(0.012, max(0.0015, cur_edge + 0.001)),
                            "reason": f"timing_lessons={len(timing_lessons)}",
                            "expected_impact": "提高净边际门槛",
                        },
                    ]
                )

            gov = getattr(getattr(self, "main_controller", None), "tuning_governance", None)
            result = {"applied": [], "pending": [], "rejected": []}
            if suggestions and gov is not None and hasattr(gov, "evaluate_and_apply"):
                result = await gov.evaluate_and_apply(suggestions, source="ai_learning_engine")
            elif suggestions:
                result["pending"] = list(suggestions)
            self._last_tuning_summary = {
                **result,
                "updated_at": datetime.now().isoformat(),
            }

            if self.memory_manager and hasattr(self.memory_manager, "add_memory"):
                for item in result.get("applied", []):
                    await self.memory_manager.add_memory(
                        memory_type="approved_rule_change",
                        content=f"{item.get('section')}.{item.get('key')} -> {item.get('new')}",
                        source_module="ai_learning_engine",
                        importance=0.82,
                        metadata={"kind": "approved_rule_change", **item},
                    )
                for item in result.get("rejected", []):
                    await self.memory_manager.add_memory(
                        memory_type="rejected_rule_change",
                        content=f"{item.get('section')}.{item.get('key')} rejected",
                        source_module="ai_learning_engine",
                        importance=0.76,
                        metadata={"kind": "rejected_rule_change", **item},
                    )
                for item in result.get("pending", []):
                    await self.memory_manager.add_memory(
                        memory_type="tuning_attempt",
                        content=f"{item.get('section')}.{item.get('key')} pending review",
                        source_module="ai_learning_engine",
                        importance=0.7,
                        metadata={"kind": "tuning_attempt", **item},
                    )

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
                logger.info(
                    "🔧 受控调优建议: total=%s applied=%s pending=%s rejected=%s",
                    len(suggestions),
                    len(result.get("applied", [])),
                    len(result.get("pending", [])),
                    len(result.get("rejected", [])),
                )
                
        except Exception as e:
            logger.error(f"优化决策规则失败: {e}")

    async def _update_strategy_learning_governance(self) -> None:
        mc = getattr(self, "main_controller", None)
        sm = getattr(mc, "strategy_manager", None) if mc else None
        if sm is None or not hasattr(sm, "set_strategy_governance_state"):
            return
        recent_lessons = [
            l for l in self.lessons
            if l.timestamp >= datetime.now() - timedelta(days=7)
        ]
        if not recent_lessons:
            return
        grouped: Dict[str, Dict[str, float]] = defaultdict(lambda: {"positive": 0.0, "negative": 0.0, "count": 0.0})
        for lesson in recent_lessons:
            strategy = str((lesson.context or {}).get("strategy") or "").strip()
            if not strategy:
                continue
            bucket = grouped[strategy]
            bucket["count"] += 1.0
            if float(lesson.impact_score or 0.0) >= 0:
                bucket["positive"] += 1.0
            else:
                bucket["negative"] += 1.0
        for strategy_id, stats in grouped.items():
            total = max(1.0, stats["count"])
            neg_ratio = stats["negative"] / total
            pos_ratio = stats["positive"] / total
            if neg_ratio >= 0.6 and stats["negative"] >= 2:
                try:
                    from src.modules.core.strategy_manager import StrategyLifecycleStage

                    sm.set_strategy_governance_state(
                        strategy_id,
                        stage=StrategyLifecycleStage.DEGRADED,
                        live_drift_status="degraded",
                        reason=f"learning_engine_negative_ratio={neg_ratio:.2f}",
                    )
                except Exception:
                    continue
            elif pos_ratio >= 0.6 and stats["positive"] >= 2:
                sm.set_strategy_governance_state(
                    strategy_id,
                    live_drift_status="healthy",
                    reason=f"learning_engine_positive_ratio={pos_ratio:.2f}",
                )

    def _build_learning_analytics(self, report: LearningReport) -> Dict[str, Any]:
        lessons = list(report.lessons_learned or [])
        positive = len([l for l in lessons if float(l.impact_score or 0.0) > 0])
        total = max(1, len(lessons))
        retrieval_accuracy = round(float(positive) / float(total), 4)
        review_completion_score = 1.0 if lessons else 0.0
        research_conversion_rate = 0.0
        try:
            mc = getattr(self, "main_controller", None)
            sm = getattr(mc, "strategy_manager", None) if mc else None
            if sm is not None:
                profiles = [
                    sm.get_strategy_governance_profile(sid)
                    for sid in list(getattr(sm, "strategy_configs", {}).keys())
                    if hasattr(sm, "get_strategy_governance_profile")
                ]
                liveish = [
                    p for p in profiles
                    if str(p.get("stage") or "") in {"limited_live", "scaled_live"}
                ]
                research_conversion_rate = round(float(len(liveish)) / float(max(1, len(profiles))), 4)
        except Exception:
            research_conversion_rate = 0.0
        study_modules = {
            "market_microstructure": len([l for l in lessons if l.lesson_type in {LessonType.TIMING_LESSON, LessonType.MARKET_INSIGHT}]),
            "strategy_logic": len([l for l in lessons if l.lesson_type in {LessonType.SUCCESS_PATTERN, LessonType.FAILURE_PATTERN}]),
            "risk_management": len([l for l in lessons if l.lesson_type == LessonType.RISK_LESSON]),
            "execution_engineering": int((self._trace_feedback_summary or {}).get("execution_failed", 0) or 0),
            "research_governance": int((self._trace_feedback_summary or {}).get("reconciliation_blocked", 0) or 0),
        }
        return {
            "study_modules": study_modules,
            "retrieval_accuracy": retrieval_accuracy,
            "research_conversion_rate": research_conversion_rate,
            "review_completion_score": review_completion_score,
            "updated_at": datetime.now().isoformat(),
        }

    async def generate_weekly_research_review(self, force: bool = False) -> Optional[Dict[str, Any]]:
        now = datetime.now()
        year, week, _ = now.isocalendar()
        week_key = f"{year}-W{int(week):02d}"
        if (not force) and self._weekly_review_summary.get("week_key") == week_key:
            return dict(self._weekly_review_summary)
        report = self.learning_reports[-1] if self.learning_reports else None
        analytics = dict(self._learning_analytics_summary or {})
        review_markdown = self._render_weekly_review_template(
            week_key=week_key,
            report=report,
            analytics=analytics,
        )
        self._weekly_review_summary = {
            "week_key": week_key,
            "review_markdown": review_markdown,
            "workflow_focus": {
                "top_workflow_stage": (self._trace_feedback_summary or {}).get("top_workflow_stage"),
                "top_workflow_status": (self._trace_feedback_summary or {}).get("top_workflow_status"),
                "top_reconciliation_block": (self._trace_feedback_summary or {}).get("top_reconciliation_block"),
            },
            "generated_at": now.isoformat(),
        }
        self._persist_learning_state_sync()
        mm = self.memory_manager
        if mm is not None and hasattr(mm, "save_knowledge_document"):
            await mm.save_knowledge_document(
                title=f"Weekly Research Review {week_key}",
                content=review_markdown,
                knowledge_type="weekly_research_review",
                metadata={
                    "week_key": week_key,
                    "generated_at": now.isoformat(),
                    "workflow_focus": (self._weekly_review_summary or {}).get("workflow_focus"),
                },
            )
        return dict(self._weekly_review_summary)

    async def generate_retrieval_practice_deck(self, limit: int = 10) -> Dict[str, Any]:
        cards: List[Dict[str, Any]] = []
        seen = set()
        for lesson in sorted(self.lessons, key=lambda x: x.timestamp, reverse=True):
            question = f"{lesson.title} 这条经验最重要的交易含义是什么？"
            answer = lesson.content
            if question in seen:
                continue
            seen.add(question)
            cards.append(
                {
                    "question": question,
                    "answer": answer,
                    "lesson_type": lesson.lesson_type.value,
                    "strategy": str((lesson.context or {}).get("strategy") or ""),
                }
            )
            if len(cards) >= max(3, min(int(limit or 10), 20)):
                break
        if len(cards) < 3:
            cards.extend(
                [
                    {
                        "question": "这个策略赚的是什么钱？",
                        "answer": "回答结构来源、参与者行为和适用 regime，而不是只说指标。",
                        "lesson_type": "research_governance",
                        "strategy": "",
                    },
                    {
                        "question": "如果要砍掉它，最先看到什么信号？",
                        "answer": "先看 OOS 失效、live drift 恶化、执行成本上升。",
                        "lesson_type": "research_governance",
                        "strategy": "",
                    },
                    {
                        "question": "近期最常见的执行问题是什么？",
                        "answer": str((self._self_review_summary or {}).get("lesson_summary") or "检查 execution_failed 与 reconciliation_blocked。"),
                        "lesson_type": "execution_review",
                        "strategy": "",
                    },
                ]
            )
        deck = {
            "generated_at": datetime.now().isoformat(),
            "cards": cards[: max(3, min(int(limit or 10), 20))],
        }
        self._retrieval_deck_summary = deck
        self._persist_learning_state_sync()
        mm = self.memory_manager
        if mm is not None and hasattr(mm, "save_knowledge_document"):
            await mm.save_knowledge_document(
                title=f"Retrieval Practice Deck {datetime.now().strftime('%Y-%m-%d')}",
                content=json.dumps(deck, ensure_ascii=False, indent=2),
                knowledge_type="retrieval_practice_deck",
                metadata={"card_count": len(deck["cards"])},
            )
        return dict(deck)

    def _render_weekly_review_template(
        self,
        *,
        week_key: str,
        report: Optional[LearningReport],
        analytics: Dict[str, Any],
    ) -> str:
        template = self._load_weekly_review_template()
        lines = template.splitlines()
        latest = report or LearningReport(
            period_start=datetime.now() - timedelta(days=7),
            period_end=datetime.now(),
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            total_pnl=0.0,
            lessons_learned=[],
            key_insights=[],
            recommendations=[],
            next_steps=[],
        )
        best = [l.title for l in latest.lessons_learned if float(l.impact_score or 0.0) > 0][:3]
        worst = [l.title for l in latest.lessons_learned if float(l.impact_score or 0.0) < 0][:3]
        top_mistakes = list((self._self_review_summary or {}).get("mistake_tags") or [])[:3]
        recs = list(latest.recommendations or [])[:3]
        next_steps = list(latest.next_steps or [])[:3]
        top_exec = (self._trace_feedback_summary or {}).get("top_execution_failure")
        top_exec_label = top_exec.get("key") if isinstance(top_exec, dict) else "暂无"
        top_workflow_stage = (self._trace_feedback_summary or {}).get("top_workflow_stage")
        top_workflow_status = (self._trace_feedback_summary or {}).get("top_workflow_status")
        top_reconciliation_block = (self._trace_feedback_summary or {}).get("top_reconciliation_block")
        workflow_stage_label = top_workflow_stage.get("key") if isinstance(top_workflow_stage, dict) else "暂无"
        workflow_status_label = top_workflow_status.get("key") if isinstance(top_workflow_status, dict) else "暂无"
        top_reconciliation_label = top_reconciliation_block.get("key") if isinstance(top_reconciliation_block, dict) else "暂无"
        applied_items = list((self._last_tuning_summary or {}).get("applied") or [])
        applied_labels = [
            f"{item.get('section')}.{item.get('key')}"
            for item in applied_items
            if isinstance(item, dict) and item.get("section") and item.get("key")
        ]
        mapping = {
            "- 本周重点主题：": f"- 本周重点主题：周研究复盘 {week_key}",
            "- 本周已完成：": f"- 本周已完成：学习报告 {len(self.learning_reports)} 份，经验 {len(self.lessons)} 条",
            "- 本周未完成：": f"- 本周未完成：待人工复核调优 {len((self._last_tuning_summary or {}).get('pending') or [])} 项",
            "- 本周新增概念：": f"- 本周新增概念：{', '.join([k for k, v in (analytics.get('study_modules') or {}).items() if v]) or '暂无'}",
            "- 本周主动回忆正确率：": f"- 本周主动回忆正确率：{float(analytics.get('retrieval_accuracy', 0.0) or 0.0):.1%}",
            "- 本周最容易混淆的三个点：": f"- 本周最容易混淆的三个点：{', '.join(top_mistakes) or '暂无'}",
            "- 下周要重复复习的内容：": f"- 下周要重复复习的内容：{', '.join(top_mistakes or ['risk_review', 'execution_review'])}",
            "- 新提出假设：": f"- 新提出假设：研究转部署转化率 {float(analytics.get('research_conversion_rate', 0.0) or 0.0):.1%}",
            "- 被证伪假设：": f"- 被证伪假设：{', '.join(worst) or '暂无'}",
            "- 继续保留假设：": f"- 继续保留假设：{', '.join(best) or '暂无'}",
            "- 最值得扩样验证的方向：": f"- 最值得扩样验证的方向：{recs[0] if recs else '扩样验证高胜率模式'}",
            "- 最佳交易 3 笔及原因：": f"- 最佳交易 3 笔及原因：{'; '.join(best) or '暂无'}",
            "- 最差交易 3 笔及原因：": f"- 最差交易 3 笔及原因：{'; '.join(worst) or '暂无'}",
            "- 可以避免的亏损：": f"- 可以避免的亏损：{', '.join(top_mistakes) or '暂无'}",
            "- 执行偏差：": f"- 执行偏差：{top_exec_label or '暂无'}",
            "- 决策 workflow 卡点：": f"- 决策 workflow 卡点：stage={workflow_stage_label} / status={workflow_status_label}",
            "- 本周最大风险暴露：": f"- 本周最大风险暴露：亏损交易 {latest.losing_trades} 笔 / 总交易 {latest.total_trades} 笔",
            "- 本周主要对账阻断：": f"- 本周主要对账阻断：{top_reconciliation_label}",
            "- 哪些策略相关性过高：": f"- 哪些策略相关性过高：{recs[1] if len(recs) > 1 else '待补充分组相关性监控'}",
            "- 哪些仓位不该持有：": f"- 哪些仓位不该持有：{recs[2] if len(recs) > 2 else '高冲突/低置信度仓位'}",
            "- 哪些规则该收紧：": f"- 哪些规则该收紧：{', '.join(applied_labels[:2]) if applied_labels else 'min_rr / confidence / margin'}",
            "- 停止做什么：": f"- 停止做什么：{top_mistakes[0] if top_mistakes else '低质量重复开仓'}",
            "- 继续做什么：": f"- 继续做什么：{best[0] if best else '保留高质量 setup'}",
            "- 新增做什么：": f"- 新增做什么：{next_steps[0] if next_steps else '补充 OOS 与实盘偏差复核'}",
            "- 谁负责：": "- 谁负责：AI 学习引擎 / 研究治理 / 人工最终审批",
        }
        out: List[str] = []
        for line in lines:
            out.append(mapping.get(line, line))
        return "\n".join(out).strip()

    def _load_weekly_review_template(self) -> str:
        path = Path(__file__).resolve().parents[3] / "docs" / "templates" / "WEEKLY_RESEARCH_REVIEW.md"
        try:
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return text
        except Exception:
            pass
        return (
            "# 每周研究复盘模板\n\n"
            "## 1. 本周目标\n\n"
            "- 本周重点主题：\n- 本周已完成：\n- 本周未完成：\n"
        )
    
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
            "self_review": dict(self._self_review_summary),
            "tuning_governance": dict(self._last_tuning_summary),
            "weekly_review": dict(self._weekly_review_summary),
            "learning_analytics": dict(self._learning_analytics_summary),
            "retrieval_deck": dict(self._retrieval_deck_summary),
            "config": self.config
        }


    async def cleanup(self):
        """清理资源"""
        pass
