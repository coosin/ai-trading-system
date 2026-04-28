"""
核心模块 - 系统核心组件
包含记忆管理、自动恢复、风险控制、稳定性分析等核心功能
"""

from .base_module import BaseModule, SingletonModule

try:
    from .user_intent_recognizer import (
        UserIntentRecognizer,
        UserIntentType,
        ExtractedIntent,
        AutoMemoryRecorder,
        user_intent_recognizer,
        auto_memory_recorder,
    )
except Exception:  # optional in lightweight/script contexts
    UserIntentRecognizer = None
    UserIntentType = None
    ExtractedIntent = None
    AutoMemoryRecorder = None
    user_intent_recognizer = None
    auto_memory_recorder = None

try:
    from .system_stability_analyzer import (
        SystemStabilityAnalyzer,
        StabilityLevel,
        DecisionType,
        StabilityMetrics,
        StabilityDecision,
    )
except Exception:  # optional in lightweight/script contexts
    SystemStabilityAnalyzer = None
    StabilityLevel = None
    DecisionType = None
    StabilityMetrics = None
    StabilityDecision = None

__all__ = [
    "BaseModule",
    "SingletonModule",
    "UserIntentRecognizer",
    "UserIntentType",
    "ExtractedIntent",
    "AutoMemoryRecorder",
    "user_intent_recognizer",
    "auto_memory_recorder",
    "SystemStabilityAnalyzer",
    "StabilityLevel",
    "DecisionType",
    "StabilityMetrics",
    "StabilityDecision"
]
