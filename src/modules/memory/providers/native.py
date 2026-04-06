from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from src.modules.core.optimized_memory_system import OptimizedMemorySystem

from .base import RecallItem, RecallResult


def _tokenize(text: str) -> List[str]:
    t = (text or "").lower()
    tokens: List[str] = []
    buf = []
    for ch in t:
        if ch.isalnum() or ch in {"_", "/"}:
            buf.append(ch)
        else:
            if buf:
                tokens.append("".join(buf))
                buf = []
    if buf:
        tokens.append("".join(buf))
    return [x for x in tokens if x]


def _bm25_scores(query: str, docs: List[Tuple[str, str]], k1: float = 1.2, b: float = 0.75) -> Dict[str, float]:
    q_tokens = _tokenize(query)
    if not q_tokens or not docs:
        return {doc_id: 0.0 for doc_id, _ in docs}

    doc_tokens = {doc_id: _tokenize(content) for doc_id, content in docs}
    df: Counter[str] = Counter()
    for tokens in doc_tokens.values():
        unique = set(tokens)
        for tok in unique:
            df[tok] += 1

    N = len(docs)
    avgdl = sum(len(toks) for toks in doc_tokens.values()) / max(N, 1)
    scores: Dict[str, float] = {doc_id: 0.0 for doc_id, _ in docs}
    for doc_id, tokens in doc_tokens.items():
        tf = Counter(tokens)
        dl = len(tokens)
        denom_norm = k1 * (1 - b + b * (dl / max(avgdl, 1e-9)))
        s = 0.0
        for q in q_tokens:
            if q not in tf:
                continue
            n_q = df.get(q, 0)
            idf = math.log(1 + (N - n_q + 0.5) / (n_q + 0.5))
            freq = tf[q]
            s += idf * (freq * (k1 + 1)) / (freq + denom_norm)
        scores[doc_id] = s
    return scores


def _keyword_overlap_scores(query: str, docs: List[Tuple[str, str]]) -> Dict[str, float]:
    q = set(_tokenize(query))
    if not q:
        return {doc_id: 0.0 for doc_id, _ in docs}
    scores: Dict[str, float] = {}
    for doc_id, content in docs:
        t = set(_tokenize(content))
        overlap = len(q.intersection(t))
        scores[doc_id] = overlap / max(len(q), 1)
    return scores


@dataclass
class NativeMemoryProvider:
    backend: OptimizedMemorySystem

    async def store(
        self,
        content: str,
        *,
        scope: str,
        category: str,
        importance: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        # Gateway already maps category/layer; provider is used for recall pipeline.
        md = dict(metadata or {})
        md.setdefault("scope", scope)
        md.setdefault("category", category)
        return await self.backend.remember(content=content, importance=importance, metadata=md)

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
    ) -> RecallResult:
        # Pull a wider candidate pool from backend
        candidates = await self.backend.recall(query=query, limit=max(limit * 8, 50))
        scope_name = (scope or "").strip()

        docs: List[Tuple[str, str]] = []
        meta_map: Dict[str, Dict[str, Any]] = {}
        imp_map: Dict[str, float] = {}
        acc_map: Dict[str, int] = {}
        for e in candidates:
            md = dict(getattr(e, "metadata", {}) or {})
            if scope_name and str(md.get("scope", "global")) != scope_name:
                continue
            importance = float(getattr(e, "importance", 0.0))
            if importance < float(min_importance):
                continue
            docs.append((e.id, e.content))
            meta_map[e.id] = md
            imp_map[e.id] = importance
            acc_map[e.id] = int(getattr(e, "access_count", 0))

        kw_scores = _keyword_overlap_scores(query, docs)
        bm25 = _bm25_scores(query, docs)

        def norm(values: Dict[str, float]) -> Dict[str, float]:
            if not values:
                return {}
            mx = max(values.values()) if values else 0.0
            if mx <= 0:
                return {k: 0.0 for k in values}
            return {k: v / mx for k, v in values.items()}

        kw_n = norm(kw_scores)
        bm25_n = norm(bm25)

        mode = (retrieval_mode or "hybrid").lower()
        items: List[RecallItem] = []
        for doc_id, content in docs:
            reasons: List[str] = []
            score = 0.0
            if mode in {"bm25", "hybrid"}:
                score += bm25_weight * bm25_n.get(doc_id, 0.0)
                if bm25.get(doc_id, 0.0) > 0:
                    reasons.append("bm25")
            if mode in {"keyword", "hybrid"}:
                # treat keyword overlap as a cheap "vector-like" proxy for now
                score += vector_weight * kw_n.get(doc_id, 0.0)
                if kw_scores.get(doc_id, 0.0) > 0:
                    reasons.append("keyword_overlap")

            # importance and access count boost
            score += 0.1 * min(1.0, imp_map.get(doc_id, 0.0))
            score += 0.02 * min(1.0, acc_map.get(doc_id, 0) / 10.0)
            if score >= float(min_score):
                items.append(
                    RecallItem(
                        id=doc_id,
                        content=content,
                        importance=imp_map.get(doc_id, 0.5),
                        metadata=meta_map.get(doc_id, {}),
                        score=score,
                        reasons=reasons,
                    )
                )

        items.sort(key=lambda x: x.score, reverse=True)
        items = items[:limit]
        trace = {
            "provider": "native",
            "mode": mode,
            "candidate_pool": len(docs),
            "weights": {"vector_weight": vector_weight, "bm25_weight": bm25_weight},
            "min_score": min_score,
        }
        return RecallResult(items=items, trace=trace)

    async def forget(self, memory_id: str) -> bool:
        return await self.backend.forget(memory_id)

    def get_stats(self) -> Dict[str, Any]:
        return self.backend.get_stats()

