"""
系统维护技能 - AI自主维护系统稳定性

核心能力：
1. 系统健康监控 - 实时监控系统各项指标
2. 异常检测与诊断 - 智能识别系统异常
3. 自动修复 - 自动修复常见问题
4. 预防性维护 - 预测并防止问题发生
5. 决策支持 - 为AI提供维护决策建议
"""

import asyncio
import logging
import psutil
import shutil
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum

from .skill_base import SkillBase, SkillResult, SkillPriority, SkillStatus

logger = logging.getLogger(__name__)


class HealthLevel(Enum):
    """健康等级"""
    EXCELLENT = "excellent"      # 优秀 - 系统运行完美
    GOOD = "good"               # 良好 - 系统正常运行
    WARNING = "warning"         # 警告 - 需要关注
    CRITICAL = "critical"       # 严重 - 需要立即处理
    EMERGENCY = "emergency"     # 紧急 - 系统可能崩溃


class MaintenanceAction(Enum):
    """维护动作"""
    NONE = "none"                      # 无需操作
    CLEAR_CACHE = "clear_cache"        # 清理缓存
    ROTATE_LOGS = "rotate_logs"        # 轮转日志
    CLEAN_TEMP = "clean_temp"          # 清理临时文件
    RESTART_MODULE = "restart_module"  # 重启模块
    ALERT_ADMIN = "alert_admin"        # 警告管理员
    EMERGENCY_STOP = "emergency_stop"  # 紧急停止


@dataclass
class SystemHealth:
    """系统健康状态"""
    level: HealthLevel
    score: float  # 0-100
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class SystemMaintenanceSkill(SkillBase):
    """
    系统维护技能
    
    赋予AI对系统稳定性的基本维护和判断能力
    """
    
    def __init__(self):
        super().__init__(
            name="system_maintenance",
            description="AI自主维护系统稳定性，包括健康监控、异常检测、自动修复",
            priority=SkillPriority.CRITICAL
        )
        
        self.auto_fix = True
        self.maintenance_history: List[Dict[str, Any]] = []
        self.health_thresholds = {
            "cpu_warning": 70,
            "cpu_critical": 90,
            "memory_warning": 75,
            "memory_critical": 90,
            "disk_warning": 80,
            "disk_critical": 95,
            "error_rate_warning": 0.05,
            "error_rate_critical": 0.15,
        }
        self._last_health_check: Optional[datetime] = None
        self._consecutive_issues = 0
        
    async def execute(self, context: Dict[str, Any]) -> SkillResult:
        """
        执行系统维护
        
        Args:
            context: 包含main_controller、trading_engine等
            
        Returns:
            SkillResult: 维护结果
        """
        start_time = datetime.now()
        
        health = await self.diagnose(context)
        
        actions_taken = []
        errors_fixed = []
        
        if health.level in [HealthLevel.WARNING, HealthLevel.CRITICAL, HealthLevel.EMERGENCY]:
            if self.auto_fix:
                actions_taken, errors_fixed = await self._perform_maintenance(health, context)
        
        self._last_health_check = datetime.now()
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        return SkillResult(
            skill_name=self.name,
            status=SkillStatus.SUCCESS if health.level in [HealthLevel.EXCELLENT, HealthLevel.GOOD] else SkillStatus.FAILED,
            priority=self.priority,
            message=f"系统健康等级: {health.level.value}, 评分: {health.score:.1f}/100",
            data={
                "health_level": health.level.value,
                "health_score": health.score,
                "issues": health.issues,
                "metrics": health.metrics,
                "actions_taken": actions_taken,
                "errors_fixed": errors_fixed
            },
            recommendations=health.recommendations,
            errors=health.issues if health.issues else None
        )
    
    async def diagnose(self, context: Dict[str, Any]) -> SystemHealth:
        """
        诊断系统健康状态
        
        Args:
            context: 诊断上下文
            
        Returns:
            SystemHealth: 系统健康状态
        """
        issues = []
        recommendations = []
        metrics = {}
        score = 100.0
        
        cpu_metrics = self._check_cpu()
        metrics["cpu"] = cpu_metrics
        if cpu_metrics["usage_percent"] > self.health_thresholds["cpu_critical"]:
            issues.append(f"CPU使用率严重过高: {cpu_metrics['usage_percent']:.1f}%")
            score -= 30
        elif cpu_metrics["usage_percent"] > self.health_thresholds["cpu_warning"]:
            issues.append(f"CPU使用率过高: {cpu_metrics['usage_percent']:.1f}%")
            score -= 15
        
        memory_metrics = self._check_memory()
        metrics["memory"] = memory_metrics
        if memory_metrics["usage_percent"] > self.health_thresholds["memory_critical"]:
            issues.append(f"内存使用率严重过高: {memory_metrics['usage_percent']:.1f}%")
            score -= 25
        elif memory_metrics["usage_percent"] > self.health_thresholds["memory_warning"]:
            issues.append(f"内存使用率过高: {memory_metrics['usage_percent']:.1f}%")
            score -= 12
        
        disk_metrics = self._check_disk()
        metrics["disk"] = disk_metrics
        if disk_metrics["usage_percent"] > self.health_thresholds["disk_critical"]:
            issues.append(f"磁盘空间严重不足: {disk_metrics['usage_percent']:.1f}%")
            score -= 25
        elif disk_metrics["usage_percent"] > self.health_thresholds["disk_warning"]:
            issues.append(f"磁盘空间不足: {disk_metrics['usage_percent']:.1f}%")
            score -= 10
        
        module_metrics = await self._check_modules(context)
        metrics["modules"] = module_metrics
        if module_metrics["error_count"] > 0:
            issues.append(f"模块错误数: {module_metrics['error_count']}")
            score -= module_metrics["error_count"] * 5
        
        connection_metrics = await self._check_connections(context)
        metrics["connections"] = connection_metrics
        if not connection_metrics["exchange_connected"]:
            issues.append("交易所连接断开")
            score -= 20
        if not connection_metrics["telegram_connected"]:
            issues.append("Telegram连接断开")
            score -= 5
        
        log_metrics = self._check_logs()
        metrics["logs"] = log_metrics
        if log_metrics["error_count_24h"] > 100:
            issues.append(f"24小时内错误日志过多: {log_metrics['error_count_24h']}")
            score -= 10
        
        score = max(0, min(100, score))
        
        if score >= 90:
            level = HealthLevel.EXCELLENT
        elif score >= 75:
            level = HealthLevel.GOOD
        elif score >= 50:
            level = HealthLevel.WARNING
        elif score >= 25:
            level = HealthLevel.CRITICAL
        else:
            level = HealthLevel.EMERGENCY
        
        if level == HealthLevel.WARNING:
            recommendations.append("建议执行预防性维护")
        elif level == HealthLevel.CRITICAL:
            recommendations.append("需要立即处理系统问题")
        elif level == HealthLevel.EMERGENCY:
            recommendations.append("系统状态紧急，建议暂停交易")
        
        return SystemHealth(
            level=level,
            score=score,
            issues=issues,
            recommendations=recommendations,
            metrics=metrics
        )
    
    def _check_cpu(self) -> Dict[str, Any]:
        """检查CPU状态"""
        return {
            "usage_percent": psutil.cpu_percent(interval=0.5),
            "count": psutil.cpu_count(),
            "load_average": list(psutil.getloadavg()) if hasattr(psutil, 'getloadavg') else [0, 0, 0]
        }
    
    def _check_memory(self) -> Dict[str, Any]:
        """检查内存状态"""
        mem = psutil.virtual_memory()
        return {
            "total_gb": round(mem.total / (1024**3), 2),
            "available_gb": round(mem.available / (1024**3), 2),
            "used_gb": round(mem.used / (1024**3), 2),
            "usage_percent": mem.percent
        }
    
    def _check_disk(self) -> Dict[str, Any]:
        """检查磁盘状态"""
        disk = psutil.disk_usage('/')
        return {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
            "usage_percent": disk.percent
        }
    
    async def _check_modules(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """检查模块状态"""
        main_controller = context.get("main_controller")
        
        error_count = 0
        module_count = 0
        running_count = 0
        
        if main_controller:
            modules = getattr(main_controller, 'modules', {})
            module_count = len(modules)
            
            for name, info in modules.items():
                if hasattr(info, 'status'):
                    if hasattr(info.status, 'value'):
                        if 'error' in info.status.value.lower():
                            error_count += 1
                        elif 'running' in info.status.value.lower():
                            running_count += 1
        
        return {
            "total_modules": module_count,
            "running_modules": running_count,
            "error_count": error_count
        }
    
    async def _check_connections(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """检查连接状态"""
        main_controller = context.get("main_controller")
        
        exchange_connected = False
        telegram_connected = False
        
        if main_controller:
            if hasattr(main_controller, 'ai_trading_engine') and main_controller.ai_trading_engine:
                exchange = getattr(main_controller.ai_trading_engine, 'exchange', None)
                exchange_connected = exchange is not None
            
            if hasattr(main_controller, 'telegram_bot') and main_controller.telegram_bot:
                telegram_connected = True
        
        return {
            "exchange_connected": exchange_connected,
            "telegram_connected": telegram_connected
        }
    
    def _check_logs(self) -> Dict[str, Any]:
        """检查日志状态"""
        log_path = Path("/home/cool/.openclaw-trading/logs")
        
        total_size = 0
        file_count = 0
        error_count_24h = 0
        
        if log_path.exists():
            log_files = list(log_path.glob("*.log"))
            file_count = len(log_files)
            total_size = sum(f.stat().st_size for f in log_files if f.is_file())
            
            for log_file in log_files:
                try:
                    if log_file.stat().st_size < 10 * 1024 * 1024:
                        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            error_count_24h += content.lower().count('error')
                except:
                    pass
        
        return {
            "total_size_mb": round(total_size / (1024**2), 2),
            "file_count": file_count,
            "error_count_24h": error_count_24h
        }
    
    async def _perform_maintenance(
        self, 
        health: SystemHealth, 
        context: Dict[str, Any]
    ) -> tuple[List[str], List[str]]:
        """
        执行维护操作
        
        Args:
            health: 系统健康状态
            context: 执行上下文
            
        Returns:
            tuple: (执行的动作, 修复的错误)
        """
        actions_taken = []
        errors_fixed = []
        
        for issue in health.issues:
            action = self._determine_action(issue)
            
            if action == MaintenanceAction.NONE:
                continue
            
            try:
                result = await self._execute_action(action, context)
                
                if result:
                    actions_taken.append(action.value)
                    errors_fixed.append(issue)
                    logger.info(f"✅ 维护动作成功: {action.value} - 修复: {issue}")
                else:
                    logger.warning(f"⚠️ 维护动作失败: {action.value}")
                    
            except Exception as e:
                logger.error(f"❌ 维护动作异常: {action.value} - {e}")
        
        if actions_taken:
            self.maintenance_history.append({
                "timestamp": datetime.now().isoformat(),
                "health_level": health.level.value,
                "actions": actions_taken,
                "fixed": errors_fixed
            })
        
        return actions_taken, errors_fixed
    
    def _determine_action(self, issue: str) -> MaintenanceAction:
        """根据问题确定维护动作"""
        issue_lower = issue.lower()
        
        if "cpu" in issue_lower and "严重" in issue_lower:
            return MaintenanceAction.ALERT_ADMIN
        elif "cpu" in issue_lower:
            return MaintenanceAction.CLEAR_CACHE
        
        if "内存" in issue_lower:
            return MaintenanceAction.CLEAR_CACHE
        
        if "磁盘" in issue_lower:
            return MaintenanceAction.CLEAN_TEMP
        
        if "日志" in issue_lower:
            return MaintenanceAction.ROTATE_LOGS
        
        if "模块" in issue_lower and "错误" in issue_lower:
            return MaintenanceAction.RESTART_MODULE
        
        if "交易所" in issue_lower and "断开" in issue_lower:
            return MaintenanceAction.ALERT_ADMIN
        
        if "紧急" in issue_lower:
            return MaintenanceAction.EMERGENCY_STOP
        
        return MaintenanceAction.NONE
    
    async def _execute_action(self, action: MaintenanceAction, context: Dict[str, Any]) -> bool:
        """执行维护动作"""
        if action == MaintenanceAction.CLEAR_CACHE:
            return await self._clear_cache(context)
        elif action == MaintenanceAction.ROTATE_LOGS:
            return await self._rotate_logs()
        elif action == MaintenanceAction.CLEAN_TEMP:
            return await self._clean_temp_files()
        elif action == MaintenanceAction.RESTART_MODULE:
            return await self._restart_error_modules(context)
        elif action == MaintenanceAction.ALERT_ADMIN:
            return await self._alert_admin(context)
        elif action == MaintenanceAction.EMERGENCY_STOP:
            return await self._emergency_stop(context)
        
        return False
    
    async def _clear_cache(self, context: Dict[str, Any]) -> bool:
        """清理缓存"""
        try:
            main_controller = context.get("main_controller")
            
            cleared = False
            
            if main_controller:
                if hasattr(main_controller, 'cache_manager') and main_controller.cache_manager:
                    if hasattr(main_controller.cache_manager, 'clear'):
                        await main_controller.cache_manager.clear()
                        cleared = True
            
            import gc
            gc.collect()
            
            logger.info("✅ 缓存清理完成")
            return True
            
        except Exception as e:
            logger.error(f"清理缓存失败: {e}")
            return False
    
    async def _rotate_logs(self) -> bool:
        """轮转日志"""
        try:
            log_path = Path("/home/cool/.openclaw-trading/logs")
            if not log_path.exists():
                return False
            
            rotated = 0
            for log_file in log_path.glob("*.log"):
                if log_file.stat().st_size > 10 * 1024 * 1024:
                    archive_name = log_file.with_suffix(f".{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
                    log_file.rename(archive_name)
                    rotated += 1
            
            logger.info(f"✅ 日志轮转完成: {rotated} 个文件")
            return True
            
        except Exception as e:
            logger.error(f"日志轮转失败: {e}")
            return False
    
    async def _clean_temp_files(self) -> bool:
        """清理临时文件"""
        try:
            temp_paths = [
                Path("/home/cool/.openclaw-trading/temp"),
                Path("/home/cool/.openclaw-trading/cache"),
                Path("/tmp")
            ]
            
            cleaned_size = 0
            for temp_path in temp_paths:
                if temp_path.exists():
                    for item in temp_path.iterdir():
                        try:
                            if item.is_file():
                                size = item.stat().st_size
                                item.unlink()
                                cleaned_size += size
                            elif item.is_dir():
                                shutil.rmtree(item)
                        except:
                            pass
            
            logger.info(f"✅ 临时文件清理完成: {cleaned_size / (1024**2):.2f}MB")
            return True
            
        except Exception as e:
            logger.error(f"清理临时文件失败: {e}")
            return False
    
    async def _restart_error_modules(self, context: Dict[str, Any]) -> bool:
        """重启错误模块"""
        try:
            main_controller = context.get("main_controller")
            
            if not main_controller:
                return False
            
            restarted = 0
            modules = getattr(main_controller, 'modules', {})
            
            for name, info in modules.items():
                if hasattr(info, 'status'):
                    status_value = info.status.value if hasattr(info.status, 'value') else str(info.status)
                    if 'error' in status_value.lower():
                        try:
                            await main_controller.restart_module(name)
                            restarted += 1
                        except:
                            pass
            
            logger.info(f"✅ 重启模块完成: {restarted} 个")
            return restarted > 0
            
        except Exception as e:
            logger.error(f"重启模块失败: {e}")
            return False
    
    async def _alert_admin(self, context: Dict[str, Any]) -> bool:
        """警告管理员"""
        try:
            main_controller = context.get("main_controller")
            
            if main_controller and hasattr(main_controller, 'telegram_bot'):
                telegram_bot = main_controller.telegram_bot
                if telegram_bot:
                    await telegram_bot.send_message(
                        "⚠️ 系统维护警告\n\n"
                        "系统检测到需要管理员关注的问题。\n"
                        "请检查系统状态。"
                    )
            
            logger.info("✅ 管理员警告已发送")
            return True
            
        except Exception as e:
            logger.error(f"发送管理员警告失败: {e}")
            return False
    
    async def _emergency_stop(self, context: Dict[str, Any]) -> bool:
        """紧急停止"""
        try:
            main_controller = context.get("main_controller")
            
            if main_controller:
                if hasattr(main_controller, 'emergency_stop') and main_controller.emergency_stop:
                    await main_controller.emergency_stop.trigger_stop("系统维护技能触发紧急停止")
                elif hasattr(main_controller, 'stop_system'):
                    await main_controller.stop_system()
            
            logger.critical("🚨 紧急停止已执行")
            return True
            
        except Exception as e:
            logger.error(f"紧急停止失败: {e}")
            return False
    
    def get_maintenance_stats(self) -> Dict[str, Any]:
        """获取维护统计"""
        if not self.maintenance_history:
            return {
                "total_maintenances": 0,
                "last_maintenance": None
            }
        
        total_actions = sum(len(m["actions"]) for m in self.maintenance_history)
        total_fixed = sum(len(m["fixed"]) for m in self.maintenance_history)
        
        return {
            "total_maintenances": len(self.maintenance_history),
            "total_actions": total_actions,
            "total_fixed": total_fixed,
            "last_maintenance": self.maintenance_history[-1] if self.maintenance_history else None
        }
