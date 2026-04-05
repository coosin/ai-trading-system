"""
技能管理器 - 管理和调度所有技能
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from .skill_base import SkillBase, SkillResult, SkillPriority, SkillStatus

logger = logging.getLogger(__name__)


class SkillManager:

    async def initialize(self) -> bool:
        """初始化模块"""
        return True

    """技能管理器"""
    
    def __init__(self):
        self.skills: Dict[str, SkillBase] = {}
        self.execution_history: List[Dict[str, Any]] = []
        self.max_history_size = 100
        
        logger.info("技能管理器初始化完成")
    
    def register_skill(self, skill: SkillBase):
        """注册技能"""
        self.skills[skill.name] = skill
        logger.info(f"📝 注册技能: {skill.name} (优先级: {skill.priority.value})")
    
    def unregister_skill(self, skill_name: str):
        """注销技能"""
        if skill_name in self.skills:
            del self.skills[skill_name]
            logger.info(f"🗑️ 注销技能: {skill_name}")
    
    async def execute_skill(self, skill_name: str, context: Dict[str, Any]) -> Optional[SkillResult]:
        """执行单个技能"""
        skill = self.skills.get(skill_name)
        if not skill:
            logger.warning(f"⚠️ 技能不存在: {skill_name}")
            return None
        
        result = await skill.run(context)
        
        self._add_to_history(result)
        
        return result
    
    async def execute_all_skills(self, context: Dict[str, Any]) -> List[SkillResult]:
        """执行所有启用的技能（按优先级排序）"""
        enabled_skills = [
            skill for skill in self.skills.values() 
            if skill.enabled
        ]
        
        sorted_skills = sorted(
            enabled_skills,
            key=lambda s: (
                s.priority == SkillPriority.CRITICAL,
                s.priority == SkillPriority.HIGH,
                s.priority == SkillPriority.MEDIUM,
                s.priority == SkillPriority.LOW
            ),
            reverse=True
        )
        
        results = []
        for skill in sorted_skills:
            result = await skill.run(context)
            results.append(result)
            self._add_to_history(result)
        
        return results
    
    async def execute_by_priority(
        self, 
        priority: SkillPriority, 
        context: Dict[str, Any]
    ) -> List[SkillResult]:
        """执行指定优先级的技能"""
        skills = [
            skill for skill in self.skills.values()
            if skill.enabled and skill.priority == priority
        ]
        
        results = []
        for skill in skills:
            result = await skill.run(context)
            results.append(result)
            self._add_to_history(result)
        
        return results
    
    async def run_health_check(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """运行健康检查（执行所有诊断技能）"""
        logger.info("🏥 开始系统健康检查...")
        
        results = await self.execute_all_skills(context)
        
        critical_issues = [
            r for r in results 
            if r.status == SkillStatus.FAILED and r.priority == SkillPriority.CRITICAL
        ]
        
        warnings = [
            r for r in results
            if r.status == SkillStatus.SUCCESS and r.priority == SkillPriority.HIGH
            and len(r.recommendations) > 0
        ]
        
        health_status = "healthy"
        if critical_issues:
            health_status = "critical"
        elif warnings:
            health_status = "warning"
        
        report = {
            "status": health_status,
            "timestamp": datetime.now().isoformat(),
            "total_skills": len(self.skills),
            "executed_skills": len(results),
            "critical_issues": len(critical_issues),
            "warnings": len(warnings),
            "results": [r.to_dict() for r in results],
            "summary": self._generate_summary(results)
        }
        
        logger.info(f"✅ 健康检查完成: {health_status}")
        return report
    
    def _generate_summary(self, results: List[SkillResult]) -> str:
        """生成摘要"""
        success_count = sum(1 for r in results if r.status == SkillStatus.SUCCESS)
        failed_count = sum(1 for r in results if r.status == SkillStatus.FAILED)
        skipped_count = sum(1 for r in results if r.status == SkillStatus.SKIPPED)
        
        summary = f"执行了 {len(results)} 个技能: "
        summary += f"✅ {success_count} 成功, "
        summary += f"❌ {failed_count} 失败, "
        summary += f"⏭️ {skipped_count} 跳过"
        
        return summary
    
    def _add_to_history(self, result: SkillResult):
        """添加到执行历史"""
        self.execution_history.append({
            "skill_name": result.skill_name,
            "status": result.status.value,
            "timestamp": result.timestamp.isoformat(),
            "execution_time": result.execution_time
        })
        
        if len(self.execution_history) > self.max_history_size:
            self.execution_history = self.execution_history[-self.max_history_size:]
    
    def get_skill_info(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """获取技能信息"""
        skill = self.skills.get(skill_name)
        return skill.get_info() if skill else None
    
    def get_skill(self, skill_name: str) -> Optional[SkillBase]:
        """获取技能实例"""
        return self.skills.get(skill_name)
    
    def get_all_skills_info(self) -> List[Dict[str, Any]]:
        """获取所有技能信息"""
        return [skill.get_info() for skill in self.skills.values()]
    
    def enable_skill(self, skill_name: str):
        """启用技能"""
        skill = self.skills.get(skill_name)
        if skill:
            skill.enable()
    
    def disable_skill(self, skill_name: str):
        """禁用技能"""
        skill = self.skills.get(skill_name)
        if skill:
            skill.disable()
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """获取执行统计"""
        if not self.execution_history:
            return {
                "total_executions": 0,
                "success_rate": 0,
                "average_execution_time": 0
            }
        
        total = len(self.execution_history)
        success_count = sum(
            1 for h in self.execution_history 
            if h["status"] == SkillStatus.SUCCESS.value
        )
        
        avg_time = sum(
            h["execution_time"] for h in self.execution_history
        ) / total
        
        return {
            "total_executions": total,
            "success_rate": success_count / total if total > 0 else 0,
            "average_execution_time": avg_time
        }


    async def cleanup(self):
        """清理资源"""
        pass
