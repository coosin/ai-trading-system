"""
系统自检技能 - 诊断系统健康状态
"""

import psutil
import logging
from typing import Dict, Any, List
from pathlib import Path
from datetime import datetime
from .skill_base import SkillBase, SkillResult, SkillPriority, SkillStatus

logger = logging.getLogger(__name__)


class SystemDiagnosisSkill(SkillBase):
    """系统自检技能"""
    
    def __init__(self):
        super().__init__(
            name="system_diagnosis",
            description="诊断系统健康状态，包括CPU、内存、磁盘、网络等",
            priority=SkillPriority.CRITICAL
        )
    
    async def execute(self, context: Dict[str, Any]) -> SkillResult:
        """执行系统诊断"""
        diagnosis = await self.diagnose(context)
        
        issues = []
        recommendations = []
        
        if diagnosis["cpu"]["usage_percent"] > 80:
            issues.append(f"CPU使用率过高: {diagnosis['cpu']['usage_percent']:.1f}%")
            recommendations.append("考虑优化算法或增加计算资源")
        
        if diagnosis["memory"]["usage_percent"] > 85:
            issues.append(f"内存使用率过高: {diagnosis['memory']['usage_percent']:.1f}%")
            recommendations.append("检查内存泄漏或增加内存")
        
        if diagnosis["disk"]["usage_percent"] > 90:
            issues.append(f"磁盘使用率过高: {diagnosis['disk']['usage_percent']:.1f}%")
            recommendations.append("清理日志文件或扩展存储")
        
        if not diagnosis["network"]["connected"]:
            issues.append("网络连接异常")
            recommendations.append("检查网络配置和代理设置")
        
        if diagnosis["processes"]["trading_system"] == 0:
            issues.append("交易系统进程未运行")
            recommendations.append("检查系统服务状态")
        
        status = SkillStatus.SUCCESS if not issues else SkillStatus.FAILED
        message = "系统健康" if not issues else f"发现 {len(issues)} 个问题"
        
        return SkillResult(
            skill_name=self.name,
            status=status,
            priority=self.priority,
            message=message,
            data=diagnosis,
            recommendations=recommendations,
            errors=issues
        )
    
    async def diagnose(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """诊断系统状态"""
        diagnosis = {
            "timestamp": datetime.now().isoformat(),
            "cpu": self._check_cpu(),
            "memory": self._check_memory(),
            "disk": self._check_disk(),
            "network": self._check_network(),
            "processes": self._check_processes(),
            "logs": self._check_logs()
        }
        
        return diagnosis
    
    def _check_cpu(self) -> Dict[str, Any]:
        """检查CPU状态"""
        return {
            "usage_percent": psutil.cpu_percent(interval=1),
            "count": psutil.cpu_count(),
            "load_average": psutil.getloadavg() if hasattr(psutil, 'getloadavg') else (0, 0, 0)
        }
    
    def _check_memory(self) -> Dict[str, Any]:
        """检查内存状态"""
        mem = psutil.virtual_memory()
        return {
            "total_gb": mem.total / (1024**3),
            "available_gb": mem.available / (1024**3),
            "used_gb": mem.used / (1024**3),
            "usage_percent": mem.percent
        }
    
    def _check_disk(self) -> Dict[str, Any]:
        """检查磁盘状态"""
        disk = psutil.disk_usage('/')
        return {
            "total_gb": disk.total / (1024**3),
            "used_gb": disk.used / (1024**3),
            "free_gb": disk.free / (1024**3),
            "usage_percent": disk.percent
        }
    
    def _check_network(self) -> Dict[str, Any]:
        """检查网络状态"""
        try:
            import socket
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            connected = True
        except:
            connected = False
        
        return {
            "connected": connected,
            "interfaces": len(psutil.net_if_addrs())
        }
    
    def _check_processes(self) -> Dict[str, Any]:
        """检查进程状态"""
        trading_processes = 0
        for proc in psutil.process_iter(['name', 'cmdline']):
            try:
                if 'python' in proc.info['name'].lower():
                    if proc.info['cmdline'] and any('src.main' in cmd for cmd in proc.info['cmdline']):
                        trading_processes += 1
            except:
                pass
        
        return {
            "total": len(psutil.pids()),
            "trading_system": trading_processes
        }
    
    def _check_logs(self) -> Dict[str, Any]:
        """检查日志状态"""
        log_path = Path("/home/cool/.openclaw-trading/logs")
        if not log_path.exists():
            return {"exists": False, "size_mb": 0}
        
        total_size = sum(f.stat().st_size for f in log_path.glob("*.log") if f.is_file())
        
        return {
            "exists": True,
            "size_mb": total_size / (1024**2),
            "files": len(list(log_path.glob("*.log")))
        }
