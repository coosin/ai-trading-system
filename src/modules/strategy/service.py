from __future__ import annotations

import inspect
from datetime import datetime, timedelta
from typing import Any, Dict, List


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return float(default)
        return float(v)
    except Exception:
        return float(default)


def _cfg_to_dict(cfg: Any, strategy_id: str) -> Dict[str, Any]:
    if hasattr(cfg, "to_dict"):
        try:
            out = cfg.to_dict()
            if isinstance(out, dict):
                return out
        except Exception:
            pass
    metadata = getattr(cfg, "metadata", {}) if cfg is not None else {}
    return {
        "strategy_id": getattr(cfg, "strategy_id", strategy_id),
        "name": getattr(cfg, "name", strategy_id),
        "description": getattr(cfg, "description", ""),
        "enabled": bool(getattr(cfg, "enabled", False)),
        "metadata": metadata if isinstance(metadata, dict) else {},
        "stage": getattr(getattr(cfg, "stage", None), "value", getattr(cfg, "stage", "unknown")),
        "oos_status": getattr(cfg, "oos_status", "unknown"),
        "live_drift_status": getattr(cfg, "live_drift_status", "unknown"),
    }


def _human_review_window(item: Dict[str, Any]) -> Dict[str, Any]:
    md = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
    rw = item.get("human_review_window") if isinstance(item.get("human_review_window"), dict) else None
    return rw or (md.get("review_window", {}) if isinstance(md.get("review_window"), dict) else {})


def _strategy_status(item: Dict[str, Any]) -> str:
    if item.get("enabled"):
        return "active"
    md = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
    approval = md.get("approval", {}) if isinstance(md.get("approval"), dict) else {}
    review = _human_review_window(item)
    if approval.get("state") == "manual_approval_required" or review.get("status") == "pending_approval":
        return "pending_approval"
    return "inactive"


class StrategyDomainService:
    def __init__(self, main_controller: Any) -> None:
        self.mc = main_controller

    async def overview(self) -> Dict[str, Any]:
        sm = getattr(self.mc, "strategy_manager", None) if self.mc else None
        if not sm:
            return {"degraded": True, "message": "strategy_manager_unavailable", "summary": {"total_strategies": 0}}

        items: List[Dict[str, Any]] = []
        for sid, cfg in list((getattr(sm, "strategy_configs", {}) or {}).items()):
            item = _cfg_to_dict(cfg, str(sid))
            item["status"] = _strategy_status(item)
            item["human_review_window"] = _human_review_window(item)
            items.append(item)

        stats = {}
        if hasattr(sm, "get_statistics"):
            try:
                stats = await sm.get_statistics()
            except Exception:
                stats = {}
        optimization = sm.get_optimization_status() if hasattr(sm, "get_optimization_status") else {}
        positions = await self._positions()
        ranking = await self._strategy_pnl_ranking(items)

        review_counts: Dict[str, int] = {}
        stage_counts: Dict[str, int] = {}
        pending: List[Dict[str, Any]] = []
        selected: List[Dict[str, Any]] = []
        retired: List[Dict[str, Any]] = []
        for item in items:
            rw = _human_review_window(item)
            status = str(rw.get("status") or "unknown")
            review_counts[status] = review_counts.get(status, 0) + 1
            md = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
            dep = md.get("deployment", {}) if isinstance(md.get("deployment"), dict) else {}
            stage = str(dep.get("stage") or item.get("stage") or "unknown")
            stage_counts[stage] = stage_counts.get(stage, 0) + 1
            row = {
                "strategy_id": item.get("strategy_id"),
                "name": item.get("name"),
                "enabled": item.get("enabled"),
                "status": item.get("status"),
                "deployment_stage": stage,
                "selection_score": rw.get("selection_score"),
                "selection_rank": rw.get("selection_rank"),
                "review_status": rw.get("status"),
                "review_mode": rw.get("mode"),
                "review_by": rw.get("review_by"),
            }
            if rw.get("status") in {"pending_approval", "open"}:
                pending.append(row)
            if rw.get("selection_reason") == "selected_high_score":
                selected.append(row)
            if rw.get("selection_reason") == "retired_low_score" or item.get("status") == "inactive":
                retired.append(row)

        selected.sort(key=lambda x: (x.get("selection_rank") is None, x.get("selection_rank") or 9999, str(x.get("strategy_id") or "")))
        retired.sort(key=lambda x: (x.get("selection_rank") is None, x.get("selection_rank") or 9999, str(x.get("strategy_id") or "")))
        pending.sort(key=lambda x: (self._parse_review_by(x.get("review_by")), str(x.get("strategy_id") or "")))
        return {
            "summary": {
                "total_strategies": len(items),
                "active_strategies": len([i for i in items if i.get("enabled")]),
                "best_strategy": getattr(sm, "best_strategy", None),
                "market_regime": getattr(getattr(sm, "market_regime", None), "value", getattr(sm, "market_regime", None)),
                "running_instances": int(stats.get("running_instances", 0) or 0),
                "total_instances": int(stats.get("total_instances", 0) or 0),
                "active_positions": len(positions),
                "realized_pnl_24h": round(sum(_to_float(r.get("total_pnl")) for r in ranking), 6),
                "realized_trades_24h": int(sum(int(r.get("trades", 0) or 0) for r in ranking)),
            },
            "strategies": items,
            "live_status": {"positions": positions[:12], "strategy_pnl_ranking_24h": ranking[:20]},
            "review_windows": {"total_visible": len([i for i in items if _human_review_window(i)]), "status_counts": review_counts, "pending_items": pending[:20]},
            "selection": {"selected_high_score": selected[:20], "retired_low_score": retired[:20]},
            "deployment_stage_counts": stage_counts,
            "optimization": optimization,
            "timestamp": datetime.now().isoformat(),
        }

    async def _positions(self) -> List[Dict[str, Any]]:
        exchange = None
        try:
            exchange = self.mc.get_exchange() if self.mc and hasattr(self.mc, "get_exchange") else getattr(self.mc, "okx_exchange", None)
        except Exception:
            exchange = None
        if exchange and hasattr(exchange, "get_positions"):
            try:
                rows = await exchange.get_positions()
                return rows if isinstance(rows, list) else []
            except Exception:
                return []
        return []

    async def _strategy_pnl_ranking(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        item_by_id = {str(i.get("strategy_id") or ""): i for i in items}
        ths = getattr(self.mc, "trade_history_service", None) if self.mc else None
        if not ths or not hasattr(ths, "get_trade_history"):
            return []
        try:
            rows = await ths.get_trade_history(start_date=datetime.now() - timedelta(days=1), limit=5000, offset=0)
        except TypeError:
            rows = await ths.get_trade_history(limit=5000)
        except Exception:
            rows = []
        by_strategy: Dict[str, Dict[str, Any]] = {}
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            strategy_id = str(md.get("strategy_id") or md.get("strategy_used") or row.get("strategy") or row.get("strategy_used") or "unknown")
            bucket = by_strategy.setdefault(strategy_id, {"strategy_id": strategy_id, "trades": 0, "wins": 0, "losses": 0, "total_pnl": 0.0, "gross_profit": 0.0, "gross_loss": 0.0, "total_fees": 0.0, "pnl_series": []})
            pnl = _to_float(row.get("pnl"))
            fee = _to_float(row.get("fee"))
            bucket["trades"] += 1
            bucket["total_pnl"] += pnl
            bucket["total_fees"] += fee
            bucket["pnl_series"].append({"timestamp": str(row.get("timestamp") or ""), "pnl": pnl})
            if pnl > 0:
                bucket["wins"] += 1
                bucket["gross_profit"] += pnl
            elif pnl < 0:
                bucket["losses"] += 1
                bucket["gross_loss"] += abs(pnl)
        out: List[Dict[str, Any]] = []
        for sid, bucket in by_strategy.items():
            item = item_by_id.get(sid) or {}
            rw = _human_review_window(item)
            md = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
            dep = md.get("deployment", {}) if isinstance(md.get("deployment"), dict) else {}
            gross_loss = float(bucket.get("gross_loss", 0.0) or 0.0)
            gross_profit = float(bucket.get("gross_profit", 0.0) or 0.0)
            trades = int(bucket.get("trades", 0) or 0)
            out.append({
                "strategy_id": sid,
                "enabled": bool(item.get("enabled", False)),
                "deployment_stage": str(dep.get("stage") or item.get("stage") or "unknown"),
                "review_status": rw.get("status"),
                "selection_rank": rw.get("selection_rank"),
                "selection_score": rw.get("selection_score"),
                "trades": trades,
                "wins": int(bucket.get("wins", 0) or 0),
                "losses": int(bucket.get("losses", 0) or 0),
                "total_pnl": round(float(bucket.get("total_pnl", 0.0) or 0.0), 6),
                "total_fees": round(float(bucket.get("total_fees", 0.0) or 0.0), 6),
                "win_rate": round((float(bucket.get("wins", 0) or 0) / max(1.0, float(trades))) * 100.0, 2),
                "expectancy_24h": round(float(bucket.get("total_pnl", 0.0) or 0.0) / max(1, trades), 6),
                "profit_factor_24h": round((gross_profit / gross_loss) if gross_loss > 1e-18 else (9999.0 if gross_profit > 0 else 0.0), 6),
                "max_drawdown_pnl_24h": round(self._calc_pnl_drawdown(list(bucket.get("pnl_series") or [])), 6),
            })
        return sorted(out, key=lambda x: (float(x.get("total_pnl", 0.0) or 0.0), int(x.get("trades", 0) or 0)), reverse=True)

    def list_items(self) -> List[Dict[str, Any]]:
        sm = getattr(self.mc, "strategy_manager", None) if self.mc else None
        if not sm:
            return []
        items: List[Dict[str, Any]] = []
        for sid, cfg in list((getattr(sm, "strategy_configs", {}) or {}).items()):
            item = _cfg_to_dict(cfg, str(sid))
            item["human_review_window"] = _human_review_window(item)
            item["status"] = _strategy_status(item)
            items.append(item)
        return items

    async def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        sm = self._manager()
        requested_enabled = bool(payload.get("enabled", True))
        data = dict(payload or {})
        if not data.get("strategy_id"):
            data["strategy_id"] = f"api_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        cfg = await sm.load_strategy_config({**data, "enabled": False if requested_enabled else bool(data.get("enabled", False))})
        if not cfg:
            return {"ok": False, "status_code": 400, "detail": "策略配置无效：需含 name、strategy_type"}
        gate = self._activation_gate(sm, cfg.strategy_id)
        if requested_enabled:
            if gate and not gate.get("eligible"):
                lock = getattr(sm, "_lock", None)
                if lock:
                    async with lock:
                        sm.strategy_configs.pop(cfg.strategy_id, None)
                        getattr(sm, "performance_metrics", {}).pop(cfg.strategy_id, None)
                else:
                    sm.strategy_configs.pop(cfg.strategy_id, None)
                return {"ok": False, "status_code": 400, "detail": f"策略未达到启用门槛: {','.join(gate.get('reasons') or [])}"}
            cfg.enabled = True
        return {"ok": True, "id": cfg.strategy_id, "name": cfg.name, "status": "active" if cfg.enabled else "inactive", "activation_gate": gate}

    async def update(self, strategy_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        sm = self._manager()
        if strategy_id not in sm.strategy_configs:
            return {"ok": False, "status_code": 404, "detail": "策略不存在"}
        cfg = sm.strategy_configs[strategy_id]
        if "enabled" in payload and bool(payload["enabled"]):
            gate = self._activation_gate(sm, strategy_id)
            if gate and not gate.get("eligible"):
                return {"ok": False, "status_code": 400, "detail": f"策略未达到启用门槛: {','.join(gate.get('reasons') or [])}"}
        for key in ("name", "description"):
            if key in payload:
                setattr(cfg, key, str(payload[key]))
        if "enabled" in payload:
            cfg.enabled = bool(payload["enabled"])
        if "parameters" in payload and isinstance(payload["parameters"], dict):
            cfg.parameters = {**getattr(cfg, "parameters", {}), **payload["parameters"]}
        if "symbols" in payload and isinstance(payload["symbols"], list):
            cfg.symbols = list(payload["symbols"])
        cfg.updated_at = datetime.now()
        item = _cfg_to_dict(cfg, strategy_id)
        return {"ok": True, "id": strategy_id, "name": getattr(cfg, "name", strategy_id), "status": _strategy_status(item)}

    async def approve(self, strategy_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        sm = self._manager()
        if strategy_id not in sm.strategy_configs:
            return {"ok": False, "status_code": 404, "detail": "策略不存在"}
        approve_fn = getattr(sm, "approve_strategy_for_execution", None) or getattr(sm, "approve_strategy", None)
        if approve_fn is None:
            return {"ok": False, "status_code": 501, "detail": "策略审批能力未实现"}
        kwargs = {
            "approved_by": str((payload or {}).get("approved_by") or "manual"),
            "reason": str((payload or {}).get("reason") or "manual_approval"),
        }
        result = await approve_fn(strategy_id, **kwargs) if inspect.iscoroutinefunction(approve_fn) else approve_fn(strategy_id, **kwargs)
        if not result.get("approved"):
            gate = result.get("activation_gate") if isinstance(result.get("activation_gate"), dict) else None
            detail = f"策略未达到启用门槛: {','.join(gate.get('reasons') or [])}" if gate and gate.get("reasons") else str(result.get("reason") or "策略审批失败")
            return {"ok": False, "status_code": 400, "detail": detail}
        return {"ok": True, "status": "success", "message": "策略已批准并启用", **result}

    async def activate(self, strategy_id: str) -> Dict[str, Any]:
        sm = self._manager()
        if strategy_id not in sm.strategy_configs:
            return {"ok": False, "status_code": 404, "detail": "策略不存在"}
        gate = self._activation_gate(sm, strategy_id)
        if gate and not gate.get("eligible"):
            return {"ok": False, "status_code": 400, "detail": f"策略未达到启用门槛: {','.join(gate.get('reasons') or [])}"}
        sm.strategy_configs[strategy_id].enabled = True
        return {"ok": True, "status": "success", "message": "策略已激活", "activation_gate": gate}

    async def deactivate(self, strategy_id: str) -> Dict[str, Any]:
        sm = self._manager()
        if strategy_id not in sm.strategy_configs:
            return {"ok": False, "status_code": 404, "detail": "策略不存在"}
        sm.strategy_configs[strategy_id].enabled = False
        return {"ok": True, "status": "success", "message": "策略已停用"}

    async def delete(self, strategy_id: str) -> Dict[str, Any]:
        sm = self._manager()
        lock = getattr(sm, "_lock", None)
        if lock:
            async with lock:
                sm.strategy_configs.pop(strategy_id, None)
                getattr(sm, "performance_metrics", {}).pop(strategy_id, None)
        else:
            sm.strategy_configs.pop(strategy_id, None)
        return {"ok": True, "status": "success", "message": "策略已删除"}

    def _manager(self) -> Any:
        sm = getattr(self.mc, "strategy_manager", None) if self.mc else None
        if not sm:
            raise RuntimeError("策略管理器未初始化")
        return sm

    @staticmethod
    def _activation_gate(sm: Any, strategy_id: str) -> Dict[str, Any] | None:
        return sm.get_strategy_activation_gate(strategy_id) if hasattr(sm, "get_strategy_activation_gate") else None

    @staticmethod
    def _parse_review_by(value: Any) -> datetime:
        raw = str(value or "").strip()
        if not raw:
            return datetime.max
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return datetime.max

    @staticmethod
    def _calc_pnl_drawdown(series: List[Dict[str, Any]]) -> float:
        cum = 0.0
        peak = 0.0
        max_dd = 0.0
        for item in sorted(series, key=lambda x: str(x.get("timestamp") or "")):
            cum += _to_float(item.get("pnl"))
            peak = max(peak, cum)
            max_dd = max(max_dd, peak - cum)
        return max_dd
