"""
技能系统 - 赋予交易系统自我认知和维护能力

核心技能：
1. 系统自检 - 诊断系统健康状态
2. 性能分析 - 分析交易表现
3. 风险评估 - 评估当前风险
4. 优化建议 - 提供改进建议
5. 自动修复 - 自动修复常见问题
6. 系统维护 - AI自主维护系统稳定性
7. 代码编辑 - AI代码编辑和修改能力
8. 代码开发 - AI自主开发新功能
9. 代码审查 - AI代码审查能力
10. 外部资源 - AI获取外部资源能力
11. 网络搜索 - AI搜索外部资源能力
12. 自助学习 - AI自主学习和知识积累
"""

from .skill_base import SkillBase, SkillResult, SkillPriority, SkillStatus
from .skill_manager import SkillManager
from .system_diagnosis_skill import SystemDiagnosisSkill
from .performance_analysis_skill import PerformanceAnalysisSkill
from .risk_assessment_skill import RiskAssessmentSkill
from .optimization_skill import OptimizationSkill
from .auto_repair_skill import AutoRepairSkill
from .system_maintenance_skill import SystemMaintenanceSkill, HealthLevel, MaintenanceAction
from .code_editor_skill import CodeEditorSkill, EditOperation, CodeLanguage, CodeChange, CodeAnalysis
from .code_developer_skill import CodeDeveloperSkill, DevelopmentType, GeneratedCode, DevelopmentPlan
from .code_reviewer_skill import CodeReviewerSkill, Severity, IssueCategory, CodeIssue, ReviewResult
from .external_resource_skill import ExternalResourceSkill, ResourceType, RequestMethod, ResourceResponse
from .web_search_skill import WebSearchSkill, SearchEngine, SearchType, SearchResult, SearchResponse
from .self_learning_skill import SelfLearningSkill, KnowledgeType, LearningSource, KnowledgeItem, LearningSession

__all__ = [
    'SkillBase',
    'SkillResult',
    'SkillPriority',
    'SkillStatus',
    'SkillManager',
    'SystemDiagnosisSkill',
    'PerformanceAnalysisSkill',
    'RiskAssessmentSkill',
    'OptimizationSkill',
    'AutoRepairSkill',
    'SystemMaintenanceSkill',
    'HealthLevel',
    'MaintenanceAction',
    'CodeEditorSkill',
    'EditOperation',
    'CodeLanguage',
    'CodeChange',
    'CodeAnalysis',
    'CodeDeveloperSkill',
    'DevelopmentType',
    'GeneratedCode',
    'DevelopmentPlan',
    'CodeReviewerSkill',
    'Severity',
    'IssueCategory',
    'CodeIssue',
    'ReviewResult',
    'ExternalResourceSkill',
    'ResourceType',
    'RequestMethod',
    'ResourceResponse',
    'WebSearchSkill',
    'SearchEngine',
    'SearchType',
    'SearchResult',
    'SearchResponse',
    'SelfLearningSkill',
    'KnowledgeType',
    'LearningSource',
    'KnowledgeItem',
    'LearningSession',
]
