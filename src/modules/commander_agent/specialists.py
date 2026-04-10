"""
子智能体（OpenClaw sub-agents 的 Python 对等物）

上游实现：独立 session + sessions_spawn + announce；本系统在同一进程内用
「命名专家 + 显式前缀」映射到已有子系统（行情智能、主对话模型等），避免重复造 pi-agent 运行时。
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from src.modules.commander_agent.types import CommanderRoute

if TYPE_CHECKING:
    from src.modules.main_controller import MainController

logger = logging.getLogger(__name__)


def list_specialist_definitions() -> List[Dict[str, Any]]:
    """供 capabilities / 运维查阅：子智能体 id 与对接模块说明。"""
    return [
        {
            "id": "main",
            "role": "主链路",
            "maps_to": "AICommandExecutor → 主脑 → NLI",
            "notes": "默认；交易/策略/行情意图优先走指令执行器。",
        },
        {
            "id": "chat",
            "role": "对话子智能体",
            "maps_to": "get_primary_ai_brain().process_user_command",
            "notes": "跳过指令执行器，仅补充对话（测试或纯闲聊）。",
        },
        {
            "id": "research",
            "role": "研究子智能体",
            "maps_to": "MarketIntelligenceEngine.get_symbol_view（若可用）",
            "notes": "从任务正文解析币对，返回结构化盘面/摘要视图。",
        },
    ]


def parse_explicit_specialist(raw: str) -> CommanderRoute:
    """解析显式子智能体前缀；无前缀则 specialist_id 为 None。"""
    s = (raw or "").strip()
    for prefix in ("/司令部子任务:", "/subagent:"):
        if s.startswith(prefix):
            rest = s[len(prefix) :].strip()
            idx = rest.find(":")
            if idx <= 0:
                return CommanderRoute(specialist_id=None, body=s, raw=raw)
            sid = rest[:idx].strip().lower()
            body = rest[idx + 1 :].strip()
            return CommanderRoute(specialist_id=sid or None, body=body, raw=raw)
    return CommanderRoute(specialist_id=None, body=s, raw=raw)


_RE_PAIR = re.compile(
    r"\b(BTC|ETH|SOL|BNB|XRP|DOGE|ADA|AVAX|DOT|MATIC|LINK|LTC)[-/]?(USDT|USD)?\b",
    re.IGNORECASE,
)


def _default_symbol_from_text(text: str) -> str:
    t = (text or "").strip()
    m = _RE_PAIR.search(t)
    if m:
        return f"{m.group(1).upper()}/USDT"
    if "比特币" in t:
        return "BTC/USDT"
    if "以太坊" in t:
        return "ETH/USDT"
    return "BTC/USDT"


async def run_specialist(
    mc: "MainController",
    specialist_id: str,
    body: str,
    source: str,
) -> Dict[str, Any]:
    """执行单个子智能体分支（显式路由时调用）。"""
    sid = (specialist_id or "").strip().lower()
    if sid == "chat":
        brain = await mc.get_primary_ai_brain()
        if brain and hasattr(brain, "process_user_command"):
            result = await brain.process_user_command(body)
            if isinstance(result, dict):
                result.setdefault("source", getattr(brain, "__class__", type(brain)).__name__)
                result.setdefault("commander_specialist", "chat")
                return result
            return {
                "success": True,
                "response": str(result),
                "source": "specialist_chat",
                "commander_specialist": "chat",
            }
        return {
            "success": False,
            "response": "核心大脑未就绪",
            "source": "specialist_chat",
            "commander_specialist": "chat",
        }

    if sid == "research":
        mi = getattr(mc, "market_intelligence", None) or getattr(mc, "market_intelligence_engine", None)
        if not mi:
            return {
                "success": False,
                "response": "市场智能（MarketIntelligence）未就绪，无法执行 research 子智能体。",
                "source": "specialist_research",
                "commander_specialist": "research",
            }
        sym = _default_symbol_from_text(body)
        try:
            if hasattr(mi, "get_symbol_view"):
                view = await mi.get_symbol_view(sym, include_snapshot=True)
                text = ""
                if hasattr(view, "summary"):
                    text = str(getattr(view, "summary", "") or "").strip()
                if hasattr(view, "to_dict"):
                    d = view.to_dict()
                    text = text or str(d.get("summary") or "")[:2000]
                if not text:
                    text = str(view)[:2000]
                return {
                    "success": True,
                    "response": f"[{sym}] 研究子智能体视图摘要：\n{text}",
                    "source": "specialist_research",
                    "commander_specialist": "research",
                    "data": {"symbol": sym},
                }
        except Exception as e:
            logger.warning("research specialist failed: %s", e)
            return {
                "success": False,
                "response": f"研究子智能体执行失败: {e}",
                "source": "specialist_research",
                "commander_specialist": "research",
            }
        return {
            "success": False,
            "response": "市场智能模块缺少 get_symbol_view",
            "source": "specialist_research",
            "commander_specialist": "research",
        }

    if sid == "executor":
        exe = getattr(mc, "ai_command_executor", None)
        if not exe or not hasattr(exe, "process_input"):
            return {
                "success": False,
                "response": "指令执行器未就绪",
                "source": "specialist_executor",
                "commander_specialist": "executor",
            }
        result = await exe.process_input(body, source=source)
        if isinstance(result, dict):
            result.setdefault("source", "ai_command_executor")
            result.setdefault("commander_specialist", "executor")
            return result
        return {
            "success": True,
            "response": str(result),
            "source": "ai_command_executor",
            "commander_specialist": "executor",
        }

    return {
        "success": False,
        "response": f"未知子智能体: {specialist_id}。可用: chat, research, executor。",
        "source": "commander_route",
        "commander_specialist": None,
    }
