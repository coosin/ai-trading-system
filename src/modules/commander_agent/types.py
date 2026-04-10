"""司令部智能体运行时类型（与 OpenClaw agent-loop 概念对齐，非 TS 运行时移植）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CommanderRoute:
    """路由结果：显式子智能体或默认主链路。"""

    specialist_id: Optional[str] = None
    """非空时表示走显式子智能体，body 为去掉前缀后的任务正文。"""
    body: str = ""
    raw: str = ""


@dataclass
class CommanderContextBundle:
    """上下文组装：对应 OpenClaw 的 context assembly（会话 + 主动记忆）。"""

    recent_block: str = ""
    active_memory_block: str = ""
    executor_input: str = ""
    brain_input: str = ""

    def trace(self) -> Dict[str, Any]:
        return {
            "has_recent": bool(self.recent_block),
            "has_active_memory": bool(self.active_memory_block),
        }


@dataclass
class CommanderRunMeta:
    """单次运行的可观测元数据（便于审计 / capabilities）。"""

    phases: List[str] = field(default_factory=list)
    route: Optional[CommanderRoute] = None
    context: Optional[CommanderContextBundle] = None
