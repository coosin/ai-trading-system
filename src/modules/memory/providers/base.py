from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol


@dataclass
class RecallItem:
    id: str
    content: str
    importance: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    reasons: List[str] = field(default_factory=list)


@dataclass
class RecallResult:
    items: List[RecallItem]
    trace: Dict[str, Any] = field(default_factory=dict)


class MemoryProvider(Protocol):
    async def store(
        self,
        content: str,
        *,
        scope: str,
        category: str,
        importance: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str: ...

    async def recall(
        self,
        query: str,
        *,
        scope: Optional[str] = None,
        limit: int = 10,
        min_importance: float = 0.0,
        retrieval_mode: str = "hybrid",
        vector_weight: float = 0.7,
        bm25_weight: float = 0.3,
        min_score: float = 0.0,
    ) -> RecallResult: ...

    async def forget(self, memory_id: str) -> bool: ...

    def get_stats(self) -> Dict[str, Any]: ...

