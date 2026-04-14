"""
自动修复技能 - 自动修复常见问题
"""

import logging
import asyncio
import os
from typing import Dict, Any, List
from datetime import datetime
from pathlib import Path
from .skill_base import SkillBase, SkillResult, SkillPriority, SkillStatus

logger = logging.getLogger(__name__)


class AutoRepairSkill(SkillBase):
    """自动修复技能"""
    
    def __init__(self):
        super().__init__(
            name="auto_repair",
            description="自动修复常见系统问题",
            priority=SkillPriority.HIGH
        )
        self.auto_fix = True
        self.repair_history: List[Dict[str, Any]] = []
    
    async def execute(self, context: Dict[str, Any]) -> SkillResult:
        """执行自动修复"""
        # Cache config snapshot for sync helpers
        self._log_path = None
        mc = context.get("main_controller")
        cm = getattr(mc, "config_manager", None) if mc else context.get("config_manager")
        if cm:
            try:
                self._log_path = await cm.get_config("paths", "log_path", None)
            except Exception:
                self._log_path = None

        repairs = await self.diagnose(context)
        
        fixed_issues = []
        failed_repairs = []
        
        for issue in repairs.get("issues", []):
            if issue.get("auto_fixable", False):
                try:
                    result = await self._repair_issue(issue, context)
                    if result:
                        fixed_issues.append(issue["type"])
                    else:
                        failed_repairs.append(issue["type"])
                except Exception as e:
                    logger.error(f"修复失败 {issue['type']}: {e}")
                    failed_repairs.append(issue["type"])
        
        status = SkillStatus.SUCCESS if fixed_issues else SkillStatus.FAILED
        message = f"修复了 {len(fixed_issues)} 个问题"
        
        if failed_repairs:
            message += f", {len(failed_repairs)} 个修复失败"
        
        return SkillResult(
            skill_name=self.name,
            status=status,
            priority=self.priority,
            message=message,
            data={
                "fixed": fixed_issues,
                "failed": failed_repairs,
                "total_issues": len(repairs.get("issues", []))
            },
            errors=failed_repairs
        )
    
    async def diagnose(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """诊断可修复问题"""
        issues = []
        
        issues.extend(self._check_log_files())
        issues.extend(self._check_memory_leaks(context))
        issues.extend(self._check_stale_positions(context))
        issues.extend(self._check_network_issues(context))
        
        return {
            "timestamp": datetime.now().isoformat(),
            "issues": issues
        }
    
    def _check_log_files(self) -> List[Dict[str, Any]]:
        """检查日志文件"""
        issues = []
        log_path = Path(self._log_path or "/app/logs")
        
        if log_path.exists():
            log_files = list(log_path.glob("*.log"))
            total_size = sum(f.stat().st_size for f in log_files) / (1024**2)
            
            if total_size > 100:
                issues.append({
                    "type": "large_log_files",
                    "description": f"日志文件总大小 {total_size:.1f}MB",
                    "auto_fixable": True,
                    "action": "rotate_logs"
                })
        
        return issues
    
    def _check_memory_leaks(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """检查内存泄漏"""
        issues = []
        
        performance_data = context.get("performance_data", {})
        if performance_data.get("memory_usage", 0) > 90:
            issues.append({
                "type": "high_memory_usage",
                "description": "内存使用率过高",
                "auto_fixable": True,
                "action": "clear_cache"
            })
        
        return issues
    
    def _check_stale_positions(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """检查过期持仓"""
        issues = []
        
        trading_engine = context.get("trading_engine")
        if trading_engine:
            positions = getattr(trading_engine, 'positions', {})
            
            for symbol, position in positions.items():
                if isinstance(position, dict):
                    if position.get('quantity', 0) == 0:
                        issues.append({
                            "type": "stale_position",
                            "description": f"{symbol} 持仓数量为0但仍在记录中",
                            "auto_fixable": True,
                            "action": "remove_stale_position",
                            "symbol": symbol
                        })
        
        return issues
    
    def _check_network_issues(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """检查网络问题"""
        issues = []
        
        return issues
    
    async def _repair_issue(self, issue: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """修复问题"""
        action = issue.get("action")
        
        if action == "rotate_logs":
            return await self._rotate_logs()
        elif action == "clear_cache":
            return await self._clear_cache(context)
        elif action == "remove_stale_position":
            return await self._remove_stale_position(issue["symbol"], context)
        
        return False
    
    async def _rotate_logs(self) -> bool:
        """轮转日志"""
        try:
            log_path = Path(self._log_path or "/app/logs")
            if not log_path.exists():
                return False
            
            for log_file in log_path.glob("*.log"):
                if log_file.stat().st_size > 10 * 1024 * 1024:
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    key = hex(abs(hash(log_file.name)))[2:10]
                    archive_name = log_path / f"rot_{ts}_{key}.log"
                    log_file.rename(archive_name)
                    logger.info(f"轮转日志: -> {archive_name.name}")
            
            return True
        except Exception as e:
            logger.error(f"日志轮转失败: {e}")
            return False
    
    async def _clear_cache(self, context: Dict[str, Any]) -> bool:
        """清理缓存"""
        try:
            trading_engine = context.get("trading_engine")
            if trading_engine and hasattr(trading_engine, 'clear_cache'):
                await trading_engine.clear_cache()
                logger.info("清理缓存成功")
                return True
            return False
        except Exception as e:
            logger.error(f"清理缓存失败: {e}")
            return False
    
    async def _remove_stale_position(self, symbol: str, context: Dict[str, Any]) -> bool:
        """移除过期持仓"""
        try:
            trading_engine = context.get("trading_engine")
            if trading_engine and hasattr(trading_engine, 'positions'):
                if symbol in trading_engine.positions:
                    del trading_engine.positions[symbol]
                    logger.info(f"移除过期持仓: {symbol}")
                    return True
            return False
        except Exception as e:
            logger.error(f"移除过期持仓失败: {e}")
            return False
