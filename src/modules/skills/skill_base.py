"""
技能基础框架 - 定义技能的基本接口和结构
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class SkillPriority(Enum):
    """技能优先级"""
    CRITICAL = "critical"      # 关键 - 立即执行
    HIGH = "high"             # 高优先级
    MEDIUM = "medium"         # 中优先级
    LOW = "low"               # 低优先级


class SkillStatus(Enum):
    """技能状态"""
    IDLE = "idle"             # 空闲
    RUNNING = "running"       # 运行中
    SUCCESS = "success"       # 成功
    FAILED = "failed"         # 失败
    SKIPPED = "skipped"       # 跳过


@dataclass
class SkillResult:
    """技能执行结果"""
    skill_name: str
    status: SkillStatus
    priority: SkillPriority
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    execution_time: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "skill_name": self.skill_name,
            "status": self.status.value,
            "priority": self.priority.value,
            "message": self.message,
            "data": self.data,
            "recommendations": self.recommendations,
            "errors": self.errors,
            "timestamp": self.timestamp.isoformat(),
            "execution_time": self.execution_time
        }


class SkillBase(ABC):
    """技能基类"""
    
    def __init__(self, name: str, description: str, priority: SkillPriority = SkillPriority.MEDIUM):
        self.name = name
        self.description = description
        self.priority = priority
        self.status = SkillStatus.IDLE
        self.last_run: Optional[datetime] = None
        self.last_result: Optional[SkillResult] = None
        self.enabled = True
        self.auto_fix = False  # 是否自动修复
        
    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> SkillResult:
        """
        执行技能
        
        Args:
            context: 执行上下文，包含系统状态、交易数据等
            
        Returns:
            SkillResult: 执行结果
        """
        pass
    
    @abstractmethod
    async def diagnose(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        诊断问题
        
        Args:
            context: 诊断上下文
            
        Returns:
            Dict: 诊断结果
        """
        pass
    
    async def run(self, context: Dict[str, Any]) -> SkillResult:
        """
        运行技能（包含状态管理和错误处理）
        
        Args:
            context: 执行上下文
            
        Returns:
            SkillResult: 执行结果
        """
        if not self.enabled:
            return SkillResult(
                skill_name=self.name,
                status=SkillStatus.SKIPPED,
                priority=self.priority,
                message=f"技能 {self.name} 已禁用"
            )
        
        self.status = SkillStatus.RUNNING
        start_time = datetime.now()
        
        try:
            logger.info(f"🔧 执行技能: {self.name}")
            result = await self.execute(context)
            
            result.execution_time = (datetime.now() - start_time).total_seconds()
            self.last_run = datetime.now()
            self.last_result = result
            self.status = result.status
            
            logger.info(f"✅ 技能 {self.name} 完成: {result.message}")
            return result
            
        except Exception as e:
            error_msg = f"技能 {self.name} 执行失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            result = SkillResult(
                skill_name=self.name,
                status=SkillStatus.FAILED,
                priority=self.priority,
                message=error_msg,
                errors=[str(e)]
            )
            result.execution_time = (datetime.now() - start_time).total_seconds()
            
            self.last_run = datetime.now()
            self.last_result = result
            self.status = SkillStatus.FAILED
            
            return result
    
    def enable(self):
        """启用技能"""
        self.enabled = True
        logger.info(f"✅ 技能 {self.name} 已启用")
    
    def disable(self):
        """禁用技能"""
        self.enabled = False
        logger.info(f"⏸️ 技能 {self.name} 已禁用")
    
    def set_auto_fix(self, enabled: bool):
        """设置自动修复"""
        self.auto_fix = enabled
        logger.info(f"🔧 技能 {self.name} 自动修复: {'启用' if enabled else '禁用'}")
    
    def get_info(self) -> Dict[str, Any]:
        """获取技能信息"""
        return {
            "name": self.name,
            "description": self.description,
            "priority": self.priority.value,
            "status": self.status.value,
            "enabled": self.enabled,
            "auto_fix": self.auto_fix,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_result": self.last_result.to_dict() if self.last_result else None
        }
