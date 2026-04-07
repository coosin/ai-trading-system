"""
日志审计追踪系统

功能：
1. 完整的操作日志记录
2. 敏感操作审计
3. 日志查询和分析
4. 合规性报告生成
"""

import asyncio
import logging
import json
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    """审计事件类型"""
    TRADE_OPEN = "trade_open"
    TRADE_CLOSE = "trade_close"
    ORDER_CREATE = "order_create"
    ORDER_CANCEL = "order_cancel"
    POSITION_UPDATE = "position_update"
    RISK_ALERT = "risk_alert"
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"
    CONFIG_CHANGE = "config_change"
    STRATEGY_LOAD = "strategy_load"
    STRATEGY_UNLOAD = "strategy_unload"
    API_CALL = "api_call"
    ERROR = "error"
    SECURITY = "security"


class AuditSeverity(Enum):
    """审计严重程度"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """审计事件"""
    event_id: str
    event_type: AuditEventType
    severity: AuditSeverity
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = ""
    action: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    ip_address: Optional[str] = None
    result: str = "success"
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "action": self.action,
            "details": self.details,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "ip_address": self.ip_address,
            "result": self.result,
            "error_message": self.error_message
        }


@dataclass
class AuditConfig:
    """审计配置"""
    log_dir: str = "logs/audit"
    max_file_size: int = 10 * 1024 * 1024
    max_files: int = 100
    retention_days: int = 90
    enable_encryption: bool = False
    sensitive_fields: List[str] = field(default_factory=lambda: [
        "api_key", "secret", "password", "token", "private_key"
    ])


class AuditLogger:
    """审计日志记录器"""

    @staticmethod
    def _resolve_writable_log_dir(preferred: Path) -> Path:
        """宿主机上 logs/audit 可能权限异常；选用首个可写目录。"""
        for d in (preferred, Path("data/audit"), Path("/tmp/openclaw_audit")):
            try:
                d.mkdir(parents=True, exist_ok=True)
                probe = d / ".audit_write_probe"
                probe.write_bytes(b"")
                probe.unlink()
                if d.resolve() != preferred.resolve():
                    logger.warning("审计目录 %s 不可写，已改用: %s", preferred, d)
                return d
            except OSError:
                continue
        return preferred
    
    def __init__(self, config: Optional[AuditConfig] = None):
        self.config = config or AuditConfig()
        self.log_dir = self._resolve_writable_log_dir(Path(self.config.log_dir))
        
        self.events: List[AuditEvent] = []
        self.event_index: Dict[str, List[str]] = {}
        
        self._current_file: Optional[Path] = None
        self._current_size: int = 0
        self._file_handle: Optional[Any] = None
        
        self._callbacks: List[callable] = []
    
    async def initialize(self) -> bool:
        """初始化审计日志记录器"""
        logger.info("审计日志记录器初始化...")
        
        await self._rotate_file()
        
        return True
    
    async def log_event(
        self,
        event_type: AuditEventType,
        severity: AuditSeverity,
        action: str,
        details: Optional[Dict[str, Any]] = None,
        source: str = "system",
        result: str = "success",
        error_message: Optional[str] = None
    ) -> str:
        """记录审计事件"""
        event_id = self._generate_event_id()
        
        details = self._sanitize_details(details or {})
        
        event = AuditEvent(
            event_id=event_id,
            event_type=event_type,
            severity=severity,
            source=source,
            action=action,
            details=details,
            result=result,
            error_message=error_message
        )
        
        self.events.append(event)
        
        if event_type.value not in self.event_index:
            self.event_index[event_type.value] = []
        self.event_index[event_type.value].append(event_id)
        
        await self._write_event(event)
        
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logger.error(f"审计事件回调失败: {e}")
        
        return event_id
    
    async def log_trade(
        self,
        action: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        order_id: Optional[str] = None,
        result: str = "success"
    ) -> str:
        """记录交易事件"""
        event_type = AuditEventType.TRADE_OPEN if "open" in action.lower() else AuditEventType.TRADE_CLOSE
        
        return await self.log_event(
            event_type=event_type,
            severity=AuditSeverity.INFO,
            action=action,
            details={
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
                "order_id": order_id
            },
            source="trading_engine",
            result=result
        )
    
    async def log_risk_alert(
        self,
        alert_type: str,
        message: str,
        details: Dict[str, Any],
        severity: AuditSeverity = AuditSeverity.WARNING
    ) -> str:
        """记录风险预警"""
        return await self.log_event(
            event_type=AuditEventType.RISK_ALERT,
            severity=severity,
            action=alert_type,
            details={"message": message, **details},
            source="risk_manager"
        )
    
    async def log_config_change(
        self,
        config_key: str,
        old_value: Any,
        new_value: Any,
        source: str = "system"
    ) -> str:
        """记录配置变更"""
        return await self.log_event(
            event_type=AuditEventType.CONFIG_CHANGE,
            severity=AuditSeverity.WARNING,
            action="config_update",
            details={
                "config_key": config_key,
                "old_value": str(old_value)[:100],
                "new_value": str(new_value)[:100]
            },
            source=source
        )
    
    async def log_error(
        self,
        error_type: str,
        message: str,
        stack_trace: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> str:
        """记录错误事件"""
        return await self.log_event(
            event_type=AuditEventType.ERROR,
            severity=AuditSeverity.ERROR,
            action=error_type,
            details={
                "message": message,
                "stack_trace": stack_trace[:500] if stack_trace else None,
                **(details or {})
            },
            result="error",
            error_message=message
        )
    
    async def query_events(
        self,
        event_type: Optional[AuditEventType] = None,
        severity: Optional[AuditSeverity] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        source: Optional[str] = None,
        limit: int = 100
    ) -> List[AuditEvent]:
        """查询审计事件"""
        results = []
        
        for event in reversed(self.events):
            if event_type and event.event_type != event_type:
                continue
            if severity and event.severity != severity:
                continue
            if start_time and event.timestamp < start_time:
                continue
            if end_time and event.timestamp > end_time:
                continue
            if source and event.source != source:
                continue
            
            results.append(event)
            
            if len(results) >= limit:
                break
        
        return results
    
    async def generate_report(
        self,
        start_time: datetime,
        end_time: datetime,
        report_type: str = "summary"
    ) -> Dict[str, Any]:
        """生成审计报告"""
        events = await self.query_events(start_time=start_time, end_time=end_time, limit=10000)
        
        report = {
            "report_type": report_type,
            "period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            },
            "generated_at": datetime.now().isoformat(),
            "total_events": len(events),
            "event_summary": {},
            "severity_summary": {},
            "top_sources": {},
            "errors": [],
            "risk_alerts": []
        }
        
        for event in events:
            et = event.event_type.value
            report["event_summary"][et] = report["event_summary"].get(et, 0) + 1
            
            sv = event.severity.value
            report["severity_summary"][sv] = report["severity_summary"].get(sv, 0) + 1
            
            src = event.source
            report["top_sources"][src] = report["top_sources"].get(src, 0) + 1
            
            if event.event_type == AuditEventType.ERROR:
                report["errors"].append({
                    "timestamp": event.timestamp.isoformat(),
                    "action": event.action,
                    "message": event.error_message
                })
            
            if event.event_type == AuditEventType.RISK_ALERT:
                report["risk_alerts"].append({
                    "timestamp": event.timestamp.isoformat(),
                    "action": event.action,
                    "details": event.details
                })
        
        report["errors"] = report["errors"][-20:]
        report["risk_alerts"] = report["risk_alerts"][-20:]
        
        return report
    
    async def cleanup_old_logs(self):
        """清理过期日志"""
        cutoff = datetime.now() - timedelta(days=self.config.retention_days)
        
        deleted_count = 0
        for log_file in self.log_dir.glob("audit_*.jsonl"):
            try:
                file_date_str = log_file.stem.split("_")[1]
                file_date = datetime.strptime(file_date_str, "%Y%m%d")
                
                if file_date < cutoff:
                    log_file.unlink()
                    deleted_count += 1
            except Exception:
                continue
        
        if deleted_count > 0:
            logger.info(f"清理过期日志文件: {deleted_count} 个")
    
    def _generate_event_id(self) -> str:
        """生成事件ID"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        random_part = hashlib.md5(str(timestamp).encode()).hexdigest()[:8]
        return f"audit_{timestamp}_{random_part}"
    
    def _sanitize_details(self, details: Dict[str, Any]) -> Dict[str, Any]:
        """清理敏感信息"""
        sanitized = {}
        
        for key, value in details.items():
            if key.lower() in self.config.sensitive_fields:
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_details(value)
            else:
                sanitized[key] = value
        
        return sanitized
    
    async def _write_event(self, event: AuditEvent):
        """写入事件到文件"""
        try:
            if self._current_size > self.config.max_file_size:
                await self._rotate_file()
            
            line = json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
            
            if self._file_handle:
                self._file_handle.write(line)
                self._file_handle.flush()
            
            self._current_size += len(line.encode())
            
        except Exception as e:
            logger.error(f"写入审计日志失败: {e}")
    
    async def _rotate_file(self):
        """轮转日志文件"""
        if self._file_handle:
            self._file_handle.close()
        
        today = datetime.now().strftime("%Y%m%d")
        self._current_file = self.log_dir / f"audit_{today}.jsonl"
        
        self._file_handle = open(self._current_file, "a", encoding="utf-8")
        self._current_size = self._current_file.stat().st_size if self._current_file.exists() else 0
    
    def register_callback(self, callback: callable):
        """注册事件回调"""
        self._callbacks.append(callback)
    
    async def cleanup(self):
        """清理资源"""
        if self._file_handle:
            self._file_handle.close()
        
        await self.cleanup_old_logs()
        
        logger.info("审计日志记录器清理完成")
