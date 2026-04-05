"""
代码编辑技能 - 赋予AI代码编辑和修改能力

核心能力：
1. 代码分析 - 理解代码结构和逻辑
2. 代码修改 - 安全地修改代码
3. 代码重构 - 优化代码结构
4. 错误修复 - 自动修复代码错误
5. 版本控制 - 管理代码变更
"""

import asyncio
import logging
import re
import ast
import difflib
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
import json

from .skill_base import SkillBase, SkillResult, SkillPriority, SkillStatus

logger = logging.getLogger(__name__)


class EditOperation(Enum):
    """编辑操作类型"""
    INSERT = "insert"           # 插入代码
    DELETE = "delete"           # 删除代码
    REPLACE = "replace"         # 替换代码
    REFACTOR = "refactor"       # 重构代码
    FIX_ERROR = "fix_error"     # 修复错误
    OPTIMIZE = "optimize"       # 优化代码


class CodeLanguage(Enum):
    """代码语言"""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JSON = "json"
    YAML = "yaml"
    MARKDOWN = "markdown"
    UNKNOWN = "unknown"


@dataclass
class CodeChange:
    """代码变更"""
    file_path: str
    operation: EditOperation
    original_code: Optional[str]
    new_code: str
    start_line: Optional[int]
    end_line: Optional[int]
    description: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "operation": self.operation.value,
            "original_code": self.original_code,
            "new_code": self.new_code,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "description": self.description,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class CodeAnalysis:
    """代码分析结果"""
    file_path: str
    language: CodeLanguage
    line_count: int
    function_count: int
    class_count: int
    import_count: int
    issues: List[Dict[str, Any]]
    suggestions: List[str]
    complexity_score: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "language": self.language.value,
            "line_count": self.line_count,
            "function_count": self.function_count,
            "class_count": self.class_count,
            "import_count": self.import_count,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "complexity_score": self.complexity_score
        }


class CodeEditorSkill(SkillBase):
    """
    代码编辑技能
    
    赋予AI安全编辑和修改代码的能力
    """
    
    def __init__(self):
        super().__init__(
            name="code_editor",
            description="AI代码编辑能力，包括分析、修改、重构、修复代码",
            priority=SkillPriority.HIGH
        )
        
        self.change_history: List[CodeChange] = []
        self.backup_dir = Path("data/backups/code")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        self.safe_mode = True
        self.auto_backup = True
        self.max_history = 100
        
        self._code_patterns = {
            "function": r"(async\s+)?def\s+(\w+)\s*\([^)]*\)\s*:",
            "class": r"class\s+(\w+)(\([^)]*\))?\s*:",
            "import": r"^(?:from\s+\S+\s+)?import\s+.+$",
            "comment": r"#.*$",
            "docstring": r'""".*?"""|\'\'\'.*?\'\'\'',
        }
        
        logger.info("代码编辑技能初始化完成")
    
    async def diagnose(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        诊断代码问题
        
        Args:
            context: 诊断上下文
            
        Returns:
            Dict: 诊断结果
        """
        file_path = context.get("file_path")
        
        if not file_path:
            return {"error": "未提供文件路径"}
        
        try:
            analysis = await self.analyze_code(file_path)
            return {
                "file_path": file_path,
                "analysis": analysis.to_dict(),
                "issues_count": len(analysis.issues),
                "suggestions": analysis.suggestions
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def execute(self, context: Dict[str, Any]) -> SkillResult:
        """
        执行代码编辑
        
        Args:
            context: 包含edit_request等信息
            
        Returns:
            SkillResult: 编辑结果
        """
        edit_request = context.get("edit_request", {})
        
        if not edit_request:
            return SkillResult(
                skill_name=self.name,
                status=SkillStatus.FAILED,
                priority=self.priority,
                message="缺少编辑请求",
                errors=["未提供edit_request参数"]
            )
        
        operation = edit_request.get("operation")
        file_path = edit_request.get("file_path")
        
        if not file_path:
            return SkillResult(
                skill_name=self.name,
                status=SkillStatus.FAILED,
                priority=self.priority,
                message="缺少文件路径",
                errors=["未提供file_path参数"]
            )
        
        try:
            if operation == "analyze":
                result = await self.analyze_code(file_path)
                return SkillResult(
                    skill_name=self.name,
                    status=SkillStatus.SUCCESS,
                    priority=self.priority,
                    message=f"代码分析完成: {file_path}",
                    data={"analysis": result.to_dict()}
                )
            
            elif operation == "edit":
                result = await self.edit_code(
                    file_path=file_path,
                    edit_type=EditOperation(edit_request.get("edit_type", "replace")),
                    content=edit_request.get("content"),
                    start_line=edit_request.get("start_line"),
                    end_line=edit_request.get("end_line"),
                    description=edit_request.get("description", "")
                )
                return SkillResult(
                    skill_name=self.name,
                    status=SkillStatus.SUCCESS if result else SkillStatus.FAILED,
                    priority=self.priority,
                    message=f"代码编辑{'成功' if result else '失败'}: {file_path}",
                    data={"change": result.to_dict() if result else None}
                )
            
            elif operation == "fix":
                result = await self.fix_code(file_path, edit_request.get("error_info", {}))
                return SkillResult(
                    skill_name=self.name,
                    status=SkillStatus.SUCCESS if result else SkillStatus.FAILED,
                    priority=self.priority,
                    message=f"代码修复{'成功' if result else '失败'}: {file_path}",
                    data={"change": result.to_dict() if result else None}
                )
            
            elif operation == "refactor":
                result = await self.refactor_code(
                    file_path=file_path,
                    refactor_type=edit_request.get("refactor_type"),
                    target=edit_request.get("target")
                )
                return SkillResult(
                    skill_name=self.name,
                    status=SkillStatus.SUCCESS if result else SkillStatus.FAILED,
                    priority=self.priority,
                    message=f"代码重构{'成功' if result else '失败'}: {file_path}",
                    data={"changes": [c.to_dict() for c in result] if result else None}
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
            logger.error(f"代码编辑失败: {e}")
            return SkillResult(
                skill_name=self.name,
                status=SkillStatus.FAILED,
                priority=self.priority,
                message=f"代码编辑异常: {str(e)}",
                errors=[str(e)]
            )
    
    def detect_language(self, file_path: str) -> CodeLanguage:
        """检测代码语言"""
        ext = Path(file_path).suffix.lower()
        
        language_map = {
            ".py": CodeLanguage.PYTHON,
            ".js": CodeLanguage.JAVASCRIPT,
            ".ts": CodeLanguage.TYPESCRIPT,
            ".json": CodeLanguage.JSON,
            ".yaml": CodeLanguage.YAML,
            ".yml": CodeLanguage.YAML,
            ".md": CodeLanguage.MARKDOWN,
        }
        
        return language_map.get(ext, CodeLanguage.UNKNOWN)
    
    async def analyze_code(self, file_path: str) -> CodeAnalysis:
        """
        分析代码
        
        Args:
            file_path: 文件路径
            
        Returns:
            CodeAnalysis: 分析结果
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        content = path.read_text(encoding='utf-8')
        language = self.detect_language(file_path)
        
        lines = content.split('\n')
        line_count = len(lines)
        
        function_count = 0
        class_count = 0
        import_count = 0
        issues = []
        suggestions = []
        
        if language == CodeLanguage.PYTHON:
            try:
                tree = ast.parse(content)
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                        function_count += 1
                    elif isinstance(node, ast.ClassDef):
                        class_count += 1
                    elif isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom):
                        import_count += 1
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        complexity = self._calculate_complexity(node)
                        if complexity > 10:
                            issues.append({
                                "type": "high_complexity",
                                "line": node.lineno,
                                "message": f"函数 '{node.name}' 复杂度过高 ({complexity})",
                                "severity": "warning"
                            })
                            suggestions.append(f"考虑重构函数 '{node.name}' 以降低复杂度")
                
            except SyntaxError as e:
                issues.append({
                    "type": "syntax_error",
                    "line": e.lineno,
                    "message": f"语法错误: {e.msg}",
                    "severity": "error"
                })
        
        for i, line in enumerate(lines, 1):
            if len(line) > 120:
                issues.append({
                    "type": "long_line",
                    "line": i,
                    "message": f"行过长 ({len(line)} 字符)",
                    "severity": "info"
                })
        
        complexity_score = max(0, 100 - len(issues) * 5 - function_count * 2)
        
        return CodeAnalysis(
            file_path=file_path,
            language=language,
            line_count=line_count,
            function_count=function_count,
            class_count=class_count,
            import_count=import_count,
            issues=issues,
            suggestions=suggestions,
            complexity_score=complexity_score
        )
    
    def _calculate_complexity(self, node: ast.AST) -> int:
        """计算代码复杂度"""
        complexity = 1
        
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        
        return complexity
    
    async def backup_file(self, file_path: str) -> str:
        """
        备份文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            str: 备份文件路径
        """
        path = Path(file_path)
        
        if not path.exists():
            return ""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{path.stem}_{timestamp}{path.suffix}"
        backup_path = self.backup_dir / backup_name
        
        import shutil
        shutil.copy2(path, backup_path)
        
        logger.info(f"文件已备份: {backup_path}")
        
        return str(backup_path)
    
    async def edit_code(
        self,
        file_path: str,
        edit_type: EditOperation,
        content: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        description: str = ""
    ) -> Optional[CodeChange]:
        """
        编辑代码
        
        Args:
            file_path: 文件路径
            edit_type: 编辑类型
            content: 新内容
            start_line: 起始行
            end_line: 结束行
            description: 描述
            
        Returns:
            CodeChange: 代码变更记录
        """
        path = Path(file_path)
        
        if not path.exists() and edit_type != EditOperation.INSERT:
            logger.error(f"文件不存在: {file_path}")
            return None
        
        if self.auto_backup and path.exists():
            await self.backup_file(file_path)
        
        original_content = path.read_text(encoding='utf-8') if path.exists() else ""
        original_lines = original_content.split('\n')
        
        if edit_type == EditOperation.INSERT:
            if start_line is None:
                start_line = len(original_lines) + 1
            
            new_lines = original_lines[:start_line-1] + content.split('\n') + original_lines[start_line-1:]
            
        elif edit_type == EditOperation.DELETE:
            if start_line is None or end_line is None:
                logger.error("删除操作需要指定行范围")
                return None
            
            new_lines = original_lines[:start_line-1] + original_lines[end_line:]
            
        elif edit_type == EditOperation.REPLACE:
            if start_line is None or end_line is None:
                logger.error("替换操作需要指定行范围")
                return None
            
            new_lines = original_lines[:start_line-1] + content.split('\n') + original_lines[end_line:]
            
        else:
            logger.error(f"不支持的编辑类型: {edit_type}")
            return None
        
        new_content = '\n'.join(new_lines)
        
        if self.safe_mode:
            if not self._validate_code(new_content, self.detect_language(file_path)):
                logger.error("代码验证失败，取消编辑")
                return None
        
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_content, encoding='utf-8')
        
        change = CodeChange(
            file_path=file_path,
            operation=edit_type,
            original_code=original_content,
            new_code=new_content,
            start_line=start_line,
            end_line=end_line,
            description=description
        )
        
        self.change_history.append(change)
        
        if len(self.change_history) > self.max_history:
            self.change_history = self.change_history[-self.max_history:]
        
        logger.info(f"代码编辑完成: {file_path}")
        
        return change
    
    def _validate_code(self, code: str, language: CodeLanguage) -> bool:
        """验证代码有效性"""
        if language == CodeLanguage.PYTHON:
            try:
                ast.parse(code)
                return True
            except SyntaxError:
                return False
        
        return True
    
    async def fix_code(
        self,
        file_path: str,
        error_info: Dict[str, Any]
    ) -> Optional[CodeChange]:
        """
        修复代码错误
        
        Args:
            file_path: 文件路径
            error_info: 错误信息
            
        Returns:
            CodeChange: 代码变更记录
        """
        path = Path(file_path)
        
        if not path.exists():
            logger.error(f"文件不存在: {file_path}")
            return None
        
        content = path.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        error_type = error_info.get("type", "")
        error_line = error_info.get("line")
        error_message = error_info.get("message", "")
        
        fixes = []
        
        if "indentation" in error_type.lower() or "indent" in error_message.lower():
            fixes = self._fix_indentation(lines, error_line)
        
        elif "syntax" in error_type.lower():
            fixes = self._fix_syntax(lines, error_line, error_message)
        
        elif "import" in error_message.lower():
            fixes = self._fix_imports(lines, error_message)
        
        elif "undefined" in error_message.lower():
            fixes = self._fix_undefined(lines, error_line, error_message)
        
        if not fixes:
            logger.warning("无法自动修复此错误")
            return None
        
        new_lines = lines.copy()
        for fix in fixes:
            line_idx = fix["line"] - 1
            if 0 <= line_idx < len(new_lines):
                new_lines[line_idx] = fix["new_content"]
        
        new_content = '\n'.join(new_lines)
        
        if self.auto_backup:
            await self.backup_file(file_path)
        
        path.write_text(new_content, encoding='utf-8')
        
        change = CodeChange(
            file_path=file_path,
            operation=EditOperation.FIX_ERROR,
            original_code=content,
            new_code=new_content,
            start_line=fixes[0]["line"] if fixes else None,
            end_line=fixes[-1]["line"] if fixes else None,
            description=f"自动修复: {error_message}"
        )
        
        self.change_history.append(change)
        
        return change
    
    def _fix_indentation(self, lines: List[str], error_line: Optional[int]) -> List[Dict]:
        """修复缩进错误"""
        fixes = []
        
        if error_line and 0 < error_line <= len(lines):
            line = lines[error_line - 1]
            stripped = line.lstrip()
            
            if stripped:
                expected_indent = 0
                for i in range(error_line - 2, -1, -1):
                    prev_line = lines[i]
                    if prev_line.strip():
                        expected_indent = len(prev_line) - len(prev_line.lstrip())
                        if prev_line.rstrip().endswith(':'):
                            expected_indent += 4
                        break
                
                new_line = ' ' * expected_indent + stripped
                fixes.append({
                    "line": error_line,
                    "new_content": new_line
                })
        
        return fixes
    
    def _fix_syntax(self, lines: List[str], error_line: Optional[int], error_message: str) -> List[Dict]:
        """修复语法错误"""
        fixes = []
        
        if error_line and 0 < error_line <= len(lines):
            line = lines[error_line - 1]
            
            if "missing" in error_message.lower() and ":" in error_message:
                if not line.rstrip().endswith(':'):
                    new_line = line.rstrip() + ':'
                    fixes.append({
                        "line": error_line,
                        "new_content": new_line
                    })
            
            if "unexpected EOF" in error_message:
                open_brackets = line.count('(') - line.count(')')
                open_braces = line.count('{') - line.count('}')
                open_brackets_sq = line.count('[') - line.count(']')
                
                new_line = line
                if open_brackets > 0:
                    new_line += ')' * open_brackets
                if open_braces > 0:
                    new_line += '}' * open_braces
                if open_brackets_sq > 0:
                    new_line += ']' * open_brackets_sq
                
                if new_line != line:
                    fixes.append({
                        "line": error_line,
                        "new_content": new_line
                    })
        
        return fixes
    
    def _fix_imports(self, lines: List[str], error_message: str) -> List[Dict]:
        """修复导入错误"""
        fixes = []
        
        return fixes
    
    def _fix_undefined(self, lines: List[str], error_line: Optional[int], error_message: str) -> List[Dict]:
        """修复未定义错误"""
        fixes = []
        
        return fixes
    
    async def refactor_code(
        self,
        file_path: str,
        refactor_type: str,
        target: str
    ) -> Optional[List[CodeChange]]:
        """
        重构代码
        
        Args:
            file_path: 文件路径
            refactor_type: 重构类型
            target: 重构目标
            
        Returns:
            List[CodeChange]: 代码变更列表
        """
        path = Path(file_path)
        
        if not path.exists():
            logger.error(f"文件不存在: {file_path}")
            return None
        
        content = path.read_text(encoding='utf-8')
        changes = []
        
        if refactor_type == "rename":
            old_name, new_name = target.split("->") if "->" in target else (target, "")
            if not new_name:
                return None
            
            new_content = content.replace(old_name, new_name)
            
            if new_content != content:
                if self.auto_backup:
                    await self.backup_file(file_path)
                
                path.write_text(new_content, encoding='utf-8')
                
                change = CodeChange(
                    file_path=file_path,
                    operation=EditOperation.REFACTOR,
                    original_code=content,
                    new_code=new_content,
                    start_line=None,
                    end_line=None,
                    description=f"重命名: {old_name} -> {new_name}"
                )
                
                changes.append(change)
                self.change_history.append(change)
        
        elif refactor_type == "extract_function":
            pass
        
        elif refactor_type == "inline_variable":
            pass
        
        return changes if changes else None
    
    def get_diff(self, change: CodeChange) -> str:
        """获取代码差异"""
        original_lines = (change.original_code or "").split('\n')
        new_lines = change.new_code.split('\n')
        
        diff = difflib.unified_diff(
            original_lines,
            new_lines,
            fromfile=f"{change.file_path} (original)",
            tofile=f"{change.file_path} (modified)",
            lineterm=''
        )
        
        return '\n'.join(diff)
    
    def get_change_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取变更历史"""
        return [c.to_dict() for c in self.change_history[-limit:]]
    
    def rollback_change(self, change_id: int) -> bool:
        """回滚变更"""
        if change_id < 0 or change_id >= len(self.change_history):
            return False
        
        change = self.change_history[change_id]
        
        if not change.original_code:
            return False
        
        path = Path(change.file_path)
        path.write_text(change.original_code, encoding='utf-8')
        
        logger.info(f"已回滚变更: {change.file_path}")
        
        return True
