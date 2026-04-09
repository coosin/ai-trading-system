"""
从 workspace/BOUNDARIES_AND_LEARNING.md 读取自然语言边界、学习要点与闸门用语。

业务分寸以正文叙述为准；附录中的短语仅用于少量字符串匹配，不写死业务规则本体。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

BOUNDARIES_FILENAME = "BOUNDARIES_AND_LEARNING.md"

DEFAULT_HIGH_RISK_PHRASES: Tuple[str, ...] = ("确认", "立即执行", "批准")
DEFAULT_WORKSPACE_EDIT_PHRASES: Tuple[str, ...] = ("确认修改", "确认编辑", "批准修改")

DEFAULT_FORCE_OPEN_MSG = (
    "检测到高风险动作【强制开仓】。请回复「确认 强制开仓」或「立即执行 强制开仓」后执行。"
)
DEFAULT_FORCE_CLOSE_MSG = (
    "检测到高风险动作【强制平仓】。请回复「确认 强制平仓」或「立即执行 强制平仓」后执行。"
)
DEFAULT_WORKSPACE_EDIT_MSG = (
    "将修改「{rel}」。此项不在宪章/记忆自维护目录内，"
    "请在下一条消息中附上原文意图并写上「确认修改」后再执行。"
)


@dataclass
class WorkspaceBoundaries:
    """从 markdown 解析出的结果；缺失项由调用方使用默认常量。"""

    learning_prose: str = ""
    high_risk_phrases: List[str] = field(default_factory=list)
    workspace_edit_phrases: List[str] = field(default_factory=list)
    force_open_message: Optional[str] = None
    force_close_message: Optional[str] = None
    workspace_edit_message_template: Optional[str] = None


def _split_h2_sections(text: str) -> Dict[str, str]:
    sections: Dict[str, str] = {}
    current: Optional[str] = None
    buf: List[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = line[3:].strip()
            buf = []
        else:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


def _parse_bullet_phrases(section_body: str) -> List[str]:
    out: List[str] = []
    for line in section_body.splitlines():
        s = line.strip()
        if s.startswith("- "):
            t = s[2:].strip().strip("「」\"'")
            if t:
                out.append(t)
    return out


def _subsection(body: str, title_needle: str) -> Optional[str]:
    """取 `### 标题` 下直到下一个 `###` 或文末的段落。"""
    if not body:
        return None
    pattern = re.compile(
        rf"###\s*{re.escape(title_needle)}\s*([\s\S]*?)(?=###\s|\Z)",
        re.MULTILINE,
    )
    m = pattern.search(body)
    if not m:
        return None
    return m.group(1).strip()


def load_workspace_boundaries(workspace_dir: Path) -> WorkspaceBoundaries:
    path = workspace_dir / BOUNDARIES_FILENAME
    if not path.is_file():
        return WorkspaceBoundaries()

    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        logger.debug(f"read boundaries: {e}")
        return WorkspaceBoundaries()

    # 首个 ## 之前的引言（常为定位说明），并入学习正文
    preamble_lines: List[str] = []
    rest_lines: List[str] = []
    seen_h2 = False
    for line in raw.splitlines():
        if line.startswith("## "):
            seen_h2 = True
        if seen_h2:
            rest_lines.append(line)
        else:
            preamble_lines.append(line)
    preamble = "\n".join(preamble_lines).strip()
    body_for_sections = "\n".join(rest_lines) if rest_lines else raw

    sections = _split_h2_sections(body_for_sections)

    learning_parts: List[str] = []
    for key in (
        "主动学习与经验运用",
        "总结经验与教训",
        "行为边界与分寸（叙事）",
        "与代码中硬性条文的区别",
    ):
        for k, v in sections.items():
            if k.startswith(key):
                learning_parts.append(v)
                break
    learning_prose = "\n\n".join(p for p in learning_parts if p).strip()
    if preamble:
        learning_prose = (preamble + "\n\n" + learning_prose).strip() if learning_prose else preamble

    high_risk: List[str] = []
    workspace_ph: List[str] = []
    for k, v in sections.items():
        if "系统闸门用确认用语" in k and "工作区" not in k:
            high_risk = _parse_bullet_phrases(v)
        if "工作区敏感路径修改确认用语" in k:
            workspace_ph = _parse_bullet_phrases(v)

    force_open = None
    force_close = None
    ws_tmpl = None
    for k, v in sections.items():
        if "高风险执行前的沟通" in k:
            fo = _subsection(v, "强制开仓时的提示")
            fc = _subsection(v, "强制平仓时的提示")
            if fo:
                force_open = fo
            if fc:
                force_close = fc
        if "工作区敏感修改前的沟通" in k:
            wt = _subsection(v, "提示模板")
            if wt:
                ws_tmpl = wt

    return WorkspaceBoundaries(
        learning_prose=learning_prose,
        high_risk_phrases=high_risk,
        workspace_edit_phrases=workspace_ph,
        force_open_message=force_open,
        force_close_message=force_close,
        workspace_edit_message_template=ws_tmpl,
    )


def effective_high_risk_phrases(b: WorkspaceBoundaries) -> Tuple[str, ...]:
    if b.high_risk_phrases:
        return tuple(b.high_risk_phrases)
    return DEFAULT_HIGH_RISK_PHRASES


def effective_workspace_phrases(b: WorkspaceBoundaries) -> Tuple[str, ...]:
    if b.workspace_edit_phrases:
        return tuple(b.workspace_edit_phrases)
    return DEFAULT_WORKSPACE_EDIT_PHRASES
