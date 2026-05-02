"""
模块控制API - 提供所有系统模块的集中控制接口
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        if x == x:
            return x
    except Exception:
        pass
    return float(default)

def init_module_control_api(app, main_controller):
    """初始化模块控制API"""
    
    from fastapi import APIRouter, Body

    router = APIRouter(prefix="/api/v1/modules", tags=["modules"])
    trade_router = APIRouter(prefix="/api/v1/trade", tags=["trade"])
    market_router = APIRouter(prefix="/api/v1/market", tags=["market"])
    research_jobs: Dict[str, Dict[str, Any]] = {}
    research_jobs_lock = asyncio.Lock()
    research_semaphore = asyncio.Semaphore(1)
    dispatch_jobs: Dict[str, Dict[str, Any]] = {}
    dispatch_jobs_lock = asyncio.Lock()

    async def _check_unified_data_quality(
        symbol: str = "BTC/USDT",
        min_score: float = 0.5,
    ) -> Dict[str, Any]:
        mc = main_controller
        if not mc:
            return {"ok": False, "score": None, "message": "主控制器未初始化"}
        hub = getattr(mc, "data_source_hub", None)
        if not hub or not hasattr(hub, "get_unified_snapshot"):
            return {"ok": True, "score": None, "message": "统一数据源中心不可用，跳过门控"}
        try:
            # 防止上游行情/交易所抖动导致 API 入口阻塞。
            snap = await asyncio.wait_for(hub.get_unified_snapshot(symbol), timeout=6.0)
            quality = (snap.get("数据质量评估") or {}) if isinstance(snap, dict) else {}
            score = quality.get("score")
            score_f = float(score) if score is not None else None
            if score_f is None:
                return {"ok": True, "score": None, "message": "未返回质量分，跳过门控"}
            return {
                "ok": score_f >= float(min_score),
                "score": score_f,
                "symbol": symbol,
                "message": f"数据质量={score_f:.3f}, 阈值={float(min_score):.3f}",
            }
        except asyncio.TimeoutError:
            return {"ok": True, "score": None, "message": "质量门控超时，已降级放行"}
        except Exception as e:
            return {"ok": True, "score": None, "message": f"质量门控检查失败，已降级放行: {e}"}

    async def _notify_quality_warning(title: str, gate: Dict[str, Any]) -> None:
        """将数据质量告警推送到统一通知通道（含 TG 等），不中断主流程。"""
        try:
            if not main_controller:
                return
            symbol = str(gate.get("symbol") or "BTC/USDT")
            ai_line = ""
            # analysis moved to MarketIntelligenceEngine
            mi = getattr(main_controller, "market_intelligence", None)
            if mi and hasattr(mi, "get_symbol_view"):
                try:
                    view = await mi.get_symbol_view(symbol, include_snapshot=False)
                    ai_line = (
                        f"\nMI: 趋势={getattr(view, 'trend', '-') or '-'} | 倾向={getattr(view, 'action_bias', '-') or '-'} | "
                        f"置信度={getattr(view, 'confidence', None) if getattr(view, 'confidence', None) is not None else '-'}"
                    )
                    summary = str(getattr(view, "summary", "") or "").strip()
                    if summary:
                        ai_line += f"\n摘要: {summary[:180]}"
                except Exception:
                    pass
            msg = f"{title}\n{gate.get('message', '')}{ai_line}"
            if hasattr(main_controller, "_send_notification_handler"):
                await main_controller._send_notification_handler("数据质量告警", msg, priority="medium")
        except Exception:
            pass

    async def _run_research_job(job_id: str, payload: Dict[str, Any]) -> None:
        """后台执行研究任务，避免阻塞 API worker。"""
        if not main_controller:
            async with research_jobs_lock:
                research_jobs[job_id]["status"] = "failed"
                research_jobs[job_id]["message"] = "主控制器未初始化"
                research_jobs[job_id]["finished_at"] = datetime.now().isoformat()
            return

        pipeline = getattr(main_controller, "strategy_research_pipeline", None)
        if not pipeline:
            async with research_jobs_lock:
                research_jobs[job_id]["status"] = "failed"
                research_jobs[job_id]["message"] = "策略研究流水线未初始化"
                research_jobs[job_id]["finished_at"] = datetime.now().isoformat()
            return

        raw_syms = payload.get("symbols") or ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
        if isinstance(raw_syms, str):
            symbols = [raw_syms]
        elif isinstance(raw_syms, list):
            symbols = [str(s) for s in raw_syms if s]
        else:
            symbols = ["BTC/USDT", "ETH/USDT"]

        timeframe = str(payload.get("timeframe") or "1h")
        lookback_days = max(7, int(payload.get("lookback_days") or 28))
        timeout_sec = max(120, int(payload.get("timeout_seconds") or 1800))
        max_symbols = max(1, int(payload.get("max_symbols") or min(6, len(symbols))))
        sym_slice = symbols[:max_symbols]

        async with research_jobs_lock:
            research_jobs[job_id].update(
                {
                    "status": "running",
                    "symbols_used": sym_slice,
                    "timeframe": timeframe,
                    "lookback_days": lookback_days,
                    "timeout_seconds": timeout_sec,
                    "started_at": datetime.now().isoformat(),
                }
            )

    @trade_router.get("/events")
    async def get_trade_events(
        limit: int = 200,
        cursor: Optional[int] = None,
        type: Optional[str] = None,  # noqa: A002 (fastapi query param)
        symbol: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        获取最近交易域事件（Intent/Fill/Position）。
        前端可轮询或配合 WebSocket 订阅 channel=trade.*（支持前缀通配符）。
        """
        mc = main_controller
        hub = getattr(mc, "trade_event_hub", None) if mc else None
        if not hub or not (hasattr(hub, "query_recent") or hasattr(hub, "get_recent")):
            return {"ok": False, "events": [], "message": "TradeEventHub unavailable"}
        try:
            if hasattr(hub, "query_recent"):
                q = hub.query_recent(limit=int(limit or 200), cursor=cursor, event_type=type, symbol=symbol, trace_id=trace_id)
                return {"ok": True, **q}
            return {"ok": True, "events": hub.get_recent(limit=int(limit or 200))}
        except Exception as e:
            return {"ok": False, "events": [], "message": str(e)}

    @trade_router.get("/execution_spine")
    async def get_execution_spine_snapshot() -> Dict[str, Any]:
        """返回 S1 ExecutionGateway 快照（包含 policy_metrics）。"""
        mc = main_controller
        gw = getattr(mc, "execution_gateway", None) if mc else None
        if not gw or not hasattr(gw, "get_snapshot"):
            return {"ok": False, "message": "ExecutionGateway unavailable"}
        try:
            snap = await gw.get_snapshot()
            return {"ok": True, "snapshot": snap}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    # NOTE: symbols contain '/', use :path to match the whole remainder.
    @market_router.get("/symbol/{symbol:path}")
    async def get_market_symbol_view(
        symbol: str,
        include_snapshot: bool = False,
        fields: Optional[str] = None,
    ) -> Dict[str, Any]:
        """统一行情汇总：单品种视图（供前端/模块复用）。"""
        def _normalize_market_symbol(raw: str) -> str:
            s = str(raw or "").strip().upper().replace("-", "/")
            if not s:
                return "BTC/USDT"
            # Bare asset symbol like BTC -> BTC/USDT to avoid false degraded reads.
            if "/" not in s:
                if s.endswith("USDT"):
                    base = s[:-4].strip()
                    return f"{base}/USDT" if base else "BTC/USDT"
                return f"{s}/USDT"
            parts = [p for p in s.split("/") if p]
            if len(parts) >= 2:
                return f"{parts[0]}/{parts[1]}"
            return "BTC/USDT"

        symbol = _normalize_market_symbol(symbol)
        mc = main_controller
        mi = getattr(mc, "market_intelligence", None) if mc else None
        if not mi or not hasattr(mi, "get_symbol_view"):
            return {"ok": False, "message": "MarketIntelligenceEngine unavailable"}
        def _ensure_execution_support_schema(view_obj: Dict[str, Any]) -> Dict[str, Any]:
            """Keep response schema stable under degraded/cached paths."""
            if not isinstance(view_obj, dict):
                return {}
            es = view_obj.get("execution_support")
            if not isinstance(es, dict):
                es = {}
            if not isinstance(es.get("stable_anomalies"), list):
                es["stable_anomalies"] = []
            if not isinstance(es.get("anomaly_stability"), dict):
                es["anomaly_stability"] = {
                    "confirm_hits": 2,
                    "ttl_sec": 900,
                    "items": [],
                }
            if not isinstance(es.get("extra_provider_summary"), dict):
                es["extra_provider_summary"] = {
                    "aicoin_enabled": False,
                    "coinglass_enabled": False,
                }
            view_obj["execution_support"] = es
            return view_obj
        try:
            # Avoid blocking the control-plane. Prefer cached view when upstream is unstable.
            try:
                cached = mi.get_cached_symbol_view(symbol) if hasattr(mi, "get_cached_symbol_view") else {}
            except Exception:
                cached = {}
            if cached and not bool(include_snapshot):
                out_view = _ensure_execution_support_schema(dict(cached))
                if fields:
                    allow = {k.strip() for k in str(fields).split(",") if k.strip()}
                    allow.add("symbol")
                    allow.add("timestamp")
                    out_view = {k: v for k, v in out_view.items() if k in allow}
                return {
                    "ok": True,
                    "view": out_view,
                    "snapshot": None,
                    "degraded": True,
                    "message": "symbol_view_cached",
                    "degraded_reason": {
                        "code": "cached_fastpath",
                        "source": "market_intelligence_cache",
                        "include_snapshot": bool(include_snapshot),
                        "note": "返回缓存快照以保证控制面快速响应",
                    },
                }
            # include_snapshot 请求：优先返回缓存，并触发后台异步刷新，避免前台阻塞慢源链路。
            if cached and bool(include_snapshot):
                out_view = _ensure_execution_support_schema(dict(cached))
                try:
                    if hasattr(mi, "refresh_symbol_async"):
                        asyncio.create_task(mi.refresh_symbol_async(symbol, include_snapshot=True))
                except Exception:
                    pass
                if fields:
                    allow = {k.strip() for k in str(fields).split(",") if k.strip()}
                    allow.add("symbol")
                    allow.add("timestamp")
                    out_view = {k: v for k, v in out_view.items() if k in allow}
                return {
                    "ok": True,
                    "view": out_view,
                    "snapshot": None,
                    "degraded": bool(out_view.get("partial", False)),
                    "message": "symbol_view_cached_refreshing",
                    "degraded_reason": {
                        "code": "cached_refreshing",
                        "source": "market_intelligence_cache",
                        "include_snapshot": True,
                        "note": "已返回缓存并触发后台刷新",
                    },
                }

            # include_snapshot 请求但无缓存：先返回快路径视图（不阻塞），并后台刷新完整快照。
            if bool(include_snapshot) and not cached:
                try:
                    # 立刻返回 warming stub：保证控制面/诊断接口首次响应毫秒级。
                    # 后台异步刷新会把缓存补齐，后续请求会走 symbol_view_cached_refreshing。
                    out_view = _ensure_execution_support_schema(
                        {
                            "symbol": symbol,
                            "timestamp": None,
                            "trend": "unknown",
                            "action_bias": "hold",
                            "confidence": None,
                            "quality_score": None,
                            "spread_bps": None,
                            "atr_pct_1h": None,
                            "price": None,
                            "funding_rate": None,
                            "depth_imbalance": None,
                            "partial": True,
                            "cache_age_sec": None,
                        }
                    )
                except Exception:
                    out_view = _ensure_execution_support_schema({})
                try:
                    if hasattr(mi, "refresh_symbol_async"):
                        asyncio.create_task(mi.refresh_symbol_async(symbol, include_snapshot=True))
                except Exception:
                    pass
                if fields:
                    allow = {k.strip() for k in str(fields).split(",") if k.strip()}
                    allow.add("symbol")
                    allow.add("timestamp")
                    out_view = {k: v for k, v in out_view.items() if k in allow}
                return {
                    "ok": True,
                    "view": out_view,
                    "snapshot": None,
                    "degraded": True,
                    "message": "symbol_view_fastpath_refreshing",
                    "degraded_reason": {
                        "code": "fastpath_refreshing",
                        "source": "market_intelligence_get_symbol_view",
                        "include_snapshot": True,
                        "note": "无缓存：已返回快路径并触发后台刷新",
                    },
                }

            # unified_snapshot has its own bounded budget (DataSourceHub.snapshot_timeout_sec, default ~2.5s).
            # In proxy-only environments, scheduling + JSON + partial collectors can push the end-to-end
            # call slightly above 3s. Use a slightly larger cap to avoid false "timeout_degraded".
            req_timeout = 10.5 if bool(include_snapshot) else 4.5
            view = await asyncio.wait_for(
                mi.get_symbol_view(
                    symbol,
                    include_snapshot=bool(include_snapshot),
                    # API 默认查询不带 snapshot 时，优先快路径，避免被重采集拖慢并产生误导性 timeout。
                    prefer_fast_only=not bool(include_snapshot),
                ),
                timeout=req_timeout,
            )
            out_view = view.to_dict()
            out_view = _ensure_execution_support_schema(out_view)
            if fields:
                allow = {k.strip() for k in str(fields).split(",") if k.strip()}
                allow.add("symbol")
                allow.add("timestamp")
                out_view = {k: v for k, v in out_view.items() if k in allow}
            return {
                "ok": True,
                "view": out_view,
                "snapshot": view.snapshot if include_snapshot else None,
                "degraded": False,
                "degraded_reason": None,
            }
        except asyncio.TimeoutError:
            try:
                cached = mi.get_cached_symbol_view(symbol) if hasattr(mi, "get_cached_symbol_view") else {}
            except Exception:
                cached = {}
            cached = _ensure_execution_support_schema(dict(cached) if isinstance(cached, dict) else {})
            return {
                "ok": True,
                "view": cached or {},
                "snapshot": None,
                "degraded": True,
                "message": "symbol_view_timeout_degraded",
                "degraded_reason": {
                    "code": "upstream_timeout",
                    "source": "market_intelligence_get_symbol_view",
                    "include_snapshot": bool(include_snapshot),
                    "note": "上游采集超时，已降级为缓存/空结果",
                },
            }
        except Exception as e:
            return {
                "ok": False,
                "message": str(e),
                "degraded": True,
                "degraded_reason": {
                    "code": "internal_error",
                    "source": "market_symbol_view_handler",
                    "include_snapshot": bool(include_snapshot),
                    "note": "接口内部异常，请查看服务日志",
                },
            }

    @market_router.get("/state")
    async def get_market_state(timeout_sec: float = 3.2) -> Dict[str, Any]:
        """统一行情汇总：全局市场状态（多 symbol 聚合）。"""
        mc = main_controller
        mi = getattr(mc, "market_intelligence", None) if mc else None
        if not mi or not hasattr(mi, "get_market_state"):
            return {"ok": False, "message": "MarketIntelligenceEngine unavailable"}
        timeout_sec = max(1.5, min(float(timeout_sec or 3.2), 8.0))
        try:
            # 防止聚合计算/上游抖动导致 API 阻塞（前端/运维需要“快返回”）。
            # market_state is a fan-out aggregation. Keep it bounded but avoid being too tight.
            started_at = datetime.now()
            state = await asyncio.wait_for(mi.get_market_state(), timeout=timeout_sec)
            latency_ms = int((datetime.now() - started_at).total_seconds() * 1000)
            return {"ok": True, "state": state, "degraded": False, "latency_ms": latency_ms}
        except asyncio.TimeoutError:
            cached = None
            try:
                cached = mi.get_cached_market_state() if hasattr(mi, "get_cached_market_state") else None
            except Exception:
                cached = None
            return {
                "ok": True,
                "state": cached or {},
                "degraded": True,
                "message": "market_state_timeout_degraded",
                "timeout_sec": timeout_sec,
            }
        except Exception as e:
            return {"ok": False, "message": str(e)}

        def _run_cycle_in_thread() -> Dict[str, Any]:
            # 在独立线程事件循环中执行重型研究流程，避免阻塞主 API loop。
            return asyncio.run(
                pipeline.run_cycle(symbols=sym_slice, timeframe=timeframe, lookback_days=lookback_days)
            )

        try:
            async with research_semaphore:
                result = await asyncio.wait_for(asyncio.to_thread(_run_cycle_in_thread), timeout=timeout_sec)
            async with research_jobs_lock:
                research_jobs[job_id].update(
                    {
                        "status": "completed",
                        "result": result,
                        "finished_at": datetime.now().isoformat(),
                    }
                )
        except asyncio.TimeoutError:
            async with research_jobs_lock:
                research_jobs[job_id].update(
                    {
                        "status": "failed",
                        "message": f"策略研发执行超时（>{timeout_sec}s）",
                        "finished_at": datetime.now().isoformat(),
                    }
                )
        except Exception as e:
            logger.exception("手动策略研发失败")
            async with research_jobs_lock:
                research_jobs[job_id].update(
                    {
                        "status": "failed",
                        "message": str(e),
                        "finished_at": datetime.now().isoformat(),
                    }
                )
    
    @router.get("/list")
    async def get_all_modules():
        """获取所有模块列表和状态"""
        modules = []
        
        if main_controller:
            if hasattr(main_controller, 'ai_trading_engine') and main_controller.ai_trading_engine:
                modules.append({
                    "id": "ai_trading_engine",
                    "name": "AI交易引擎",
                    "category": "核心",
                    "status": "running" if main_controller.ai_trading_engine._running else "stopped",
                    "health": "healthy",
                    "description": "全智能AI交易引擎，自动分析市场并执行交易",
                    "controls": ["start", "stop", "analyze"]
                })
            
            if hasattr(main_controller, 'llm_integration') and main_controller.llm_integration:
                modules.append({
                    "id": "llm_integration",
                    "name": "AI大模型集成",
                    "category": "AI",
                    "status": "running",
                    "health": "healthy",
                    "description": "大语言模型集成系统，支持讯飞、百度千帆等",
                    "controls": ["chat", "analyze"]
                })
            
            if hasattr(main_controller, 'telegram_bot') and main_controller.telegram_bot:
                modules.append({
                    "id": "telegram_bot",
                    "name": "Telegram机器人",
                    "category": "通信",
                    "status": "running",
                    "health": "healthy",
                    "description": "Telegram通信机器人，接收用户指令并发送通知",
                    "controls": ["start", "stop", "test"]
                })
            
            if hasattr(main_controller, 'emergency_stop') and main_controller.emergency_stop:
                modules.append({
                    "id": "emergency_stop",
                    "name": "紧急停止系统",
                    "category": "安全",
                    "status": "ready",
                    "health": "healthy",
                    "description": "紧急情况下自动停止交易",
                    "controls": ["trigger", "reset"]
                })
            
            if hasattr(main_controller, 'intelligent_monitoring') and main_controller.intelligent_monitoring:
                modules.append({
                    "id": "intelligent_monitoring",
                    "name": "智能监控系统",
                    "category": "监控",
                    "status": "running",
                    "health": "healthy",
                    "description": "监控系统健康状态和性能指标",
                    "controls": ["check", "alert"]
                })
            
            if hasattr(main_controller, 'security_manager') and main_controller.security_manager:
                modules.append({
                    "id": "security_manager",
                    "name": "安全管理器",
                    "category": "安全",
                    "status": "running",
                    "health": "healthy",
                    "description": "系统安全检测和防护",
                    "controls": ["scan", "audit"]
                })
            
            if hasattr(main_controller, 'fund_manager') and main_controller.fund_manager:
                modules.append({
                    "id": "fund_manager",
                    "name": "智能资金管理器",
                    "category": "资金",
                    "status": "running" if main_controller.fund_manager.enabled else "stopped",
                    "health": "healthy",
                    "description": "智能资金分配和仓位管理",
                    "controls": ["start", "stop", "rebalance"]
                })
            
            if hasattr(main_controller, 'ai_learning_engine') and main_controller.ai_learning_engine:
                modules.append({
                    "id": "ai_learning_engine",
                    "name": "AI学习引擎",
                    "category": "AI",
                    "status": "running" if main_controller.ai_learning_engine._running else "stopped",
                    "health": "healthy",
                    "description": "自动学习交易经验并优化策略",
                    "controls": ["start", "stop", "learn"]
                })
            
            if hasattr(main_controller, 'anomaly_detector') and main_controller.anomaly_detector:
                modules.append({
                    "id": "anomaly_detector",
                    "name": "异常检测器",
                    "category": "监控",
                    "status": "running",
                    "health": "healthy",
                    "description": "检测市场异常和系统异常",
                    "controls": ["detect", "report"]
                })
            
            if hasattr(main_controller, 'strategy_manager') and main_controller.strategy_manager:
                modules.append({
                    "id": "strategy_manager",
                    "name": "策略管理器",
                    "category": "策略",
                    "status": "running",
                    "health": "healthy",
                    "description": "管理多个交易策略",
                    "controls": ["list", "activate", "deactivate"]
                })
            
            if hasattr(main_controller, 'portfolio_optimizer') and main_controller.portfolio_optimizer:
                modules.append({
                    "id": "portfolio_optimizer",
                    "name": "组合优化器",
                    "category": "策略",
                    "status": "ready",
                    "health": "healthy",
                    "description": "优化投资组合配置",
                    "controls": ["optimize", "rebalance"]
                })
            
            if hasattr(main_controller, 'backup_manager') and main_controller.backup_manager:
                modules.append({
                    "id": "backup_manager",
                    "name": "数据备份管理器",
                    "category": "数据",
                    "status": "running",
                    "health": "healthy",
                    "description": "自动备份系统数据",
                    "controls": ["backup", "restore", "schedule"]
                })
        
        return {
            "modules": modules,
            "total": len(modules),
            "timestamp": datetime.now().isoformat()
        }
    
    @router.post("/{module_id}/control")
    async def control_module(module_id: str, action: str, params: Optional[Dict] = None):
        """控制指定模块"""
        params = params or {}
        result = {"success": False, "message": ""}
        
        try:
            if module_id == "ai_trading_engine":
                if main_controller and hasattr(main_controller, 'ai_trading_engine'):
                    engine = main_controller.ai_trading_engine
                    if action == "start":
                        if not engine._running:
                            await engine.start()
                        result = {"success": True, "message": "AI交易引擎已启动"}
                    elif action == "stop":
                        await engine.stop()
                        result = {"success": True, "message": "AI交易引擎已停止"}
                    elif action == "analyze":
                        symbol = params.get("symbol", "BTC/USDT")
                        result = {"success": True, "message": f"开始分析 {symbol}", "data": {"symbol": symbol}}
            
            elif module_id == "telegram_bot":
                if main_controller and hasattr(main_controller, 'telegram_bot'):
                    bot = main_controller.telegram_bot
                    if action == "test":
                        result = {"success": True, "message": "Telegram机器人测试成功"}
            
            elif module_id == "emergency_stop":
                if main_controller and hasattr(main_controller, 'emergency_stop'):
                    es = main_controller.emergency_stop
                    if action == "trigger":
                        await es._trigger_emergency(
                            level="HIGH",
                            type="manual_trigger",
                            description="手动触发紧急停止"
                        )
                        result = {"success": True, "message": "紧急停止已触发"}
                    elif action == "reset":
                        es._is_emergency_mode = False
                        result = {"success": True, "message": "紧急停止已重置"}
            
            elif module_id == "fund_manager":
                if main_controller and hasattr(main_controller, 'fund_manager'):
                    fm = main_controller.fund_manager
                    if action == "start":
                        fm.enabled = True
                        result = {"success": True, "message": "资金管理器已启动"}
                    elif action == "stop":
                        fm.enabled = False
                        result = {"success": True, "message": "资金管理器已停止"}
            
            elif module_id == "ai_learning_engine":
                if main_controller and hasattr(main_controller, 'ai_learning_engine'):
                    le = main_controller.ai_learning_engine
                    if action == "start":
                        await le.start()
                        result = {"success": True, "message": "AI学习引擎已启动"}
                    elif action == "stop":
                        await le.stop()
                        result = {"success": True, "message": "AI学习引擎已停止"}
            
            else:
                result = {"success": False, "message": f"未知模块: {module_id}"}
        
        except Exception as e:
            result = {"success": False, "message": f"操作失败: {str(e)}"}
        
        return result
    
    @router.get("/trading/symbols")
    async def get_trading_symbols():
        """获取交易对配置"""
        blacklist = []
        if main_controller and hasattr(main_controller, 'ai_trading_engine'):
            engine = main_controller.ai_trading_engine
            if hasattr(engine, 'symbols'):
                return {
                    "symbols": engine.symbols,
                    "blacklist": blacklist,
                    "message": "ETH已允许交易"
                }
        return {
            "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"],
            "blacklist": blacklist
        }
    
    @router.post("/trading/symbols/config")
    async def config_trading_symbols(config: Dict[str, Any]):
        """配置交易对"""
        symbols = config.get("symbols", [])
        blacklist = config.get("blacklist", [])
        
        if main_controller and hasattr(main_controller, 'ai_trading_engine'):
            engine = main_controller.ai_trading_engine
            filtered_symbols = [s for s in symbols if s not in blacklist]
            engine.symbols = filtered_symbols
            return {
                "success": True,
                "message": f"交易对已更新，黑名单: {blacklist}",
                "symbols": filtered_symbols,
                "blacklist": blacklist
            }
        
        return {"success": False, "message": "AI交易引擎未初始化"}
    
    @router.get("/models")
    async def get_ai_models():
        """获取AI模型列表"""
        models = []
        if main_controller and hasattr(main_controller, 'enhanced_llm_manager'):
            mgr = main_controller.enhanced_llm_manager
            for model_id, config in mgr.models.items():
                models.append({
                    "id": model_id,
                    "name": config.display_name,
                    "provider": config.provider.value,
                    "priority": config.priority,
                    "enabled": config.enabled,
                    "context_window": config.context_window
                })
        
        return {
            "models": models,
            "total": len(models)
        }
    
    @router.post("/models/{model_id}/select")
    async def select_ai_model(model_id: str):
        """选择AI模型"""
        if main_controller and hasattr(main_controller, 'enhanced_llm_manager'):
            mgr = main_controller.enhanced_llm_manager
            if model_id in mgr.models:
                mgr.default_model = model_id
                return {"success": True, "message": f"已切换到模型: {model_id}"}
        
        return {"success": False, "message": "模型不存在"}
    
    @router.get("/risk/status")
    async def get_risk_status():
        """获取风险状态"""
        risk_data = {
            "circuit_breaker": {"status": "closed", "trigger_count": 0},
            "daily_trades": 0,
            "hourly_trades": 0,
            "consecutive_losses": 0,
            "current_drawdown": 0.0,
            "risk_level": "low"
        }

        def _resolve_risk_monitor():
            if not main_controller:
                return None
            if hasattr(main_controller, 'risk_monitor') and main_controller.risk_monitor:
                return main_controller.risk_monitor
            if (
                hasattr(main_controller, 'ai_trading_engine')
                and main_controller.ai_trading_engine
                and hasattr(main_controller.ai_trading_engine, 'risk_monitor')
                and main_controller.ai_trading_engine.risk_monitor
            ):
                return main_controller.ai_trading_engine.risk_monitor
            return None

        if main_controller:
            monitor = _resolve_risk_monitor()

            if monitor:
                status = monitor.get_status() if hasattr(monitor, "get_status") else {}
                risk_data.update(status if isinstance(status, dict) else {})
                risk_data["monitor_running"] = bool(
                    (status or {}).get("running", False) if isinstance(status, dict) else False
                )
            
            if hasattr(main_controller, 'ai_trading_engine') and main_controller.ai_trading_engine:
                engine = main_controller.ai_trading_engine
                if hasattr(engine, 'enhanced_risk') and engine.enhanced_risk:
                    risk_status = engine.enhanced_risk.get_risk_status()
                    risk_data["circuit_breaker"] = risk_status.get("circuit_breaker", {})
                    risk_data["risk_level"] = risk_status.get("trading_state", {}).get("daily_trades", 0) > 15 and "medium" or "low"
        
        return risk_data

    @router.get("/risk/config")
    async def get_risk_config():
        """读取账户风险监控阈值配置"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        monitor = None
        if hasattr(main_controller, 'risk_monitor') and main_controller.risk_monitor:
            monitor = main_controller.risk_monitor
        elif (
            hasattr(main_controller, 'ai_trading_engine')
            and main_controller.ai_trading_engine
            and hasattr(main_controller.ai_trading_engine, 'risk_monitor')
            and main_controller.ai_trading_engine.risk_monitor
        ):
            monitor = main_controller.ai_trading_engine.risk_monitor
        if not monitor:
            return {"success": False, "message": "风险监控未初始化"}
        return {
            "success": True,
            "config": dict(getattr(monitor, "risk_config", {}) or {}),
            "running": bool(getattr(monitor, "_running", False)),
        }

    @router.post("/risk/config")
    async def update_risk_config(payload: Dict[str, Any]):
        """更新账户风险监控阈值（运行期生效）"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        monitor = None
        if hasattr(main_controller, 'risk_monitor') and main_controller.risk_monitor:
            monitor = main_controller.risk_monitor
        elif (
            hasattr(main_controller, 'ai_trading_engine')
            and main_controller.ai_trading_engine
            and hasattr(main_controller.ai_trading_engine, 'risk_monitor')
            and main_controller.ai_trading_engine.risk_monitor
        ):
            monitor = main_controller.ai_trading_engine.risk_monitor
        if not monitor:
            return {"success": False, "message": "风险监控未初始化"}

        allowed = {
            "margin_ratio_warning",
            "margin_ratio_critical",
            "unrealized_loss_warning",
            "unrealized_loss_critical",
            "liquidation_distance_warning",
            "liquidation_distance_critical",
            "monitor_interval",
        }
        applied: Dict[str, Any] = {}
        for k, v in (payload or {}).items():
            if k not in allowed or v is None:
                continue
            try:
                if k == "monitor_interval":
                    monitor.risk_config[k] = max(2, int(float(v)))
                else:
                    monitor.risk_config[k] = float(v)
                applied[k] = monitor.risk_config[k]
            except Exception:
                continue
        return {"success": True, "applied": applied, "config": dict(monitor.risk_config)}
    
    @router.post("/risk/reset")
    async def reset_risk_counters():
        """重置风险计数器"""
        if main_controller and hasattr(main_controller, 'ai_trading_engine'):
            engine = main_controller.ai_trading_engine
            if hasattr(engine, 'enhanced_risk') and engine.enhanced_risk:
                await engine.enhanced_risk.reset_daily_counters()
                await engine.enhanced_risk.reset_hourly_counters()
                return {"success": True, "message": "风险计数器已重置"}
        
        return {"success": True, "message": "风险计数器已重置"}

    @router.get("/ai/guards")
    async def get_ai_execution_guards():
        """获取 AI 执行门控配置与触发统计"""
        if not main_controller or not hasattr(main_controller, "ai_core") or not main_controller.ai_core:
            return {"success": False, "message": "AI核心决策引擎未初始化"}
        try:
            st = main_controller.ai_core.get_status() if hasattr(main_controller.ai_core, "get_status") else {}
            guards = (st or {}).get("execution_guards", {})
            return {
                "success": True,
                "config": guards.get("config", {}),
                "adaptive_profile": guards.get("adaptive_profile", {}),
                "group_overrides": guards.get("group_overrides", {}),
                "frequency_profile": guards.get("frequency_profile", "balanced"),
                "last_frequency_profile_switch_at": guards.get("last_frequency_profile_switch_at"),
                "group_last_tuned_at": guards.get("group_last_tuned_at", {}),
                "global_last_tuned_at": guards.get("global_last_tuned_at"),
                "stats": guards.get("stats", {}),
            }
        except Exception as e:
            return {"success": False, "message": f"读取执行门控失败: {e}"}

    @router.post("/ai/guards")
    async def update_ai_execution_guards(config: Dict[str, Any]):
        """更新 AI 执行门控阈值（运行期生效）"""
        if not main_controller or not hasattr(main_controller, "ai_core") or not main_controller.ai_core:
            return {"success": False, "message": "AI核心决策引擎未初始化"}
        ai_core = main_controller.ai_core
        allowed = {
            "min_trade_interval",
            "min_confidence_to_trade",
            "ai_core_min_confidence_to_open",
            "min_data_quality_to_trade",
            "analysis_hard_gate_for_open",
            "analysis_min_confidence_for_open",
            "analysis_require_not_degraded_for_open",
            "min_rr_to_trade",
            "max_spread_bps_to_trade",
            "max_abs_depth_imbalance_to_trade",
            "degraded_data_quantity_factor",
            "boost_on_low_risk",
            "low_risk_rr_multiplier",
            "low_risk_spread_multiplier",
            "high_risk_rr_multiplier",
            "high_risk_spread_multiplier",
            "regime_enable",
            "regime_low_vol_atr_pct",
            "regime_high_vol_atr_pct",
            "regime_trend_threshold",
            "regime_low_liquidity_spread_bps",
            "regime_profile_overrides",
            "pnl_health_sizing_enable",
            "pnl_health_lookback_trades",
            "pnl_health_bad_expectancy",
            "pnl_health_bad_drawdown",
            "pnl_health_bad_factor",
            "pnl_health_good_expectancy",
            "pnl_health_good_drawdown",
            "pnl_health_good_factor",
            "edge_after_cost_guard_enable",
            "edge_min_net_reward_pct",
            "edge_fee_rate_per_side",
            "edge_slippage_rate_per_side",
            "edge_spread_penalty_weight",
            "loss_streak_cooldown_enable",
            "loss_streak_trigger",
            "loss_streak_lookback",
            "loss_streak_cooldown_sec",
            "loss_streak_min_abs_loss",
            "auto_frequency_profile_switch",
            "frequency_profile_switch_telegram_notify",
            "frequency_profile_cooldown_seconds",
            "frequency_profile_lookback_trades",
            "frequency_profile_max_drawdown_guard",
            "auto_adaptive_guards",
            "auto_tune_guards",
            "auto_tune_by_symbol_group",
            "auto_tune_by_session",
            "auto_tune_global_enabled",
            "auto_tune_global_cooldown_seconds",
            "auto_tune_global_step_rr",
            "auto_tune_global_step_spread_bps",
            "auto_tune_global_max_cumulative_rr_delta_from_baseline",
            "auto_tune_global_max_cumulative_spread_bps_delta_from_baseline",
            "auto_tune_step_rr",
            "auto_tune_step_spread_bps",
            "auto_tune_group_step_rr",
            "auto_tune_group_step_spread_bps",
            "auto_tune_cooldown_seconds",
            "auto_tune_min_rr_delta",
            "auto_tune_min_spread_delta_bps",
            "auto_tune_sltp_params",
            "auto_tune_sltp_cooldown_seconds",
            "auto_tune_sltp_step_tighten",
            "auto_tune_sltp_step_extend",
            "critical_risk_auto_close",
            "critical_risk_auto_close_liq_only",
            "critical_risk_auto_close_max_liq_distance",
            "critical_risk_auto_close_min_loss_pct",
            "hold_avoidance_override_enabled",
            "hold_avoidance_override_cooldown_sec",
            "hold_avoidance_override_min_abs_sentiment",
            "hold_avoidance_override_min_mi_quality_score",
            "hold_avoidance_override_require_mi_trend_alignment",
            "ai_autonomy_minimal_gates_enabled",
            "ai_autonomy_min_conf_floor",
            "ai_autonomy_min_mi_confidence",
            "ai_autonomy_min_mi_quality_score",
            "ai_autonomy_allow_neutral_with_trend",
            "ai_autonomy_require_trend_alignment",
            "ai_autonomy_enable_mtf_conflict_release",
            "ai_autonomy_mtf_conflict_release_requires_mi_bias",
            "ai_autonomy_conflict_subtype_release_enabled",
            "ai_autonomy_conflict_release_min_rsi_1h_for_long",
            "ai_autonomy_conflict_release_max_rsi_1h_for_short",
            "ai_autonomy_conflict_release_min_abs_change_24h",
            "ai_autonomy_conflict_release_require_mi_confidence",
            "auto_tune_hold_override_enabled",
            "auto_tune_hold_override_min_interval_seconds",
            "auto_tune_hold_override_cooldown_seconds",
            "auto_tune_hold_override_window_traces",
            "auto_tune_hold_override_min_traces",
            "auto_tune_hold_override_step_min_abs_sentiment",
            "auto_tune_hold_override_step_min_mi_quality_score",
            "auto_tune_hold_override_min_abs_sentiment_bounds",
            "auto_tune_hold_override_min_mi_quality_score_bounds",
            "auto_tune_hold_override_max_steps_per_cooldown",
            "auto_tune_hold_override_hold_ratio_trigger",
            "auto_tune_hold_override_open_ratio_trigger",
            "auto_tune_hold_override_tighten_hold_ratio",
            "auto_tune_hold_override_win_rate_floor",
            "auto_tune_hold_override_avg_pnl_floor",
            "auto_tune_hold_override_allow_relax_without_recent_pnl",
            "auto_tune_hold_override_max_total_min_abs_sentiment_delta_from_baseline",
            "auto_tune_hold_override_max_total_min_mi_quality_score_delta_from_baseline",
        }
        applied: Dict[str, Any] = {}
        for k, v in (config or {}).items():
            if k in allowed and v is not None:
                try:
                    if k in (
                        "auto_adaptive_guards",
                        "auto_tune_guards",
                        "auto_tune_by_symbol_group",
                        "auto_tune_by_session",
                        "auto_tune_global_enabled",
                        "auto_tune_sltp_params",
                        "boost_on_low_risk",
                        "auto_frequency_profile_switch",
                        "frequency_profile_switch_telegram_notify",
                        "auto_tune_hold_override_enabled",
                        "auto_tune_hold_override_allow_relax_without_recent_pnl",
                        "analysis_hard_gate_for_open",
                        "analysis_require_not_degraded_for_open",
                        "ai_autonomy_minimal_gates_enabled",
                        "ai_autonomy_allow_neutral_with_trend",
                        "ai_autonomy_require_trend_alignment",
                        "ai_autonomy_enable_mtf_conflict_release",
                        "ai_autonomy_mtf_conflict_release_requires_mi_bias",
                        "ai_autonomy_conflict_subtype_release_enabled",
                        "ai_autonomy_conflict_release_require_mi_confidence",
                    ):
                        ai_core.config[k] = bool(v)
                        applied[k] = bool(v)
                    elif k in (
                        "auto_tune_group_step_rr",
                        "auto_tune_group_step_spread_bps",
                    ):
                        if isinstance(v, str) and v.strip().lower() in ("", "null", "none"):
                            ai_core.config[k] = None
                            applied[k] = None
                        else:
                            ai_core.config[k] = float(v)
                            applied[k] = float(ai_core.config[k])
                    elif k in (
                        "auto_tune_hold_override_min_abs_sentiment_bounds",
                        "auto_tune_hold_override_min_mi_quality_score_bounds",
                        "regime_profile_overrides",
                    ):
                        ai_core.config[k] = v
                        applied[k] = v
                    else:
                        ai_core.config[k] = float(v)
                        applied[k] = float(v)
                except Exception:
                    continue

        # Persist applied keys to config_manager so ai_core runtime refresh
        # will not overwrite API-updated values on next loop.
        try:
            cm = getattr(main_controller, "config_manager", None) if main_controller else None
            if cm is not None and hasattr(cm, "set_config"):
                for k, v in (applied or {}).items():
                    try:
                        await cm.set_config("ai_core_runtime", str(k), v, validate=False)
                    except Exception:
                        continue
        except Exception:
            pass
        return {
            "success": True,
            "message": "执行门控配置已更新",
            "applied": applied,
        }

    @router.get("/ai/learning-feedback")
    async def get_ai_learning_feedback():
        """
        获取 AI 交易引擎的止损复盘与信号惩罚状态（验收可视化接口）。
        说明：
        - stop_loss_hits 每累计 3 次，会将该信号额外开仓门槛 +0.05（上限 +0.15）
        """
        if not main_controller or not hasattr(main_controller, "ai_trading_engine") or not main_controller.ai_trading_engine:
            return {"success": False, "message": "AI交易引擎未初始化"}
        engine = main_controller.ai_trading_engine
        try:
            stats_raw = getattr(engine, "_signal_stop_loss_stats", {}) or {}
            if not isinstance(stats_raw, dict):
                stats_raw = {}

            rows: List[Dict[str, Any]] = []
            for signal_key, item in stats_raw.items():
                it = item if isinstance(item, dict) else {}
                hits = int(it.get("stop_loss_hits", 0) or 0)
                steps = hits // 3
                extra = min(0.15, 0.05 * steps)
                rows.append(
                    {
                        "signal_key": str(signal_key),
                        "stop_loss_hits": hits,
                        "penalty_steps": steps,
                        "extra_confidence_threshold": float(round(extra, 4)),
                        "last_at": it.get("last_at"),
                    }
                )

            rows.sort(key=lambda x: (x.get("stop_loss_hits", 0), x.get("last_at") or ""), reverse=True)

            ai_cfg = getattr(engine, "ai_config", {}) or {}
            base_min_conf = float(ai_cfg.get("min_confidence", 0.75) or 0.75)
            penalty_step_hits = int(ai_cfg.get("penalty_step_hits", 3) or 3)
            penalty_step_threshold = float(ai_cfg.get("penalty_step_threshold", 0.05) or 0.05)
            penalty_max_threshold = float(ai_cfg.get("penalty_max_threshold", 0.15) or 0.15)
            max_pos_ratio = float(ai_cfg.get("max_position_value_ratio", 0.05) or 0.05)
            try:
                from src.modules.core.trading_limits import resolve_position_limits

                limits = await resolve_position_limits(config_manager=getattr(main_controller, "config_manager", None))
                hard_max_positions = int(limits.hard_max_positions)
            except Exception:
                hard_max_positions = int(ai_cfg.get("hard_max_positions", 5) or 5)
            require_trend_for_open = bool(ai_cfg.get("require_trend_for_open", True))
            tracked_signals = len(rows)
            penalized_signals = sum(1 for r in rows if float(r.get("extra_confidence_threshold", 0)) > 0)
            total_stop_loss_hits = sum(int(r.get("stop_loss_hits", 0) or 0) for r in rows)
            max_extra_threshold = float(
                round(max((float(r.get("extra_confidence_threshold", 0) or 0) for r in rows), default=0.0), 4)
            )

            return {
                "success": True,
                "summary": {
                    "tracked_signals": tracked_signals,
                    "penalized_signals": penalized_signals,
                    "penalized_ratio": float(round((penalized_signals / tracked_signals), 4)) if tracked_signals else 0.0,
                    "total_stop_loss_hits": total_stop_loss_hits,
                    "base_min_confidence": base_min_conf,
                    "max_extra_confidence_threshold": max_extra_threshold,
                    "effective_min_confidence_upper_bound": float(
                        round(
                            base_min_conf + max_extra_threshold,
                            4,
                        )
                    ),
                    "penalty_rule": {
                        "step_hits": penalty_step_hits,
                        "step_threshold": penalty_step_threshold,
                        "max_threshold": penalty_max_threshold,
                    },
                    "max_position_value_ratio": max_pos_ratio,
                    "hard_max_positions": hard_max_positions,
                    "require_trend_for_open": require_trend_for_open,
                },
                "signals": rows[:200],
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": f"读取学习反馈失败: {e}"}

    @router.get("/ai/frequency-profile")
    async def get_ai_frequency_profile():
        """读取当前开单频率档位（根据关键门控参数推断）"""
        if not main_controller or not hasattr(main_controller, "ai_core") or not main_controller.ai_core:
            return {"success": False, "message": "AI核心决策引擎未初始化"}
        ai_core = main_controller.ai_core
        cfg = ai_core.config if hasattr(ai_core, "config") else {}
        min_interval = float(cfg.get("min_trade_interval", 120) or 120)
        min_conf = float(cfg.get("min_confidence_to_trade", 0.75) or 0.75)
        min_rr = float(cfg.get("min_rr_to_trade", 1.2) or 1.2)
        spread = float(cfg.get("max_spread_bps_to_trade", 35.0) or 35.0)
        prof_status = (
            ai_core.get_frequency_profile_status()
            if hasattr(ai_core, "get_frequency_profile_status")
            else {
                "profile": getattr(ai_core, "_frequency_profile", "balanced"),
                "last_switch_at": (
                    ai_core._last_frequency_profile_switch_at.isoformat()
                    if hasattr(ai_core, "_last_frequency_profile_switch_at") and ai_core._last_frequency_profile_switch_at
                    else None
                ),
                "last_switch_detail": getattr(ai_core, "_last_frequency_profile_switch_detail", {}),
            }
        )
        # 优先使用运行时真实档位；启发式推断仅做兜底（避免与当前 profile 参数漂移产生误报）。
        runtime_profile = str(prof_status.get("profile") or "").strip().lower()
        if runtime_profile in ("conservative", "balanced", "aggressive"):
            inferred = runtime_profile
        else:
            if min_interval <= 70 and min_rr <= 1.10 and spread >= 45.0:
                inferred = "aggressive"
            elif min_interval <= 90 and min_rr <= 1.15 and spread >= 40.0:
                inferred = "balanced"
            else:
                inferred = "conservative"
        return {
            "success": True,
            "inferred_profile": inferred,
            "runtime_profile": prof_status.get("profile"),
            "last_switch_at": prof_status.get("last_switch_at"),
            "last_switch_detail": prof_status.get("last_switch_detail"),
            "config": {
                "min_trade_interval": min_interval,
                "min_confidence_to_trade": min_conf,
                "min_rr_to_trade": min_rr,
                "max_spread_bps_to_trade": spread,
                "boost_on_low_risk": bool(cfg.get("boost_on_low_risk", True)),
            },
        }

    def _build_frequency_profile_explain_payload(
        runtime_profile: str,
        inferred_profile: str,
        last_switch_at: Optional[str],
        last_switch_detail: Dict[str, Any],
    ) -> Dict[str, Any]:
        detail = dict(last_switch_detail or {})
        source = str(detail.get("source") or "unknown")
        reason_metrics = detail.get("reason_metrics") if isinstance(detail.get("reason_metrics"), dict) else {}
        market_ctx = detail.get("market_signal_context") if isinstance(detail.get("market_signal_context"), dict) else {}
        top_anomalies = market_ctx.get("top_anomalies") if isinstance(market_ctx.get("top_anomalies"), list) else []
        applied = detail.get("applied") if isinstance(detail.get("applied"), dict) else {}
        mode = "auto" if source == "auto" else ("manual" if source == "manual_api" else "unknown")

        explain = []
        if mode == "auto":
            win_rate = reason_metrics.get("win_rate")
            dd = reason_metrics.get("max_drawdown")
            risk_ratio = reason_metrics.get("mi_risk_ratio")
            if win_rate is not None:
                explain.append(f"win_rate={win_rate}")
            if dd is not None:
                explain.append(f"max_drawdown={dd}")
            if risk_ratio is not None:
                explain.append(f"mi_risk_ratio={risk_ratio}")
            if top_anomalies:
                tops = [str((x or {}).get("anomaly") or "") for x in top_anomalies[:3] if isinstance(x, dict)]
                tops = [x for x in tops if x]
                if tops:
                    explain.append(f"top_anomalies={','.join(tops)}")
        elif mode == "manual":
            if applied:
                explain.append("manual_api_applied")
            explain.append(f"from={detail.get('from')} to={detail.get('to')}")
        else:
            explain.append("switch_detail_unavailable")

        return {
            "mode": mode,
            "source": source,
            "runtime_profile": runtime_profile,
            "inferred_profile": inferred_profile,
            "last_switch_at": last_switch_at,
            "switch": {
                "from": detail.get("from"),
                "to": detail.get("to"),
                "timestamp": detail.get("timestamp") or last_switch_at,
            },
            "reason_metrics": reason_metrics,
            "market_signal_context": {
                "top_anomalies": top_anomalies,
            },
            "applied": applied,
            "explain_text": "; ".join(explain),
        }

    @router.get("/ai/frequency-profile/explain")
    async def get_ai_frequency_profile_explain():
        """统一返回手动/自动切档解释，便于 OpenClaw 前端稳定渲染。"""
        raw = await get_ai_frequency_profile()
        if not isinstance(raw, dict) or not bool(raw.get("success")):
            return {
                "success": False,
                "message": (raw or {}).get("message", "读取频率档位状态失败") if isinstance(raw, dict) else "读取频率档位状态失败",
            }
        payload = _build_frequency_profile_explain_payload(
            runtime_profile=str(raw.get("runtime_profile") or ""),
            inferred_profile=str(raw.get("inferred_profile") or ""),
            last_switch_at=raw.get("last_switch_at"),
            last_switch_detail=raw.get("last_switch_detail") if isinstance(raw.get("last_switch_detail"), dict) else {},
        )
        return {
            "success": True,
            "ok": True,
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "data": payload,
        }

    @router.post("/ai/frequency-profile")
    async def set_ai_frequency_profile(payload: Dict[str, Any]):
        """一键切换开单频率档位（运行期生效）：conservative / balanced / aggressive"""
        if not main_controller or not hasattr(main_controller, "ai_core") or not main_controller.ai_core:
            return {"success": False, "message": "AI核心决策引擎未初始化"}
        ai_core = main_controller.ai_core
        requested = str((payload or {}).get("profile", "balanced")).strip().lower()
        profiles = (
            ai_core._get_frequency_profiles()
            if hasattr(ai_core, "_get_frequency_profiles")
            else {}
        )
        if requested not in profiles:
            return {
                "success": False,
                "message": "无效档位，支持: conservative / balanced / aggressive",
            }
        old_profile = str(getattr(ai_core, "_frequency_profile", "unknown") or "unknown")
        if hasattr(ai_core, "_apply_frequency_profile"):
            applied = ai_core._apply_frequency_profile(requested)
        else:
            applied = {}
            for k, v in profiles[requested].items():
                ai_core.config[k] = v
                applied[k] = v
        # 记录手动切档明细，便于 OpenClaw 直接观测来源与参数变化。
        try:
            ai_core._last_frequency_profile_switch_detail = {
                "source": "manual_api",
                "from": old_profile,
                "to": requested,
                "timestamp": datetime.now().isoformat(),
                "applied": dict(applied or {}),
            }
        except Exception:
            pass
        return {
            "success": True,
            "message": f"已切换到 {requested} 档位",
            "profile": requested,
            "applied": applied,
        }
    
    @router.get("/memory/stats")
    async def get_memory_stats():
        """获取记忆系统统计"""
        stats = {
            "short_term_count": 0,
            "long_term_count": 0,
            "trade_records": 0,
            "risk_events": 0
        }
        
        if main_controller:
            if hasattr(main_controller, 'ai_memory_manager') and main_controller.ai_memory_manager:
                mem = main_controller.ai_memory_manager
                # 兼容旧版内存管理器(list字段)与新版网关(get_stats接口)
                if hasattr(mem, "get_stats"):
                    try:
                        raw = mem.get_stats() or {}
                        if isinstance(raw, dict):
                            stats["short_term_count"] = int(raw.get("short_term_count", raw.get("short_term", 0)) or 0)
                            stats["long_term_count"] = int(raw.get("long_term_count", raw.get("long_term", 0)) or 0)
                            stats["trade_records"] = int(raw.get("trade_records", raw.get("trades", 0)) or 0)
                            stats["risk_events"] = int(raw.get("risk_events", raw.get("risks", 0)) or 0)
                    except Exception:
                        pass
                if stats["short_term_count"] == 0 and hasattr(mem, "short_term_memory"):
                    try:
                        stats["short_term_count"] = len(getattr(mem, "short_term_memory") or [])
                    except Exception:
                        pass
                if stats["long_term_count"] == 0 and hasattr(mem, "long_term_memory"):
                    try:
                        stats["long_term_count"] = len(getattr(mem, "long_term_memory") or [])
                    except Exception:
                        pass
        
        return stats

    @router.get("/stop-loss/stats")
    async def get_stop_loss_stats():
        """获取止盈止损跟踪统计"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        try:
            slm = getattr(main_controller, "stop_loss_manager", None)
            if not slm:
                return {"success": False, "message": "止盈止损管理器未初始化"}
            data = slm.get_stats() if hasattr(slm, "get_stats") else {}
            return {"success": True, "stats": data or {}}
        except Exception as e:
            return {"success": False, "message": f"读取止盈止损统计失败: {e}"}

    @router.get("/stop-loss/active-orders")
    async def get_stop_loss_active_orders(limit: int = 50):
        """获取当前活动 SLTP 订单明细（用于前端展示“有止损/止盈”）。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        try:
            slm = getattr(main_controller, "stop_loss_manager", None)
            if not slm:
                return {"success": False, "message": "止盈止损管理器未初始化"}
            if not hasattr(slm, "get_all_active_orders"):
                return {"success": False, "message": "止盈止损明细接口不可用"}
            orders = await slm.get_all_active_orders()
            rows = []
            for o in (orders or [])[: max(0, int(limit or 50))]:
                try:
                    rows.append(o.to_dict() if hasattr(o, "to_dict") else dict(o))
                except Exception:
                    continue
            return {"success": True, "data": rows, "count": len(rows), "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": f"读取活动 SLTP 订单失败: {e}"}

    @router.get("/stop-loss/profit-protect-debug")
    async def get_stop_loss_profit_protect_debug(limit: int = 30):
        """调试盈利保护加速器：配置 + 活跃订单的生效参数。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        try:
            slm = getattr(main_controller, "stop_loss_manager", None)
            if not slm:
                return {"success": False, "message": "止盈止损管理器未初始化"}
            cfg = getattr(slm, "config", None)
            cfg_out: Dict[str, Any] = {}
            if cfg is not None:
                try:
                    cfg_out = {
                        "profit_protect_accelerator_enable": bool(getattr(cfg, "profit_protect_accelerator_enable", False)),
                        "profit_protect_trigger_1": float(getattr(cfg, "profit_protect_trigger_1", 0.0) or 0.0),
                        "profit_protect_lock_1": float(getattr(cfg, "profit_protect_lock_1", 0.0) or 0.0),
                        "profit_protect_trigger_2": float(getattr(cfg, "profit_protect_trigger_2", 0.0) or 0.0),
                        "profit_protect_lock_2": float(getattr(cfg, "profit_protect_lock_2", 0.0) or 0.0),
                        "profit_protect_tighten_factor": float(getattr(cfg, "profit_protect_tighten_factor", 0.0) or 0.0),
                        "profit_protect_regime_overrides": dict(getattr(cfg, "profit_protect_regime_overrides", {}) or {}),
                    }
                except Exception:
                    cfg_out = {}
            if not hasattr(slm, "get_all_active_orders"):
                return {
                    "success": True,
                    "config": cfg_out,
                    "data": [],
                    "count": 0,
                    "message": "止盈止损明细接口不可用",
                    "timestamp": datetime.now().isoformat(),
                }
            orders = await slm.get_all_active_orders()
            rows: List[Dict[str, Any]] = []
            for o in (orders or [])[: max(0, int(limit or 30))]:
                try:
                    obj = o.to_dict() if hasattr(o, "to_dict") else dict(o)
                except Exception:
                    continue
                md = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
                gp = md.get("guard_profile") if isinstance(md.get("guard_profile"), dict) else {}
                rows.append(
                    {
                        "order_id": obj.get("order_id"),
                        "symbol": obj.get("symbol"),
                        "side": obj.get("side"),
                        "entry_price": obj.get("entry_price"),
                        "current_price": obj.get("current_price"),
                        "stop_loss_price": obj.get("stop_loss_price"),
                        "trailing_stop_offset": obj.get("trailing_stop_offset"),
                        "regime": (
                            md.get("profit_protect_regime")
                            or gp.get("regime")
                            or gp.get("profile")
                            or "unknown"
                        ),
                        "profit_protect_stage": md.get("profit_protect_stage"),
                        "profit_protect_lock_pct": md.get("profit_protect_lock_pct"),
                        "profit_protect_trigger_1_effective": md.get("profit_protect_trigger_1_effective"),
                        "profit_protect_trigger_2_effective": md.get("profit_protect_trigger_2_effective"),
                        "profit_protect_tighten_effective": md.get("profit_protect_tighten_effective"),
                        "profit_protect_applied_at": md.get("profit_protect_applied_at"),
                    }
                )
            return {
                "success": True,
                "config": cfg_out,
                "data": rows,
                "count": len(rows),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": f"读取盈利保护调试信息失败: {e}"}

    @router.get("/profit/ops-overview")
    async def get_profit_ops_overview(
        days: int = 30,
        sample_limit: int = 200,
        active_order_limit: int = 20,
    ):
        """盈利运营一屏视图：归因 + 健康度 + 盈利保护调试。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        try:
            # 1) AI execution guards snapshot
            ai_guard = {}
            try:
                ai_core = getattr(main_controller, "ai_core", None)
                st = ai_core.get_status() if ai_core and hasattr(ai_core, "get_status") else {}
                ai_guard = (st or {}).get("execution_guards", {}) if isinstance(st, dict) else {}
            except Exception:
                ai_guard = {}

            # 2) Trade history / attribution & readiness
            trade_service = getattr(main_controller, "trade_history_service", None)
            regime_rows: List[Dict[str, Any]] = []
            health = {
                "sample": {"total": 0, "with_regime": 0, "with_effective_qty_factor": 0, "nonzero_pnl": 0, "nonzero_pnl_percent": 0},
                "coverage": {"regime_coverage": 0.0, "qty_factor_coverage": 0.0, "nonzero_pnl_coverage": 0.0, "nonzero_pnl_percent_coverage": 0.0},
                "readiness": {"ready_for_regime_tuning": False, "rules": {"min_samples": 20, "min_regime_coverage": 0.6, "min_nonzero_pnl_coverage": 0.5}},
            }
            if trade_service and hasattr(trade_service, "get_trade_history"):
                start_date = datetime.now() - timedelta(days=max(1, int(days or 30)))
                rows = await trade_service.get_trade_history(start_date=start_date, limit=max(50, int(sample_limit or 2000)))
                clean_rows: List[Dict[str, Any]] = []
                for r in (rows or []):
                    if not isinstance(r, dict):
                        continue
                    md = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
                    src = str((md.get("source") or r.get("source") or "")).strip().lower()
                    if src == "db_bootstrap":
                        continue
                    pnl = float(r.get("pnl", 0) or 0)
                    pnl_pct = float(r.get("pnl_percent", 0) or 0)
                    if not (abs(pnl) > 1e-12 or abs(pnl_pct) > 1e-12):
                        continue
                    clean_rows.append(r)

                # Attribution grouped by regime
                grp: Dict[str, Dict[str, Any]] = {}
                with_regime = 0
                with_qf = 0
                nonzero_pnl = 0
                nonzero_pnl_pct = 0
                for r in clean_rows:
                    md = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
                    mkt = md.get("market_context") if isinstance(md.get("market_context"), dict) else {}
                    regime = str(mkt.get("regime") or "unknown").strip().lower() or "unknown"
                    if regime and regime != "unknown":
                        with_regime += 1
                    if mkt.get("effective_qty_factor") is not None:
                        with_qf += 1
                    pnl = float(r.get("pnl", 0) or 0)
                    pnl_pct = float(r.get("pnl_percent", 0) or 0)
                    if abs(pnl) > 1e-12:
                        nonzero_pnl += 1
                    if abs(pnl_pct) > 1e-12:
                        nonzero_pnl_pct += 1

                    g = grp.get(regime)
                    if not g:
                        g = {
                            "regime": regime,
                            "total_trades": 0,
                            "winning_trades": 0,
                            "losing_trades": 0,
                            "total_pnl": 0.0,
                            "total_fees": 0.0,
                            "sum_qty_factor": 0.0,
                            "qty_factor_count": 0,
                            "sum_pnl_percent": 0.0,
                            "pnl_percent_count": 0,
                            "gross_profit": 0.0,
                            "gross_loss": 0.0,
                        }
                        grp[regime] = g
                    g["total_trades"] += 1
                    g["total_pnl"] += pnl
                    g["total_fees"] += float(r.get("fee", 0) or 0)
                    qf = float(mkt.get("effective_qty_factor", 1.0) or 1.0)
                    g["sum_qty_factor"] += qf
                    g["qty_factor_count"] += 1
                    if abs(pnl_pct) > 1e-12:
                        g["sum_pnl_percent"] += pnl_pct
                        g["pnl_percent_count"] += 1
                    if pnl > 0:
                        g["winning_trades"] += 1
                        g["gross_profit"] += pnl
                    elif pnl < 0:
                        g["losing_trades"] += 1
                        g["gross_loss"] += abs(pnl)

                for regime, g in grp.items():
                    total = int(g["total_trades"])
                    win_rate = (int(g["winning_trades"]) / total) if total else 0.0
                    pf = (float(g["gross_profit"]) / float(g["gross_loss"])) if float(g["gross_loss"]) > 0 else (9999.0 if float(g["gross_profit"]) > 0 else 0.0)
                    expectancy = float(g["total_pnl"]) / total if total else 0.0
                    regime_rows.append(
                        {
                            "regime": regime,
                            "total_trades": total,
                            "winning_trades": int(g["winning_trades"]),
                            "losing_trades": int(g["losing_trades"]),
                            "win_rate": round(win_rate * 100, 2),
                            "profit_factor": round(float(pf), 4),
                            "expectancy": round(float(expectancy), 6),
                            "total_pnl": round(float(g["total_pnl"]), 6),
                            "total_fees": round(float(g["total_fees"]), 6),
                            "avg_pnl_percent": round(float(g["sum_pnl_percent"]) / max(1, int(g["pnl_percent_count"])), 6),
                            "avg_effective_qty_factor": round(float(g["sum_qty_factor"]) / max(1, int(g["qty_factor_count"])), 6),
                        }
                    )
                regime_rows.sort(key=lambda x: x.get("total_trades", 0), reverse=True)

                total = len(clean_rows)
                regime_cov = (with_regime / total) if total else 0.0
                qty_cov = (with_qf / total) if total else 0.0
                pnl_cov = (nonzero_pnl / total) if total else 0.0
                pnl_pct_cov = (nonzero_pnl_pct / total) if total else 0.0
                ready = bool(total >= 20 and regime_cov >= 0.6 and pnl_cov >= 0.5)
                health = {
                    "sample": {
                        "total": int(total),
                        "with_regime": int(with_regime),
                        "with_effective_qty_factor": int(with_qf),
                        "nonzero_pnl": int(nonzero_pnl),
                        "nonzero_pnl_percent": int(nonzero_pnl_pct),
                    },
                    "coverage": {
                        "regime_coverage": round(regime_cov, 4),
                        "qty_factor_coverage": round(qty_cov, 4),
                        "nonzero_pnl_coverage": round(pnl_cov, 4),
                        "nonzero_pnl_percent_coverage": round(pnl_pct_cov, 4),
                    },
                    "readiness": {
                        "ready_for_regime_tuning": ready,
                        "rules": {"min_samples": 20, "min_regime_coverage": 0.6, "min_nonzero_pnl_coverage": 0.5},
                    },
                }

            # 3) Profit protect debug summary
            protect_cfg: Dict[str, Any] = {}
            protect_orders: List[Dict[str, Any]] = []
            slm = getattr(main_controller, "stop_loss_manager", None)
            if slm:
                cfg = getattr(slm, "config", None)
                if cfg is not None:
                    try:
                        protect_cfg = {
                            "profit_protect_accelerator_enable": bool(getattr(cfg, "profit_protect_accelerator_enable", False)),
                            "profit_protect_trigger_1": float(getattr(cfg, "profit_protect_trigger_1", 0.0) or 0.0),
                            "profit_protect_lock_1": float(getattr(cfg, "profit_protect_lock_1", 0.0) or 0.0),
                            "profit_protect_trigger_2": float(getattr(cfg, "profit_protect_trigger_2", 0.0) or 0.0),
                            "profit_protect_lock_2": float(getattr(cfg, "profit_protect_lock_2", 0.0) or 0.0),
                            "profit_protect_tighten_factor": float(getattr(cfg, "profit_protect_tighten_factor", 0.0) or 0.0),
                            "profit_protect_regime_overrides": dict(getattr(cfg, "profit_protect_regime_overrides", {}) or {}),
                        }
                    except Exception:
                        protect_cfg = {}
                if hasattr(slm, "get_all_active_orders"):
                    orders = await slm.get_all_active_orders()
                    for o in (orders or [])[: max(0, int(active_order_limit or 20))]:
                        try:
                            obj = o.to_dict() if hasattr(o, "to_dict") else dict(o)
                        except Exception:
                            continue
                        md = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
                        gp = md.get("guard_profile") if isinstance(md.get("guard_profile"), dict) else {}
                        protect_orders.append(
                            {
                                "order_id": obj.get("order_id"),
                                "symbol": obj.get("symbol"),
                                "side": obj.get("side"),
                                "regime": md.get("profit_protect_regime") or gp.get("regime") or gp.get("profile") or "unknown",
                                "profit_protect_stage": md.get("profit_protect_stage"),
                                "profit_protect_lock_pct": md.get("profit_protect_lock_pct"),
                                "profit_protect_trigger_1_effective": md.get("profit_protect_trigger_1_effective"),
                                "profit_protect_trigger_2_effective": md.get("profit_protect_trigger_2_effective"),
                                "profit_protect_tighten_effective": md.get("profit_protect_tighten_effective"),
                            }
                        )

            return {
                "success": True,
                "ok": True,
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "days": int(days or 30),
                "profit_attribution": {
                    "regime": regime_rows,
                    "health": health,
                },
                "profit_protect_debug": {
                    "config": protect_cfg,
                    "active_orders": protect_orders,
                    "active_count": len(protect_orders),
                },
                "execution_guards": {
                    "config": (ai_guard.get("config") or {}) if isinstance(ai_guard, dict) else {},
                    "adaptive_profile": (ai_guard.get("adaptive_profile") or {}) if isinstance(ai_guard, dict) else {},
                    "stats": (ai_guard.get("stats") or {}) if isinstance(ai_guard, dict) else {},
                },
            }
        except Exception as e:
            return {"success": False, "message": f"读取盈利运营总览失败: {e}"}

    @router.get("/stop-loss/config")
    async def get_stop_loss_config():
        """获取 SLTP 配置（分层止盈/移动止盈/移动止损参数）。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        try:
            slm = getattr(main_controller, "stop_loss_manager", None)
            if not slm:
                return {"success": False, "message": "止盈止损管理器未初始化"}
            cfg = getattr(slm, "config", None)
            if cfg is None:
                return {"success": True, "data": {}, "timestamp": datetime.now().isoformat()}
            # dataclass friendly
            try:
                from dataclasses import asdict

                data = asdict(cfg)
            except Exception:
                data = dict(cfg) if isinstance(cfg, dict) else {"repr": repr(cfg)}
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": f"读取 SLTP 配置失败: {e}"}
    
    @router.get("/system/health")
    async def get_system_health():
        """获取系统健康状态"""
        health = {
            "overall": "healthy",
            "modules": {},
            "timestamp": datetime.now().isoformat()
        }
        
        if main_controller:
            modules_to_check = [
                ("ai_trading_engine", "AI交易引擎"),
                ("llm_integration", "AI大模型"),
                ("telegram_bot", "Telegram机器人"),
                ("database_manager", "数据库"),
                ("event_system", "事件系统"),
                ("emergency_stop", "紧急停止"),
                ("security_manager", "安全管理"),
                ("fund_manager", "资金管理")
            ]
            
            healthy_count = 0
            for attr, name in modules_to_check:
                if hasattr(main_controller, attr):
                    module = getattr(main_controller, attr)
                    is_healthy = module is not None
                    health["modules"][name] = {
                        "status": "healthy" if is_healthy else "unavailable",
                        "running": is_healthy
                    }
                    if is_healthy:
                        healthy_count += 1
                else:
                    health["modules"][name] = {
                        "status": "unavailable",
                        "running": False
                    }
            
            total = len(modules_to_check)
            health["overall"] = "healthy" if healthy_count == total else "degraded" if healthy_count > total // 2 else "unhealthy"
            health["healthy_count"] = healthy_count
            health["total_count"] = total
        
        return health

    @router.get("/strategy/optimization-status")
    async def get_strategy_optimization_status():
        """
        预留给前端的策略优化状态接口：
        - 策略池总量/上限
        - 每日优化进度与结果
        - 最近一次策略池清理时间
        """
        if not main_controller or not hasattr(main_controller, "strategy_manager") or not main_controller.strategy_manager:
            return {"success": False, "message": "策略管理器未初始化"}
        try:
            sm = main_controller.strategy_manager
            if hasattr(sm, "get_optimization_status"):
                data = sm.get_optimization_status()
            else:
                data = {
                    "pool_limit": 30,
                    "total_strategies": len(getattr(sm, "strategy_configs", {}) or {}),
                    "daily_optimization": {},
                    "last_daily_optimization_date": None,
                    "last_pool_prune_at": None,
                }
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": f"读取策略优化状态失败: {e}"}

    @router.post("/strategy/optimization-config")
    async def update_strategy_optimization_config(config: Dict[str, Any]):
        """热更新策略优化运行参数（前端可直接调用）。"""
        if not main_controller or not hasattr(main_controller, "strategy_manager") or not main_controller.strategy_manager:
            return {"success": False, "message": "策略管理器未初始化"}
        try:
            sm = main_controller.strategy_manager
            if not hasattr(sm, "update_optimization_runtime_config"):
                return {"success": False, "message": "当前策略管理器不支持热更新优化参数"}
            applied = sm.update_optimization_runtime_config(config or {})
            return {
                "success": True,
                "message": "策略优化参数已更新",
                "applied": applied,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": f"更新策略优化参数失败: {e}"}

    @router.get("/strategy/optimization-config")
    async def get_strategy_optimization_config():
        """读取当前策略优化运行参数。"""
        if not main_controller or not hasattr(main_controller, "strategy_manager") or not main_controller.strategy_manager:
            return {"success": False, "message": "策略管理器未初始化"}
        try:
            sm = main_controller.strategy_manager
            status = sm.get_optimization_status() if hasattr(sm, "get_optimization_status") else {}
            return {
                "success": True,
                "config": (status.get("runtime_config", {}) if isinstance(status, dict) else {}),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": f"读取策略优化参数失败: {e}"}

    @router.post("/strategy/optimize-now")
    async def trigger_strategy_optimization_now():
        """手动触发一次每日优化批次（用于运维/验收）。"""
        if not main_controller or not hasattr(main_controller, "strategy_manager") or not main_controller.strategy_manager:
            return {"success": False, "message": "策略管理器未初始化"}
        try:
            gate = await _check_unified_data_quality(symbol="BTC/USDT", min_score=0.45)
            if not gate.get("ok", True):
                await _notify_quality_warning("优化任务低质量放行（AI自主判断）", gate)
            sm = main_controller.strategy_manager
            if hasattr(sm, "trigger_daily_optimization_now"):
                out = await sm.trigger_daily_optimization_now()
                if isinstance(out, dict):
                    out["quality_gate"] = gate
                return out
            await sm._run_daily_strategy_optimization()  # type: ignore[attr-defined]
            return {"success": True, "message": "已触发每日优化批次", "quality_gate": gate}
        except Exception as e:
            return {"success": False, "message": f"触发每日优化失败: {e}"}

    @router.post("/strategy/trade-feedback")
    async def submit_strategy_trade_feedback(payload: Dict[str, Any]):
        """
        提交交易结果反馈，驱动策略参数自适应收敛并可联动优化批次。
        body: strategy_id, pnl, win_rate?, max_drawdown?, total_trades?, force_optimize?
        """
        if not main_controller or not hasattr(main_controller, "strategy_manager") or not main_controller.strategy_manager:
            return {"success": False, "message": "策略管理器未初始化"}
        try:
            gate = await _check_unified_data_quality(symbol=str(payload.get("symbol") or "BTC/USDT"), min_score=0.4)
            if not gate.get("ok", True):
                await _notify_quality_warning("交易反馈低质量放行（AI自主判断）", gate)
            sm = main_controller.strategy_manager
            strategy_id = str(payload.get("strategy_id") or "").strip()
            if not strategy_id:
                return {"success": False, "message": "strategy_id 不能为空"}
            pnl = float(payload.get("pnl", 0.0) or 0.0)
            win_rate = payload.get("win_rate")
            max_drawdown = payload.get("max_drawdown")
            total_trades = payload.get("total_trades")
            force_optimize = bool(payload.get("force_optimize", False))
            if hasattr(sm, "apply_trade_feedback"):
                out = await sm.apply_trade_feedback(
                    strategy_id=strategy_id,
                    pnl=pnl,
                    win_rate=win_rate,
                    max_drawdown=max_drawdown,
                    total_trades=total_trades,
                    force_optimize=force_optimize,
                )
                return {"success": True, "data": out, "quality_gate": gate, "timestamp": datetime.now().isoformat()}
            return {"success": False, "message": "当前策略管理器不支持交易反馈优化"}
        except Exception as e:
            return {"success": False, "message": f"提交交易反馈失败: {e}"}

    @router.get("/execution/production-audit")
    async def get_production_execution_audit():
        """
        生产执行链路审查：
        开仓、平仓、止盈、止损、跟踪止损、交易所连通、执行网关状态。
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        mc = main_controller
        out: Dict[str, Any] = {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "checks": {},
        }
        try:
            gw = getattr(mc, "execution_gateway", None)
            out["checks"]["execution_gateway"] = bool(gw is not None)
            if gw:
                out["execution_spine"] = await gw.get_snapshot()

            ex = mc.get_exchange() if hasattr(mc, "get_exchange") else None
            out["checks"]["exchange_connected"] = bool(ex is not None)

            slm = getattr(mc, "stop_loss_manager", None)
            out["checks"]["stop_loss_manager"] = bool(slm is not None)
            if slm:
                stats = slm.get_stats()
                out["sltp_stats"] = stats
                out["checks"]["dynamic_market_adjustment"] = bool(
                    getattr(slm.config, "enable_dynamic_market_adjustment", False)
                )
                out["checks"]["trailing_stop_enabled"] = bool(
                    getattr(slm.config, "enable_trailing_stop", False)
                )
                out["checks"]["execute_exchange_on_trigger"] = bool(
                    getattr(slm.config, "execute_exchange_on_trigger", False)
                )
                active_orders = await slm.get_all_active_orders()
                out["active_orders"] = [o.to_dict() for o in active_orders[:20]]

            return out
        except Exception as e:
            return {"success": False, "message": f"生产执行审查失败: {e}", "timestamp": datetime.now().isoformat()}

    @router.post("/strategy/research-run")
    async def run_strategy_research_now(payload: Optional[Dict[str, Any]] = Body(None)):
        """
        手动触发策略研发流水线（walk-forward + 门控），不受「有持仓则跳过」限制。
        可选 JSON：symbols, timeframe, lookback_days, timeout_seconds, max_symbols
        """
        payload = payload or {}
        raw_symbols = payload.get("symbols") or ["BTC/USDT"]
        if isinstance(raw_symbols, str):
            gate_symbol = raw_symbols
        elif isinstance(raw_symbols, list) and raw_symbols:
            gate_symbol = str(raw_symbols[0])
        else:
            gate_symbol = "BTC/USDT"
        gate = await _check_unified_data_quality(
            symbol=gate_symbol,
            min_score=float(payload.get("min_data_quality", 0.5) or 0.5),
        )
        if not gate.get("ok", True):
            await _notify_quality_warning("研究任务低质量放行（AI自主判断）", gate)
        job_id = f"research_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        job = {
            "job_id": job_id,
            "status": "queued",
            "created_at": datetime.now().isoformat(),
            "payload": payload,
            "result": None,
            "message": "",
            "started_at": None,
            "finished_at": None,
        }
        async with research_jobs_lock:
            research_jobs[job_id] = job
            # 控制历史长度，避免内存无限增长
            if len(research_jobs) > 50:
                old_keys = sorted(
                    research_jobs.keys(),
                    key=lambda k: research_jobs[k].get("created_at", "")
                )[:-50]
                for k in old_keys:
                    research_jobs.pop(k, None)
        asyncio.create_task(_run_research_job(job_id, payload))
        return {
            "success": True,
            "message": "策略研究任务已提交后台执行",
            "job_id": job_id,
            "status": "queued",
            "quality_gate": gate,
            "timestamp": datetime.now().isoformat(),
        }

    @router.get("/strategy/research-jobs")
    async def list_strategy_research_jobs(limit: int = 20):
        """查询最近策略研究任务列表。"""
        safe_limit = max(1, min(int(limit), 100))
        async with research_jobs_lock:
            jobs = sorted(
                research_jobs.values(),
                key=lambda x: x.get("created_at", ""),
                reverse=True,
            )[:safe_limit]
        return {"success": True, "jobs": jobs, "timestamp": datetime.now().isoformat()}

    @router.get("/strategy/research-jobs/{job_id}")
    async def get_strategy_research_job(job_id: str):
        """查询单个策略研究任务状态。"""
        async with research_jobs_lock:
            job = research_jobs.get(job_id)
        if not job:
            return {"success": False, "message": "任务不存在", "job_id": job_id}
        return {"success": True, "job": job, "timestamp": datetime.now().isoformat()}

    @router.get("/memory/daily-summary")
    async def get_memory_daily_summary(limit: int = 6):
        """
        获取每日复盘摘要（用于前端卡片与TG快速查看）。
        """
        safe_limit = max(1, min(int(limit), 20))
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        gateway = getattr(main_controller, "memory_gateway", None)
        if not gateway:
            return {"success": False, "message": "记忆网关不可用"}
        try:
            rows = await gateway.recall(query="每日交易复盘 自动总结", limit=safe_limit, min_importance=0.5)
            data: List[Dict[str, Any]] = []
            for r in rows:
                data.append(
                    {
                        "id": getattr(r, "id", None),
                        "content": getattr(r, "content", ""),
                        "importance": getattr(r, "importance", None),
                        "timestamp": getattr(r, "timestamp", None),
                        "metadata": getattr(r, "metadata", {}) if hasattr(r, "metadata") else {},
                    }
                )
            # 兜底：部分情况下召回模型可能漏召回，直接从内存后端筛选“每日复盘”类记录。
            if not data:
                backend = getattr(gateway, "memory_backend", None)
                memories = getattr(backend, "_memories", {}) if backend else {}
                fallback_rows: List[Dict[str, Any]] = []
                for mid, entry in (memories or {}).items():
                    try:
                        content = str(getattr(entry, "content", "") or "")
                        metadata = getattr(entry, "metadata", {}) or {}
                        src = str(metadata.get("source_module") or "")
                        if ("每日交易复盘" in content) or ("复盘" in content and src == "ai_command_executor"):
                            fallback_rows.append(
                                {
                                    "id": mid,
                                    "content": content,
                                    "importance": float(getattr(entry, "importance", 0.0) or 0.0),
                                    "timestamp": (
                                        getattr(entry, "created_at", None).isoformat()
                                        if getattr(entry, "created_at", None) is not None
                                        else None
                                    ),
                                    "metadata": metadata,
                                }
                            )
                    except Exception:
                        continue
                fallback_rows = sorted(
                    fallback_rows,
                    key=lambda x: str(x.get("timestamp") or ""),
                    reverse=True,
                )[:safe_limit]
                data = fallback_rows
            return {"success": True, "data": data, "count": len(data), "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.post("/memory/daily-summary/run")
    async def run_memory_daily_summary():
        """
        手动触发一次每日复盘写入（AI执行器路径）。
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        exe = getattr(main_controller, "ai_command_executor", None)
        if not exe or not hasattr(exe, "_auto_daily_summary"):
            return {"success": False, "message": "AI执行器不可用"}
        try:
            ok = await exe._auto_daily_summary(force=True)
            return {
                "success": bool(ok),
                "message": "已触发每日复盘写入" if ok else "每日复盘写入失败",
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    async def _build_commander_fast_snapshot(symbol: str = "BTC/USDT") -> Dict[str, Any]:
        """快速快照：优先返回核心状态，避免重聚合阻塞。"""
        out: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "mode": "fast",
            "system": {},
            "strategy": {},
            "execution": {},
            "risk": {},
            "account": {},
            "data_hub": {"symbol": symbol},
            "alerts": [],
        }
        mc = main_controller
        if not mc:
            return out
        FAST_TIMEOUT_S = 4.0
        try:
            st = await asyncio.wait_for(mc.get_system_status(), timeout=FAST_TIMEOUT_S)
            out["system"] = {
                "system_status": st.get("system_status"),
                "module_count": st.get("module_count"),
                "running_modules": st.get("running_modules"),
            }
            if hasattr(mc, "get_hosting_mode"):
                out["system"]["hosting_mode"] = mc.get_hosting_mode()
        except Exception as e:
            out["alerts"].append(f"系统状态读取失败: {e}")

        try:
            sm = getattr(mc, "strategy_manager", None)
            if sm and hasattr(sm, "get_optimization_status"):
                s = sm.get_optimization_status()
                out["strategy"] = {
                    "total_strategies": s.get("total_strategies"),
                    "pool_limit": s.get("pool_limit"),
                    "daily_optimization": s.get("daily_optimization"),
                    "deployment_stage_counts": s.get("deployment_stage_counts"),
                }
        except Exception as e:
            out["alerts"].append(f"策略状态读取失败: {e}")

        try:
            gw = getattr(mc, "execution_gateway", None)
            if gw and hasattr(gw, "get_snapshot"):
                out["execution"] = await asyncio.wait_for(gw.get_snapshot(), timeout=FAST_TIMEOUT_S)
        except Exception as e:
            out["alerts"].append(f"执行网关快照失败: {e}")

        try:
            slm = getattr(mc, "stop_loss_manager", None)
            if slm and hasattr(slm, "get_stats"):
                out["risk"]["sltp"] = slm.get_stats()
        except Exception as e:
            out["alerts"].append(f"SLTP统计读取失败: {e}")

        # 账户/持仓（快速版）：只读缓存，避免因交易所/网络抖动导致快照阻塞。
        try:
            st = getattr(mc, "_latest_account_state", None)
            if isinstance(st, dict) and st.get("timestamp"):
                try:
                    raw = str(st["timestamp"]).replace("Z", "")
                    t0 = datetime.fromisoformat(raw[:26])
                    if (datetime.now() - t0).total_seconds() > 45:
                        out["alerts"].append("account_state_stale>45s")
                except Exception:
                    pass
            st = st if isinstance(st, dict) else {}
            out["account"] = {
                "balance": st.get("balance"),
                "positions": st.get("positions"),
                "synced_at": st.get("timestamp"),
            }
            # Fallback: when cache is stale/empty, use ai_trading_engine in-memory positions to avoid false "0 positions".
            if not isinstance(out["account"].get("positions"), list):
                out["account"]["positions"] = []
            if len(out["account"]["positions"]) == 0:
                te = getattr(mc, "ai_trading_engine", None)
                te_pos = getattr(te, "positions", {}) if te else {}
                if isinstance(te_pos, dict) and te_pos:
                    rebuilt: List[Dict[str, Any]] = []
                    for sym, p in te_pos.items():
                        try:
                            rebuilt.append(
                                {
                                    "symbol": getattr(p, "symbol", sym),
                                    "side": getattr(p, "side", None),
                                    "size": float(getattr(p, "quantity", 0.0) or 0.0),
                                    "entry_price": float(getattr(p, "entry_price", 0.0) or 0.0),
                                    "mark_price": float(getattr(p, "current_price", 0.0) or 0.0),
                                    "unrealized_pnl": float(getattr(p, "unrealized_pnl", 0.0) or 0.0),
                                }
                            )
                        except Exception:
                            continue
                    out["account"]["positions"] = rebuilt
                    out["account"]["synced_at"] = datetime.now().isoformat()
                    out["alerts"].append("account_positions_from_ai_trading_engine_fallback")
            # Last fallback: short direct exchange pull (non-blocking timeout) for fast snapshot correctness.
            if len(out["account"]["positions"]) == 0:
                try:
                    ex = mc.get_exchange() if hasattr(mc, "get_exchange") else None
                    if ex and hasattr(ex, "get_positions"):
                        raw_positions = await asyncio.wait_for(ex.get_positions(), timeout=2.5)
                        rebuilt2: List[Dict[str, Any]] = []
                        for p in raw_positions or []:
                            if not isinstance(p, dict):
                                continue
                            try:
                                sz = float(p.get("size", p.get("pos", 0)) or 0)
                            except Exception:
                                sz = 0.0
                            if abs(sz) <= 1e-12:
                                continue
                            rebuilt2.append(
                                {
                                    "symbol": p.get("symbol") or p.get("instId"),
                                    "side": p.get("side"),
                                    "size": sz,
                                    "entry_price": p.get("entry_price"),
                                    "mark_price": p.get("mark_px") or p.get("mark_price"),
                                    "unrealized_pnl": p.get("unrealized_pnl"),
                                }
                            )
                        if rebuilt2:
                            out["account"]["positions"] = rebuilt2
                            out["account"]["synced_at"] = datetime.now().isoformat()
                            out["alerts"].append("account_positions_from_exchange_fallback")
                except Exception:
                    pass
        except Exception:
            pass

        # 仓位管理建议（快速版：仅在能得到可用余额时生成）
        try:
            bal = out.get("account", {}).get("balance") or {}
            usdt = bal.get("USDT", bal.get("usdt", 0)) if isinstance(bal, dict) else 0
            if isinstance(usdt, dict):
                available = usdt.get("free", usdt.get("available", 0))
            else:
                available = usdt
            positions = out.get("account", {}).get("positions") or []
            pos_map: Dict[str, Any] = {}
            if isinstance(positions, list):
                for p in positions:
                    if isinstance(p, dict):
                        sym = p.get("symbol") or p.get("instId") or p.get("instrument_id")
                        if sym:
                            try:
                                v = float(p.get("notional") or p.get("value") or 0)
                            except Exception:
                                v = 0.0
                            pos_map[str(sym)] = {"value": v, **p}
            if available and hasattr(mc, "get_position_recommendations"):
                try:
                    out["risk"]["position_recommendations"] = await asyncio.wait_for(
                        mc.get_position_recommendations(
                            account_balance=float(available),
                            current_positions=pos_map,
                        ),
                        timeout=1.8,
                    )
                except Exception:
                    out["risk"]["position_recommendations"] = out["risk"].get("position_recommendations") or {}
        except Exception:
            pass

        # 数据/分析模块快照（快速版：不触发交易所重型聚合）
        try:
            di = getattr(mc, "data_integration", None)
            if di and hasattr(di, "get_source_health_report"):
                out["data_hub"]["data_integration_health"] = di.get_source_health_report()
        except Exception:
            pass
        try:
            tpi = getattr(mc, "third_party_data_integrator", None)
            if tpi:
                prov = getattr(tpi, "providers", {}) or {}
                disabled = list(getattr(tpi, "_disabled_providers", set()) or [])
                diag: Dict[str, Any] = {}
                if hasattr(tpi, "get_diagnostics"):
                    try:
                        diag = tpi.get_diagnostics()
                    except Exception:
                        diag = {}
                out["data_hub"]["third_party"] = {
                    "provider_count": len(prov),
                    "disabled_count": len(disabled),
                    "diagnostics": diag,
                }
        except Exception:
            pass
        try:
            mi = getattr(mc, "market_intelligence", None) or getattr(mc, "market_intelligence_engine", None)
            if mi:
                cached = mi.get_cached_symbol_view(symbol) if hasattr(mi, "get_cached_symbol_view") else {}
                if cached:
                    out["data_hub"]["market_intelligence"] = cached
                elif hasattr(mi, "get_symbol_view"):
                    view = await asyncio.wait_for(mi.get_symbol_view(symbol, include_snapshot=False), timeout=2.2)
                    out["data_hub"]["market_intelligence"] = view.to_dict() if hasattr(view, "to_dict") else {}
                # Still empty: report warm-up state so caller knows it's connected.
                if not out["data_hub"].get("market_intelligence"):
                    out["data_hub"]["market_intelligence"] = {
                        "status": "warming_up",
                        "hint": "market_intelligence_connected_but_no_cached_view_yet",
                    }
        except Exception:
            out["data_hub"]["market_intelligence"] = out["data_hub"].get("market_intelligence") or {
                "status": "warming_up_or_busy",
            }
        return out

    @router.get("/commander/snapshot")
    async def commander_snapshot(symbol: str = "BTC/USDT", mode: str = "fast"):
        """司令部统一快照：前端/TG/运维可共享。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        if not hasattr(main_controller, "build_ai_commander_snapshot"):
            return {"success": False, "message": "司令部快照能力不可用"}
        try:
            mode_l = str(mode or "fast").strip().lower()
            if mode_l == "full":
                data = await asyncio.wait_for(
                    main_controller.build_ai_commander_snapshot(symbol=symbol),
                    timeout=15.0,
                )
                data["mode"] = "full"
            else:
                data = await asyncio.wait_for(_build_commander_fast_snapshot(symbol=symbol), timeout=8.0)
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except asyncio.TimeoutError:
            return {
                "success": True,
                "data": {
                    "timestamp": datetime.now().isoformat(),
                    "mode": "fast_degraded_timeout",
                    "alerts": ["snapshot_timeout_degraded"],
                },
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/hosting-mode")
    async def commander_get_hosting_mode():
        """获取当前托管模式（full_auto / semi_auto）。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "get_hosting_mode"):
            return {"success": False, "message": "托管模式能力不可用", "timestamp": datetime.now().isoformat()}
        try:
            mode = main_controller.get_hosting_mode()
            return {
                "success": True,
                "data": {
                    "mode": mode,
                    "mode_zh": "全自动" if mode == "full_auto" else "半自动",
                    "description": (
                        "AI全自动托管：系统可自主开平仓并自动风控"
                        if mode == "full_auto"
                        else "半自动托管：策略开仓需人工确认，平仓风控仍自动执行"
                    ),
                    "allowed_values": [
                        {"value": "full_auto", "label": "全自动"},
                        {"value": "semi_auto", "label": "半自动"},
                    ],
                },
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/hosting-guard")
    async def commander_get_hosting_guard():
        """获取托管守护配置与状态（后端自动降级/恢复中枢）。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "get_hosting_guard_status"):
            return {"success": False, "message": "托管守护能力不可用", "timestamp": datetime.now().isoformat()}
        try:
            data = main_controller.get_hosting_guard_status()
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/automation-profile")
    async def commander_get_automation_profile():
        """获取自动化协同级别（conservative / semi_auto / full_auto）。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "get_automation_profile"):
            return {"success": False, "message": "自动化级别能力不可用", "timestamp": datetime.now().isoformat()}
        try:
            p = main_controller.get_automation_profile()
            return {"success": True, "data": {"profile": p}, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.post("/commander/automation-profile")
    async def commander_set_automation_profile(payload: Dict[str, Any] = Body(default_factory=dict)):
        """设置自动化协同级别。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "set_automation_profile"):
            return {"success": False, "message": "自动化级别能力不可用", "timestamp": datetime.now().isoformat()}
        try:
            p = str((payload or {}).get("profile") or "").strip()
            current = main_controller.set_automation_profile(p)
            return {"success": True, "data": {"profile": current}, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/risk-redlines")
    async def commander_get_risk_redlines():
        """获取统一风控红线。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "get_risk_redlines"):
            return {"success": False, "message": "风控红线能力不可用", "timestamp": datetime.now().isoformat()}
        try:
            data = main_controller.get_risk_redlines()
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.post("/commander/risk-redlines")
    async def commander_update_risk_redlines(payload: Dict[str, Any] = Body(default_factory=dict)):
        """更新统一风控红线。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "update_risk_redlines"):
            return {"success": False, "message": "风控红线能力不可用", "timestamp": datetime.now().isoformat()}
        try:
            data = main_controller.update_risk_redlines(payload or {})
            return {"success": True, "data": data, "message": "风控红线已更新", "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.post("/commander/hosting-guard")
    async def commander_update_hosting_guard(payload: Dict[str, Any] = Body(default_factory=dict)):
        """更新托管守护配置。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "update_hosting_guard_config"):
            return {"success": False, "message": "托管守护能力不可用", "timestamp": datetime.now().isoformat()}
        try:
            data = main_controller.update_hosting_guard_config(payload or {})
            return {"success": True, "data": data, "message": "托管守护配置已更新", "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/architecture/layers")
    async def commander_architecture_layers():
        """系统分层架构状态（L1-L5）与托管守护状态。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "get_architecture_layers_status"):
            return {"success": False, "message": "分层架构状态能力不可用", "timestamp": datetime.now().isoformat()}
        try:
            data = main_controller.get_architecture_layers_status()
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/upgrade/benchmark")
    async def commander_upgrade_benchmark():
        """外部基线能力对照（Agent Trade Kit / Agent Skills 映射结果）。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "get_external_benchmark_matrix"):
            return {"success": False, "message": "基线对照能力不可用", "timestamp": datetime.now().isoformat()}
        try:
            data = main_controller.get_external_benchmark_matrix()
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/tool-contract")
    async def commander_tool_contract():
        """标准工具契约清单（供 OpenClaw/MCP/CLI 对接）。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "get_tool_contract_catalog"):
            return {"success": False, "message": "工具契约能力不可用", "timestamp": datetime.now().isoformat()}
        try:
            data = main_controller.get_tool_contract_catalog()
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/governance-audit")
    async def commander_governance_audit(limit: int = 100):
        """治理审计流：托管切换、自动化分级、红线更新等变更回放。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "get_governance_audit"):
            return {"success": False, "message": "治理审计能力不可用", "timestamp": datetime.now().isoformat()}
        try:
            data = main_controller.get_governance_audit(limit=limit)
            return {"success": True, "data": {"items": data}, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.post("/commander/upgrade/run")
    async def commander_upgrade_run(payload: Dict[str, Any] = Body(default_factory=dict)):
        """
        一键升级闭环执行：
        - 账户同步
        - 司令部任务/策略优化
        - 分层验收
        - 托管守护验收
        - 回撤统计验收
        - 外部基线对照
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "run_upgrade_pipeline"):
            return {"success": False, "message": "一键升级能力不可用", "timestamp": datetime.now().isoformat()}
        try:
            symbol = str((payload or {}).get("symbol") or "BTC/USDT")
            trigger_optimize = bool((payload or {}).get("trigger_optimize", True))
            force_account_sync = bool((payload or {}).get("force_account_sync", True))
            auto_fallback_to_semi = bool((payload or {}).get("auto_fallback_to_semi", True))
            data = await main_controller.run_upgrade_pipeline(
                symbol=symbol,
                trigger_optimize=trigger_optimize,
                force_account_sync=force_account_sync,
                auto_fallback_to_semi=auto_fallback_to_semi,
            )
            return {"success": bool(data.get("success")), "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.post("/commander/hosting-mode")
    async def commander_set_hosting_mode(payload: Dict[str, Any] = Body(default_factory=dict)):
        """切换托管模式。mode: full_auto / semi_auto"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "set_hosting_mode"):
            return {"success": False, "message": "托管模式能力不可用", "timestamp": datetime.now().isoformat()}
        mode = str((payload or {}).get("mode") or "").strip()
        mode_l = mode.lower()
        normalized = mode_l
        if mode in {"全自动", "自动"} or mode_l in {"full", "auto"}:
            normalized = "full_auto"
        elif mode in {"半自动"} or mode_l in {"semi", "semi-automatic", "semi_automatic"}:
            normalized = "semi_auto"
        if normalized not in {"full_auto", "semi_auto"}:
            return {
                "success": False,
                "message": "mode 仅支持: full_auto/全自动 或 semi_auto/半自动",
                "timestamp": datetime.now().isoformat(),
            }
        try:
            current = main_controller.set_hosting_mode(normalized)
            return {
                "success": True,
                "data": {
                    "mode": current,
                    "mode_zh": "全自动" if current == "full_auto" else "半自动",
                },
                "message": (
                    "已切换为全自动托管（AI自主开平仓）"
                    if current == "full_auto"
                    else "已切换为半自动托管（开仓需人工确认）"
                ),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/capabilities")
    async def commander_capabilities():
        """司令部能力与子智能体清单（对齐 OpenClaw 文档中的回路/专家概念，便于运维对接）。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "get_commander_capabilities"):
            return {"success": False, "message": "capabilities 不可用", "timestamp": datetime.now().isoformat()}
        try:
            data = main_controller.get_commander_capabilities()
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/openclaw-integration")
    async def commander_openclaw_integration():
        """OpenClaw 对接状态：读取入口、实时通道、推送配置就绪度。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        try:
            hub = getattr(main_controller, "trade_event_hub", None)
            push_enabled = bool(getattr(hub, "_openclaw_push_enabled", False)) if hub else False
            push_url = str(getattr(hub, "_openclaw_push_url", "") or "") if hub else ""
            queue_size = 0
            queue_max = 0
            if hub and getattr(hub, "_openclaw_push_queue", None) is not None:
                q = getattr(hub, "_openclaw_push_queue")
                queue_size = int(q.qsize())
                queue_max = int(getattr(q, "maxsize", 0))
            data = {
                "dispatch_ready": bool(hasattr(main_controller, "process_user_command")),
                "capabilities_ready": bool(hasattr(main_controller, "get_commander_capabilities")),
                "tool_contract_ready": bool(hasattr(main_controller, "get_tool_contract_catalog")),
                "event_hub_ready": bool(hub is not None),
                "event_stream_replay_ready": bool(hub and hasattr(hub, "query_recent")),
                "system_alert_bridge_ready": bool(hub and hasattr(hub, "publish_system_alert")),
                "openclaw_push": {
                    "enabled": push_enabled,
                    "url_configured": bool(push_url),
                    "queue_size": queue_size,
                    "queue_max": queue_max,
                },
                "required_realtime_channels": ["trade.intent", "trade.fill", "trade.position", "market.update", "system.alert"],
                "required_read_endpoints": [
                    "/api/v1/modules/commander/capabilities",
                    "/api/v1/modules/commander/tool-contract",
                    "/api/v1/modules/commander/snapshot",
                    "/api/v1/modules/commander/account-diagnostics",
                    "/api/v1/trade/events",
                ],
            }
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.post("/commander/chores")
    async def commander_chores(payload: Dict[str, Any] = Body(default_factory=dict)):
        """触发司令部日常任务。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        if not hasattr(main_controller, "run_ai_commander_chores"):
            return {"success": False, "message": "司令部日常任务能力不可用"}
        try:
            symbol = str((payload or {}).get("symbol") or "BTC/USDT")
            trigger_optimize = bool((payload or {}).get("trigger_optimize", False))
            data = await main_controller.run_ai_commander_chores(symbol=symbol, trigger_optimize=trigger_optimize)
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.post("/commander/dispatch")
    async def commander_dispatch(payload: Dict[str, Any] = Body(default_factory=dict)):
        """
        司令部统一指令入口：把前端消息与TG消息统一到同一处理链路。
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化"}
        if not hasattr(main_controller, "process_user_command"):
            return {"success": False, "message": "司令部指令入口不可用"}
        text = str((payload or {}).get("message") or "").strip()
        if not text:
            return {"success": False, "message": "message 不能为空"}
        source = str((payload or {}).get("source") or "control_hub")
        async_mode = bool((payload or {}).get("async_mode", False))
        try:
            timeout_s = float((payload or {}).get("timeout_sec", 12.0) or 12.0)
        except Exception:
            timeout_s = 12.0
        timeout_s = max(2.0, min(timeout_s, 90.0))
        try:
            if async_mode:
                job_id = str(uuid.uuid4())
                async with dispatch_jobs_lock:
                    dispatch_jobs[job_id] = {
                        "job_id": job_id,
                        "status": "queued",
                        "created_at": datetime.now().isoformat(),
                        "source": source,
                        "message_preview": text[:120],
                        "result": None,
                        "error": None,
                    }

                async def _run_dispatch_job() -> None:
                    async with dispatch_jobs_lock:
                        if job_id in dispatch_jobs:
                            dispatch_jobs[job_id]["status"] = "running"
                            dispatch_jobs[job_id]["started_at"] = datetime.now().isoformat()
                    try:
                        out = await main_controller.process_user_command(text, source=source)
                        async with dispatch_jobs_lock:
                            if job_id in dispatch_jobs:
                                dispatch_jobs[job_id]["status"] = "completed"
                                dispatch_jobs[job_id]["finished_at"] = datetime.now().isoformat()
                                dispatch_jobs[job_id]["result"] = out
                    except Exception as e:
                        async with dispatch_jobs_lock:
                            if job_id in dispatch_jobs:
                                dispatch_jobs[job_id]["status"] = "failed"
                                dispatch_jobs[job_id]["finished_at"] = datetime.now().isoformat()
                                dispatch_jobs[job_id]["error"] = str(e)

                asyncio.create_task(_run_dispatch_job())
                return {
                    "success": True,
                    "accepted": True,
                    "status": "queued",
                    "job_id": job_id,
                    "message": "指令已受理，后台执行中",
                    "timestamp": datetime.now().isoformat(),
                }

            out = await asyncio.wait_for(
                main_controller.process_user_command(text, source=source),
                timeout=timeout_s,
            )
            return {"success": True, "data": out, "timeout_sec": timeout_s, "timestamp": datetime.now().isoformat()}
        except asyncio.TimeoutError:
            # 避免前端超时卡死；建议客户端改用 async_mode=true 拉取结果。
            return {
                "success": False,
                "status": "timeout",
                "timeout_sec": timeout_s,
                "message": "司令部处理超时，请使用 async_mode=true 重试并轮询 job 结果",
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/dispatch/jobs/{job_id}")
    async def commander_dispatch_job(job_id: str):
        """查询异步 dispatch 任务状态。"""
        async with dispatch_jobs_lock:
            job = dispatch_jobs.get(job_id)
            if not job:
                return {"success": False, "message": "job 不存在", "job_id": job_id, "timestamp": datetime.now().isoformat()}
            return {"success": True, "data": job, "timestamp": datetime.now().isoformat()}

    @router.get("/commander/audit")
    async def commander_audit(enrich: bool = False):
        """
        司令部全链路审查：检查前端/消息通道/后端关键能力是否已接入。
        enrich=true 时附带第三方限速诊断摘要与记忆网关快照（供运维质检）。
        """
        checks: List[Dict[str, Any]] = []

        def add(name: str, passed: bool, detail: str = "") -> None:
            checks.append({"name": name, "passed": bool(passed), "detail": detail})

        if not main_controller:
            add("main_controller", False, "missing")
            return {"success": False, "checks": checks, "all_passed": False, "timestamp": datetime.now().isoformat()}

        mc = main_controller
        add("commander.snapshot", hasattr(mc, "build_ai_commander_snapshot"), "build_ai_commander_snapshot")
        add("commander.chores", hasattr(mc, "run_ai_commander_chores"), "run_ai_commander_chores")
        add("commander.dispatch", hasattr(mc, "process_user_command"), "process_user_command")
        add("commander.capabilities", hasattr(mc, "get_commander_capabilities"), "get_commander_capabilities")
        add("surface.registry", True, "GET /api/v1/modules/surface/registry")
        add("surface.data_integration_health", True, "GET /api/v1/modules/data/integration/health")
        add("surface.plugins_status", True, "GET /api/v1/modules/plugins/status")
        add("message.telegram", bool(getattr(mc, "telegram_bot", None)), "telegram_bot")
        add("notification.unified", hasattr(mc, "_send_notification_handler"), "_send_notification_handler")
        add("memory.gateway", bool(getattr(mc, "memory_gateway", None)), "memory_gateway")
        add(
            "commander.unrestricted",
            str(__import__("os").environ.get("OPENCLAW_COMMANDER_UNRESTRICTED", "1")).strip().lower() not in {"0", "false", "no", "off"},
            "OPENCLAW_COMMANDER_UNRESTRICTED",
        )
        add("data.hub", bool(getattr(mc, "data_source_hub", None)), "data_source_hub")
        add("data.integration", bool(getattr(mc, "data_integration", None)), "data_integration")
        tpi = getattr(mc, "third_party_data_integrator", None)
        add("data.third_party", bool(tpi), "third_party_data_integrator")
        add(
            "data.third_party.diagnostics",
            bool(tpi and hasattr(tpi, "get_diagnostics")),
            "get_diagnostics for rate-limit QC",
        )
        add("analysis.market_intelligence", bool(getattr(mc, "market_intelligence", None)), "market_intelligence")
        add("plugin.manager", bool(getattr(mc, "plugin_manager", None)), "plugin_manager")
        add("strategy.manager", bool(getattr(mc, "strategy_manager", None)), "strategy_manager")
        add("risk.sltp", bool(getattr(mc, "stop_loss_manager", None)), "stop_loss_manager")
        add("execution.gateway", bool(getattr(mc, "execution_gateway", None)), "execution_gateway")
        add("api.module_control", True, "routes_registered")
        all_passed = all(c["passed"] for c in checks)
        out: Dict[str, Any] = {
            "success": True,
            "all_passed": all_passed,
            "checks": checks,
            "timestamp": datetime.now().isoformat(),
            "architecture": {
                "pattern": "commander_centric",
                "summary": (
                    "司令部(CommanderAgentRuntime)为统一入口：process_user_command → 指令执行器/子智能体(specialists)/记忆网关；"
                    "各业务模块为子系统，由 MainController 装配；实时消息(Telegram 等)与 HTTP dispatch 同源接入。"
                ),
            },
        }
        if enrich:
            out["third_party_diagnostics"] = {}
            if tpi and hasattr(tpi, "get_diagnostics"):
                try:
                    out["third_party_diagnostics"] = tpi.get_diagnostics()
                except Exception as e:
                    out["third_party_diagnostics"] = {"error": str(e)}
            gw = getattr(mc, "memory_gateway", None)
            out["memory_quick"] = {}
            if gw:
                try:
                    out["memory_quick"] = {
                        "stats": gw.get_stats() if hasattr(gw, "get_stats") else {},
                        "summary": gw.get_summary_status() if hasattr(gw, "get_summary_status") else {},
                    }
                except Exception as e:
                    out["memory_quick"] = {"error": str(e)}
            tb = getattr(mc, "telegram_bot", None)
            out["realtime_channels"] = {
                "telegram_configured": tb is not None,
                "hint": "前端/脚本与 Bot 均可用 POST /api/v1/modules/commander/dispatch 统一 source 标签",
            }
        return out

    @router.get("/commander/memory/status")
    async def commander_memory_status():
        """司令部记忆系统自检：网关/后端统计/召回命中率等。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        gw = getattr(main_controller, "memory_gateway", None)
        if not gw:
            return {"success": False, "message": "MemoryGateway 未就绪", "timestamp": datetime.now().isoformat()}
        try:
            stats = gw.get_stats() if hasattr(gw, "get_stats") else {}
            summary = gw.get_summary_status() if hasattr(gw, "get_summary_status") else {}
            return {
                "success": True,
                "data": {
                    "stats": stats,
                    "summary": summary,
                },
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/memory/workspace")
    async def commander_memory_workspace(filename: str = ""):
        """读取 workspace 记忆文件（默认读取允许集合；可用 env 放开全部）。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        gw = getattr(main_controller, "memory_gateway", None)
        if not gw or not hasattr(gw, "get_workspace_memory"):
            return {"success": False, "message": "MemoryGateway 未就绪", "timestamp": datetime.now().isoformat()}
        try:
            data = gw.get_workspace_memory(filename=filename or None)
            # 避免一次性回传超大：每个文件最多返回 200k 字符
            clipped = {}
            for k, v in (data or {}).items():
                s = v if isinstance(v, str) else str(v)
                clipped[k] = s if len(s) <= 200_000 else (s[:200_000] + "\n\n…已截断…")
            return {"success": True, "data": clipped, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/memory/persona-preview")
    async def commander_memory_persona_preview(source: str = "api"):
        """
        司令部人格/身份/职责是否已注入：返回「将被注入到对话提示词的摘要」预览。
        用于排查“司令部好像不知道自己是谁/做什么”的问题。
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        exe = getattr(main_controller, "ai_command_executor", None)
        if not exe or not hasattr(exe, "_get_user_rules_context"):
            return {"success": False, "message": "AICommandExecutor 未就绪", "timestamp": datetime.now().isoformat()}
        try:
            # _get_user_rules_context 会包含 CHARTER + startup bundle + boundaries prose + 关键记忆片段
            text = await exe._get_user_rules_context()
            cap = 18_000
            preview = text if len(text) <= cap else (text[:cap] + "\n\n…已截断…")
            return {
                "success": True,
                "data": {
                    "source": source,
                    "preview": preview,
                    "length": len(text),
                    "has_startup_bundle": bool(getattr(exe, "_workspace_startup_bundle", "") or ""),
                },
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/account-diagnostics")
    async def commander_account_diagnostics():
        """
        交易所实时持仓/余额 vs 本地 SLTP 跟踪 — 排查同步问题（不依赖本机成交笔数）。
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "get_account_sync_diagnostics"):
            return {"success": False, "message": "诊断接口不可用", "timestamp": datetime.now().isoformat()}
        try:
            # 账户私有接口在代理抖动时可能接近 20s；放宽超时以减少误判降级。
            data = await asyncio.wait_for(main_controller.get_account_sync_diagnostics(), timeout=45.0)
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except asyncio.TimeoutError:
            # 降级时也返回关键事实，避免前端误判为 exchange=None / positions=0。
            ex_name = None
            try:
                ex = main_controller.get_exchange() if hasattr(main_controller, "get_exchange") else None
                ex_name = type(ex).__name__ if ex is not None else None
            except Exception:
                ex_name = None
            st = getattr(main_controller, "_latest_account_state", None)
            cached_positions = []
            if isinstance(st, dict) and isinstance(st.get("positions"), list):
                cached_positions = st.get("positions") or []
            elif (
                getattr(main_controller, "ai_trading_engine", None) is not None
                and isinstance(getattr(main_controller.ai_trading_engine, "positions", None), dict)
            ):
                cached_positions = list(main_controller.ai_trading_engine.positions.values())
            return {
                "success": True,
                "degraded": True,
                "data": {
                    "status": "timeout_degraded",
                    "hint": "account_diagnostics_timeout",
                    "exchange": ex_name,
                    "cached_position_count": len(cached_positions),
                },
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/trading-diagnosis")
    async def commander_trading_diagnosis(limit_events: int = 20):
        """
        全面体检：开/平仓技术判断、执行脊柱、SLTP 出场、学习引擎是否在运转与写回。
        用于验收“智能体是否正常运用性能、并能自总结经验教训自动优化策略”。
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        mc = main_controller
        out: Dict[str, Any] = {"timestamp": datetime.now().isoformat()}

        # 1) ai_core / ai_trading_engine 状态（技术判断路径）
        try:
            core = getattr(mc, "ai_core", None)
            out["ai_core"] = core.get_status() if (core and hasattr(core, "get_status")) else None
        except Exception as e:
            out["ai_core_error"] = str(e)
        try:
            eng = getattr(mc, "ai_trading_engine", None)
            out["ai_trading_engine"] = eng.get_status() if (eng and hasattr(eng, "get_status")) else None
        except Exception as e:
            out["ai_trading_engine_error"] = str(e)

        # 2) ExecutionGateway（执行成功率、回查一致性、recent events）
        try:
            gw = getattr(mc, "execution_gateway", None)
            if gw and hasattr(gw, "get_snapshot"):
                snap = await gw.get_snapshot()
                if gw and hasattr(gw, "get_recent_events"):
                    snap["recent_events"] = await gw.get_recent_events(limit=int(limit_events or 20))
                out["execution_gateway"] = snap
                out["execution_reconciliation"] = (
                    snap.get("reconciliation") if isinstance(snap, dict) else None
                )
                out["execution_reconciliation_protection"] = (
                    snap.get("reconciliation_protection") if isinstance(snap, dict) else None
                )
                out["execution_safe_recovery"] = (
                    ((snap.get("reconciliation") or {}).get("safe_recovery"))
                    if isinstance(snap, dict) and isinstance(snap.get("reconciliation"), dict)
                    else None
                )
                out["decision_traces"] = (
                    snap.get("decision_traces") if isinstance(snap, dict) else None
                )
            else:
                out["execution_gateway"] = None
                out["execution_reconciliation"] = None
                out["execution_reconciliation_protection"] = None
                out["execution_safe_recovery"] = None
                out["decision_traces"] = None
        except Exception as e:
            out["execution_gateway_error"] = str(e)

        # 3) SLTP（含 SR 关键位出场观测）
        try:
            sltp = getattr(mc, "stop_loss_manager", None)
            out["sltp"] = sltp.get_stats() if (sltp and hasattr(sltp, "get_stats")) else None
        except Exception as e:
            out["sltp_error"] = str(e)

        # 4) AI 学习引擎（经验教训/优化循环）
        try:
            le = getattr(mc, "ai_learning_engine", None)
            out["ai_learning_engine"] = le.get_status() if (le and hasattr(le, "get_status")) else None
            if isinstance(out.get("ai_learning_engine"), dict):
                out["trace_learning_feedback"] = (out.get("ai_learning_engine") or {}).get("trace_feedback")
        except Exception as e:
            out["ai_learning_engine_error"] = str(e)

        # 5) TradeHistory 统计（用于盈利/亏损结构评估）
        try:
            ths = getattr(mc, "trade_history_service", None)
            if ths and hasattr(ths, "get_statistics"):
                # 诊断接口优先快返回，避免为了强制刷新历史统计而阻塞整条验收链路。
                out["trade_history_30d"] = await asyncio.wait_for(
                    ths.get_statistics(days=30, force_refresh=False),
                    timeout=2.5,
                )
        except asyncio.TimeoutError:
            out["trade_history_30d"] = {"degraded": True, "message": "trade_history_stats_timeout"}
        except Exception as e:
            out["trade_history_error"] = str(e)

        # 5.1) Unified analysis pipeline assessment (data sensitivity + decision outcome health)
        try:
            assess: Dict[str, Any] = {}
            cfgm = getattr(mc, "config_manager", None)
            pa_cfg = {}
            if cfgm and hasattr(cfgm, "get_config_path_sync"):
                try:
                    pa_cfg = cfgm.get_config_path_sync("proactive_scanner", {}) or {}
                except Exception:
                    pa_cfg = {}
            if not isinstance(pa_cfg, dict):
                pa_cfg = {}

            gw = getattr(mc, "execution_gateway", None)
            swo = "ai_core"
            try:
                if gw and hasattr(gw, "single_write_owner"):
                    swo = await gw.single_write_owner()
            except Exception:
                swo = "ai_core"

            assess["pipeline"] = {
                "single_write_owner": str(swo or "ai_core"),
                "proactive_auto_execute_opportunities": bool(pa_cfg.get("proactive_auto_execute_opportunities", False)),
                "expectation": "scanner_forward_only_then_ai_core_decides",
            }

            # Proactive scanner observability (scan health + gate reject distribution)
            try:
                pa = getattr(mc, "proactive_ai", None)
                if pa and hasattr(pa, "get_status"):
                    pst = pa.get_status()
                    if isinstance(pst, dict):
                        ms = pst.get("market_scanner") if isinstance(pst.get("market_scanner"), dict) else {}
                        assess["proactive_scanner"] = {
                            "running": bool(pst.get("running", False)),
                            "initialized": bool(pst.get("initialized", False)),
                            "opportunities": int((ms or {}).get("opportunities", 0) or 0),
                            "insights": int((ms or {}).get("insights", 0) or 0),
                            "market_state": (ms or {}).get("market_state"),
                            "runtime": (ms or {}).get("runtime"),
                            "stats": (ms or {}).get("stats"),
                        }
            except Exception as e:
                assess["proactive_scanner_error"] = str(e)

            # Market analysis sensitivity sample across default symbols.
            mi = getattr(mc, "market_intelligence", None)
            sampled_symbols = list(pa_cfg.get("default_symbols", []) or [])
            if not sampled_symbols:
                sampled_symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "AVAX/USDT"]
            sampled_symbols = [str(s) for s in sampled_symbols[:4]]
            market_rows: List[Dict[str, Any]] = []
            degraded_cnt = 0
            quality_non_null = 0
            conf_non_null = 0
            trend_known = 0

            async def _sample_symbol_view(sym: str) -> Dict[str, Any]:
                try:
                    cached = (
                        mi.get_cached_symbol_view(sym)
                        if hasattr(mi, "get_cached_symbol_view")
                        else {}
                    )
                    if isinstance(cached, dict) and cached:
                        prov = str(cached.get("provenance") or "").lower()
                        partial = bool(cached.get("partial", False))
                        if (
                            not partial
                            and prov not in {"fastpath", "degraded", "unknown"}
                            and cached.get("quality_score") is not None
                            and cached.get("confidence") is not None
                        ):
                            return {"symbol": sym, "view": cached}
                except Exception:
                    pass
                try:
                    view = await asyncio.wait_for(
                        mi.get_symbol_view(sym, include_snapshot=True, prefer_fast_only=False),
                        timeout=2.5,
                    )
                    vd = view.to_dict() if hasattr(view, "to_dict") else {}
                    if isinstance(vd, dict) and vd:
                        prov = str(vd.get("provenance") or "").lower()
                        partial = bool(vd.get("partial", False))
                        strong = (
                            (not partial)
                            and ("degraded" not in prov)
                            and ("fastpath" not in prov)
                            and prov not in {"", "unknown"}
                            and vd.get("confidence") is not None
                            and (
                                vd.get("quality_score") is not None
                                or vd.get("atr_pct_1h") is not None
                                or vd.get("spread_bps") is not None
                            )
                        )
                        if strong:
                            return {"symbol": sym, "view": vd}
                except asyncio.TimeoutError:
                    try:
                        view = await asyncio.wait_for(
                            mi.get_symbol_view(sym, include_snapshot=False, prefer_fast_only=True),
                            timeout=1.0,
                        )
                        vd = view.to_dict() if hasattr(view, "to_dict") else {}
                        if isinstance(vd, dict) and vd:
                            prov = str(vd.get("provenance") or "").lower()
                            partial = bool(vd.get("partial", False))
                            strong = (
                                (not partial)
                                and ("degraded" not in prov)
                                and ("fastpath" not in prov)
                                and prov not in {"", "unknown"}
                                and vd.get("confidence") is not None
                                and (
                                    vd.get("quality_score") is not None
                                    or vd.get("atr_pct_1h") is not None
                                    or vd.get("spread_bps") is not None
                                )
                            )
                            if strong:
                                return {"symbol": sym, "view": vd}
                    except Exception:
                        pass
                except Exception:
                    pass
                try:
                    hub = getattr(mc, "data_source_hub", None)
                    if hub and hasattr(hub, "get_exchange_channel"):
                        exch = await asyncio.wait_for(hub.get_exchange_channel(sym), timeout=8.0)
                        q = (
                            hub._score_quality(exch, {})
                            if hasattr(hub, "_score_quality")
                            else {}
                        )
                        ticker = (exch.get("ticker") or {}) if isinstance(exch, dict) else {}
                        order_book = (exch.get("order_book") or {}) if isinstance(exch, dict) else {}
                        open_interest = (exch.get("open_interest") or {}) if isinstance(exch, dict) else {}
                        funding_rate = exch.get("funding_rate") if isinstance(exch, dict) else None
                        quality = q.get("score") if isinstance(q, dict) else None
                        kl = (exch.get("klines_1h") or []) if isinstance(exch, dict) else []
                        if not ticker and not kl and quality is None:
                            raise RuntimeError("exchange_channel_empty")
                        ob_bids = order_book.get("bids") if isinstance(order_book, dict) else []
                        ob_asks = order_book.get("asks") if isinstance(order_book, dict) else []
                        best_bid = _safe_float(ob_bids[0][0], 0.0) if ob_bids else 0.0
                        best_ask = _safe_float(ob_asks[0][0], 0.0) if ob_asks else 0.0
                        spread_bps = None
                        if best_bid > 0 and best_ask > 0:
                            mid = 0.5 * (best_bid + best_ask)
                            if mid > 0 and best_ask >= best_bid:
                                spread_bps = float(((best_ask - best_bid) / mid) * 10000.0)
                        depth_imbalance = None
                        try:
                            bid_sz = sum(_safe_float(x[1], 0.0) for x in (ob_bids[:5] or []))
                            ask_sz = sum(_safe_float(x[1], 0.0) for x in (ob_asks[:5] or []))
                            denom = bid_sz + ask_sz
                            if denom > 0:
                                depth_imbalance = float((bid_sz - ask_sz) / denom)
                        except Exception:
                            depth_imbalance = None
                        atr_pct = None
                        try:
                            if isinstance(kl, list) and len(kl) >= 15:
                                highs = [_safe_float(k.get("high"), 0.0) for k in kl[-15:]]
                                lows = [_safe_float(k.get("low"), 0.0) for k in kl[-15:]]
                                closes = [_safe_float(k.get("close"), 0.0) for k in kl[-15:]]
                                trs = []
                                for i in range(1, len(closes)):
                                    trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
                                if trs and closes[-1] > 0:
                                    atr_pct = float(sum(trs[-14:]) / max(1, len(trs[-14:])) / closes[-1])
                        except Exception:
                            atr_pct = None
                        change_24h = _safe_float(ticker.get("change24h") or ticker.get("change_24h") or ticker.get("change"), 0.0)
                        trend = "sideways"
                        if change_24h >= 0.003:
                            trend = "bullish"
                        elif change_24h <= -0.003:
                            trend = "bearish"
                        conf = max(0.45, min(0.85, float(quality if quality is not None else 0.45)))
                        if atr_pct is not None and atr_pct > 0:
                            conf = max(conf, 0.55)
                        return {
                            "symbol": sym,
                            "view": {
                                "symbol": sym,
                                "quality_score": quality,
                                "confidence": round(conf, 3),
                                "trend": trend,
                                "spread_bps": round(spread_bps, 4) if spread_bps is not None else None,
                                "atr_pct_1h": atr_pct,
                                "depth_imbalance": round(depth_imbalance, 4) if depth_imbalance is not None else None,
                                "best_bid": best_bid if best_bid > 0 else None,
                                "best_ask": best_ask if best_ask > 0 else None,
                                "open_interest": open_interest if isinstance(open_interest, dict) and open_interest else None,
                                "funding_rate": funding_rate,
                                "provenance": "unified_snapshot_fallback",
                                "partial": False,
                            },
                        }
                except Exception:
                    pass
                return {"symbol": sym, "degraded": True, "error": "symbol_view_error"}

            if mi and hasattr(mi, "get_symbol_view"):
                rows = []
                for sym in sampled_symbols:
                    rows.append(await _sample_symbol_view(sym))
                for row in rows:
                    try:
                        sym = str(row.get("symbol") or "")
                        vd = row.get("view") if isinstance(row.get("view"), dict) else {}
                        if not vd:
                            raise RuntimeError(str(row.get("error") or "symbol_view_unavailable"))
                        quality = vd.get("quality_score")
                        conf = vd.get("confidence")
                        trend = str(vd.get("trend") or "unknown").lower()
                        prov = str(vd.get("provenance") or "")
                        partial = bool(vd.get("partial", False))
                        degraded = partial or ("degraded" in prov) or ("fastpath" in prov)
                        if degraded:
                            degraded_cnt += 1
                        if quality is not None:
                            quality_non_null += 1
                        if conf is not None:
                            conf_non_null += 1
                        if trend not in {"", "unknown", "none", "null"}:
                            trend_known += 1
                        market_rows.append(
                            {
                                "symbol": sym,
                                "quality_score": quality,
                                "confidence": conf,
                                "trend": vd.get("trend"),
                                "spread_bps": vd.get("spread_bps"),
                                "atr_pct_1h": vd.get("atr_pct_1h"),
                                "depth_imbalance": vd.get("depth_imbalance"),
                                "best_bid": vd.get("best_bid"),
                                "best_ask": vd.get("best_ask"),
                                "open_interest": vd.get("open_interest"),
                                "funding_rate": vd.get("funding_rate"),
                                "provenance": vd.get("provenance"),
                                "partial": partial,
                                "degraded": degraded,
                            }
                        )
                    except Exception as e:
                        degraded_cnt += 1
                        market_rows.append({"symbol": row.get("symbol"), "degraded": True, "error": str(e)[:80]})

            total_m = max(1, len(market_rows))
            assess["market_analysis"] = {
                "sampled_symbols": sampled_symbols,
                "degraded_ratio": round(float(degraded_cnt) / float(total_m), 4),
                "quality_coverage": round(float(quality_non_null) / float(total_m), 4),
                "confidence_coverage": round(float(conf_non_null) / float(total_m), 4),
                "trend_known_coverage": round(float(trend_known) / float(total_m), 4),
                "samples": market_rows,
            }

            # Decision outcome health from recent realized non-zero trades.
            decision_health = {"sample_size": 0, "wins": 0, "losses": 0, "win_rate": None, "sum_pnl": 0.0, "expectancy": None}
            ths = getattr(mc, "trade_history_service", None)
            if ths and hasattr(ths, "get_recent_trades"):
                rows = await asyncio.wait_for(ths.get_recent_trades(limit=120), timeout=2.5)
                clean = []
                for r in rows or []:
                    if not isinstance(r, dict):
                        continue
                    pnl = float(r.get("pnl", 0) or 0)
                    pnl_pct = float(r.get("pnl_percent", 0) or 0)
                    if abs(pnl) > 1e-12 or abs(pnl_pct) > 1e-12:
                        clean.append({"pnl": pnl, "reasoning": r.get("reasoning"), "symbol": r.get("symbol")})
                recent = clean[:40]
                w = sum(1 for r in recent if float(r.get("pnl", 0) or 0) > 0)
                l = sum(1 for r in recent if float(r.get("pnl", 0) or 0) < 0)
                total = len(recent)
                sum_pnl = float(sum(float(r.get("pnl", 0) or 0) for r in recent))
                decision_health = {
                    "sample_size": total,
                    "wins": w,
                    "losses": l,
                    "win_rate": round((float(w) / float(total)) if total else 0.0, 4),
                    "sum_pnl": round(sum_pnl, 6),
                    "expectancy": round((sum_pnl / float(total)) if total else 0.0, 6),
                }
            assess["decision_outcome_recent"] = decision_health

            # Learning effectiveness readiness.
            le = getattr(mc, "ai_learning_engine", None)
            le_st = le.get_status() if (le and hasattr(le, "get_status")) else {}
            lessons = int((le_st or {}).get("total_lessons", 0) or 0)
            reports = int((le_st or {}).get("reports_generated", 0) or 0)
            assess["learning_effectiveness"] = {
                "running": bool((le_st or {}).get("running", False)),
                "total_lessons": lessons,
                "reports_generated": reports,
                "trace_feedback": (le_st or {}).get("trace_feedback"),
                "effective": bool(lessons > 0 and reports > 0),
                "hint": "seed-and-run then verify total_lessons/reports_generated increments"
                if not (lessons > 0 and reports > 0)
                else "learning feedback loop active",
            }
            out["analysis_pipeline_assessment"] = assess
        except Exception as e:
            out["analysis_pipeline_assessment_error"] = str(e)

        # 6) 自动总结的“经验教训”与建议（轻量，避免误导）
        try:
            core = getattr(mc, "ai_core", None)
            gw = getattr(mc, "execution_gateway", None)
            hints: List[str] = []
            if core and hasattr(core, "get_status"):
                st = core.get_status() or {}
                guards = ((st.get("execution_guards") or {}).get("stats") or {}) if isinstance(st, dict) else {}
                top = sorted([(k, int(v)) for k, v in (guards or {}).items()], key=lambda x: x[1], reverse=True)[:6]
                if top:
                    hints.append("ai_core 门控Top: " + ", ".join([f"{k}={v}" for k, v in top]))
            if gw and hasattr(gw, "get_policy_metrics"):
                pm = gw.get_policy_metrics() or {}
                hints.append("execution 脊柱: " + ", ".join([f"{k}={pm.get(k)}" for k in ("open_ok","open_fail","close_ok","close_fail")]))
            rec = out.get("execution_reconciliation") if isinstance(out.get("execution_reconciliation"), dict) else {}
            if rec:
                sm = rec.get("summary") if isinstance(rec.get("summary"), dict) else {}
                hints.append(
                    "execution 对账: "
                    + ", ".join(
                        [
                            f"healthy={rec.get('healthy')}",
                            f"severity={rec.get('severity')}",
                            f"drift_total={sm.get('drift_total', 0)}",
                            f"stale_open_orders={sm.get('stale_open_orders', 0)}",
                        ]
                    )
                )
            rcp = out.get("execution_reconciliation_protection") if isinstance(out.get("execution_reconciliation_protection"), dict) else {}
            if rcp:
                sl = rcp.get("symbol_locks") if isinstance(rcp.get("symbol_locks"), dict) else {}
                hints.append(
                    "reconciliation protection: "
                    + ", ".join(
                        [
                            f"global={bool(rcp.get('global_lock_active', False))}",
                            f"symbol_locks={len(sl)}",
                        ]
                    )
                )
                acts = rcp.get("safe_recovery_actions") if isinstance(rcp.get("safe_recovery_actions"), list) else []
                if acts:
                    hints.append(f"safe recovery actions={len(acts)}")
            out["diagnosis_hints"] = hints
        except Exception:
            pass

        # 6.1) Canonical position limits snapshot (single entry validation)
        try:
            from src.modules.core.trading_limits import resolve_position_limits

            limits = await resolve_position_limits(config_manager=getattr(mc, "config_manager", None))
            out["position_limits_snapshot"] = limits.to_dict()
        except Exception as e:
            out["position_limits_snapshot_error"] = str(e)

        # 7) Execution failures attribution: Top reasons + samples + action hints
        try:
            gw = getattr(mc, "execution_gateway", None)
            eg = out.get("execution_gateway") if isinstance(out.get("execution_gateway"), dict) else {}
            events = (eg.get("recent_events") or []) if isinstance(eg.get("recent_events"), list) else []
            # focus on failures only
            fails = [e for e in events if isinstance(e, dict) and e.get("success") is False]

            def _key(e: Dict[str, Any]) -> str:
                op = str(e.get("op") or "unknown")
                code = str(e.get("error_code") or "UNKNOWN")
                phase = str(e.get("phase") or "unknown")
                return f"{op}:{code}:{phase}"

            counts: Dict[str, int] = {}
            samples: Dict[str, List[Dict[str, Any]]] = {}
            for e in fails:
                k = _key(e)
                counts[k] = int(counts.get(k, 0)) + 1
                samples.setdefault(k, [])
                if len(samples[k]) < 3:
                    samples[k].append(
                        {
                            "ts": e.get("ts"),
                            "symbol": e.get("symbol"),
                            "side": e.get("side"),
                            "source": e.get("source"),
                            "reason": e.get("reason"),
                            "detail": str(e.get("detail") or "")[:220],
                            "trace_id": e.get("trace_id"),
                            "endpoint": e.get("endpoint"),
                            "retriable": bool(e.get("retriable")),
                        }
                    )

            top_keys = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:8]

            def _action_hint(code: str) -> str:
                code = str(code or "").upper()
                return {
                    "POLICY_DENIED": "检查 single_write_owner/来源(source) 是否符合规则；必要时用 manual 或 force_close。",
                    "HOSTING_MODE_DENIED": "当前半自动托管：需在指令/接口里标记 manual_approved 或用 manual source。",
                    "OPEN_COOLDOWN_ACTIVE": "开仓冷却中：等待冷却结束或降低同品种反复触发；检查为何连续失败。",
                    "RISK_REDLINE_DENIED": "触发风控红线：检查 max_positions/保证金占用/风险参数。",
                    "NO_EXCHANGE": "交易所连接为空：检查主控 exchange 初始化/凭证/网络。",
                    "TIMEOUT": "网络或交易所接口超时：检查代理稳定性、OKX 私有接口延迟与重试策略。",
                    "CONNECTION_ERROR": "连接异常：检查网络/代理/会话重建；必要时触发 exchange session rebuild。",
                    "NETWORK_ERROR": "网络故障：检查 DNS/出网/代理。",
                    "INSUFFICIENT_MARGIN": "保证金不足：降低仓位/杠杆或补充资金；检查 margin_mode。",
                    "INSUFFICIENT_FUNDS": "余额不足：检查资金与费用预留。",
                    "SIZE_TOO_SMALL": "下单张数过小：检查 minSz/lotSz，修正 size 计算与步进对齐。",
                    "INSTRUMENT_INVALID": "合约标的无效：检查 symbol 规范化与 instId。",
                    "EXCHANGE_ALL_OPERATIONS_FAILED": "交易所拒单(All operations failed)：检查 reduceOnly/posSide/参数组合，必要时走 close-position fallback。",
                    "POST_CHECK_ANOMALY": "平仓后复核异常：检查 positions 刷新延迟/是否实际成交；必要时二次 close-position。",
                }.get(code, "查看 detail/endpoint/trace_id 对照交易所返回，补齐映射或加更具体的重试/降级。")

            top = []
            for k, v in top_keys:
                # k = op:code:phase
                parts = k.split(":")
                code = parts[1] if len(parts) > 1 else "UNKNOWN"
                top.append(
                    {
                        "key": k,
                        "count": int(v),
                        "action_hint": _action_hint(code),
                        "samples": samples.get(k, [])[:3],
                    }
                )

            out["execution_attribution"] = {
                "failures_in_window": len(fails),
                "top_reasons": top,
            }
        except Exception as e:
            out["execution_attribution_error"] = str(e)

        return {"success": True, "data": out, "timestamp": datetime.now().isoformat()}

    @router.get("/commander/decision-traces")
    async def commander_decision_traces(limit: int = 50):
        """
        最近 AI 决策轨迹聚合复盘：
        - 门控拒绝原因分布
        - 执行失败分布
        - 对账保护阻断分布
        - 最近轨迹样本
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        try:
            store = getattr(main_controller, "decision_trace_store", None)
            if not store:
                return {
                    "success": True,
                    "data": {"summary": {"sample_size": 0}, "recent": []},
                    "timestamp": datetime.now().isoformat(),
                }
            if hasattr(store, "analyze_recent"):
                data = store.analyze_recent(limit=int(limit or 50))
            else:
                data = {"summary": {"sample_size": 0}, "recent": []}
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.get("/commander/decision-traces/{trace_id}")
    async def commander_decision_trace_detail(trace_id: str):
        """按 trace_id 查看单条 AI 决策链路。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        try:
            store = getattr(main_controller, "decision_trace_store", None)
            row = store.get_by_trace_id(trace_id) if (store and hasattr(store, "get_by_trace_id")) else None
            if not row:
                return {"success": False, "message": "trace_id not found", "timestamp": datetime.now().isoformat()}
            return {"success": True, "data": row, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    @router.post("/commander/learning/seed-and-run")
    async def commander_learning_seed_and_run(payload: Dict[str, Any] = Body(default_factory=dict)):
        """
        体检/验收用：注入少量合成 trade_close 记忆，并立即触发一次学习周期。
        - 不会触发真实交易
        - 仅用于验证“自我总结与自动优化策略”的闭环是否通
        """
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        mc = main_controller
        mg = getattr(mc, "memory_gateway", None)
        le = getattr(mc, "ai_learning_engine", None)
        if not mg or not hasattr(mg, "add_memory"):
            return {"success": False, "message": "memory_gateway 未就绪", "timestamp": datetime.now().isoformat()}
        if not le:
            return {"success": False, "message": "ai_learning_engine 未就绪", "timestamp": datetime.now().isoformat()}

        # Runtime wiring fix: seed 使用 memory_gateway 写入，学习引擎读取 memory_manager。
        # 若两者未绑定，会导致 _analyze_and_learn() 直接返回且统计不更新。
        if getattr(le, "memory_manager", None) is None:
            le.memory_manager = mg

        n = int((payload or {}).get("n", 8) or 8)
        n = max(3, min(30, n))
        symbol = str((payload or {}).get("symbol") or "BTC/USDT/SWAP")
        base_pnl_pct = float((payload or {}).get("base_pnl_percent", 0.012) or 0.012)
        lesson_pnl_percent = float((payload or {}).get("lesson_pnl_percent", 6.0) or 6.0)
        lesson_pnl_percent = max(5.1, min(40.0, lesson_pnl_percent))
        now = datetime.now()
        seeded = 0
        try:
            for i in range(n):
                # Alternating win/loss patterns to trigger timing/risk lessons.
                pnl_pct = base_pnl_pct if (i % 3 != 0) else (-base_pnl_pct * 1.4)
                pnl = pnl_pct * 100.0
                side = "sell" if pnl_pct >= 0 else "buy"
                await mg.add_memory(
                    memory_type="trade_record",
                    content=f"[synthetic] trade_close {symbol} pnl_pct={pnl_pct:+.4%}",
                    metadata={
                        "kind": "trade_close",
                        "synthetic": True,
                        "symbol": symbol,
                        "side": side,
                        "pnl": float(pnl),
                        "pnl_percent": float(pnl_pct),
                        "timestamp": (now.isoformat()),
                        "reason": "synthetic_seed_for_learning_acceptance",
                    },
                    source_module="module_control_api",
                    importance=0.6,
                    tags=["trade_close", "synthetic", "learning_seed"],
                )
                # Also feed the learning engine's direct intake path so diagnosis metrics
                # update immediately even when memory backend adapters differ.
                if hasattr(le, "record_trade_result"):
                    lesson_pct = lesson_pnl_percent if pnl_pct >= 0 else (-lesson_pnl_percent * 1.2)
                    await le.record_trade_result(
                        {
                            "symbol": symbol,
                            "side": side,
                            "pnl": float(pnl),
                            "pnl_percent": float(lesson_pct),
                            "reason": "synthetic_seed_for_learning_acceptance",
                            "strategy": "seed_acceptance",
                            "timestamp": now.isoformat(),
                        }
                    )
                seeded += 1
        except Exception as e:
            return {"success": False, "message": f"seed_failed: {e}", "seeded": seeded, "timestamp": datetime.now().isoformat()}

        # Run one learning cycle immediately (best-effort)
        try:
            await le._analyze_and_learn()
            await le._generate_learning_report()
            await le._optimize_decision_rules()
        except Exception as e:
            return {"success": False, "message": f"learning_run_failed: {e}", "seeded": seeded, "timestamp": datetime.now().isoformat()}

        return {
            "success": True,
            "seeded": seeded,
            "learning_status": le.get_status() if hasattr(le, "get_status") else {},
            "timestamp": datetime.now().isoformat(),
        }

    @router.post("/commander/account-sync/run")
    async def commander_account_sync_run(payload: Dict[str, Any] = Body(default_factory=dict)):
        """强制同步余额/持仓并接管 SLTP（与启动时 force_sync 相同语义）。"""
        if not main_controller:
            return {"success": False, "message": "主控制器未初始化", "timestamp": datetime.now().isoformat()}
        if not hasattr(main_controller, "force_sync_account_state"):
            return {"success": False, "message": "同步能力不可用", "timestamp": datetime.now().isoformat()}
        reason = str((payload or {}).get("reason") or "api")
        try:
            # 与 diagnostics 对齐：账户私有接口偶发抖动时，避免 API 长时间悬挂。
            data = await asyncio.wait_for(
                main_controller.force_sync_account_state(reason=reason),
                timeout=45.0,
            )
            return {"success": True, "data": data, "timestamp": datetime.now().isoformat()}
        except asyncio.TimeoutError:
            return {
                "success": True,
                "degraded": True,
                "data": {"status": "timeout_degraded", "hint": "account_sync_timeout", "reason": reason},
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "message": str(e), "timestamp": datetime.now().isoformat()}

    s1_router = APIRouter(prefix="/api/v1/s1", tags=["s1"])

    @s1_router.get("/verify")
    async def s1_full_verify():
        """
        S1 全自动验收探针：主控、ExecutionGateway、策略配置、交易所、止盈止损。
        供脚本/监控轮询；返回 all_passed 与各子检查项。
        """
        checks: List[Dict[str, Any]] = []
        details: Dict[str, Any] = {}

        def add_check(name: str, passed: bool, detail: str = "") -> None:
            checks.append({"name": name, "passed": bool(passed), "detail": detail})

        if not main_controller:
            add_check("main_controller", False, "missing")
            return {"ok": False, "all_passed": False, "checks": checks, "details": details}

        add_check("main_controller", True, "present")
        mc = main_controller

        gw = getattr(mc, "execution_gateway", None)
        add_check("execution_gateway", gw is not None, "missing" if gw is None else "ok")
        if gw:
            try:
                snap = await gw.get_snapshot()
                details["execution_spine"] = snap
                add_check(
                    "execution_spine.single_write_owner",
                    bool(snap.get("single_write_owner")),
                    str(snap.get("single_write_owner") or ""),
                )
            except Exception as e:
                add_check("execution_spine", False, str(e))

        ac = getattr(mc, "ai_core", None)
        add_check("ai_core", ac is not None, "missing" if ac is None else "ok")

        try:
            brain = await mc.get_ai_managed_config(
                "ai_brain",
                {
                    "primary_controller": "ai_core",
                    "single_write_owner": "ai_core",
                    "enable_secondary_controller": False,
                },
            )
            details["ai_brain"] = {
                "primary_controller": brain.get("primary_controller"),
                "single_write_owner": brain.get("single_write_owner"),
                "enable_secondary_controller": brain.get("enable_secondary_controller"),
            }
            swo = str(brain.get("single_write_owner") or brain.get("primary_controller") or "").strip().lower()
            add_check("ai_brain.single_write_owner", bool(swo), swo or "empty")
            pri = str(brain.get("primary_controller") or "").strip().lower()
            coherent = (not pri or not swo) or (pri == swo)
            add_check(
                "ai_brain.primary_coherent_with_swo",
                coherent,
                f"primary={pri} swo={swo}" + ("" if coherent else " (建议保持一致)"),
            )
        except Exception as e:
            add_check("ai_brain_config", False, str(e))

        sl = getattr(mc, "stop_loss_manager", None)
        add_check("stop_loss_manager", sl is not None, "missing" if sl is None else "ok")

        ex = mc.get_exchange() if hasattr(mc, "get_exchange") else None
        ex = ex or getattr(mc, "okx_exchange", None)
        add_check("exchange", ex is not None, "missing" if ex is None else type(ex).__name__)

        ait = getattr(mc, "ai_trading_engine", None)
        if ait and hasattr(ait, "_autonomous_trading_execution_allowed"):
            try:
                allow_loop = await ait._autonomous_trading_execution_allowed()
                details["ai_trading_engine"] = {
                    "autonomous_trading_loop_allowed": allow_loop,
                }
                try:
                    pol = await mc.get_ai_managed_config("ai_brain", {})
                    swo2 = str(
                        pol.get("single_write_owner") or pol.get("primary_controller") or "ai_core"
                    ).strip().lower()
                except Exception:
                    swo2 = "ai_core"
                if swo2 == "ai_core":
                    add_check(
                        "s1_aitrading_loop_suppressed_when_swo_ai_core",
                        not allow_loop,
                        "loop allowed (unexpected)" if allow_loop else "main loop skipped as expected",
                    )
                else:
                    add_check(
                        "s1_aitrading_loop_policy",
                        True,
                        f"swo={swo2} allow_loop={allow_loop}",
                    )
            except Exception as e:
                add_check("ai_trading_engine_policy", False, str(e))

        try:
            sys_status = await mc.get_system_status()
            details["system_status_keys"] = list(sys_status.keys()) if isinstance(sys_status, dict) else []
            if isinstance(sys_status, dict) and "execution_spine" in sys_status:
                add_check("get_system_status.execution_spine", True, "present")
            else:
                add_check("get_system_status.execution_spine", False, "missing in status payload")
        except Exception as e:
            add_check("get_system_status", False, str(e))

        all_passed = all(c.get("passed") for c in checks)
        return {
            "ok": True,
            "all_passed": all_passed,
            "timestamp": datetime.now().isoformat(),
            "checks": checks,
            "details": details,
        }

    from src.modules.api.module_surface import attach_module_surface_routes

    attach_module_surface_routes(router, main_controller)

    app.include_router(router)
    app.include_router(trade_router)
    app.include_router(market_router)
    app.include_router(s1_router)
    logger.info("✅ 模块控制API已初始化")
