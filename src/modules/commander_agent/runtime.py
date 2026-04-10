"""
司令部智能体运行时：对齐 OpenClaw「agent loop」阶段划分（intake → context → route → execute → persist），
实现落在 Python 与现有 MainController 子系统上，而非嵌入 pi-agent-core。
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from src.modules.commander_agent.specialists import (
    list_specialist_definitions,
    parse_explicit_specialist,
    run_specialist,
)
from src.modules.commander_agent.types import CommanderContextBundle, CommanderRunMeta, CommanderRoute

if TYPE_CHECKING:
    from src.modules.main_controller import MainController

logger = logging.getLogger(__name__)

LOOP_VERSION = "2026.04.10"


def strip_user_utterance_for_memory_query(raw: str) -> str:
    """与 AICommandExecutor._strip_user_utterance_for_routing 一致。"""
    text = (raw or "").strip()
    for sep in ("【司令部宪章】", "【记忆节选】"):
        if sep in text:
            text = text.split(sep, 1)[0].strip()
    return text[:2000]


async def active_memory_block(mc: "MainController", command: str) -> str:
    """OpenClaw active-memory 风格：按当前句召回结构化记忆（可环境关闭）。"""
    if not getattr(mc, "memory_gateway", None):
        return ""
    env = str(os.environ.get("OPENCLAW_COMMANDER_ACTIVE_MEMORY", "1") or "").strip().lower()
    if env in {"0", "false", "no", "off"}:
        return ""
    utter = strip_user_utterance_for_memory_query(command)
    if len(utter) < 4:
        return ""
    try:
        timeout = float(os.environ.get("OPENCLAW_COMMANDER_ACTIVE_MEMORY_TIMEOUT_SEC", "2.5") or 2.5)
    except ValueError:
        timeout = 2.5
    try:
        max_chars = int(os.environ.get("OPENCLAW_COMMANDER_ACTIVE_MEMORY_MAX_CHARS", "1200") or 1200)
    except ValueError:
        max_chars = 1200
    max_chars = max(200, min(max_chars, 8000))

    async def _recall() -> List[Any]:
        return await mc.memory_gateway.retrieve_memories(
            query=utter[:500],
            min_importance=0.2,
            limit=5,
        )

    try:
        rows = await asyncio.wait_for(_recall(), timeout=timeout)
    except (asyncio.TimeoutError, Exception):
        return ""
    if not rows:
        return ""
    lines: List[str] = ["[司令部·相关记忆]"]
    used = len(lines[0]) + 1
    seen: set = set()
    for r in rows:
        c = (getattr(r, "content", None) or "").strip().replace("\n", " ")
        if not c or c in seen:
            continue
        seen.add(c)
        imp = float(getattr(r, "importance", 0.0) or 0.0)
        line = f"- ({imp:.2f}) {c[:280]}"
        if used + len(line) + 1 > max_chars:
            break
        lines.append(line)
        used += len(line) + 1
    if len(lines) <= 1:
        return ""
    return "\n".join(lines)


async def assemble_context(mc: "MainController", command: str, source: str) -> CommanderContextBundle:
    bundle = CommanderContextBundle()
    recent_lines: List[str] = []
    if getattr(mc, "memory_gateway", None):
        try:
            recent = await mc.memory_gateway.recent_conversation(scope=f"channel:{source}", limit=6)
            if recent:
                recent_lines = [f"- {m.content}" for m in recent[-4:]]
        except Exception:
            pass
    if recent_lines:
        bundle.recent_block = "\n".join(recent_lines)

    try:
        bundle.active_memory_block = await active_memory_block(mc, command)
    except Exception:
        bundle.active_memory_block = ""

    base = command
    if bundle.recent_block:
        bundle.brain_input = f"{base}\n\n[最近对话上下文]\n{bundle.recent_block}"
    else:
        bundle.brain_input = base
    if bundle.active_memory_block:
        bundle.brain_input = f"{bundle.brain_input}\n\n{bundle.active_memory_block}"

    bundle.executor_input = base
    if bundle.active_memory_block:
        bundle.executor_input = f"{base}\n\n{bundle.active_memory_block}"
    return bundle


async def store_user_turn(mc: "MainController", command: str, source: str) -> None:
    if not getattr(mc, "memory_gateway", None):
        return
    try:
        await mc.memory_gateway.add_memory(
            memory_type="conversation",
            content=f"[user@{source}] {command}",
            metadata={"scope": f"channel:{source}", "role": "user"},
            source_module="main_controller",
            importance=0.35,
            tags=["conversation"],
        )
    except Exception:
        pass


async def store_assistant_turn(mc: "MainController", result_dict: Dict[str, Any], source: str) -> None:
    if not getattr(mc, "memory_gateway", None) or not isinstance(result_dict, dict):
        return
    try:
        resp_text = result_dict.get("response") or result_dict.get("message") or ""
        if not resp_text:
            return
        src = str(result_dict.get("source") or "assistant")
        await mc.memory_gateway.add_memory(
            memory_type="conversation",
            content=f"[assistant@{src}] {resp_text}",
            metadata={"scope": f"channel:{source}", "role": "assistant"},
            source_module="main_controller",
            importance=0.35,
            tags=["conversation"],
        )
    except Exception:
        pass


def commander_capabilities(mc: "MainController") -> Dict[str, Any]:
    base = "/api/v1/modules/commander"
    subsystems = {
        "ai_command_executor": getattr(mc, "ai_command_executor", None) is not None,
        "telegram_bot": getattr(mc, "telegram_bot", None) is not None,
        "strategy_manager": getattr(mc, "strategy_manager", None) is not None,
        "data_integration": getattr(mc, "data_integration", None) is not None,
        "data_source_hub": getattr(mc, "data_source_hub", None) is not None,
        "trading_monitor": getattr(mc, "trading_monitor", None) is not None,
        "market_intelligence": (
            getattr(mc, "market_intelligence", None) or getattr(mc, "market_intelligence_engine", None)
        )
        is not None,
        "execution_gateway": getattr(mc, "execution_gateway", None) is not None,
        "stop_loss_manager": getattr(mc, "stop_loss_manager", None) is not None,
    }
    skills = sorted(list(mc.skill_manager.skills.keys())) if getattr(mc, "skill_manager", None) else []
    plugins = sorted(list(mc.plugin_manager.plugins.keys())) if getattr(mc, "plugin_manager", None) else []
    return {
        "design": "commander_agent_runtime",
        "openclaw_parity_note": (
            "Phases mirror docs/concepts/agent-loop (intake/context/route/execute/persist); "
            "sub-agents map to specialists.* — not embedded pi-agent-core."
        ),
        "agent_loop_version": LOOP_VERSION,
        "specialists": list_specialist_definitions(),
        "entrypoints": {
            "process_user_command": True,
            "build_ai_commander_snapshot": hasattr(mc, "build_ai_commander_snapshot"),
            "run_ai_commander_chores": hasattr(mc, "run_ai_commander_chores"),
        },
        "memory": {
            "memory_gateway": getattr(mc, "memory_gateway", None) is not None,
            "active_memory_env": str(os.environ.get("OPENCLAW_COMMANDER_ACTIVE_MEMORY", "1")),
        },
        "skills": skills,
        "plugins": plugins,
        "subsystems": subsystems,
        "api": {
            "snapshot": f"{base}/snapshot",
            "dispatch": f"{base}/dispatch",
            "chores": f"{base}/chores",
            "audit": f"{base}/audit",
            "capabilities": f"{base}/capabilities",
            "surface_registry": f"{base}/surface/registry",
            "surface_channels": f"{base}/surface/channels",
            "memory_status": f"{base}/memory/status",
            "memory_workspace": f"{base}/memory/workspace",
        },
    }


class CommanderAgentRuntime:
    """
    单入口司令部运行时：显式阶段划分，便于对照 OpenClaw 文档与扩展子智能体。
    """

    LOOP_VERSION = LOOP_VERSION  # noqa: PIE794 — alias module singleton for callers

    async def run(self, mc: "MainController", command: str, source: str = "system") -> Dict[str, Any]:
        meta = CommanderRunMeta(phases=["intake"])
        raw = (command or "").strip()
        if not raw:
            return {"success": False, "response": "空指令", "source": "commander_agent_runtime"}

        meta.phases.append("persist_user")
        await store_user_turn(mc, command, source)

        route = parse_explicit_specialist(command)
        meta.route = route
        meta.phases.append("route")

        if route.specialist_id:
            meta.phases.append("execute_specialist")
            out = await run_specialist(mc, route.specialist_id, route.body, source)
            if isinstance(out, dict):
                out.setdefault("commander_loop", meta.phases)
                out.setdefault("commander_meta", {"route": route.specialist_id, "loop_version": self.LOOP_VERSION})
                await store_assistant_turn(mc, out, source)
            return out

        meta.phases.append("assemble_context")
        ctx = await assemble_context(mc, command, source)
        meta.context = ctx
        meta.phases.append("execute_main")

        if getattr(mc, "ai_command_executor", None):
            try:
                result = await mc.ai_command_executor.process_input(ctx.executor_input, source=source)
                if isinstance(result, dict):
                    result.setdefault("source", "ai_command_executor")
                    result.setdefault("commander_loop", meta.phases)
                    result.setdefault(
                        "commander_meta",
                        {"route": "main", "context": ctx.trace(), "loop_version": self.LOOP_VERSION},
                    )
                    await store_assistant_turn(mc, result, source)
                    return result
                wrapped = {
                    "success": True,
                    "response": str(result),
                    "source": "ai_command_executor",
                    "commander_loop": meta.phases,
                    "commander_meta": {"route": "main", "context": ctx.trace(), "loop_version": self.LOOP_VERSION},
                }
                await store_assistant_turn(mc, wrapped, source)
                return wrapped
            except Exception as e:
                logger.error("指令执行器处理失败(source=%s): %s", source, e)

        meta.phases.append("fallback_brain")
        brain = await mc.get_primary_ai_brain()
        if brain and hasattr(brain, "process_user_command"):
            try:
                result = await brain.process_user_command(ctx.brain_input)
                if isinstance(result, dict):
                    result.setdefault("source", getattr(brain, "__class__", type(brain)).__name__)
                    result.setdefault("commander_loop", meta.phases)
                    result.setdefault(
                        "commander_meta",
                        {"route": "fallback_brain", "context": ctx.trace(), "loop_version": self.LOOP_VERSION},
                    )
                    await store_assistant_turn(mc, result, source)
                    return result
                out = {
                    "success": True,
                    "response": str(result),
                    "commander_loop": meta.phases,
                    "commander_meta": {"route": "fallback_brain", "context": ctx.trace(), "loop_version": self.LOOP_VERSION},
                }
                await store_assistant_turn(mc, out, source)
                return out
            except Exception as e:
                logger.error("核心大脑处理失败(source=%s): %s", source, e)

        if getattr(mc, "natural_language_interface", None):
            result = await mc.natural_language_interface.process_and_respond(command, {"source": source})
            if isinstance(result, dict):
                result.setdefault("source", "natural_language_interface")
                result.setdefault("commander_loop", meta.phases)
                await store_assistant_turn(mc, result, source)
                return result
            out = {
                "success": True,
                "response": str(result),
                "source": "natural_language_interface",
                "commander_loop": meta.phases,
            }
            await store_assistant_turn(mc, out, source)
            return out

        return {
            "success": False,
            "response": "核心大脑未就绪",
            "source": "none",
            "commander_loop": meta.phases,
        }
