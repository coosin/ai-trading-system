"""
记忆与 Workspace 上下文策略（规划层）：谁在读什么、读多少、何时按需召回。

设计原则（回答「10 条还是 50 条」）：
- 硬注入（最近对话）宜小：**8～12 轮**足够维持指代与情绪连续；再大边际收益低、噪声与成本升。
- 软注入（向量/BM25 召回）宜 **per 块 4～8 条**；多块拼接总 Budget 控制在本模块的 max_chars。
- 规则/偏好：**3～5 条**高重要性即可（黑名单、授权口径）。
- 任务型：在执行交易/策略/风控类意图时，额外用 **1～2 条定向 query** 拉「经验/教训」，limit 略大于闲聊。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# --- 启动期：只读 workspace 人格/职责文件（顺序 meaningful）---
DEFAULT_STARTUP_WORKSPACE_FILES: Tuple[str, ...] = (
    "COMMANDER_PROFILE.md",
)

# 运行期允许通过 API/网关读写的治理文件（与 MemoryGateway.ALLOWED 对齐）
GOVERNANCE_WORKSPACE_FILES: Tuple[str, ...] = (
    "COMMANDER_PROFILE.md",
)

# 默认对话注入（可被 memory.context_policy 覆盖）
DEFAULT_CONTEXT_POLICY: Dict[str, Any] = {
    "conversation_recent_limit": 12,
    "conversation_recall_limit": 8,
    "rules_recall_query": "黑名单 授权 偏好 风控",
    "rules_recall_limit": 5,
    "line_max_chars": 220,
    "recall_line_max_chars": 240,
    "startup_bundle_max_total_chars": 12000,
    "startup_max_chars_per_file": 4000,
    "task_memory": {
        "trade": {
            "queries": ["开平仓 止损 止盈 滑点 经验 教训", "SLTP 风控"],
            "limit_each": 5,
        },
        "risk": {
            "queries": ["风险 强平 止损 黑名单"],
            "limit_each": 5,
        },
        "strategy_create": {
            "queries": ["策略 开发 回测 教训", "参数 过拟合"],
            "limit_each": 4,
        },
        "strategy_optimize": {
            "queries": ["策略 优化 回测 教训"],
            "limit_each": 4,
        },
        "backtest": {
            "queries": ["回测 样本外 过拟合 教训"],
            "limit_each": 4,
        },
        "market_analysis": {
            "queries": ["市场 观察 数据质量"],
            "limit_each": 4,
        },
    },
    "decision_engine_recall": {
        "trade_experience_limit": 12,
        "strategy_performance_limit": 6,
        "lesson_query": "经验教训 止损 止盈 滑点",
        "lesson_limit": 8,
    },
}


def get_effective_context_policy(
    config_manager: Any = None,
    channel: Optional[str] = None,
) -> Dict[str, Any]:
    merged = dict(DEFAULT_CONTEXT_POLICY)
    try:
        if config_manager is not None:
            mem = config_manager.get_config_sync("memory", None, {}) or {}
            override = mem.get("context_policy") if isinstance(mem, dict) else None
            if isinstance(override, dict):
                for k, v in override.items():
                    if k == "channels":
                        # Per-channel overrides (e.g. telegram); merged after base policy.
                        continue
                    if k == "task_memory" and isinstance(v, dict) and isinstance(merged.get("task_memory"), dict):
                        base_tm = dict(merged["task_memory"])
                        for ak, av in v.items():
                            if isinstance(av, dict) and isinstance(base_tm.get(ak), dict):
                                m = dict(base_tm[ak])
                                m.update(av)
                                base_tm[ak] = m
                            else:
                                base_tm[ak] = av
                        merged["task_memory"] = base_tm
                    elif k == "decision_engine_recall" and isinstance(v, dict):
                        m = dict(merged.get("decision_engine_recall") or {})
                        m.update(v)
                        merged["decision_engine_recall"] = m
                    else:
                        merged[k] = v
    except Exception as e:
        logger.debug(f"context_policy merge failed: {e}")
    try:
        if config_manager is not None and channel:
            mem = config_manager.get_config_sync("memory", None, {}) or {}
            cp = mem.get("context_policy") if isinstance(mem, dict) else None
            chmap = cp.get("channels") if isinstance(cp, dict) else None
            ch_ov = chmap.get(str(channel).strip()) if isinstance(chmap, dict) else None
            if isinstance(ch_ov, dict):
                for k, v in ch_ov.items():
                    if k == "channels":
                        continue
                    if k == "task_memory" and isinstance(v, dict) and isinstance(merged.get("task_memory"), dict):
                        base_tm = dict(merged["task_memory"])
                        for ak, av in v.items():
                            if isinstance(av, dict) and isinstance(base_tm.get(ak), dict):
                                m = dict(base_tm[ak])
                                m.update(av)
                                base_tm[ak] = m
                            else:
                                base_tm[ak] = av
                        merged["task_memory"] = base_tm
                    elif k == "decision_engine_recall" and isinstance(v, dict):
                        m = dict(merged.get("decision_engine_recall") or {})
                        m.update(v)
                        merged["decision_engine_recall"] = m
                    else:
                        merged[k] = v
    except Exception as e:
        logger.debug(f"context_policy channel merge failed: {e}")
    return merged


def get_startup_file_list(config_manager: Any = None) -> List[str]:
    try:
        if config_manager is not None:
            mem = config_manager.get_config_sync("memory", None, {}) or {}
            cp = mem.get("context_policy") if isinstance(mem, dict) else None
            if isinstance(cp, dict) and isinstance(cp.get("startup_workspace_files"), list):
                return [str(x) for x in cp["startup_workspace_files"] if x]
    except Exception:
        pass
    return list(DEFAULT_STARTUP_WORKSPACE_FILES)


def load_startup_workspace_bundle(
    workspace_path: Path,
    *,
    config_manager: Any = None,
) -> str:
    """拼接启动期只读 workspace 摘要（缺失文件跳过）。"""
    policy = get_effective_context_policy(config_manager)
    names = get_startup_file_list(config_manager)
    max_total = int(policy.get("startup_bundle_max_total_chars", 12000))
    cap_each = int(policy.get("startup_max_chars_per_file", 4000))
    parts: List[str] = []
    used = 0
    for name in names:
        p = workspace_path / name
        if not p.is_file():
            continue
        try:
            raw = p.read_text(encoding="utf-8", errors="replace").strip()
        except OSError as e:
            logger.debug(f"read workspace {name}: {e}")
            continue
        if not raw:
            continue
        chunk = raw[:cap_each]
        if len(raw) > cap_each:
            chunk += "\n…(截断)"
        block = f"### {name}\n{chunk}"
        if used + len(block) > max_total:
            remain = max_total - used - 20
            if remain > 200:
                parts.append(f"### {name}\n{chunk[:remain]}…(总Budget截断)")
            break
        parts.append(block)
        used += len(block)
    if not parts:
        base = ""
    else:
        base = (
        "【Workspace 人格与职责摘要（启动时读入；叙述型偏好，非实时行情数字）】\n"
        + "\n\n".join(parts)
        )

    # Also include short daily memory snippets (today + yesterday), mirroring
    # the reference system's startup behavior without turning it into rigid rules.
    daily_parts: List[str] = []
    daily_dir = workspace_path / "memory" / "daily"
    if daily_dir.is_dir():
        for d in (0, 1):
            date_key = (datetime.now() - timedelta(days=d)).strftime("%Y-%m-%d")
            p = daily_dir / f"{date_key}.md"
            if not p.is_file():
                continue
            try:
                raw = p.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                continue
            if not raw:
                continue
            snippet = raw[-1400:] if len(raw) > 1400 else raw
            daily_parts.append(f"### daily/{date_key}.md\n{snippet}")

    if daily_parts:
        daily_block = "【近期日记忆片段（today+yesterday）】\n" + "\n\n".join(daily_parts)
        if base:
            return (base + "\n\n" + daily_block).strip()
        return daily_block

    return base


def task_memory_config(intent_action: str, config_manager: Any = None) -> Optional[Dict[str, Any]]:
    act = (intent_action or "chat").strip().lower()
    pol = get_effective_context_policy(config_manager)
    tm = pol.get("task_memory") or {}
    if not isinstance(tm, dict):
        return None
    return tm.get(act)


async def format_task_memory_block(
    memory_gateway: Any,
    intent_action: str,
    *,
    user_input: str,
    config_manager: Any = None,
) -> str:
    """按任务类型追加结构化记忆中的定向召回（按需）。"""
    if memory_gateway is None or not hasattr(memory_gateway, "retrieve_memories"):
        return ""
    cfg = task_memory_config(intent_action, config_manager)
    if not cfg:
        return ""
    queries = cfg.get("queries") or []
    lim = int(cfg.get("limit_each", 5))
    parts: List[str] = []
    policy = get_effective_context_policy(config_manager)
    rline = int(policy.get("recall_line_max_chars", 240))
    for q in queries[:3]:
        try:
            items = await memory_gateway.retrieve_memories(query=str(q), limit=lim)
        except Exception:
            continue
        if not items:
            continue
        parts.append(f"**query: {q}**")
        for m in items[:lim]:
            try:
                c = str(getattr(m, "content", "") or (m.get("content") if isinstance(m, dict) else ""))
            except Exception:
                c = str(m)
            if c.strip():
                parts.append(f"- {c.strip()[:rline]}")
    if not parts:
        return ""
    hint = (user_input or "").strip()[:120]
    return (
        "\n【任务相关记忆片段（"
        + str(intent_action)
        + "；按需参考，与用户原话「"
        + hint
        + "」相关时再用）】\n"
        + "\n".join(parts)
    )
