"""
代码开发技能 - 赋予AI自主开发能力

核心能力：
1. 模块生成 - 自动生成新模块
2. 功能开发 - 开发新功能
3. 接口实现 - 实现接口和API
4. 测试生成 - 生成测试代码
5. 文档生成 - 生成代码文档
"""

import asyncio
import logging
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
import re

from .skill_base import SkillBase, SkillResult, SkillPriority, SkillStatus

logger = logging.getLogger(__name__)


class DevelopmentType(Enum):
    """开发类型"""
    NEW_MODULE = "new_module"           # 新模块
    NEW_FUNCTION = "new_function"       # 新函数
    NEW_CLASS = "new_class"             # 新类
    NEW_API = "new_api"                 # 新API
    NEW_TEST = "new_test"               # 新测试
    NEW_PLUGIN = "new_plugin"           # 新插件
    NEW_STRATEGY = "new_strategy"       # 新策略
    NEW_SKILL = "new_skill"             # 新技能


@dataclass
class GeneratedCode:
    """生成的代码"""
    file_path: str
    code: str
    language: str
    description: str
    dependencies: List[str]
    imports: List[str]
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "code": self.code,
            "language": self.language,
            "description": self.description,
            "dependencies": self.dependencies,
            "imports": self.imports,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class DevelopmentPlan:
    """开发计划"""
    name: str
    description: str
    dev_type: DevelopmentType
    files_to_create: List[str]
    files_to_modify: List[str]
    dependencies: List[str]
    steps: List[Dict[str, Any]]
    estimated_complexity: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "dev_type": self.dev_type.value,
            "files_to_create": self.files_to_create,
            "files_to_modify": self.files_to_modify,
            "dependencies": self.dependencies,
            "steps": self.steps,
            "estimated_complexity": self.estimated_complexity
        }


class CodeDeveloperSkill(SkillBase):
    """
    代码开发技能
    
    赋予AI自主开发新功能和模块的能力
    """
    
    def __init__(self):
        super().__init__(
            name="code_developer",
            description="AI代码开发能力，包括生成模块、功能、API、测试等",
            priority=SkillPriority.HIGH
        )
        
        self.generated_files: List[GeneratedCode] = []
        self.templates_dir = Path(os.environ.get("OPENCLAW_TEMPLATES_DIR", "/app/templates"))
        try:
            self.templates_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            self.templates_dir = Path("/tmp/openclaw_templates")
            self.templates_dir.mkdir(parents=True, exist_ok=True)
        
        self._init_templates()
        
        logger.info("代码开发技能初始化完成")
    
    def _init_templates(self):
        """初始化代码模板"""
        self._templates = {
            "module": '''"""
{description}

功能:
{features}
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class {class_name}:
    """
    {class_description}
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """初始化"""
        self.config = config or {{}}
        self._initialized = False
        self._running = False
        
    async def initialize(self) -> bool:
        """初始化模块"""
        if self._initialized:
            return True
        
        try:
            # 初始化逻辑
            logger.info("初始化 {class_name}")
            
            self._initialized = True
            return True
        except Exception as e:
            logger.error(f"初始化失败: {{e}}")
            return False
    
    async def start(self) -> bool:
        """启动模块"""
        if not self._initialized:
            if not await self.initialize():
                return False
        
        if self._running:
            return True
        
        try:
            # 启动逻辑
            logger.info("启动 {class_name}")
            
            self._running = True
            return True
        except Exception as e:
            logger.error(f"启动失败: {{e}}")
            return False
    
    async def stop(self) -> bool:
        """停止模块"""
        if not self._running:
            return True
        
        try:
            # 停止逻辑
            logger.info("停止 {class_name}")
            
            self._running = False
            return True
        except Exception as e:
            logger.error(f"停止失败: {{e}}")
            return False
    
    async def cleanup(self):
        """清理资源"""
        if self._running:
            await self.stop()
        
        self._initialized = False
        logger.info("清理 {class_name}")
''',

            "function": '''async def {function_name}({parameters}) -> {return_type}:
    """
    {description}
    
    Args:
        {args_doc}
    
    Returns:
        {return_doc}
    """
    try:
        # 函数逻辑
        {body}
        
        return {return_value}
    except Exception as e:
        logger.error(f"{function_name} 执行失败: {{e}}")
        raise
''',

            "class": '''class {class_name}:
    """
    {description}
    """
    
    def __init__(self{init_params}):
        """初始化"""
        {init_body}
    
    {methods}
''',

            "api": '''@router.{method}("{path}")
async def {function_name}({parameters}) -> Dict[str, Any]:
    """
    API: {api_name}
    
    {description}
    """
    try:
        # API逻辑
        {body}
        
        return {{
            "success": True,
            "data": {return_value},
            "message": "{api_name}执行成功"
        }}
    except Exception as e:
        logger.error(f"{api_name} 失败: {{e}}")
        return {{
            "success": False,
            "error": str(e),
            "message": "{api_name}执行失败"
        }}
''',

            "test": '''"""
测试: {test_name}
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock

from {module_path} import {class_name}


class Test{class_name}:
    """测试 {class_name}"""
    
    @pytest.fixture
    def instance(self):
        """创建测试实例"""
        return {class_name}()
    
    @pytest.mark.asyncio
    async def test_initialize(self, instance):
        """测试初始化"""
        result = await instance.initialize()
        assert result is True
    
    @pytest.mark.asyncio
    async def test_start(self, instance):
        """测试启动"""
        await instance.initialize()
        result = await instance.start()
        assert result is True
    
    @pytest.mark.asyncio
    async def test_stop(self, instance):
        """测试停止"""
        await instance.initialize()
        await instance.start()
        result = await instance.stop()
        assert result is True
''',

            "strategy": '''"""
交易策略: {strategy_name}

{description}
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from src.modules.strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class {class_name}(BaseStrategy):
    """
    {strategy_name} 策略
    
    {description}
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(name="{strategy_name}", config=config)
        
        # 策略参数
        self.{param_name} = config.get("{param_name}", {default_value})
        
    async def analyze(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        分析市场数据
        
        Args:
            market_data: 市场数据
            
        Returns:
            分析结果
        """
        # 分析逻辑
        result = {{
            "signal": "neutral",
            "confidence": 0.0,
            "reason": ""
        }}
        
        return result
    
    async def generate_signal(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成交易信号
        
        Args:
            analysis: 分析结果
            
        Returns:
            交易信号
        """
        signal = {{
            "action": "hold",
            "symbol": None,
            "size": 0.0,
            "price": None,
            "stop_loss": None,
            "take_profit": None
        }}
        
        return signal
    
    async def execute(self, signal: Dict[str, Any]) -> bool:
        """
        执行交易信号
        
        Args:
            signal: 交易信号
            
        Returns:
            是否执行成功
        """
        # 执行逻辑
        return True
''',

            "skill": '''"""
技能: {skill_name}

{description}
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from .skill_base import SkillBase, SkillResult, SkillPriority, SkillStatus

logger = logging.getLogger(__name__)


class {class_name}(SkillBase):
    """
    {skill_name} 技能
    
    {description}
    """
    
    def __init__(self):
        super().__init__(
            name="{skill_name}",
            description="{description}",
            priority=SkillPriority.{priority}
        )
        
        # 技能参数
        
    async def execute(self, context: Dict[str, Any]) -> SkillResult:
        """
        执行技能
        
        Args:
            context: 执行上下文
            
        Returns:
            SkillResult: 执行结果
        """
        start_time = datetime.now()
        
        try:
            # 技能逻辑
            result_data = {{}}
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            return SkillResult(
                skill_name=self.name,
                status=SkillStatus.SUCCESS,
                priority=self.priority,
                message="{skill_name}执行成功",
                data=result_data,
                recommendations=[]
            )
            
        except Exception as e:
            logger.error(f"{skill_name}执行失败: {{e}}")
            return SkillResult(
                skill_name=self.name,
                status=SkillStatus.FAILED,
                priority=self.priority,
                message=f"{skill_name}执行失败: {{str(e)}}",
                errors=[str(e)]
            )
''',

            "plugin": '''"""
插件: {plugin_name}

{description}
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional

from src.modules.plugins.base_plugin import BasePlugin, PluginInfo

logger = logging.getLogger(__name__)


class {class_name}(BasePlugin):
    """
    {plugin_name} 插件
    
    {description}
    """
    
    @property
    def info(self) -> PluginInfo:
        """插件信息"""
        return PluginInfo(
            name="{plugin_name}",
            version="1.0.0",
            description="{description}",
            author="AI Developer",
            dependencies=[]
        )
    
    async def initialize(self) -> bool:
        """初始化插件"""
        try:
            # 初始化逻辑
            logger.info("初始化 {plugin_name}")
            return True
        except Exception as e:
            logger.error(f"初始化失败: {{e}}")
            return False
    
    async def start(self) -> bool:
        """启动插件"""
        try:
            # 启动逻辑
            logger.info("启动 {plugin_name}")
            return True
        except Exception as e:
            logger.error(f"启动失败: {{e}}")
            return False
    
    async def stop(self) -> bool:
        """停止插件"""
        try:
            # 停止逻辑
            logger.info("停止 {plugin_name}")
            return True
        except Exception as e:
            logger.error(f"停止失败: {{e}}")
            return False
    
    async def cleanup(self):
        """清理资源"""
        logger.info("清理 {plugin_name}")
'''
        }
    
    async def diagnose(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        诊断开发需求
        
        Args:
            context: 诊断上下文
            
        Returns:
            Dict: 诊断结果
        """
        requirements = context.get("requirements", [])
        description = context.get("description", "")
        
        return {
            "requirements_count": len(requirements),
            "description_length": len(description),
            "estimated_complexity": "medium" if len(requirements) > 3 else "low",
            "recommended_dev_type": "new_module"
        }
    
    async def execute(self, context: Dict[str, Any]) -> SkillResult:
        """
        执行开发任务
        
        Args:
            context: 包含dev_request等信息
            
        Returns:
            SkillResult: 开发结果
        """
        dev_request = context.get("dev_request", {})
        
        if not dev_request:
            return SkillResult(
                skill_name=self.name,
                status=SkillStatus.FAILED,
                priority=self.priority,
                message="缺少开发请求",
                errors=["未提供dev_request参数"]
            )
        
        operation = dev_request.get("operation")
        
        try:
            if operation == "plan":
                plan = await self.create_development_plan(dev_request)
                return SkillResult(
                    skill_name=self.name,
                    status=SkillStatus.SUCCESS,
                    priority=self.priority,
                    message="开发计划创建完成",
                    data={"plan": plan.to_dict()}
                )
            
            elif operation == "generate":
                code = await self.generate_code(
                    dev_type=DevelopmentType(dev_request.get("dev_type", "new_module")),
                    spec=dev_request.get("spec", {})
                )
                return SkillResult(
                    skill_name=self.name,
                    status=SkillStatus.SUCCESS if code else SkillStatus.FAILED,
                    priority=self.priority,
                    message=f"代码生成{'成功' if code else '失败'}",
                    data={"generated_code": code.to_dict() if code else None}
                )
            
            elif operation == "create":
                code = await self.generate_code(
                    dev_type=DevelopmentType(dev_request.get("dev_type", "new_module")),
                    spec=dev_request.get("spec", {})
                )
                
                if code:
                    success = await self.save_code(code)
                    return SkillResult(
                        skill_name=self.name,
                        status=SkillStatus.SUCCESS if success else SkillStatus.FAILED,
                        priority=self.priority,
                        message=f"文件创建{'成功' if success else '失败'}: {code.file_path}",
                        data={"generated_code": code.to_dict()}
                    )
                
                return SkillResult(
                    skill_name=self.name,
                    status=SkillStatus.FAILED,
                    priority=self.priority,
                    message="代码生成失败"
                )
            
            elif operation == "implement":
                result = await self.implement_feature(
                    feature_spec=dev_request.get("feature_spec", {}),
                    target_file=dev_request.get("target_file")
                )
                return SkillResult(
                    skill_name=self.name,
                    status=SkillStatus.SUCCESS if result else SkillStatus.FAILED,
                    priority=self.priority,
                    message=f"功能实现{'成功' if result else '失败'}",
                    data={"result": result}
                )
            
            else:
                return SkillResult(
                    skill_name=self.name,
                    status=SkillStatus.FAILED,
                    priority=self.priority,
                    message=f"未知操作: {operation}",
                    errors=[f"不支持的操作类型: {operation}"]
                )
                
        except Exception as e:
            logger.error(f"开发任务失败: {e}")
            return SkillResult(
                skill_name=self.name,
                status=SkillStatus.FAILED,
                priority=self.priority,
                message=f"开发任务异常: {str(e)}",
                errors=[str(e)]
            )
    
    async def create_development_plan(self, request: Dict[str, Any]) -> DevelopmentPlan:
        """
        创建开发计划
        
        Args:
            request: 开发请求
            
        Returns:
            DevelopmentPlan: 开发计划
        """
        name = request.get("name", "unnamed")
        description = request.get("description", "")
        dev_type = DevelopmentType(request.get("dev_type", "new_module"))
        
        files_to_create = []
        files_to_modify = []
        dependencies = []
        steps = []
        
        if dev_type == DevelopmentType.NEW_MODULE:
            module_name = name.lower().replace(" ", "_")
            files_to_create.append(f"src/modules/{module_name}/{module_name}.py")
            files_to_create.append(f"src/modules/{module_name}/__init__.py")
            
            steps = [
                {"step": 1, "action": "create_directory", "target": f"src/modules/{module_name}"},
                {"step": 2, "action": "generate_module", "target": f"{module_name}.py"},
                {"step": 3, "action": "create_init", "target": "__init__.py"},
                {"step": 4, "action": "register_module", "target": "main_controller.py"}
            ]
            
        elif dev_type == DevelopmentType.NEW_STRATEGY:
            strategy_name = name.replace(" ", "")
            files_to_create.append(f"src/modules/strategies/{strategy_name.lower()}_strategy.py")
            
            steps = [
                {"step": 1, "action": "generate_strategy", "target": f"{strategy_name.lower()}_strategy.py"},
                {"step": 2, "action": "register_strategy", "target": "strategy_manager.py"}
            ]
            
        elif dev_type == DevelopmentType.NEW_SKILL:
            skill_name = name.replace(" ", "")
            files_to_create.append(f"src/modules/skills/{skill_name.lower()}_skill.py")
            
            steps = [
                {"step": 1, "action": "generate_skill", "target": f"{skill_name.lower()}_skill.py"},
                {"step": 2, "action": "register_skill", "target": "skill_manager.py"}
            ]
            
        elif dev_type == DevelopmentType.NEW_PLUGIN:
            plugin_name = name.replace(" ", "")
            files_to_create.append(f"src/modules/plugins/{plugin_name.lower()}_plugin.py")
            
            steps = [
                {"step": 1, "action": "generate_plugin", "target": f"{plugin_name.lower()}_plugin.py"},
                {"step": 2, "action": "register_plugin", "target": "plugin_manager.py"}
            ]
        
        estimated_complexity = "medium"
        if len(files_to_create) > 3 or len(dependencies) > 5:
            estimated_complexity = "high"
        elif len(files_to_create) == 1 and not dependencies:
            estimated_complexity = "low"
        
        return DevelopmentPlan(
            name=name,
            description=description,
            dev_type=dev_type,
            files_to_create=files_to_create,
            files_to_modify=files_to_modify,
            dependencies=dependencies,
            steps=steps,
            estimated_complexity=estimated_complexity
        )
    
    async def generate_code(
        self,
        dev_type: DevelopmentType,
        spec: Dict[str, Any]
    ) -> Optional[GeneratedCode]:
        """
        生成代码
        
        Args:
            dev_type: 开发类型
            spec: 规格说明
            
        Returns:
            GeneratedCode: 生成的代码
        """
        name = spec.get("name", "unnamed")
        description = spec.get("description", "")
        class_name = spec.get("class_name", name.replace(" ", "_").title())
        file_path = spec.get("file_path", "")
        
        template = None
        language = "python"
        dependencies = []
        imports = []
        
        if dev_type == DevelopmentType.NEW_MODULE:
            template = self._templates["module"]
            template = template.format(
                description=description,
                features=spec.get("features", "- 基础功能"),
                class_name=class_name,
                class_description=description
            )
            
            if not file_path:
                module_name = name.lower().replace(" ", "_")
                file_path = f"src/modules/{module_name}/{module_name}.py"
            
        elif dev_type == DevelopmentType.NEW_FUNCTION:
            template = self._templates["function"]
            template = template.format(
                function_name=spec.get("function_name", name),
                parameters=spec.get("parameters", ""),
                return_type=spec.get("return_type", "Any"),
                description=description,
                args_doc=spec.get("args_doc", "参数"),
                return_doc=spec.get("return_doc", "返回值"),
                body=spec.get("body", "pass"),
                return_value=spec.get("return_value", "None")
            )
            
        elif dev_type == DevelopmentType.NEW_CLASS:
            template = self._templates["class"]
            template = template.format(
                class_name=class_name,
                description=description,
                init_params=spec.get("init_params", ""),
                init_body=spec.get("init_body", "pass"),
                methods=spec.get("methods", "pass")
            )
            
        elif dev_type == DevelopmentType.NEW_API:
            template = self._templates["api"]
            template = template.format(
                method=spec.get("method", "get"),
                path=spec.get("path", f"/api/{name}"),
                function_name=spec.get("function_name", name),
                parameters=spec.get("parameters", ""),
                api_name=name,
                description=description,
                body=spec.get("body", "pass"),
                return_value=spec.get("return_value", "None")
            )
            
        elif dev_type == DevelopmentType.NEW_TEST:
            template = self._templates["test"]
            template = template.format(
                test_name=name,
                module_path=spec.get("module_path", ""),
                class_name=class_name
            )
            
            if not file_path:
                file_path = f"tests/test_{name.lower()}.py"
            
        elif dev_type == DevelopmentType.NEW_STRATEGY:
            template = self._templates["strategy"]
            template = template.format(
                strategy_name=name,
                class_name=class_name,
                description=description,
                param_name=spec.get("param_name", "param"),
                default_value=spec.get("default_value", "None")
            )
            
            if not file_path:
                file_path = f"src/modules/strategies/{name.lower()}_strategy.py"
            
        elif dev_type == DevelopmentType.NEW_SKILL:
            template = self._templates["skill"]
            template = template.format(
                skill_name=name,
                class_name=class_name,
                description=description,
                priority=spec.get("priority", "MEDIUM")
            )
            
            if not file_path:
                file_path = f"src/modules/skills/{name.lower()}_skill.py"
            
        elif dev_type == DevelopmentType.NEW_PLUGIN:
            template = self._templates["plugin"]
            template = template.format(
                plugin_name=name,
                class_name=class_name,
                description=description
            )
            
            if not file_path:
                file_path = f"src/modules/plugins/{name.lower()}_plugin.py"
        
        if not template:
            logger.error(f"不支持的开发类型: {dev_type}")
            return None
        
        return GeneratedCode(
            file_path=file_path,
            code=template,
            language=language,
            description=description,
            dependencies=dependencies,
            imports=imports
        )
    
    async def save_code(self, generated_code: GeneratedCode) -> bool:
        """
        保存生成的代码
        
        Args:
            generated_code: 生成的代码
            
        Returns:
            bool: 是否保存成功
        """
        try:
            path = Path(generated_code.file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            path.write_text(generated_code.code, encoding='utf-8')
            
            self.generated_files.append(generated_code)
            
            logger.info(f"代码已保存: {generated_code.file_path}")
            
            return True
            
        except Exception as e:
            logger.error(f"保存代码失败: {e}")
            return False
    
    async def implement_feature(
        self,
        feature_spec: Dict[str, Any],
        target_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        实现功能
        
        Args:
            feature_spec: 功能规格
            target_file: 目标文件
            
        Returns:
            Dict: 实现结果
        """
        result = {
            "success": False,
            "files_created": [],
            "files_modified": [],
            "errors": []
        }
        
        try:
            plan = await self.create_development_plan({
                "name": feature_spec.get("name", "feature"),
                "description": feature_spec.get("description", ""),
                "dev_type": feature_spec.get("dev_type", "new_module")
            })
            
            for file_path in plan.files_to_create:
                code = await self.generate_code(
                    dev_type=plan.dev_type,
                    spec={
                        **feature_spec,
                        "file_path": file_path
                    }
                )
                
                if code:
                    if await self.save_code(code):
                        result["files_created"].append(file_path)
                    else:
                        result["errors"].append(f"保存失败: {file_path}")
            
            result["success"] = len(result["files_created"]) > 0
            
        except Exception as e:
            result["errors"].append(str(e))
        
        return result
    
    def get_generated_files(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取已生成的文件列表"""
        return [f.to_dict() for f in self.generated_files[-limit:]]
    
    async def generate_documentation(
        self,
        file_path: str,
        doc_type: str = "module"
    ) -> Optional[str]:
        """
        生成文档
        
        Args:
            file_path: 文件路径
            doc_type: 文档类型
            
        Returns:
            str: 生成的文档
        """
        path = Path(file_path)
        
        if not path.exists():
            return None
        
        content = path.read_text(encoding='utf-8')
        
        doc = f"""# {path.stem}

## 概述

自动生成的文档

## 文件信息

- 文件路径: `{file_path}`
- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 模块结构

"""
        
        import ast
        try:
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    doc += f"### 类: {node.name}\n\n"
                    if ast.get_docstring(node):
                        doc += f"{ast.get_docstring(node)}\n\n"
                    
                elif isinstance(node, ast.FunctionDef):
                    doc += f"#### 方法: {node.name}\n\n"
                    if ast.get_docstring(node):
                        doc += f"{ast.get_docstring(node)}\n\n"
                        
        except:
            pass
        
        return doc
