"""
操作审计日志系统

为无人化AI交易系统提供完整的操作审计和追溯能力
"""

import asyncio
import logging
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class AuditLevel(str, Enum):
    """审计级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AuditType(str, Enum):
    """审计类型"""
    TRADE = "trade"
    DECISION = "decision"
    RISK = "risk"
    SYSTEM = "system"
    SECURITY = "security"
    DATA = "data"
    API = "api"
    CONFIG = "config"


@dataclass
class AuditRecord:
    """审计记录"""
    id: str
    timestamp: datetime
    level: AuditLevel
    type: AuditType
    operation: str
    description: str
    user: str = "AUTOMATED_SYSTEM"
    details: Dict[str, Any] = field(default_factory=dict)
    result: str = "success"
    duration_ms: float = 0.0
    ip_address: str = "localhost"
    user_agent: str = "OpenClaw-Trading-System/1.0"
    checksum: str = ""


class OperationAuditLogger:
    """操作审计日志器"""
    
    def __init__(self, log_dir: str = "logs/audit"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 审计记录
        self.records: List[AuditRecord] = []
        self.max_records = 10000
        
        # 当前会话
        self.session_id = self._generate_session_id()
        
        # 统计
        self.stats = {
            "total_records": 0,
            "by_level": {},
            "by_type": {},
            "failed_operations": 0,
        }
    
    async def log_operation(
        self,
        level: AuditLevel,
        type: AuditType,
        operation: str,
        description: str,
        details: Optional[Dict[str, Any]] = None,
        result: str = "success",
        duration_ms: float = 0.0
    ) -> str:
        """
        记录操作审计
        
        Args:
            level: 审计级别
            type: 审计类型
            operation: 操作名称
            description: 操作描述
            details: 详细信息
            result: 操作结果
            duration_ms: 操作耗时(毫秒)
        
        Returns:
            审计记录ID
        """
        
        import uuid
        
        # 创建审计记录
        record_id = str(uuid.uuid4())
        
        record = AuditRecord(
            id=record_id,
            timestamp=datetime.now(),
            level=level,
            type=type,
            operation=operation,
            description=description,
            details=details or {},
            result=result,
            duration_ms=duration_ms
        )
        
        # 计算校验和
        record.checksum = self._calculate_checksum(record)
        
        # 保存记录
        self.records.append(record)
        self.stats["total_records"] += 1
        
        # 更新统计
        if level.value not in self.stats["by_level"]:
            self.stats["by_level"][level.value] = 0
        self.stats["by_level"][level.value] += 1
        
        if type.value not in self.stats["by_type"]:
            self.stats["by_type"][type.value] = 0
        self.stats["by_type"][type.value] += 1
        
        if result != "success":
            self.stats["failed_operations"] += 1
        
        # 保持记录数量限制
        if len(self.records) > self.max_records:
            # 保存到文件
            await self._save_to_file(self.records[:1000])
            self.records = self.records[1000:]
        
        # 记录日志
        log_msg = f"[{level.value.upper()}] {type.value} - {operation}: {description}"
        if result != "success":
            logger.error(log_msg)
        elif level == AuditLevel.WARNING:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)
        
        return record_id
    
    async def log_trade_operation(
        self,
        operation: str,
        symbol: str,
        action: str,
        quantity: float,
        price: float,
        result: str = "success",
        details: Optional[Dict] = None
    ) -> str:
        """记录交易操作"""
        
        return await self.log_operation(
            level=AuditLevel.INFO,
            type=AuditType.TRADE,
            operation=operation,
            description=f"{action} {quantity} {symbol} @ {price}",
            details={
                "symbol": symbol,
                "action": action,
                "quantity": quantity,
                "price": price,
                **(details or {})
            },
            result=result
        )
    
    async def log_ai_decision(
        self,
        decision_id: str,
        symbol: str,
        action: str,
        confidence: float,
        reasoning: str,
        model_id: str,
        result: str = "success"
    ) -> str:
        """记录AI决策"""
        
        return await self.log_operation(
            level=AuditLevel.INFO,
            type=AuditType.DECISION,
            operation="ai_decision",
            description=f"AI决策: {action} {symbol} (置信度: {confidence:.2f})",
            details={
                "decision_id": decision_id,
                "symbol": symbol,
                "action": action,
                "confidence": confidence,
                "reasoning": reasoning,
                "model_id": model_id
            },
            result=result
        )
    
    async def log_risk_event(
        self,
        event_type: str,
        description: str,
        risk_level: str,
        details: Optional[Dict] = None
    ) -> str:
        """记录风险事件"""
        
        level = AuditLevel.WARNING if risk_level in ["low", "medium"] else AuditLevel.ERROR
        
        return await self.log_operation(
            level=level,
            type=AuditType.RISK,
            operation=event_type,
            description=description,
            details={
                "risk_level": risk_level,
                **(details or {})
            }
        )
    
    async def log_security_event(
        self,
        event_type: str,
        description: str,
        severity: str,
        details: Optional[Dict] = None
    ) -> str:
        """记录安全事件"""
        
        level = AuditLevel.CRITICAL if severity == "high" else AuditLevel.ERROR
        
        return await self.log_operation(
            level=level,
            type=AuditType.SECURITY,
            operation=event_type,
            description=description,
            details={
                "severity": severity,
                **(details or {})
            }
        )
    
    def _calculate_checksum(self, record: AuditRecord) -> str:
        """计算校验和"""
        
        data = f"{record.id}{record.timestamp}{record.operation}{record.description}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    async def _save_to_file(self, records: List[AuditRecord]):
        """保存到文件"""
        
        date_str = datetime.now().strftime("%Y-%m-%d")
        file_path = self.log_dir / f"audit_{date_str}.jsonl"
        
        try:
            with open(file_path, "a", encoding="utf-8") as f:
                for record in records:
                    record_dict = {
                        "id": record.id,
                        "timestamp": record.timestamp.isoformat(),
                        "level": record.level.value,
                        "type": record.type.value,
                        "operation": record.operation,
                        "description": record.description,
                        "user": record.user,
                        "details": record.details,
                        "result": record.result,
                        "duration_ms": record.duration_ms,
                        "checksum": record.checksum
                    }
                    f.write(json.dumps(record_dict, ensure_ascii=False) + "\n")
            
            logger.info(f"审计日志已保存: {file_path}")
            
        except Exception as e:
            logger.error(f"保存审计日志失败: {e}")
    
    def _generate_session_id(self) -> str:
        """生成会话ID"""
        import uuid
        return str(uuid.uuid4())[:8]
    
    async def query_records(
        self,
        level: Optional[AuditLevel] = None,
        type: Optional[AuditType] = None,
        operation: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[AuditRecord]:
        """查询审计记录"""
        
        filtered_records = self.records
        
        if level:
            filtered_records = [r for r in filtered_records if r.level == level]
        
        if type:
            filtered_records = [r for r in filtered_records if r.type == type]
        
        if operation:
            filtered_records = [r for r in filtered_records if r.operation == operation]
        
        if start_time:
            filtered_records = [r for r in filtered_records if r.timestamp >= start_time]
        
        if end_time:
            filtered_records = [r for r in filtered_records if r.timestamp <= end_time]
        
        return filtered_records[:limit]
    
    def get_audit_summary(self) -> Dict[str, Any]:
        """获取审计摘要"""
        
        return {
            "session_id": self.session_id,
            "total_records": self.stats["total_records"],
            "records_in_memory": len(self.records),
            "by_level": self.stats["by_level"],
            "by_type": self.stats["by_type"],
            "failed_operations": self.stats["failed_operations"],
            "last_record_time": self.records[-1].timestamp.isoformat() if self.records else None
        }
