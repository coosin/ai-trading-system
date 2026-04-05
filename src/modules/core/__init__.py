"""
核心模块 - 系统核心组件
包含记忆管理、自动恢复、风险控制、稳定性分析等核心功能
"""

from .base_module import BaseModule, SingletonModule

from .user_intent_recognizer import (
    UserIntentRecognizer,
    UserIntentType,
    ExtractedIntent,
    AutoMemoryRecorder,
    user_intent_recognizer,
    auto_memory_recorder
)

from .system_stability_analyzer import (
    SystemStabilityAnalyzer,
    StabilityLevel,
    DecisionType,
    StabilityMetrics,
    StabilityDecision
)

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
