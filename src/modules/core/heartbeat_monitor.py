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
        main_controller: Any = None,
        interval: int = 1800,  # 30分钟
        config_manager=None,
    ):
        self.trading_engine = trading_engine
        self.skill_manager = skill_manager
        self.memory_manager = memory_manager
        self.notification_handler = notification_handler
        self.main_controller = main_controller
        self.config_manager = config_manager
        self.interval = interval
        self.market_opportunity_cooldown_sec = 6 * 3600
        # Default off: this notification is often low-value/noisy.
        self.market_opportunity_notice_enabled = False
        
        self._running = False
        self._last_heartbeat: Optional[datetime] = None
        self.heartbeat_count = 0
        self.heartbeat_history: List[Dict[str, Any]] = []

        # Notification dedup at source (in addition to SmartNotificationSystem).
        self._last_notice_at: Dict[str, datetime] = {}
        self._last_trading_diag_sent_day: Optional[str] = None
        self._trading_diag_last_metrics: Dict[str, Any] = {}

        # Trading diagnosis reporting/alerts (defaults can be overridden via config heartbeat.*)
        self.trading_diagnosis_daily_report_enabled: bool = True
        self.trading_diagnosis_daily_report_hour_local: int = 9
        self.trading_diagnosis_daily_report_min_interval_sec: int = 8 * 3600
        self.trading_diagnosis_alerts_enabled: bool = True
        self.trading_diagnosis_alert_cooldown_sec: int = 900
        
        self.tasks = [
            self._check_system_health,
            self._check_positions_risk,
            self._trading_diagnosis_report_and_alerts,
            self._analyze_market_opportunities,
            self._update_memories,
            self._generate_reports,
            self._optimize_system
        ]
        
        logger.info(f"心跳监控器初始化完成，间隔: {interval}秒")

    def _reload_runtime_config(self) -> None:
        """在运行期刷新心跳配置，避免每次改配置都重启。"""
        if not self.config_manager:
            return
        try:
            hb_cfg = self.config_manager.get_config_sync("heartbeat", {}) or {}
            if not isinstance(hb_cfg, dict):
                return
            self.interval = int(hb_cfg.get("interval_sec", self.interval))
            self.market_opportunity_cooldown_sec = int(
                hb_cfg.get("market_opportunity_notice_cooldown_sec", self.market_opportunity_cooldown_sec)
            )
            self.market_opportunity_notice_enabled = bool(
                hb_cfg.get("market_opportunity_notice_enabled", self.market_opportunity_notice_enabled)
            )
            td = hb_cfg.get("trading_diagnosis", {}) if isinstance(hb_cfg.get("trading_diagnosis"), dict) else {}
            if isinstance(td, dict) and td:
                self.trading_diagnosis_daily_report_enabled = bool(
                    td.get("daily_report_enabled", self.trading_diagnosis_daily_report_enabled)
                )
                self.trading_diagnosis_daily_report_hour_local = int(
                    td.get("daily_report_hour_local", self.trading_diagnosis_daily_report_hour_local)
                )
                self.trading_diagnosis_daily_report_min_interval_sec = int(
                    td.get("daily_report_min_interval_sec", self.trading_diagnosis_daily_report_min_interval_sec)
                )
                self.trading_diagnosis_alerts_enabled = bool(
                    td.get("alerts_enabled", self.trading_diagnosis_alerts_enabled)
                )
                self.trading_diagnosis_alert_cooldown_sec = int(
                    td.get("alerts_cooldown_sec", self.trading_diagnosis_alert_cooldown_sec)
                )
        except Exception as e:
            logger.debug(f"刷新心跳配置失败，继续使用当前参数: {e}")

    async def _build_trading_diagnosis(self, limit_events: int = 8) -> Dict[str, Any]:
        """轻量构建 trading diagnosis（与 API commander/trading-diagnosis 同口径，避免翻日志）。"""
        mc = self.main_controller
        out: Dict[str, Any] = {"timestamp": datetime.now().isoformat()}
        if not mc:
            out["error"] = "main_controller_missing"
            return out

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
        try:
            gw = getattr(mc, "execution_gateway", None)
            if gw and hasattr(gw, "get_snapshot"):
                snap = await gw.get_snapshot()
                if hasattr(gw, "get_recent_events"):
                    snap["recent_events"] = await gw.get_recent_events(limit=int(limit_events or 8))
                out["execution_gateway"] = snap
            else:
                out["execution_gateway"] = None
        except Exception as e:
            out["execution_gateway_error"] = str(e)
        try:
            sltp = getattr(mc, "stop_loss_manager", None)
            out["sltp"] = sltp.get_stats() if (sltp and hasattr(sltp, "get_stats")) else None
        except Exception as e:
            out["sltp_error"] = str(e)
        try:
            le = getattr(mc, "ai_learning_engine", None)
            out["ai_learning_engine"] = le.get_status() if (le and hasattr(le, "get_status")) else None
        except Exception as e:
            out["ai_learning_engine_error"] = str(e)
        return out

    async def _trading_diagnosis_report_and_alerts(self, context: Dict[str, Any]) -> None:
        """Telegram 每日诊断摘要 + 异常即时告警（去重/节流）。"""
        if not self.main_controller:
            return
        now = datetime.now()

        diag = await self._build_trading_diagnosis(limit_events=6)
        gw = (diag.get("execution_gateway") or {}) if isinstance(diag.get("execution_gateway"), dict) else {}
        sltp = (diag.get("sltp") or {}) if isinstance(diag.get("sltp"), dict) else {}
        rec = (
            (diag.get("execution_gateway") or {}).get("reconciliation")
            if isinstance(diag.get("execution_gateway"), dict)
            else {}
        )
        if not isinstance(rec, dict):
            rec = {}
        rcp = (
            (diag.get("execution_gateway") or {}).get("reconciliation_protection")
            if isinstance(diag.get("execution_gateway"), dict)
            else {}
        )
        if not isinstance(rcp, dict):
            rcp = {}
        safe_rec = (
            (diag.get("execution_gateway") or {}).get("reconciliation", {}).get("safe_recovery")
            if isinstance(diag.get("execution_gateway"), dict)
            and isinstance((diag.get("execution_gateway") or {}).get("reconciliation"), dict)
            else {}
        )
        if not isinstance(safe_rec, dict):
            safe_rec = {}

        # --- 1) 即时告警：执行失败增量 / SR 分批止盈失败增量 ---
        if self.trading_diagnosis_alerts_enabled:
            try:
                pm = (gw.get("policy_metrics") or {}) if isinstance(gw.get("policy_metrics"), dict) else {}
                cur_open_fail = int(pm.get("open_fail", 0) or 0)
                cur_close_fail = int(pm.get("close_fail", 0) or 0)
                cur_sr_fail = int(sltp.get("sr_partial_tp_failed", 0) or 0)
                recent = (gw.get("recent_events") or []) if isinstance(gw.get("recent_events"), list) else []
                if not isinstance(recent, list):
                    recent = []

                prev = dict(self._trading_diag_last_metrics or {})
                prev_open_fail = int(prev.get("open_fail", cur_open_fail) or 0)
                prev_close_fail = int(prev.get("close_fail", cur_close_fail) or 0)
                prev_sr_fail = int(prev.get("sr_partial_tp_failed", cur_sr_fail) or 0)

                d_open_fail = max(0, cur_open_fail - prev_open_fail)
                d_close_fail = max(0, cur_close_fail - prev_close_fail)
                d_sr_fail = max(0, cur_sr_fail - prev_sr_fail)

                def _cooldown_ok(key: str) -> bool:
                    last = self._last_notice_at.get(key)
                    if not last:
                        return True
                    return (now - last).total_seconds() >= float(self.trading_diagnosis_alert_cooldown_sec or 900)

                if (d_open_fail + d_close_fail) > 0 and _cooldown_ok("trading_diag_exec_fail"):
                    self._last_notice_at["trading_diag_exec_fail"] = now
                    # include top failure reason in the window (low-cardinality)
                    codes: Dict[str, int] = {}
                    for e in recent[-12:]:
                        if not isinstance(e, dict) or e.get("success") is not False:
                            continue
                        code = str(e.get("error_code") or "UNKNOWN")
                        op = str(e.get("op") or "unknown")
                        k = f"{op}:{code}"
                        codes[k] = int(codes.get(k, 0)) + 1
                    top_code = None
                    if codes:
                        top_code = sorted(codes.items(), key=lambda x: x[1], reverse=True)[0][0]
                    await self._send_notification(
                        "🚨 交易执行异常",
                        f"近一轮心跳检测到执行失败增量。\n"
                        f"- open_fail +{d_open_fail} (total={cur_open_fail})\n"
                        f"- close_fail +{d_close_fail} (total={cur_close_fail})\n"
                        + (f"- top_reason {top_code}\n" if top_code else "")
                        + f"建议：查看 /api/v1/modules/commander/trading-diagnosis 的 execution_attribution.top_reasons。",
                        priority="high",
                    )

                rec_summary = rec.get("summary") if isinstance(rec.get("summary"), dict) else {}
                rec_drift_total = int(rec_summary.get("drift_total", 0) or 0)
                if (
                    rec
                    and bool(rec.get("healthy")) is False
                    and rec_drift_total > 0
                    and _cooldown_ok("trading_diag_reconciliation")
                ):
                    self._last_notice_at["trading_diag_reconciliation"] = now
                    await self._send_notification(
                        "⚠️ 交易状态对账异常",
                        f"检测到本地/交易所状态漂移。\n"
                        f"- severity={rec.get('severity')}\n"
                        f"- drift_total={rec_drift_total}\n"
                        f"- stale_open_orders={int(rec_summary.get('stale_open_orders', 0) or 0)}\n"
                        f"建议：查看 /api/v1/modules/commander/trading-diagnosis 的 execution_reconciliation。",
                        priority="high" if str(rec.get("severity")) == "critical" else "medium",
                    )

                symbol_locks = rcp.get("symbol_locks") if isinstance(rcp.get("symbol_locks"), dict) else {}
                if (
                    rcp
                    and (bool(rcp.get("global_lock_active", False)) or len(symbol_locks) > 0)
                    and _cooldown_ok("trading_diag_reconciliation_protection")
                ):
                    self._last_notice_at["trading_diag_reconciliation_protection"] = now
                    await self._send_notification(
                        "🛡️ 对账保护已生效",
                        f"检测到对账保护正在阻断新开仓。\n"
                        f"- global_lock={bool(rcp.get('global_lock_active', False))}\n"
                        f"- symbol_locks={len(symbol_locks)}\n"
                        f"建议：查看 /api/v1/modules/commander/trading-diagnosis 的 execution_reconciliation_protection。",
                        priority="medium",
                    )

                auto_actions = safe_rec.get("automatic_actions_attempted") if isinstance(safe_rec.get("automatic_actions_attempted"), list) else []
                applied_auto = [a for a in auto_actions if isinstance(a, dict) and a.get("status") == "applied"]
                if applied_auto and _cooldown_ok("trading_diag_safe_recovery"):
                    self._last_notice_at["trading_diag_safe_recovery"] = now
                    await self._send_notification(
                        "🧰 安全恢复已执行",
                        "检测到系统已执行保守恢复动作（仅刷新本地状态/施加保护，不直接撤单或强平）。\n"
                        f"- applied_actions={len(applied_auto)}\n"
                        f"建议：查看 /api/v1/modules/commander/trading-diagnosis 的 execution_safe_recovery。",
                        priority="low",
                    )

                # 细粒度告警：某一类失败原因突增（避免只看 open_fail/close_fail 总数）
                try:
                    codes: Dict[str, int] = {}
                    last_samples: Dict[str, str] = {}
                    for e in recent[-12:]:
                        if not isinstance(e, dict) or e.get("success") is not False:
                            continue
                        code = str(e.get("error_code") or "UNKNOWN")
                        op = str(e.get("op") or "unknown")
                        k = f"{op}:{code}"
                        codes[k] = int(codes.get(k, 0)) + 1
                        if k not in last_samples:
                            last_samples[k] = str(e.get("detail") or "")[:180]
                    prev_codes = (prev.get("recent_fail_codes") or {}) if isinstance(prev.get("recent_fail_codes"), dict) else {}
                    spikes = []
                    for k, v in codes.items():
                        pv = int(prev_codes.get(k, 0) or 0)
                        dv = int(v) - pv
                        if dv >= 2:
                            spikes.append((k, dv, v))
                    if spikes:
                        spikes.sort(key=lambda x: x[1], reverse=True)
                        topk, dv, v = spikes[0]
                        alert_key = f"trading_diag_reason_spike:{topk}"
                        if _cooldown_ok(alert_key):
                            self._last_notice_at[alert_key] = now
                            await self._send_notification(
                                "⚠️ 执行失败原因突增",
                                f"检测到失败原因突增：{topk} (+{dv}, window_total={v})\n"
                                f"sample: {last_samples.get(topk,'')}\n"
                                f"建议：查看 /api/v1/modules/commander/trading-diagnosis 的 execution_attribution.top_reasons。",
                                priority="medium",
                            )
                except Exception:
                    pass

                if d_sr_fail > 0 and _cooldown_ok("trading_diag_sr_fail"):
                    self._last_notice_at["trading_diag_sr_fail"] = now
                    await self._send_notification(
                        "⚠️ SR 分批止盈执行失败",
                        f"检测到 SR 分批止盈失败增量 +{d_sr_fail} (total={cur_sr_fail})。\n"
                        f"建议：检查交易所下单权限/最小下单量/网络稳定性；并查看 sltp.sr_recent_events。",
                        priority="medium",
                    )

                self._trading_diag_last_metrics = {
                    "open_fail": cur_open_fail,
                    "close_fail": cur_close_fail,
                    "sr_partial_tp_failed": cur_sr_fail,
                    "recent_fail_codes": codes if isinstance(locals().get("codes"), dict) else {},
                }
            except Exception:
                pass

        # --- 2) 每日固定时间摘要（默认 09:00 本地时间） ---
        if self.trading_diagnosis_daily_report_enabled:
            try:
                day = now.strftime("%Y-%m-%d")
                hour = int(now.hour)
                if hour == int(self.trading_diagnosis_daily_report_hour_local):
                    # ensure min interval even if heartbeat interval is short
                    last = self._last_notice_at.get("trading_diag_daily")
                    if last and (now - last).total_seconds() < float(self.trading_diagnosis_daily_report_min_interval_sec or 28800):
                        return
                    if self._last_trading_diag_sent_day == day:
                        return

                    self._last_notice_at["trading_diag_daily"] = now
                    self._last_trading_diag_sent_day = day

                    hints = []
                    try:
                        core = diag.get("ai_core") or {}
                        guards = (((core.get("execution_guards") or {}).get("stats")) or {}) if isinstance(core, dict) else {}
                        top = sorted([(k, int(v)) for k, v in (guards or {}).items()], key=lambda x: x[1], reverse=True)[:6]
                        if top:
                            hints.append("门控Top: " + ", ".join([f"{k}={v}" for k, v in top]))
                    except Exception:
                        pass
                    try:
                        pm = (gw.get("policy_metrics") or {}) if isinstance(gw.get("policy_metrics"), dict) else {}
                        hints.append(
                            "执行: " + ", ".join([f"{k}={int(pm.get(k,0) or 0)}" for k in ("open_ok","open_fail","close_ok","close_fail")])
                        )
                    except Exception:
                        pass
                    try:
                        if isinstance(sltp, dict):
                            hints.append(
                                "SR: "
                                + ", ".join(
                                    [
                                        f"triggered={int(sltp.get('sr_partial_tp_triggered',0) or 0)}",
                                        f"success={int(sltp.get('sr_partial_tp_success',0) or 0)}",
                                        f"failed={int(sltp.get('sr_partial_tp_failed',0) or 0)}",
                                        f"breakeven_lock={int(sltp.get('sr_breakeven_lock_applied',0) or 0)}",
                                    ]
                                )
                            )
                    except Exception:
                        pass

                    body = "（trading-diagnosis 日报摘要）\n" + ("\n".join([f"- {x}" for x in hints]) if hints else "- 暂无关键指标")
                    await self._send_notification("📌 交易系统诊断日报", body, priority="medium")
            except Exception:
                pass
    
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
        self._reload_runtime_config()
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

        actionable_failures = int(health_report.get("actionable_failures", 0) or 0)
        critical_issues = int(health_report.get("critical_issues", 0) or 0)
        status = str(health_report.get("status", "healthy")).lower()

        # 仅当关键失败达到明显阈值时再发严重告警，避免单点诊断误报为“严重问题”。
        if status == "critical" and critical_issues > 0 and actionable_failures >= 3:
            await self._send_notification(
                "🚨 系统健康检查",
                f"发现严重问题！\n{health_report['summary']}",
                priority="high"
            )
        elif status == "warning" or actionable_failures > 0:
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
        if not self.market_opportunity_notice_enabled:
            return
        logger.info("📈 分析市场机会...")
        
        trading_engine = context.get("trading_engine")
        if not trading_engine:
            return
        
        positions = getattr(trading_engine, 'positions', {})
        
        if len(positions) < 3:
            # Avoid spamming the same low-priority hint every heartbeat.
            now = datetime.now()
            last = self._last_notice_at.get("market_opportunity")
            if last and (now - last).total_seconds() < self.market_opportunity_cooldown_sec:
                return
            self._last_notice_at["market_opportunity"] = now
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
