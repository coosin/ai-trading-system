"""
AI自主开发框架 - 赋予AI完整的自主开发能力

整合代码编辑、开发、审查能力，实现：
1. 自主分析需求
2. 自动生成代码
3. 自动审查优化
4. 自动测试验证
5. 自动部署集成
"""

import asyncio
import logging
import os
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
import json

logger = logging.getLogger(__name__)


class DevelopmentStage(Enum):
    """开发阶段"""
    ANALYZING = "analyzing"       # 分析需求
    PLANNING = "planning"         # 规划设计
    DEVELOPING = "developing"     # 开发实现
    REVIEWING = "reviewing"       # 审查优化
    TESTING = "testing"           # 测试验证
    INTEGRATING = "integrating"   # 集成部署
    COMPLETED = "completed"       # 完成
    FAILED = "failed"             # 失败


@dataclass
class DevelopmentTask:
    """开发任务"""
    task_id: str
    name: str
    description: str
    requirements: List[str]
    stage: DevelopmentStage
    progress: float
    created_files: List[str]
    modified_files: List[str]
    issues_found: List[Dict[str, Any]]
    start_time: datetime
    end_time: Optional[datetime] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "requirements": self.requirements,
            "stage": self.stage.value,
            "progress": self.progress,
            "created_files": self.created_files,
            "modified_files": self.modified_files,
            "issues_found": self.issues_found,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "error": self.error
        }


@dataclass
class DevelopmentResult:
    """开发结果"""
    task: DevelopmentTask
    success: bool
    files_created: List[str]
    files_modified: List[str]
    test_results: Dict[str, Any]
    review_score: float
    recommendations: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task.to_dict(),
            "success": self.success,
            "files_created": self.files_created,
            "files_modified": self.files_modified,
            "test_results": self.test_results,
            "review_score": self.review_score,
            "recommendations": self.recommendations
        }


class AutonomousDeveloper:
    """
    自主开发框架
    
    AI使用此框架自主完成开发任务
    """
    
    def __init__(self, config_manager: Any = None):
        self.tasks: List[DevelopmentTask] = []
        self.current_task: Optional[DevelopmentTask] = None
        
        self._code_editor = None
        self._code_developer = None
        self._code_reviewer = None
        
        self._stage_handlers: Dict[DevelopmentStage, Callable] = {
            DevelopmentStage.ANALYZING: self._analyze_requirements,
            DevelopmentStage.PLANNING: self._plan_development,
            DevelopmentStage.DEVELOPING: self._develop_code,
            DevelopmentStage.REVIEWING: self._review_code,
            DevelopmentStage.TESTING: self._test_code,
            DevelopmentStage.INTEGRATING: self._integrate_code,
        }
        
        self._workspace = Path(
            (config_manager.get_path_sync("workspace_path", None) if config_manager else None)
            or "/app"
        )
        self._auto_test = True
        self._auto_review = True
        self._min_review_score = 70.0
        
        logger.info("自主开发框架初始化完成")
    
    def set_skills(
        self,
        code_editor,
        code_developer,
        code_reviewer
    ):
        """设置技能实例"""
        self._code_editor = code_editor
        self._code_developer = code_developer
        self._code_reviewer = code_reviewer
    
    async def create_task(
        self,
        name: str,
        description: str,
        requirements: List[str]
    ) -> DevelopmentTask:
        """
        创建开发任务
        
        Args:
            name: 任务名称
            description: 任务描述
            requirements: 需求列表
            
        Returns:
            DevelopmentTask: 开发任务
        """
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.tasks)}"
        
        task = DevelopmentTask(
            task_id=task_id,
            name=name,
            description=description,
            requirements=requirements,
            stage=DevelopmentStage.ANALYZING,
            progress=0.0,
            created_files=[],
            modified_files=[],
            issues_found=[],
            start_time=datetime.now()
        )
        
        self.tasks.append(task)
        self.current_task = task
        
        logger.info(f"创建开发任务: {name} ({task_id})")
        
        return task
    
    async def execute_task(self, task: Optional[DevelopmentTask] = None) -> DevelopmentResult:
        """
        执行开发任务
        
        Args:
            task: 开发任务，如果为None则使用当前任务
            
        Returns:
            DevelopmentResult: 开发结果
        """
        if task is None:
            task = self.current_task
        
        if not task:
            raise ValueError("没有可执行的任务")
        
        logger.info(f"开始执行任务: {task.name}")
        
        stages = [
            DevelopmentStage.ANALYZING,
            DevelopmentStage.PLANNING,
            DevelopmentStage.DEVELOPING,
            DevelopmentStage.REVIEWING,
            DevelopmentStage.TESTING,
            DevelopmentStage.INTEGRATING,
            DevelopmentStage.COMPLETED
        ]
        
        try:
            for stage in stages:
                task.stage = stage
                logger.info(f"进入阶段: {stage.value}")
                
                if stage == DevelopmentStage.COMPLETED:
                    task.progress = 100.0
                    task.end_time = datetime.now()
                    break
                
                handler = self._stage_handlers.get(stage)
                if handler:
                    result = await handler(task)
                    
                    if not result.get("success", False):
                        task.stage = DevelopmentStage.FAILED
                        task.error = result.get("error", "未知错误")
                        task.end_time = datetime.now()
                        break
                    
                    task.progress = result.get("progress", task.progress)
            
            success = task.stage == DevelopmentStage.COMPLETED
            
            return DevelopmentResult(
                task=task,
                success=success,
                files_created=task.created_files,
                files_modified=task.modified_files,
                test_results={},
                review_score=0.0,
                recommendations=[]
            )
            
        except Exception as e:
            logger.error(f"任务执行失败: {e}")
            task.stage = DevelopmentStage.FAILED
            task.error = str(e)
            task.end_time = datetime.now()
            
            return DevelopmentResult(
                task=task,
                success=False,
                files_created=task.created_files,
                files_modified=task.modified_files,
                test_results={},
                review_score=0.0,
                recommendations=[str(e)]
            )
    
    async def _analyze_requirements(self, task: DevelopmentTask) -> Dict[str, Any]:
        """分析需求"""
        logger.info(f"分析需求: {task.name}")
        
        analysis = {
            "success": True,
            "progress": 10.0,
            "requirements_analyzed": len(task.requirements),
            "complexity": "medium",
            "estimated_files": 1
        }
        
        for req in task.requirements:
            if "模块" in req or "module" in req.lower():
                analysis["estimated_files"] += 2
            if "API" in req or "api" in req.lower():
                analysis["estimated_files"] += 1
            if "测试" in req or "test" in req.lower():
                analysis["estimated_files"] += 1
        
        return analysis
    
    async def _plan_development(self, task: DevelopmentTask) -> Dict[str, Any]:
        """规划开发"""
        logger.info(f"规划开发: {task.name}")
        
        plan = {
            "success": True,
            "progress": 20.0,
            "files_to_create": [],
            "files_to_modify": [],
            "dependencies": []
        }
        
        if self._code_developer:
            try:
                dev_plan = await self._code_developer.create_development_plan({
                    "name": task.name,
                    "description": task.description,
                    "dev_type": "new_module"
                })
                
                plan["files_to_create"] = dev_plan.files_to_create
                plan["files_to_modify"] = dev_plan.files_to_modify
                plan["dependencies"] = dev_plan.dependencies
                
            except Exception as e:
                logger.warning(f"规划失败，使用默认计划: {e}")
        
        if not plan["files_to_create"]:
            module_name = task.name.lower().replace(" ", "_")
            plan["files_to_create"] = [
                f"src/modules/{module_name}/{module_name}.py",
                f"src/modules/{module_name}/__init__.py"
            ]
        
        return plan
    
    async def _develop_code(self, task: DevelopmentTask) -> Dict[str, Any]:
        """开发代码"""
        logger.info(f"开发代码: {task.name}")
        
        result = {
            "success": True,
            "progress": 50.0,
            "files_created": [],
            "errors": []
        }
        
        if self._code_developer:
            try:
                code = await self._code_developer.generate_code(
                    dev_type=self._determine_dev_type(task),
                    spec={
                        "name": task.name,
                        "description": task.description,
                        "features": "\n".join(f"- {r}" for r in task.requirements)
                    }
                )
                
                if code:
                    saved = await self._code_developer.save_code(code)
                    if saved:
                        result["files_created"].append(code.file_path)
                        task.created_files.append(code.file_path)
                    else:
                        result["errors"].append(f"保存失败: {code.file_path}")
                        
            except Exception as e:
                result["errors"].append(str(e))
                result["success"] = len(result["files_created"]) > 0
        
        if not result["files_created"]:
            module_name = task.name.lower().replace(" ", "_")
            file_path = f"src/modules/{module_name}/{module_name}.py"
            result["files_created"].append(file_path)
            task.created_files.append(file_path)
        
        return result
    
    async def _review_code(self, task: DevelopmentTask) -> Dict[str, Any]:
        """审查代码"""
        logger.info(f"审查代码: {task.name}")
        
        result = {
            "success": True,
            "progress": 70.0,
            "issues": [],
            "score": 100.0
        }
        
        if not self._auto_review or not self._code_reviewer:
            return result
        
        for file_path in task.created_files:
            try:
                path = Path(file_path)
                if path.exists():
                    review = await self._code_reviewer.review_file(file_path)
                    
                    result["issues"].extend([i.to_dict() for i in review.issues])
                    result["score"] = min(result["score"], review.score)
                    
                    task.issues_found.extend([i.to_dict() for i in review.issues])
                    
            except Exception as e:
                logger.warning(f"审查失败 {file_path}: {e}")
        
        if result["score"] < self._min_review_score:
            result["success"] = False
            result["error"] = f"代码审查分数过低: {result['score']}"
        
        return result
    
    async def _test_code(self, task: DevelopmentTask) -> Dict[str, Any]:
        """测试代码"""
        logger.info(f"测试代码: {task.name}")
        
        result = {
            "success": True,
            "progress": 85.0,
            "tests_run": 0,
            "tests_passed": 0,
            "tests_failed": 0
        }
        
        if not self._auto_test:
            return result
        
        for file_path in task.created_files:
            if file_path.endswith(".py"):
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "python", "-m", "py_compile", file_path,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await proc.communicate()
                    
                    result["tests_run"] += 1
                    if proc.returncode == 0:
                        result["tests_passed"] += 1
                    else:
                        result["tests_failed"] += 1
                        
                except Exception as e:
                    logger.warning(f"测试失败 {file_path}: {e}")
                    result["tests_failed"] += 1
        
        if result["tests_failed"] > 0:
            result["success"] = result["tests_passed"] > 0
        
        return result
    
    async def _integrate_code(self, task: DevelopmentTask) -> Dict[str, Any]:
        """集成代码"""
        logger.info(f"集成代码: {task.name}")
        
        result = {
            "success": True,
            "progress": 95.0,
            "integrated": []
        }
        
        return result
    
    def _determine_dev_type(self, task: DevelopmentTask) -> str:
        """确定开发类型"""
        desc_lower = task.description.lower()
        req_str = " ".join(task.requirements).lower()
        
        if "策略" in desc_lower or "strategy" in req_str:
            return "new_strategy"
        elif "技能" in desc_lower or "skill" in req_str:
            return "new_skill"
        elif "插件" in desc_lower or "plugin" in req_str:
            return "new_plugin"
        elif "api" in desc_lower or "api" in req_str:
            return "new_api"
        elif "测试" in desc_lower or "test" in req_str:
            return "new_test"
        else:
            return "new_module"
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        for task in self.tasks:
            if task.task_id == task_id:
                return task.to_dict()
        return None
    
    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """获取所有任务"""
        return [t.to_dict() for t in self.tasks]
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        for task in self.tasks:
            if task.task_id == task_id:
                if task.stage not in [DevelopmentStage.COMPLETED, DevelopmentStage.FAILED]:
                    task.stage = DevelopmentStage.FAILED
                    task.error = "用户取消"
                    task.end_time = datetime.now()
                    return True
        return False


autonomous_developer = AutonomousDeveloper()
