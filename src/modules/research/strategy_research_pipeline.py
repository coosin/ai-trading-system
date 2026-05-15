"""
Strategy research pipeline:
- generate candidates (DSL primitives combos)
- backtest on train window
- optimize parameters (simple grid)
- walk-forward evaluate on test window
- gate by risk metrics (drawdown, sharpe, trades)
- publish into StrategyManager as StrategyConfig with versioned metadata
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.modules.backtesting.backtest_engine import BacktestConfig, BacktestEngine
from src.modules.backtesting.strategies.dsl_strategy import DSLStrategy
from src.modules.strategies.strategy_dsl import bump_version, normalize_symbol, validate_dsl

logger = logging.getLogger(__name__)


@dataclass
class ResearchGates:
    min_sharpe: float = 0.8
    max_drawdown: float = 0.25
    min_trades: int = 8


class StrategyResearchPipeline:
    def __init__(self, main_controller=None, gates: Optional[ResearchGates] = None):
        self.main_controller = main_controller
        self.gates = gates or ResearchGates()
        self.engine = BacktestEngine()
        self.fee_rate = 0.0005
        self.slippage_rate = 0.0003
        self.fold_count = 3
        self.train_ratio = 0.7
        # Resource guardrails: keep heavy research bounded.
        self.max_parallel_symbols = 2
        self.max_candidates_per_symbol = 12
        self.max_backtests_per_cycle = 240
        self.per_symbol_time_budget_sec = 25.0
        self._bt_calls = 0
        self._symbol_semaphore = asyncio.Semaphore(self.max_parallel_symbols)
        self.min_data_quality_for_research = 0.5
        self.publish_min_score = 0.55
        self.promote_small_score = 1.10
        self.redevelop_below_score = 0.35
        self.discard_below_score = 0.10
        self.auto_activate_published = True
        self.require_activation_gate = True
        self.max_auto_activate_stage = "paper"
        self.production_auto_activate_allowed = False
        self.manual_approval_required = False
        self.auto_enable_published = True
        self.auto_deploy_after_approval = True
        self.auto_activate_after_approval = True
        self.max_post_approval_auto_stage = "paper"

    @staticmethod
    def _build_review_window(
        *,
        decision: str,
        manual_approval_required: bool,
        deployment_stage: str,
        score: float,
    ) -> Dict[str, Any]:
        opened_at = datetime.now()
        review_by = opened_at + timedelta(hours=24 if deployment_stage == "paper" else 12)
        status = "pending_approval" if manual_approval_required else "open"
        mode = "pre_publish_approval" if manual_approval_required else "post_publish_observation"
        return {
            "visible": True,
            "status": status,
            "mode": mode,
            "decision": str(decision or "publish"),
            "deployment_stage": str(deployment_stage or "paper"),
            "opened_at": opened_at.isoformat(),
            "review_by": review_by.isoformat(),
            "score": float(round(score, 6)),
            "summary": "manual approval required before enable" if manual_approval_required else "auto-published; keep visible for human review",
        }

    @staticmethod
    def _deployment_stage_rank(stage: str) -> int:
        return {
            "paper": 0,
            "shadow": 1,
            "small": 2,
            "full": 3,
        }.get(str(stage or "").strip().lower(), 99)

    def _resolve_publish_policy(
        self,
        cfg: Optional[Dict[str, Any]],
        *,
        gov_decision: str,
    ) -> Tuple[str, bool, bool, Dict[str, Any]]:
        research_cfg = cfg if isinstance(cfg, dict) else {}
        rollout = research_cfg.get("rollout", {}) if isinstance(research_cfg.get("rollout"), dict) else {}
        governance = research_cfg.get("governance", {}) if isinstance(research_cfg.get("governance"), dict) else {}
        deployment_stage = "small" if gov_decision == "production_small" else "shadow"
        force_paper = bool(rollout.get("force_paper_stage", True))
        if force_paper:
            deployment_stage = "paper"
        allow_auto_activate = bool(rollout.get("auto_activate_published", self.auto_activate_published))
        require_gate = bool(rollout.get("require_activation_gate", self.require_activation_gate))
        max_stage = str(rollout.get("max_auto_activate_stage", self.max_auto_activate_stage) or self.max_auto_activate_stage).strip().lower()
        prod_allow = bool(governance.get("production_auto_activate_allowed", self.production_auto_activate_allowed))
        manual_approval_required = bool(rollout.get("manual_approval_required", self.manual_approval_required))
        auto_enable = bool(rollout.get("auto_enable_published", self.auto_enable_published))
        auto_deploy_after_approval = bool(rollout.get("auto_deploy_after_approval", self.auto_deploy_after_approval))
        auto_activate_after_approval = bool(rollout.get("auto_activate_after_approval", self.auto_activate_after_approval))
        max_post_approval_stage = str(
            rollout.get("max_post_approval_auto_stage", self.max_post_approval_auto_stage) or self.max_post_approval_auto_stage
        ).strip().lower()
        if gov_decision == "publish" and not prod_allow and deployment_stage not in {"paper", "shadow"}:
            allow_auto_activate = False
        if self._deployment_stage_rank(deployment_stage) > self._deployment_stage_rank(max_stage):
            allow_auto_activate = False
        if manual_approval_required:
            auto_enable = False
            allow_auto_activate = False
        policy = {
            "auto_activate_published": allow_auto_activate,
            "require_activation_gate": require_gate,
            "max_auto_activate_stage": max_stage,
            "production_auto_activate_allowed": prod_allow,
            "force_paper_stage": force_paper,
            "manual_approval_required": manual_approval_required,
            "auto_enable_published": auto_enable,
            "auto_deploy_after_approval": auto_deploy_after_approval,
            "auto_activate_after_approval": auto_activate_after_approval,
            "max_post_approval_auto_stage": max_post_approval_stage,
        }
        return deployment_stage, allow_auto_activate, auto_enable, policy

    def _build_experiment_card(
        self,
        *,
        dsl: Dict[str, Any],
        train_metrics: Dict[str, Any],
        test_metrics: Dict[str, Any],
        decision: str,
    ) -> Dict[str, Any]:
        return {
            "hypothesis": f"{dsl.get('name', 'strategy')} can generalize from train to OOS with bounded drawdown",
            "setup": {
                "symbol": dsl.get("symbol", "BTC/USDT"),
                "timeframe": dsl.get("timeframe", "1h"),
                "entry_count": len(dsl.get("entry", []) or []),
                "exit_count": len(dsl.get("exit", []) or []),
            },
            "cost_model": {"slippage_bps": 6, "fees_bps": 8},
            "train_summary": train_metrics,
            "oos_summary": test_metrics,
            "decision": decision,
            "created_at": datetime.now().isoformat(),
        }

    def _build_review_answers(
        self,
        *,
        dsl: Dict[str, Any],
        test_metrics: Dict[str, Any],
        decision: str,
    ) -> Dict[str, Any]:
        return {
            "what_edge": f"{dsl.get('name', 'strategy')} captures {dsl.get('entry', [{}])[0].get('type', 'pattern')} behavior",
            "why_not_immediately_gone": "requires matching regime, execution discipline, and risk gating",
            "net_after_cost": f"pnl={test_metrics.get('pnl', 0)} sharpe={test_metrics.get('sharpe', 0)}",
            "failure_shape": f"drawdown={test_metrics.get('max_drawdown', 0)} trades={test_metrics.get('trades', 0)}",
            "kill_signal": "OOS fail / live drift degraded / execution slippage worsening",
            "decision": decision,
        }

    def _build_parameter_sensitivity(
        self,
        *,
        dsl: Dict[str, Any],
        train_metrics: Dict[str, Any],
        test_metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        train_sharpe = float(train_metrics.get("sharpe", 0.0) or 0.0)
        test_sharpe = float(test_metrics.get("sharpe", 0.0) or 0.0)
        train_pnl = float(train_metrics.get("pnl", 0.0) or 0.0)
        test_pnl = float(test_metrics.get("pnl", 0.0) or 0.0)
        drift = round(test_sharpe - train_sharpe, 4)
        pnl_drift = round(test_pnl - train_pnl, 4)
        return {
            "summary": "stable" if abs(drift) <= 0.35 and abs(pnl_drift) <= max(1.0, abs(train_pnl) * 0.35) else "fragile",
            "train_vs_oos": {
                "sharpe_delta": drift,
                "pnl_delta": pnl_drift,
                "trade_count_delta": int(test_metrics.get("trades", 0) or 0) - int(train_metrics.get("trades", 0) or 0),
            },
            "core_parameters": dict(dsl.get("parameters") or {}),
            "notes": [
                f"entry_rules={len(dsl.get('entry', []) or [])}",
                f"exit_rules={len(dsl.get('exit', []) or [])}",
                f"timeframe={dsl.get('timeframe', '1h')}",
            ],
        }

    async def run_cycle(self, symbols: List[str], timeframe: str = "1h", lookback_days: int = 30) -> Dict[str, Any]:
        # load config (best-effort)
        cfg: Dict[str, Any] = {}
        try:
            cm = getattr(self.main_controller, "config_manager", None)
            cfg = await cm.get_config("research", {}) if cm else {}
            if isinstance(cfg, dict):
                gates = cfg.get("gates", {})
                if isinstance(gates, dict):
                    self.gates.min_sharpe = float(gates.get("min_sharpe", self.gates.min_sharpe))
                    self.gates.max_drawdown = float(gates.get("max_drawdown", self.gates.max_drawdown))
                    self.gates.min_trades = int(gates.get("min_trades", self.gates.min_trades))
                cost = cfg.get("cost_model", {})
                if isinstance(cost, dict):
                    self.fee_rate = float(cost.get("fee_rate", self.fee_rate))
                    self.slippage_rate = float(cost.get("slippage_rate", self.slippage_rate))
                wf = cfg.get("walk_forward", {})
                if isinstance(wf, dict):
                    self.fold_count = int(wf.get("folds", self.fold_count))
                    self.train_ratio = float(wf.get("train_ratio", self.train_ratio))
                limits = cfg.get("resource_limits", {})
                if isinstance(limits, dict):
                    self.max_parallel_symbols = max(1, int(limits.get("max_parallel_symbols", self.max_parallel_symbols) or self.max_parallel_symbols))
                    self.max_candidates_per_symbol = max(4, int(limits.get("max_candidates_per_symbol", self.max_candidates_per_symbol) or self.max_candidates_per_symbol))
                    self.max_backtests_per_cycle = max(40, int(limits.get("max_backtests_per_cycle", self.max_backtests_per_cycle) or self.max_backtests_per_cycle))
                    self.per_symbol_time_budget_sec = max(5.0, float(limits.get("per_symbol_time_budget_sec", self.per_symbol_time_budget_sec) or self.per_symbol_time_budget_sec))
                dq = cfg.get("data_quality", {})
                if isinstance(dq, dict):
                    self.min_data_quality_for_research = float(dq.get("min_quality_for_research", self.min_data_quality_for_research))
                gov = cfg.get("governance", {})
                if isinstance(gov, dict):
                    self.publish_min_score = float(gov.get("publish_min_score", self.publish_min_score))
                    self.promote_small_score = float(gov.get("promote_small_score", self.promote_small_score))
                    self.redevelop_below_score = float(gov.get("redevelop_below_score", self.redevelop_below_score))
                    self.discard_below_score = float(gov.get("discard_below_score", self.discard_below_score))
                    self.production_auto_activate_allowed = bool(
                        gov.get("production_auto_activate_allowed", self.production_auto_activate_allowed)
                    )
                rollout = cfg.get("rollout", {})
                if isinstance(rollout, dict):
                    self.auto_activate_published = bool(
                        rollout.get("auto_activate_published", self.auto_activate_published)
                    )
                    self.require_activation_gate = bool(
                        rollout.get("require_activation_gate", self.require_activation_gate)
                    )
                    self.max_auto_activate_stage = str(
                        rollout.get("max_auto_activate_stage", self.max_auto_activate_stage) or self.max_auto_activate_stage
                    ).strip().lower()
                    self.manual_approval_required = bool(
                        rollout.get("manual_approval_required", self.manual_approval_required)
                    )
                    self.auto_enable_published = bool(
                        rollout.get("auto_enable_published", self.auto_enable_published)
                    )
                    self.auto_deploy_after_approval = bool(
                        rollout.get("auto_deploy_after_approval", self.auto_deploy_after_approval)
                    )
                    self.auto_activate_after_approval = bool(
                        rollout.get("auto_activate_after_approval", self.auto_activate_after_approval)
                    )
                    self.max_post_approval_auto_stage = str(
                        rollout.get("max_post_approval_auto_stage", self.max_post_approval_auto_stage) or self.max_post_approval_auto_stage
                    ).strip().lower()
        except Exception:
            pass

        self._bt_calls = 0
        self._symbol_semaphore = asyncio.Semaphore(self.max_parallel_symbols)
        results: Dict[str, Any] = {"published": [], "rejected": [], "errors": []}
        unique_symbols = []
        seen = set()
        for s in symbols:
            x = str(s or "").strip()
            if x and x not in seen:
                unique_symbols.append(x)
                seen.add(x)

        async def _run_one(sym: str):
            async with self._symbol_semaphore:
                try:
                    return {
                        "symbol": sym,
                        "published": await self._research_symbol(
                            sym,
                            timeframe=timeframe,
                            lookback_days=lookback_days,
                            research_cfg=cfg,
                        ),
                    }
                except Exception as e:
                    logger.error(f"research cycle failed for {sym}: {e}")
                    return {"symbol": sym, "error": str(e)}

        jobs = [asyncio.create_task(_run_one(sym)) for sym in unique_symbols]
        for out in await asyncio.gather(*jobs, return_exceptions=False):
            if isinstance(out, dict) and out.get("error"):
                results["errors"].append({"symbol": out.get("symbol"), "error": out.get("error")})
            else:
                results["published"].extend(out.get("published", []))
        results["backtest_calls"] = self._bt_calls
        return results

    async def _research_symbol(
        self,
        symbol: str,
        timeframe: str,
        lookback_days: int,
        research_cfg: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        started_at = datetime.now()
        # Data quality gate: low-quality unified snapshot skips heavy research to avoid bad strategy fit.
        snapshot = await self._get_unified_snapshot(symbol)
        q_score = self._extract_quality_score(snapshot)
        if q_score is not None and q_score < float(self.min_data_quality_for_research):
            # Soft gate: do not block AI research; downgrade workload and keep exploratory capability.
            logger.warning(
                "low-quality research mode for %s: %.3f < %.3f",
                symbol,
                q_score,
                float(self.min_data_quality_for_research),
            )
            self.max_candidates_per_symbol = max(4, int(self.max_candidates_per_symbol * 0.6))
        exchange = getattr(getattr(self.main_controller, "ai_trading_engine", None), "exchange", None)
        if not exchange:
            return []
        end = datetime.now()
        start = end - timedelta(days=lookback_days)
        df = await self._load_klines_df(exchange, symbol, timeframe=timeframe, limit=720)
        if df is None or len(df) < 120:
            return []

        folds = self._walk_forward_folds(df, folds=max(1, self.fold_count), train_ratio=self.train_ratio)
        market_ctx = await self._build_market_context(symbol)
        candidates = self._generate_candidates(symbol, timeframe, market_ctx)
        candidates = self._limit_candidates(candidates, market_ctx)

        published: List[Dict[str, Any]] = []
        for dsl in candidates:
            if (datetime.now() - started_at).total_seconds() >= self.per_symbol_time_budget_sec:
                logger.info("research time budget reached for %s; stop evaluating remaining candidates", symbol)
                break
            if self._bt_calls >= self.max_backtests_per_cycle:
                logger.warning("research backtest budget reached (%s); stopping cycle", self.max_backtests_per_cycle)
                break
            validate_dsl(dsl)
            # multi-fold walk-forward: optimize on each train window, score on test windows
            fold_scores: List[Dict[str, Any]] = []
            best_dsl = dsl
            best_train = {}
            for train_df, test_df in folds:
                best_dsl, train_metrics = await self._optimize_candidate(best_dsl, train_df)
                test_metrics = await self._backtest(best_dsl, test_df)
                fold_scores.append(test_metrics)
                best_train = train_metrics
                if self._bt_calls >= self.max_backtests_per_cycle:
                    break
            test_metrics = self._aggregate_fold_metrics(fold_scores)
            score = self._research_score(test_metrics)
            decision = self._governance_decision(score)

            # 最低规则：先过风险门，再过最低研究评分。
            if self._passes_gates(test_metrics) and score >= self.publish_min_score:
                item = await self._publish(
                    best_dsl,
                    test_metrics,
                    best_train,
                    score=score,
                    decision=decision,
                    research_cfg=research_cfg,
                )
                if item:
                    published.append(item)
        return published

    async def _get_unified_snapshot(self, symbol: str) -> Optional[Dict[str, Any]]:
        mc = self.main_controller
        if not mc:
            return None
        hub = getattr(mc, "data_source_hub", None)
        if not hub or not hasattr(hub, "get_unified_snapshot"):
            return None
        try:
            snap = await hub.get_unified_snapshot(symbol)
            return snap if isinstance(snap, dict) else None
        except Exception:
            return None

    @staticmethod
    def _extract_quality_score(snapshot: Optional[Dict[str, Any]]) -> Optional[float]:
        if not isinstance(snapshot, dict):
            return None
        q = snapshot.get("数据质量评估", {})
        if not isinstance(q, dict):
            return None
        val = q.get("score")
        try:
            return float(val) if val is not None else None
        except Exception:
            return None

    async def _load_klines_df(self, exchange, symbol: str, timeframe: str, limit: int) -> Optional[pd.DataFrame]:
        tf = timeframe.lower().replace("h", "H").replace("m", "m")
        raw = await exchange.get_klines(symbol.replace("/", "-"), tf, limit=limit)
        if not raw:
            return None
        rows = []
        for k in raw:
            if isinstance(k, (list, tuple)) and len(k) >= 6:
                ts, o, h, l, c, v = k[:6]
            elif isinstance(k, dict):
                ts = k.get("ts") or k.get("timestamp") or k.get("t")
                o, h, l, c, v = k.get("open"), k.get("high"), k.get("low"), k.get("close"), k.get("volume")
            else:
                continue
            try:
                rows.append(
                    {
                        "timestamp": pd.to_datetime(ts, unit="ms", errors="coerce"),
                        "open": float(o),
                        "high": float(h),
                        "low": float(l),
                        "close": float(c),
                        "volume": float(v),
                    }
                )
            except Exception:
                continue
        df = pd.DataFrame(rows).dropna()
        if df.empty:
            return None
        df = df.sort_values("timestamp").set_index("timestamp")
        return df

    def _walk_forward_folds(self, df: pd.DataFrame, folds: int, train_ratio: float) -> List[Tuple[pd.DataFrame, pd.DataFrame]]:
        n = len(df)
        folds = max(1, min(folds, 6))
        cut = max(50, int(n * train_ratio))
        # expanding window walk-forward
        out: List[Tuple[pd.DataFrame, pd.DataFrame]] = []
        if n - cut < 30:
            out.append((df.iloc[:cut].copy(), df.iloc[cut:].copy()))
            return out
        step = max(20, int((n - cut) / folds))
        for i in range(folds):
            test_start = cut + i * step
            test_end = min(n, test_start + step)
            if test_end - test_start < 20:
                break
            train = df.iloc[:test_start].copy()
            test = df.iloc[test_start:test_end].copy()
            if len(train) >= 80 and len(test) >= 20:
                out.append((train, test))
        return out or [(df.iloc[:cut].copy(), df.iloc[cut:].copy())]

    def _aggregate_fold_metrics(self, folds: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not folds:
            return {"sharpe_ratio": 0.0, "max_drawdown": 1.0, "total_trades": 0, "win_rate": 0.0, "total_pnl": 0.0}
        sharpe = sum(float(f.get("sharpe_ratio", 0)) for f in folds) / len(folds)
        max_dd = max(float(f.get("max_drawdown", 0)) for f in folds)
        trades = sum(int(f.get("total_trades", 0)) for f in folds)
        win = sum(float(f.get("win_rate", 0)) for f in folds) / len(folds)
        pnl = sum(float(f.get("total_pnl", 0)) for f in folds)
        return {
            "sharpe_ratio": sharpe,
            "max_drawdown": max_dd,
            "total_trades": trades,
            "win_rate": win,
            "total_pnl": pnl,
            "folds": folds,
        }

    async def _build_market_context(self, symbol: str) -> Dict[str, Any]:
        """融合行情与第三方信息，指导候选策略生成。"""
        out: Dict[str, Any] = {"volatility": None, "sentiment": "neutral", "market_mood": "neutral"}
        mc = self.main_controller
        try:
            ui = getattr(mc, "unified_info_collector", None) if mc else None
            if ui and hasattr(ui, "get_market_info"):
                mi = ui.get_market_info(symbol)
                if mi:
                    out["volatility"] = getattr(mi, "volatility_24h", None)
                    out["sentiment"] = getattr(mi, "market_mood", out["sentiment"])
                    out["market_mood"] = getattr(mi, "market_mood", out["market_mood"])
        except Exception:
            pass
        try:
            eng = getattr(mc, "ai_trading_engine", None) if mc else None
            if eng and hasattr(eng, "exchange") and eng.exchange and hasattr(eng.exchange, "get_market_data"):
                md = await eng.exchange.get_market_data(symbol)
                if isinstance(md, dict):
                    vol = md.get("volatility") or md.get("volatility_24h")
                    if isinstance(vol, (int, float)):
                        out["volatility"] = float(vol)
        except Exception:
            pass
        return out

    def _generate_candidates(self, symbol: str, timeframe: str, market_ctx: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        symbol = normalize_symbol(symbol)
        market_ctx = market_ctx or {}
        base = {
            "symbol": symbol,
            "timeframe": timeframe,
            "risk": {"stop_loss_pct": 0.02, "take_profit_pct": 0.04},
        }
        candidates: List[Dict[str, Any]] = []
        for fast in (10, 12, 16, 20):
            for slow in (30, 40, 50, 60):
                if fast >= slow:
                    continue
                candidates.append(
                    {
                        **base,
                        "name": f"MA{fast}x{slow}",
                        "version": "1.0.0",
                        "entry": [{"type": "ma_crossover", "params": {"fast": fast, "slow": slow}}],
                        "filters": [],
                        "exit": [{"type": "bollinger_reversion", "params": {"window": 20, "std": 2.0}}],
                        "tags": ["dsl", "ma", "walkforward"],
                        "metadata": {"generator": "grid"},
                    }
                )
        # breakout variants
        for lookback in (12, 20, 30):
            candidates.append(
                {
                    **base,
                    "name": f"Breakout{lookback}",
                    "version": "1.0.0",
                    "entry": [{"type": "breakout_channel", "params": {"lookback": lookback}}],
                    "filters": [],
                    "exit": [{"type": "bollinger_reversion", "params": {"window": 20, "std": 2.0}}],
                    "tags": ["dsl", "breakout", "walkforward"],
                    "metadata": {"generator": "grid"},
                }
            )
        # volatility breakout variants
        for window in (14, 20):
            for atr_mult in (1.2, 1.5):
                candidates.append(
                    {
                        **base,
                        "name": f"VolBreak{window}x{atr_mult}",
                        "version": "1.0.0",
                        "entry": [{"type": "volatility_breakout", "params": {"window": window, "atr_mult": atr_mult}}],
                        "filters": [],
                        "exit": [{"type": "bollinger_reversion", "params": {"window": 20, "std": 2.0}}],
                        "tags": ["dsl", "volatility", "walkforward"],
                        "metadata": {"generator": "grid", "kind": "volatility"},
                    }
                )
        # scalping variants (short-term mean reversion)
        for window in (7, 9, 12):
            for z in (1.0, 1.2, 1.5):
                candidates.append(
                    {
                        **base,
                        "name": f"ScalpMR{window}z{z}",
                        "version": "1.0.0",
                        "entry": [{"type": "scalp_reversion", "params": {"window": window, "zscore": z}}],
                        "filters": [],
                        "exit": [{"type": "bollinger_reversion", "params": {"window": max(14, window * 2), "std": 1.8}}],
                        "tags": ["dsl", "scalping", "walkforward"],
                        "metadata": {"generator": "grid", "kind": "scalping"},
                    }
                )
        # pin-catch variants (wick reversal)
        for body_ratio in (0.25, 0.35):
            for wick_ratio in (2.0, 2.5):
                candidates.append(
                    {
                        **base,
                        "name": f"PinCatch{int(body_ratio*100)}x{wick_ratio}",
                        "version": "1.0.0",
                        "entry": [
                            {"type": "pinbar_reversal", "params": {"body_ratio_max": body_ratio, "wick_ratio_min": wick_ratio}}
                        ],
                        "filters": [],
                        "exit": [{"type": "bollinger_reversion", "params": {"window": 20, "std": 2.0}}],
                        "tags": ["dsl", "pinbar", "walkforward"],
                        "metadata": {"generator": "grid", "kind": "pin_catch"},
                    }
                )
        vol = market_ctx.get("volatility")
        mood = str(market_ctx.get("market_mood", "neutral") or "neutral").lower()
        if isinstance(vol, (int, float)) and vol >= 0.05:
            candidates.extend([c for c in candidates if "volatility" in (c.get("tags") or [])][:6])
        if "bear" in mood or "fear" in mood:
            candidates.extend([c for c in candidates if "breakout" in (c.get("tags") or [])][:4])
        if "bull" in mood or "greed" in mood:
            candidates.extend([c for c in candidates if "ma" in (c.get("tags") or [])][:4])
        random.shuffle(candidates)
        return candidates

    def _limit_candidates(self, candidates: List[Dict[str, Any]], market_ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
        """限制候选规模，按市场上下文偏好排序后截断。"""
        mood = str(market_ctx.get("market_mood", "neutral") or "neutral").lower()
        vol = market_ctx.get("volatility")

        def score(c: Dict[str, Any]) -> float:
            tags = set(c.get("tags") or [])
            s = 0.0
            if "ma" in tags:
                s += 1.0
            if "breakout" in tags:
                s += 1.0
            if "volatility" in tags:
                s += 0.8
            if "scalping" in tags:
                s += 0.6
            if isinstance(vol, (int, float)) and vol >= 0.05 and "volatility" in tags:
                s += 1.2
            if ("bull" in mood or "greed" in mood) and "ma" in tags:
                s += 0.8
            if ("bear" in mood or "fear" in mood) and "breakout" in tags:
                s += 0.8
            return s

        ranked = sorted(candidates, key=score, reverse=True)
        return ranked[: self.max_candidates_per_symbol]

    @staticmethod
    def _map_strategy_type(dsl: Dict[str, Any]) -> str:
        tags = set((dsl.get("tags") or []))
        kind = str((dsl.get("metadata") or {}).get("kind", "")).lower()
        if "scalping" in tags or kind == "scalping":
            return "grid_trading"
        if "volatility" in tags or kind == "volatility":
            return "market_making"
        if "ma" in tags or "breakout" in tags:
            return "trend_following"
        return "ai_generated"

    async def _optimize_candidate(self, dsl: Dict[str, Any], train_df: pd.DataFrame) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        # For MA candidates, optimize fast/slow around the initial values.
        entry = (dsl.get("entry") or [{}])[0]
        if entry.get("type") != "ma_crossover":
            metrics = await self._backtest(dsl, train_df)
            return dsl, metrics

        init_fast = int(entry.get("params", {}).get("fast", 20))
        init_slow = int(entry.get("params", {}).get("slow", 50))
        fast_space = sorted(set([max(6, init_fast - 4), init_fast, init_fast + 4, init_fast + 8]))
        slow_space = sorted(set([max(init_fast + 10, init_slow - 10), init_slow, init_slow + 10, init_slow + 20]))

        best_dsl = dsl
        best_metrics = {"sharpe_ratio": -1.0}
        for fast in fast_space:
            for slow in slow_space:
                if fast >= slow:
                    continue
                cand = {**dsl}
                cand["entry"] = [{"type": "ma_crossover", "params": {"fast": int(fast), "slow": int(slow)}}]
                metrics = await self._backtest(cand, train_df)
                if metrics.get("sharpe_ratio", -1) > best_metrics.get("sharpe_ratio", -1):
                    best_metrics = metrics
                    best_dsl = cand
        return best_dsl, best_metrics

    async def _backtest(self, dsl: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:
        if self._bt_calls >= self.max_backtests_per_cycle:
            return {
                "final_balance": 10000.0,
                "total_pnl": -9999.0,
                "win_rate": 0.0,
                "max_drawdown": 1.0,
                "sharpe_ratio": -9.0,
                "total_trades": 0,
                "estimated_cost": 0.0,
            }
        self._bt_calls += 1
        validate_dsl(dsl)
        config = BacktestConfig(
            symbol=dsl.get("symbol", "BTC/USDT"),
            start_time=df.index[0].to_pydatetime(),
            end_time=df.index[-1].to_pydatetime(),
            initial_balance=10000.0,
            time_frame=dsl.get("timeframe", "1h"),
        )
        strat = DSLStrategy({"name": dsl.get("name", "dsl"), "dsl": dsl})
        res = await self.engine.run_backtest(strat, df.copy(), config)
        # cost model: approximate fee+slippage on notional traded
        cost = 0.0
        try:
            traded_notional = 0.0
            for t in res.trades:
                traded_notional += float(getattr(t, "price", 0) or 0) * float(getattr(t, "quantity", 0) or 0)
            cost = traded_notional * float(self.fee_rate + self.slippage_rate)
        except Exception:
            cost = 0.0
        return {
            "final_balance": res.final_balance,
            "total_pnl": float(res.total_pnl) - float(cost),
            "win_rate": float(res.win_rate) / 100.0 if res.win_rate > 1 else float(res.win_rate),
            "max_drawdown": float(res.max_drawdown) / 100.0 if res.max_drawdown > 1 else float(res.max_drawdown),
            "sharpe_ratio": float(res.sharpe_ratio),
            "total_trades": int(res.total_trades),
            "estimated_cost": float(cost),
        }

    def _passes_gates(self, metrics: Dict[str, Any]) -> bool:
        return (
            metrics.get("sharpe_ratio", 0) >= self.gates.min_sharpe
            and metrics.get("max_drawdown", 1) <= self.gates.max_drawdown
            and metrics.get("total_trades", 0) >= self.gates.min_trades
        )

    @staticmethod
    def _research_score(test_metrics: Dict[str, Any]) -> float:
        """
        统一研究评分（用于后续策略池清理/排序）：
        高 sharpe、正 pnl、低回撤、有交易样本 => 高分。
        """
        sharpe = float(test_metrics.get("sharpe_ratio", 0.0) or 0.0)
        pnl = float(test_metrics.get("total_pnl", 0.0) or 0.0)
        dd = float(test_metrics.get("max_drawdown", 1.0) or 1.0)
        trades = float(test_metrics.get("total_trades", 0.0) or 0.0)
        return sharpe * 0.6 + (pnl / 1000.0) * 0.25 - dd * 0.1 + min(trades, 100.0) * 0.0005

    def _governance_decision(self, score: float) -> str:
        if score < self.discard_below_score:
            return "discard"
        if score < self.redevelop_below_score:
            return "redevelop"
        if score >= self.promote_small_score:
            return "production_small"
        return "production_shadow"

    async def _publish(
        self,
        dsl: Dict[str, Any],
        test_metrics: Dict[str, Any],
        train_metrics: Dict[str, Any],
        score: Optional[float] = None,
        decision: Optional[str] = None,
        research_cfg: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self.main_controller or not getattr(self.main_controller, "strategy_manager", None):
            return None
        strategy_manager = self.main_controller.strategy_manager

        # Create StrategyConfig-like dict that StrategyManager.load_strategy_config understands
        strategy_id = f"dsl_{dsl['symbol'].replace('/','_')}_{dsl['name'].replace(' ','_')}"
        version = bump_version(dsl.get("version", "1.0.0"))
        dsl = {**dsl, "version": version}

        research_score = float(score if score is not None else self._research_score(test_metrics))
        gov_decision = decision or self._governance_decision(research_score)
        deployment_stage, auto_activate_allowed, auto_enable_published, rollout_policy = self._resolve_publish_policy(
            research_cfg,
            gov_decision=gov_decision,
        )
        manual_approval_required = bool(rollout_policy.get("manual_approval_required", False))
        review_window = self._build_review_window(
            decision=gov_decision,
            manual_approval_required=manual_approval_required,
            deployment_stage=deployment_stage,
            score=research_score,
        )

        config_data = {
            "strategy_id": strategy_id,
            "name": dsl["name"],
            "description": f"DSL strategy auto-researched. gates={self.gates}",
            "strategy_type": self._map_strategy_type(dsl),
            "enabled": auto_enable_published,
            "version": version,
            "parameters": {"dsl": dsl},
            "symbols": [dsl.get("symbol", "BTC/USDT")],
            "timeframe": dsl.get("timeframe", "1h"),
            "initial_capital": 10000.0,
            "metadata": {
                "dsl": dsl,
                "deployment": {
                    "stage": deployment_stage,
                    "cap_multiplier": 0.0 if deployment_stage == "paper" else (0.5 if deployment_stage == "small" else 0.25),
                    "policy": "guarded_rollout",
                },
                "research": {
                    "train": train_metrics,
                    "test": test_metrics,
                    "gates": self.gates.__dict__,
                    "published_at": datetime.now().isoformat(),
                    "score": research_score,
                    "decision": gov_decision,
                    "rollout_policy": rollout_policy,
                    "approval_state": "manual_approval_required" if manual_approval_required else "auto_enabled",
                    "review_window": review_window,
                },
                "approval": {
                    "required": manual_approval_required,
                    "state": "manual_approval_required" if manual_approval_required else "approved",
                    "approved": False if manual_approval_required else True,
                    "approved_by": "system_auto_publish" if not manual_approval_required else None,
                    "approved_at": datetime.now().isoformat() if not manual_approval_required else None,
                },
                "review_window": review_window,
            },
        }

        cfg = await strategy_manager.load_strategy_config(config_data)
        if not cfg:
            return None
        experiment_card = self._build_experiment_card(
            dsl=dsl,
            train_metrics=train_metrics,
            test_metrics=test_metrics,
            decision=gov_decision,
        )
        review_answers = self._build_review_answers(
            dsl=dsl,
            test_metrics=test_metrics,
            decision=gov_decision,
        )
        parameter_sensitivity = self._build_parameter_sensitivity(
            dsl=dsl,
            train_metrics=train_metrics,
            test_metrics=test_metrics,
        )
        try:
            strategy_manager.save_strategy_experiment_card(
                strategy_id,
                hypothesis=str(experiment_card.get("hypothesis") or ""),
                experiment_card=experiment_card,
            )
            strategy_manager.record_strategy_review(
                strategy_id,
                review_type="research_pipeline_publish",
                answers=review_answers,
                action_items=[
                    "monitor live drift",
                    "track cost after deployment",
                    "revisit if regime changes",
                ],
                status="completed" if gov_decision == "publish" else "review_required",
            )
            strategy_manager.save_strategy_parameter_sensitivity(
                strategy_id,
                parameter_sensitivity=parameter_sensitivity,
            )
            if gov_decision != "publish":
                strategy_manager.record_strategy_failure_case(
                    strategy_id,
                    title=f"{strategy_id} OOS review required",
                    case_type="oos_failure",
                    summary="OOS / governance gate did not pass publish threshold",
                    trigger=f"decision={gov_decision}",
                    action_taken="kept in review_required state",
                    metadata={"test_metrics": dict(test_metrics or {})},
                )
        except Exception:
            pass

        instance_id = None
        activated = False
        activation_blockers: List[str] = []
        try:
            from src.modules.core.strategy_manager import StrategyStatus

            if auto_activate_allowed:
                if rollout_policy.get("require_activation_gate", True) and hasattr(strategy_manager, "get_strategy_activation_gate"):
                    gate = strategy_manager.get_strategy_activation_gate(strategy_id)
                    if not bool((gate or {}).get("eligible", False)):
                        activation_blockers.extend(list((gate or {}).get("reasons") or ["activation_gate_denied"]))
                running = []
                if not activation_blockers:
                    running = await strategy_manager.get_strategy_instances(
                        strategy_id=strategy_id, status=StrategyStatus.RUNNING
                    )
                if not running and not activation_blockers:
                    instance_id = await strategy_manager.create_strategy_instance(strategy_id)
                    if instance_id:
                        init_ok = await strategy_manager.initialize_strategy(instance_id)
                        if init_ok:
                            activated = await strategy_manager.start_strategy(instance_id)
                        else:
                            activation_blockers.append("initialize_failed")
            else:
                activation_blockers.append("auto_activate_disabled")
        except Exception as e:
            logger.warning("publish strategy activate failed %s: %s", strategy_id, e)
            activation_blockers.append(f"activate_exception:{type(e).__name__}")

        # Audit + memory trace
        if hasattr(self.main_controller, "log_audit_event"):
            try:
                from src.modules.core.audit_logger import AuditEventType, AuditSeverity

                await self.main_controller.log_audit_event(
                    event_type=AuditEventType.STRATEGY_LOAD,
                    severity=AuditSeverity.INFO,
                    action="publish_researched_strategy",
                    details={"strategy_id": strategy_id, "version": version, "metrics": test_metrics},
                    source="research_pipeline",
                )
            except Exception:
                pass

        if hasattr(self.main_controller, "memory_gateway") and self.main_controller.memory_gateway:
            try:
                await self.main_controller.memory_gateway.add_memory(
                    memory_type="strategy",
                    content=f"发布策略 {strategy_id} v{version}: test={test_metrics}",
                    metadata={"strategy_id": strategy_id, "version": version, "dsl": dsl, "test": test_metrics},
                    source_module="strategy_research_pipeline",
                    importance=0.85,
                    tags=["strategy", "research", "walkforward"],
                )
            except Exception:
                pass
            try:
                await self.main_controller.memory_gateway.save_knowledge_document(
                    title=f"Strategy Research Decision {strategy_id}",
                    content=(
                        f"version={version}\n"
                        f"decision={gov_decision}\n"
                        f"score={research_score}\n"
                        f"deployment_stage={deployment_stage}\n"
                        f"test_metrics={json.dumps(test_metrics, ensure_ascii=False)}"
                    ),
                    knowledge_type="strategy_research_decision",
                    metadata={"strategy_id": strategy_id, "version": version},
                )
            except Exception:
                pass
            try:
                await self.main_controller.memory_gateway.save_knowledge_document(
                    title=f"Experiment Card {strategy_id}",
                    content=json.dumps(experiment_card, ensure_ascii=False, indent=2),
                    knowledge_type="strategy_experiment_card",
                    metadata={"strategy_id": strategy_id, "version": version},
                )
            except Exception:
                pass
        try:
            fs = getattr(self.main_controller, "feature_store_lite", None)
            if fs and hasattr(fs, "append_research_label"):
                fs.append_research_label(
                    strategy_id,
                    {
                        "stage": "published" if gov_decision == "publish" else "review_required",
                        "oos_status": "passed" if gov_decision == "publish" else "review_required",
                        "decision": gov_decision,
                        "score": research_score,
                        "test_metrics": dict(test_metrics or {}),
                        "deployment_stage": deployment_stage,
                        "auto_activated": activated,
                        "activation_blockers": list(activation_blockers),
                        "review_window": review_window,
                    },
                )
        except Exception:
            pass

        try:
            from src.modules.core.strategy_manager import StrategyLifecycleStage

            if manual_approval_required:
                stage = StrategyLifecycleStage.PROPOSAL
            elif activated and deployment_stage == "full":
                stage = StrategyLifecycleStage.SCALED_LIVE
            elif activated:
                stage = StrategyLifecycleStage.LIMITED_LIVE
            else:
                stage = StrategyLifecycleStage.OOS_VALIDATING
            strategy_manager.set_strategy_governance_state(
                strategy_id,
                stage=stage,
                oos_status="manual_review_required" if manual_approval_required else ("passed" if gov_decision == "publish" else "review_required"),
                live_drift_status="unknown",
                reason="research_pipeline_publish",
            )
        except Exception:
            pass

        return {
            "strategy_id": strategy_id,
            "version": version,
            "test": test_metrics,
            "instance_id": instance_id,
            "activated": activated,
            "score": research_score,
            "decision": gov_decision,
            "deployment_stage": deployment_stage,
            "activation_blockers": activation_blockers,
            "enabled": auto_enable_published,
            "manual_approval_required": manual_approval_required,
            "review_window": review_window,
        }
