"""
司令部用户可见回复的「根部护栏」。

问题根因：纯 LLM 闲聊会编造「[调用：workspace_read…]」、假目录树、假价位等；
提示词约束可被模型忽略。此处对**最终返回给渠道的文本**做确定性后处理，与提示词互补。

关闭护栏（仅排障）：环境变量 OPENCLAW_REPLY_GUARD=0
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict

# 模型常编的假工具标注（本栈不会把工具调用以这种字符串形式回显给用户）
# 允许 [ 与「调用」之间插空格 / 零宽字符；允许括号内换行后再闭合
_FAKE_SQUARE = re.compile(r"\[[\s\u200b\u00a0]*调用[：:][\s\S]*?\]")
_FAKE_CORNER = re.compile(r"【\s*调用[：:][^】]*】")
_FAKE_FULLWIDTH = re.compile(r"［\s*调用[：:][^\］]*］")
# 独占一行、无括号的「调用：xxx」表演行
_FAKE_BARE_LINE = re.compile(r"(?m)^\s*调用[：:][^\n]+\s*$")
# markdown 代码块：内嵌典型幻觉目录（本仓库主代码在 src/modules/，无 src/data_source 等顶层名）
_FAKE_TREE_MARKERS = (
    "src/data_source",
    "src/analysis/",
    "src/trading/",
    "├── data_source",
    "├── analysis/",
    "├── trading/",
)
_MARKDOWN_FENCE = re.compile(r"```(?:[a-zA-Z0-9_-]*)?\s*\r?\n([\s\S]*?)```", re.MULTILINE)


def reply_guard_enabled() -> bool:
    raw = str(os.environ.get("OPENCLAW_REPLY_GUARD", "1") or "").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _scrub_hallucinated_repo_fences(text: str) -> str:
    """将含典型假路径的「目录树」代码块替换为短说明（保留其它代码块）。"""

    def repl(m: re.Match) -> str:
        inner = m.group(1)
        if not any(marker in inner for marker in _FAKE_TREE_MARKERS):
            return m.group(0)
        tree_like = (
            "├──" in inner
            or "└──" in inner
            or inner.lstrip().startswith("/")
        )
        if not tree_like and "src/" not in inner:
            return m.group(0)
        return (
            "（已省略模型编造的目录树；本仓库主代码在 **src/modules/**，"
            "请以 **docs/ENGINEERING.md** 或真实 workspace_read 结果为准。）"
        )

    return _MARKDOWN_FENCE.sub(repl, text)


def sanitize_commander_reply_text(text: str) -> str:
    """去掉假工具标注、压缩空行；不改动真实行情/读盘正文中的合法内容。"""
    if not isinstance(text, str):
        return text
    if not reply_guard_enabled():
        return text
    t = text
    t = _scrub_hallucinated_repo_fences(t)
    t = _FAKE_SQUARE.sub("", t)
    t = _FAKE_CORNER.sub("", t)
    t = _FAKE_FULLWIDTH.sub("", t)
    t = _FAKE_BARE_LINE.sub("", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t


def sanitize_commander_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """浅拷贝 dict，仅处理 response 字符串（及嵌套里常见的 message 字段）。"""
    if not isinstance(result, dict):
        return result
    if not reply_guard_enabled():
        return result
    out: Dict[str, Any] = dict(result)
    r = out.get("response")
    if isinstance(r, str):
        out["response"] = sanitize_commander_reply_text(r)
    msg = out.get("message")
    if isinstance(msg, str):
        out["message"] = sanitize_commander_reply_text(msg)
    return out


def sanitize_any_response_payload(payload: Any) -> Any:
    """CommanderAgentRuntime 等处的 dict / str 统一入口。"""
    if isinstance(payload, dict):
        return sanitize_commander_result(payload)
    if isinstance(payload, str) and reply_guard_enabled():
        return sanitize_commander_reply_text(payload)
    return payload
