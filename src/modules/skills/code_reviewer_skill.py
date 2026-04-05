"""
代码审查技能 - 赋予AI代码审查能力

核心能力：
1. 代码质量检查 - 检查代码质量
2. 安全漏洞扫描 - 发现安全问题
3. 性能分析 - 分析性能瓶颈
4. 最佳实践检查 - 检查是否符合最佳实践
5. 自动修复建议 - 提供修复建议
"""

import asyncio
import logging
import ast
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum

from .skill_base import SkillBase, SkillResult, SkillPriority, SkillStatus

logger = logging.getLogger(__name__)


class Severity(Enum):
    """严重程度"""
    CRITICAL = "critical"     # 严重 - 必须修复
    HIGH = "high"             # 高 - 应该修复
    MEDIUM = "medium"         # 中 - 建议修复
    LOW = "low"               # 低 - 可选修复
    INFO = "info"             # 信息 - 提示


class IssueCategory(Enum):
    """问题类别"""
    SECURITY = "security"           # 安全问题
    PERFORMANCE = "performance"     # 性能问题
    MAINTAINABILITY = "maintainability"  # 可维护性
    RELIABILITY = "reliability"     # 可靠性
    STYLE = "style"                 # 代码风格
    COMPLEXITY = "complexity"       # 复杂度
    DOCUMENTATION = "documentation"  # 文档
    TESTING = "testing"             # 测试


@dataclass
class CodeIssue:
    """代码问题"""
    file_path: str
    line: int
    column: int
    category: IssueCategory
    severity: Severity
    rule_id: str
    message: str
    suggestion: str
    code_snippet: str
    fix_available: bool = False
    fix_code: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "line": self.line,
            "column": self.column,
            "category": self.category.value,
            "severity": self.severity.value,
            "rule_id": self.rule_id,
            "message": self.message,
            "suggestion": self.suggestion,
            "code_snippet": self.code_snippet,
            "fix_available": self.fix_available,
            "fix_code": self.fix_code
        }


@dataclass
class ReviewResult:
    """审查结果"""
    file_path: str
    total_issues: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    info_count: int
    issues: List[CodeIssue]
    score: float
    summary: str
    recommendations: List[str]
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "total_issues": self.total_issues,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "info_count": self.info_count,
            "issues": [i.to_dict() for i in self.issues],
            "score": self.score,
            "summary": self.summary,
            "recommendations": self.recommendations,
            "timestamp": self.timestamp.isoformat()
        }


class CodeReviewerSkill(SkillBase):
    """
    代码审查技能
    
    赋予AI审查代码质量、安全、性能的能力
    """
    
    def __init__(self):
        super().__init__(
            name="code_reviewer",
            description="AI代码审查能力，包括质量检查、安全扫描、性能分析",
            priority=SkillPriority.HIGH
        )
        
        self.review_history: List[ReviewResult] = []
        
        self._security_patterns = {
            "hardcoded_password": {
                "pattern": r"(password|passwd|pwd)\s*=\s*['\"][^'\"]+['\"]",
                "message": "硬编码密码",
                "severity": Severity.CRITICAL,
                "suggestion": "使用环境变量或配置文件存储敏感信息"
            },
            "hardcoded_api_key": {
                "pattern": r"(api_key|apikey|api_secret)\s*=\s*['\"][^'\"]+['\"]",
                "message": "硬编码API密钥",
                "severity": Severity.CRITICAL,
                "suggestion": "使用环境变量或安全存储"
            },
            "sql_injection": {
                "pattern": r"execute\s*\(\s*[f\"'].*\{.*\}.*[\"']",
                "message": "潜在的SQL注入风险",
                "severity": Severity.CRITICAL,
                "suggestion": "使用参数化查询"
            },
            "eval_usage": {
                "pattern": r"\beval\s*\(",
                "message": "使用eval()函数存在安全风险",
                "severity": Severity.HIGH,
                "suggestion": "避免使用eval()，使用更安全的替代方案"
            },
            "exec_usage": {
                "pattern": r"\bexec\s*\(",
                "message": "使用exec()函数存在安全风险",
                "severity": Severity.HIGH,
                "suggestion": "避免使用exec()，使用更安全的替代方案"
            }
        }
        
        self._performance_patterns = {
            "loop_in_loop": {
                "pattern": r"for\s+\w+\s+in\s+.+:\s*\n(\s+)for\s+\w+\s+in",
                "message": "嵌套循环可能导致性能问题",
                "severity": Severity.MEDIUM,
                "suggestion": "考虑优化算法减少嵌套"
            },
            "large_list_comprehension": {
                "pattern": r"\[[^\]]{100,}\]",
                "message": "大型列表推导式可能影响可读性",
                "severity": Severity.LOW,
                "suggestion": "考虑使用普通循环"
            }
        }
        
        self._quality_rules = {
            "missing_docstring": {
                "check": self._check_docstring,
                "message": "缺少文档字符串",
                "severity": Severity.LOW,
                "suggestion": "添加文档字符串说明函数用途"
            },
            "long_function": {
                "check": self._check_function_length,
                "message": "函数过长",
                "severity": Severity.MEDIUM,
                "suggestion": "考虑拆分函数"
            },
            "too_many_parameters": {
                "check": self._check_parameters,
                "message": "参数过多",
                "severity": Severity.MEDIUM,
                "suggestion": "考虑使用配置对象"
            },
            "high_complexity": {
                "check": self._check_complexity,
                "message": "函数复杂度过高",
                "severity": Severity.HIGH,
                "suggestion": "简化逻辑或拆分函数"
            }
        }
        
        logger.info("代码审查技能初始化完成")
    
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
            issues = await self.quick_check(
                context.get("code", ""),
                file_path
            )
            
            return {
                "file_path": file_path,
                "issues_count": len(issues),
                "issues": [i.to_dict() for i in issues],
                "has_critical": any(i.severity == Severity.CRITICAL for i in issues),
                "has_security_issues": any(i.category == IssueCategory.SECURITY for i in issues)
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def execute(self, context: Dict[str, Any]) -> SkillResult:
        """
        执行代码审查
        
        Args:
            context: 包含review_request等信息
            
        Returns:
            SkillResult: 审查结果
        """
        review_request = context.get("review_request", {})
        
        if not review_request:
            return SkillResult(
                skill_name=self.name,
                status=SkillStatus.FAILED,
                priority=self.priority,
                message="缺少审查请求",
                errors=["未提供review_request参数"]
            )
        
        operation = review_request.get("operation")
        
        try:
            if operation == "review_file":
                result = await self.review_file(review_request.get("file_path"))
                return SkillResult(
                    skill_name=self.name,
                    status=SkillStatus.SUCCESS,
                    priority=self.priority,
                    message=f"文件审查完成: {review_request.get('file_path')}",
                    data={"review_result": result.to_dict()}
                )
            
            elif operation == "review_directory":
                results = await self.review_directory(
                    review_request.get("directory"),
                    recursive=review_request.get("recursive", True)
                )
                return SkillResult(
                    skill_name=self.name,
                    status=SkillStatus.SUCCESS,
                    priority=self.priority,
                    message=f"目录审查完成: {len(results)} 个文件",
                    data={"review_results": [r.to_dict() for r in results]}
                )
            
            elif operation == "quick_check":
                issues = await self.quick_check(
                    review_request.get("code", ""),
                    review_request.get("file_path", "unknown")
                )
                return SkillResult(
                    skill_name=self.name,
                    status=SkillStatus.SUCCESS,
                    priority=self.priority,
                    message=f"快速检查完成: {len(issues)} 个问题",
                    data={"issues": [i.to_dict() for i in issues]}
                )
            
            elif operation == "security_scan":
                issues = await self.security_scan(
                    review_request.get("file_path"),
                    review_request.get("code")
                )
                return SkillResult(
                    skill_name=self.name,
                    status=SkillStatus.SUCCESS,
                    priority=self.priority,
                    message=f"安全扫描完成: {len(issues)} 个问题",
                    data={"security_issues": [i.to_dict() for i in issues]}
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
            logger.error(f"代码审查失败: {e}")
            return SkillResult(
                skill_name=self.name,
                status=SkillStatus.FAILED,
                priority=self.priority,
                message=f"代码审查异常: {str(e)}",
                errors=[str(e)]
            )
    
    async def review_file(self, file_path: str) -> ReviewResult:
        """
        审查文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            ReviewResult: 审查结果
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        content = path.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        issues: List[CodeIssue] = []
        
        security_issues = await self._check_security_patterns(file_path, content)
        issues.extend(security_issues)
        
        performance_issues = await self._check_performance_patterns(file_path, content)
        issues.extend(performance_issues)
        
        quality_issues = await self._check_quality_rules(file_path, content)
        issues.extend(quality_issues)
        
        style_issues = await self._check_style(file_path, content)
        issues.extend(style_issues)
        
        critical_count = sum(1 for i in issues if i.severity == Severity.CRITICAL)
        high_count = sum(1 for i in issues if i.severity == Severity.HIGH)
        medium_count = sum(1 for i in issues if i.severity == Severity.MEDIUM)
        low_count = sum(1 for i in issues if i.severity == Severity.LOW)
        info_count = sum(1 for i in issues if i.severity == Severity.INFO)
        
        score = max(0, 100 - critical_count * 20 - high_count * 10 - medium_count * 5 - low_count * 2)
        
        summary = self._generate_summary(issues)
        recommendations = self._generate_recommendations(issues)
        
        result = ReviewResult(
            file_path=file_path,
            total_issues=len(issues),
            critical_count=critical_count,
            high_count=high_count,
            medium_count=medium_count,
            low_count=low_count,
            info_count=info_count,
            issues=issues,
            score=score,
            summary=summary,
            recommendations=recommendations
        )
        
        self.review_history.append(result)
        
        return result
    
    async def review_directory(
        self,
        directory: str,
        recursive: bool = True
    ) -> List[ReviewResult]:
        """
        审查目录
        
        Args:
            directory: 目录路径
            recursive: 是否递归
            
        Returns:
            List[ReviewResult]: 审查结果列表
        """
        path = Path(directory)
        
        if not path.exists():
            raise FileNotFoundError(f"目录不存在: {directory}")
        
        results = []
        
        pattern = "**/*.py" if recursive else "*.py"
        
        for file_path in path.glob(pattern):
            if file_path.is_file():
                try:
                    result = await self.review_file(str(file_path))
                    results.append(result)
                except Exception as e:
                    logger.warning(f"审查文件失败 {file_path}: {e}")
        
        return results
    
    async def quick_check(self, code: str, file_path: str = "unknown") -> List[CodeIssue]:
        """
        快速检查代码
        
        Args:
            code: 代码内容
            file_path: 文件路径
            
        Returns:
            List[CodeIssue]: 问题列表
        """
        issues = []
        
        issues.extend(await self._check_security_patterns(file_path, code))
        issues.extend(await self._check_performance_patterns(file_path, code))
        
        return issues
    
    async def security_scan(
        self,
        file_path: Optional[str],
        code: Optional[str]
    ) -> List[CodeIssue]:
        """
        安全扫描
        
        Args:
            file_path: 文件路径
            code: 代码内容
            
        Returns:
            List[CodeIssue]: 安全问题列表
        """
        if file_path and not code:
            code = Path(file_path).read_text(encoding='utf-8')
        
        if not code:
            return []
        
        return await self._check_security_patterns(file_path or "unknown", code)
    
    async def _check_security_patterns(
        self,
        file_path: str,
        content: str
    ) -> List[CodeIssue]:
        """检查安全模式"""
        issues = []
        lines = content.split('\n')
        
        for rule_id, rule in self._security_patterns.items():
            pattern = rule["pattern"]
            
            for i, line in enumerate(lines, 1):
                matches = re.finditer(pattern, line, re.IGNORECASE)
                
                for match in matches:
                    issue = CodeIssue(
                        file_path=file_path,
                        line=i,
                        column=match.start() + 1,
                        category=IssueCategory.SECURITY,
                        severity=rule["severity"],
                        rule_id=f"SEC-{rule_id}",
                        message=rule["message"],
                        suggestion=rule["suggestion"],
                        code_snippet=line.strip(),
                        fix_available=False
                    )
                    issues.append(issue)
        
        return issues
    
    async def _check_performance_patterns(
        self,
        file_path: str,
        content: str
    ) -> List[CodeIssue]:
        """检查性能模式"""
        issues = []
        lines = content.split('\n')
        
        for rule_id, rule in self._performance_patterns.items():
            pattern = rule["pattern"]
            
            matches = re.finditer(pattern, content, re.MULTILINE)
            
            for match in matches:
                line_num = content[:match.start()].count('\n') + 1
                
                issue = CodeIssue(
                    file_path=file_path,
                    line=line_num,
                    column=1,
                    category=IssueCategory.PERFORMANCE,
                    severity=rule["severity"],
                    rule_id=f"PERF-{rule_id}",
                    message=rule["message"],
                    suggestion=rule["suggestion"],
                    code_snippet=lines[line_num - 1].strip() if line_num <= len(lines) else "",
                    fix_available=False
                )
                issues.append(issue)
        
        return issues
    
    async def _check_quality_rules(
        self,
        file_path: str,
        content: str
    ) -> List[CodeIssue]:
        """检查质量规则"""
        issues = []
        
        try:
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    for rule_id, rule in self._quality_rules.items():
                        check_func = rule["check"]
                        result = check_func(node)
                        
                        if result:
                            issue = CodeIssue(
                                file_path=file_path,
                                line=node.lineno,
                                column=node.col_offset + 1,
                                category=IssueCategory.MAINTAINABILITY,
                                severity=rule["severity"],
                                rule_id=f"QUAL-{rule_id}",
                                message=f"{rule['message']}: {node.name} ({result})",
                                suggestion=rule["suggestion"],
                                code_snippet="",
                                fix_available=False
                            )
                            issues.append(issue)
                            
        except SyntaxError:
            pass
        
        return issues
    
    def _check_docstring(self, node: ast.AST) -> Optional[str]:
        """检查文档字符串"""
        docstring = ast.get_docstring(node)
        if not docstring:
            return "缺少文档"
        return None
    
    def _check_function_length(self, node: ast.AST) -> Optional[str]:
        """检查函数长度"""
        if hasattr(node, 'end_lineno') and hasattr(node, 'lineno'):
            length = node.end_lineno - node.lineno
            if length > 50:
                return f"{length} 行"
        return None
    
    def _check_parameters(self, node: ast.AST) -> Optional[str]:
        """检查参数数量"""
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            param_count = len(node.args.args)
            if param_count > 5:
                return f"{param_count} 个参数"
        return None
    
    def _check_complexity(self, node: ast.AST) -> Optional[str]:
        """检查复杂度"""
        complexity = 1
        
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        
        if complexity > 10:
            return f"复杂度 {complexity}"
        return None
    
    async def _check_style(self, file_path: str, content: str) -> List[CodeIssue]:
        """检查代码风格"""
        issues = []
        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            if len(line) > 120:
                issues.append(CodeIssue(
                    file_path=file_path,
                    line=i,
                    column=1,
                    category=IssueCategory.STYLE,
                    severity=Severity.LOW,
                    rule_id="STYLE-line-length",
                    message=f"行过长 ({len(line)} 字符)",
                    suggestion="将行长度限制在120字符以内",
                    code_snippet=line[:50] + "..." if len(line) > 50 else line,
                    fix_available=False
                ))
            
            if line.rstrip() != line:
                issues.append(CodeIssue(
                    file_path=file_path,
                    line=i,
                    column=len(line.rstrip()) + 1,
                    category=IssueCategory.STYLE,
                    severity=Severity.INFO,
                    rule_id="STYLE-trailing-whitespace",
                    message="行尾空白字符",
                    suggestion="移除行尾空白字符",
                    code_snippet=line,
                    fix_available=True,
                    fix_code=line.rstrip()
                ))
        
        return issues
    
    def _generate_summary(self, issues: List[CodeIssue]) -> str:
        """生成摘要"""
        if not issues:
            return "代码质量良好，未发现问题"
        
        critical = sum(1 for i in issues if i.severity == Severity.CRITICAL)
        high = sum(1 for i in issues if i.severity == Severity.HIGH)
        
        if critical > 0:
            return f"发现 {critical} 个严重问题和 {high} 个高优先级问题，需要立即修复"
        elif high > 0:
            return f"发现 {high} 个高优先级问题，建议尽快修复"
        else:
            return f"发现 {len(issues)} 个问题，建议优化"
    
    def _generate_recommendations(self, issues: List[CodeIssue]) -> List[str]:
        """生成建议"""
        recommendations = []
        
        security_issues = [i for i in issues if i.category == IssueCategory.SECURITY]
        if security_issues:
            recommendations.append(f"修复 {len(security_issues)} 个安全问题")
        
        performance_issues = [i for i in issues if i.category == IssueCategory.PERFORMANCE]
        if performance_issues:
            recommendations.append(f"优化 {len(performance_issues)} 个性能问题")
        
        quality_issues = [i for i in issues if i.category == IssueCategory.MAINTAINABILITY]
        if quality_issues:
            recommendations.append(f"改进 {len(quality_issues)} 个代码质量问题")
        
        return recommendations
    
    def get_review_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取审查历史"""
        return [r.to_dict() for r in self.review_history[-limit:]]
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        if not self.review_history:
            return {"total_reviews": 0}
        
        total_issues = sum(r.total_issues for r in self.review_history)
        avg_score = sum(r.score for r in self.review_history) / len(self.review_history)
        
        return {
            "total_reviews": len(self.review_history),
            "total_issues_found": total_issues,
            "average_score": round(avg_score, 2),
            "last_review": self.review_history[-1].to_dict() if self.review_history else None
        }
