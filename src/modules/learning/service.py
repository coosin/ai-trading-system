from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class LearningDomainService:
    def __init__(self, main_controller: Any) -> None:
        self.mc = main_controller

    async def overview(self) -> Dict[str, Any]:
        status: Dict[str, Any]
        engine = getattr(self.mc, "ai_learning_engine", None) if self.mc else None
        if engine and hasattr(engine, "get_status"):
            try:
                status = dict(engine.get_status() or {})
            except Exception as exc:
                status = {"degraded": True, "error": str(exc)}
        else:
            status = {"degraded": True, "message": "ai_learning_engine_unavailable"}

        review = await self._build_post_trade_review()
        status["post_trade_review"] = review
        status["coverage_gaps"] = self._learning_coverage_gaps(status, review)
        return status

    async def backfill_lessons(
        self,
        *,
        dry_run: bool = True,
        limit: int = 500,
        generate_report: bool = True,
    ) -> Dict[str, Any]:
        """Convert aggregate post-trade review candidates into learning lessons.

        This is intentionally limited to local learning/memory state. It does
        not alter strategies, orders, positions, or exchange state.
        """
        engine = getattr(self.mc, "ai_learning_engine", None) if self.mc else None
        if not engine or not hasattr(engine, "_add_lesson"):
            return {"success": False, "message": "ai_learning_engine_unavailable"}

        review = await self._build_post_trade_review(limit=limit)
        candidates = list(review.get("candidate_lessons") or [])
        if not candidates:
            return {"success": True, "dry_run": dry_run, "written": 0, "skipped": 0, "review": review}

        try:
            from src.modules.core.ai_learning_engine import LessonType, TradingLesson
        except Exception as exc:
            return {"success": False, "message": f"learning_types_unavailable:{exc}"}

        existing_contents = {
            str(getattr(lesson, "content", "") or "")
            for lesson in list(getattr(engine, "lessons", []) or [])
        }
        written = 0
        skipped = 0
        report_generated = False
        retrieval_deck_generated = False
        prepared: List[Dict[str, Any]] = []
        type_map = {
            "fee_drag": LessonType.RISK_LESSON,
            "win_rate": LessonType.STRATEGY_ADJUSTMENT,
            "symbol_filter": LessonType.RISK_LESSON,
            "exit_reason": LessonType.TIMING_LESSON,
        }
        for item in candidates:
            if not isinstance(item, dict):
                continue
            lesson_type_key = str(item.get("type") or "post_trade_review")
            content = str(item.get("lesson") or "").strip()
            if not content:
                skipped += 1
                continue
            if content in existing_contents:
                skipped += 1
                continue
            evidence = item.get("evidence") if isinstance(item.get("evidence"), (dict, list)) else {}
            lesson = TradingLesson(
                id=f"post_trade_review_{lesson_type_key}_{int(datetime.now().timestamp() * 1000)}",
                lesson_type=type_map.get(lesson_type_key, LessonType.MARKET_INSIGHT),
                title=f"后验复盘: {lesson_type_key}",
                content=content,
                context={
                    "source": "learning.backfill_lessons",
                    "review_sample_size": review.get("sample_size"),
                    "closed_trades": review.get("closed_trades"),
                    "evidence": evidence,
                },
                impact_score=-0.25 if str(item.get("priority")) == "high" else -0.1,
                confidence=0.75 if str(item.get("priority")) == "high" else 0.65,
            )
            prepared.append(lesson.to_dict())
            if not dry_run:
                engine._add_lesson(lesson)
                existing_contents.add(content)
                written += 1

                memory = getattr(self.mc, "memory_gateway", None) or getattr(self.mc, "memory", None)
                if memory and hasattr(memory, "save_lesson_learned"):
                    try:
                        await memory.save_lesson_learned(lesson.lesson_type.value, lesson.content, str(lesson.context))
                    except Exception:
                        pass
            else:
                written += 1

        if not dry_run and written > 0 and generate_report:
            if hasattr(engine, "_generate_learning_report"):
                try:
                    report_generated = bool(await engine._generate_learning_report())
                except Exception:
                    report_generated = False
            if hasattr(engine, "generate_retrieval_practice_deck"):
                try:
                    await engine.generate_retrieval_practice_deck()
                    retrieval_deck_generated = True
                except Exception:
                    retrieval_deck_generated = False

        return {
            "success": True,
            "dry_run": dry_run,
            "prepared": len(prepared),
            "written": 0 if dry_run else written,
            "would_write": written if dry_run else 0,
            "skipped": skipped,
            "report_generated": report_generated,
            "retrieval_deck_generated": retrieval_deck_generated,
            "lessons": prepared[:10],
            "review": {
                "sample_size": review.get("sample_size"),
                "closed_trades": review.get("closed_trades"),
                "realized_pnl": review.get("realized_pnl"),
                "fees": review.get("fees"),
                "net_pnl_plus_fees": review.get("net_pnl_plus_fees"),
            },
        }

    async def _build_post_trade_review(self, limit: int = 500) -> Dict[str, Any]:
        ths = getattr(self.mc, "trade_history_service", None) if self.mc else None
        if not ths or not hasattr(ths, "get_trade_history"):
            return {"available": False, "message": "trade_history_service_unavailable"}
        try:
            rows = await ths.get_trade_history(limit=max(50, int(limit or 500)))
        except Exception as exc:
            return {"available": False, "message": f"trade_history_load_failed:{exc}"}

        closes: List[Dict[str, Any]] = []
        fees = 0.0
        realized = 0.0
        wins = 0
        losses = 0
        symbol_pnl: Dict[str, float] = defaultdict(float)
        strategy_pnl: Dict[str, float] = defaultdict(float)
        close_reasons: Counter[str] = Counter()
        trace_linked = 0
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            gateway = md.get("gateway") if isinstance(md.get("gateway"), dict) else {}
            ctx = gateway.get("context") if isinstance(gateway.get("context"), dict) else {}
            if ctx.get("trace_id"):
                trace_linked += 1
            fees += _safe_float(row.get("fee"))
            if str(gateway.get("op") or "").lower() != "close":
                continue
            closes.append(row)
            pnl = _safe_float(row.get("pnl"))
            realized += pnl
            if pnl > 1e-9:
                wins += 1
            elif pnl < -1e-9:
                losses += 1
            symbol = str(row.get("symbol") or "UNKNOWN")
            strategy = str(md.get("strategy_id") or row.get("strategy") or "unknown")
            symbol_pnl[symbol] += pnl
            strategy_pnl[strategy] += pnl
            close_reasons[str(row.get("reasoning") or gateway.get("reason") or "unknown")] += 1

        decided = wins + losses
        net = realized + fees
        candidates: List[Dict[str, Any]] = []
        if closes:
            if fees < 0 and abs(fees) / max(1e-9, abs(realized)) >= 0.25:
                candidates.append(
                    {
                        "type": "fee_drag",
                        "priority": "high",
                        "lesson": "手续费吞噬已实现收益比例偏高，优先减少低质量高频开平仓。",
                        "evidence": {"realized_pnl": round(realized, 6), "fees": round(fees, 6)},
                    }
                )
            if decided and wins / decided < 0.55:
                candidates.append(
                    {
                        "type": "win_rate",
                        "priority": "medium",
                        "lesson": "胜率低于 55%，需要优先复盘亏损交易的共同入场条件。",
                        "evidence": {"wins": wins, "losses": losses, "win_rate": round(wins / decided, 4)},
                    }
                )
            worst_symbols = sorted(symbol_pnl.items(), key=lambda kv: kv[1])[:3]
            if worst_symbols and worst_symbols[0][1] < 0:
                candidates.append(
                    {
                        "type": "symbol_filter",
                        "priority": "high",
                        "lesson": "亏损集中标的应进入降权或观察清单，直到复盘确认 edge 恢复。",
                        "evidence": [{"symbol": k, "pnl": round(v, 6)} for k, v in worst_symbols],
                    }
                )
            top_reason = close_reasons.most_common(1)
            if top_reason:
                candidates.append(
                    {
                        "type": "exit_reason",
                        "priority": "medium",
                        "lesson": "主要平仓原因需要与策略预期一致；若原因集中但收益不佳，应调参或禁用对应退出逻辑。",
                        "evidence": {"top_reason": top_reason[0][0], "count": int(top_reason[0][1])},
                    }
                )

        return {
            "available": True,
            "sample_size": len(rows or []),
            "closed_trades": len(closes),
            "realized_pnl": round(realized, 6),
            "fees": round(fees, 6),
            "net_pnl_plus_fees": round(net, 6),
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / decided, 4) if decided else 0.0,
            "trace_linked_rows": trace_linked,
            "top_close_reasons": [{"reason": k, "count": int(v)} for k, v in close_reasons.most_common(5)],
            "top_symbols_by_pnl": [{"symbol": k, "pnl": round(v, 6)} for k, v in sorted(symbol_pnl.items(), key=lambda kv: kv[1], reverse=True)[:5]],
            "worst_symbols_by_pnl": [{"symbol": k, "pnl": round(v, 6)} for k, v in sorted(symbol_pnl.items(), key=lambda kv: kv[1])[:5]],
            "top_strategies_by_pnl": [{"strategy_id": k, "pnl": round(v, 6)} for k, v in sorted(strategy_pnl.items(), key=lambda kv: kv[1], reverse=True)[:5]],
            "candidate_lessons": candidates,
        }

    def _learning_coverage_gaps(self, status: Dict[str, Any], review: Dict[str, Any]) -> List[Dict[str, Any]]:
        gaps: List[Dict[str, Any]] = []
        total_lessons = int(status.get("total_lessons", 0) or 0)
        reports_generated = int(status.get("reports_generated", 0) or 0)
        closed_trades = int(review.get("closed_trades", 0) or 0)
        candidates = list(review.get("candidate_lessons") or [])
        if closed_trades > 0 and total_lessons == 0:
            gaps.append(
                {
                    "priority": "high",
                    "gap": "真实平仓存在但学习引擎 lessons 为空",
                    "next_action": "将 post_trade_review.candidate_lessons 写入 AILearningEngine 或记忆层，形成可召回经验。",
                    "evidence": {"closed_trades": closed_trades, "candidate_lessons": len(candidates)},
                }
            )
        if closed_trades > 0 and reports_generated == 0:
            gaps.append(
                {
                    "priority": "medium",
                    "gap": "没有生成学习报告",
                    "next_action": "触发学习报告生成任务，至少每日基于真实平仓输出一次复盘摘要。",
                    "evidence": {"closed_trades": closed_trades},
                }
            )
        if candidates and not status.get("retrieval_deck"):
            gaps.append(
                {
                    "priority": "medium",
                    "gap": "有候选经验但没有 retrieval deck",
                    "next_action": "把候选经验转为问答卡片，供决策前经验召回。",
                    "evidence": {"candidate_lessons": len(candidates)},
                }
            )
        return gaps
