"""
从主配置注入进程级网络代理环境变量，供 LLM/OKX/数据采集等统一读取 HTTP(S)_PROXY。

说明（架构边界）：
- **首选**：在**服务器宿主机**运行的 **Clash / mihomo** 上开启 **TUN + auto-route + rules**，
  在代理软件内完成「绑定虚拟网卡、系统路由接管、域名/IP/GEOIP 分流」；详见仓库
  ``deploy/HOST_CLASH_EGRESS.md``。
- 本进程侧通过 **HTTP_PROXY / NO_PROXY** 等，让 aiohttp/httpx 等与宿主机策略**互补**
  （尤其 Docker bridge 下未继承宿主机路由时，显式指向 ``host.docker.internal:7890``）。
- 无宿主机代理时，可选 **Compose sidecar** 或 **network_mode: host**（须评估安全与端口）。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)


def docker_loopback_proxy_use_gateway_host() -> bool:
    """
    是否在 Docker 内把代理 host 127.0.0.1 / localhost 改写为 host.docker.internal。

    -默认：在 /.dockerenv 下为 True（bridge 容器访问宿主机代理）。
    - host 网络：compose 可设 OPENCLAW_DOCKER_NETWORK_HOST=1，此时不改写（与 .env 里当前代理地址一致）。
    - 显式关闭：OPENCLAW_PROXY_LOOPBACK_REWRITE=0
    """
    if os.getenv("OPENCLAW_DOCKER_NETWORK_HOST", "").strip().lower() in ("1", "true", "yes", "on"):
        return False
    if os.getenv("OPENCLAW_PROXY_LOOPBACK_REWRITE", "").strip().lower() in ("0", "false", "no", "off"):
        return False
    return os.path.exists("/.dockerenv")


def _env_credentials(gp: Dict[str, Any]) -> tuple[str, str]:
    user_env = str(gp.get("username_env") or "").strip()
    pwd_env = str(gp.get("password_env") or "").strip()
    u = os.getenv(user_env, "") if user_env else ""
    p = os.getenv(pwd_env, "") if pwd_env else ""
    return u, p


def build_proxy_url_from_config(cfg: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    根据 ``proxy`` 段构造 ``http(s)://[user:pass@]host:port``。
    未启用或缺少 host/port 时返回 None。
    """
    if not isinstance(cfg, dict):
        return None
    if not cfg.get("enabled"):
        return None
    gp = cfg.get("global_proxy")
    if not isinstance(gp, dict) or not gp.get("enabled"):
        return None
    host = gp.get("host")
    port = gp.get("port")
    if not host or port is None:
        return None
    try:
        port_i = int(port)
    except (TypeError, ValueError):
        return None
    ptype = str(gp.get("proxy_type") or "http").strip().lower()
    if ptype not in ("http", "https", "socks5", "socks4"):
        ptype = "http"
    user, pwd = _env_credentials(gp)
    if user or pwd:
        auth = f"{quote(user, safe='')}:{quote(pwd, safe='')}@"
    else:
        auth = ""
    return f"{ptype}://{auth}{host}:{port_i}"


def _merge_no_proxy_env(px: Dict[str, Any]) -> None:
    """合并 bypass_domains、no_proxy_extra 与现有 NO_PROXY（用于「直连白名单」分流）。"""
    if not px.get("merge_no_proxy_from_config", True):
        return
    parts: List[str] = []
    for key in ("bypass_domains", "no_proxy_extra"):
        raw = px.get(key)
        if isinstance(raw, list):
            parts.extend(str(x).strip() for x in raw if str(x).strip())
    cur = (os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or "").strip()
    if cur:
        parts.extend(p.strip() for p in cur.replace(";", ",").split(",") if p.strip())
    seen: set[str] = set()
    merged: List[str] = []
    for p in parts:
        pl = p.lower()
        if pl not in seen:
            seen.add(pl)
            merged.append(p)
    if not merged:
        return
    joined = ",".join(merged)
    os.environ["NO_PROXY"] = joined
    os.environ["no_proxy"] = joined
    logger.info("已合并 NO_PROXY（共 %s 项）", len(merged))


def apply_proxy_environment_from_merged_config(root: Dict[str, Any]) -> None:
    """
    将 ``proxy`` 段反映到环境变量（可选，尊重已有变量）。

    - ``proxy.apply_to_process_env`` 默认 true
    - ``proxy.respect_existing_env`` 默认 true：已存在 HTTP_PROXY/HTTPS_PROXY 时不覆盖
    - ``proxy.force_override_env`` 为 true 时：强制覆盖已有 HTTP(S)_PROXY（用于「主配置优先」）
    """
    if not isinstance(root, dict):
        return
    px = root.get("proxy")
    if not isinstance(px, dict):
        return
    if not px.get("enabled", True):
        return
    if not px.get("apply_to_process_env", True):
        return
    respect = bool(px.get("respect_existing_env", True))
    force = bool(px.get("force_override_env", False))
    _merge_no_proxy_env(px)

    url = build_proxy_url_from_config(px)
    if not url:
        logger.debug("主配置 proxy 未生成可用 URL（跳过进程环境注入）")
        return
    for key in ("HTTP_PROXY", "HTTPS_PROXY"):
        if respect and not force and os.getenv(key):
            continue
        os.environ[key] = url
        logger.info("已从主配置注入 %s", key)
    # 可选 ALL_PROXY（socks）
    gp = px.get("global_proxy") if isinstance(px.get("global_proxy"), dict) else {}
    ptype = str((gp or {}).get("proxy_type") or "http").strip().lower()
    if ptype.startswith("socks"):
        if not (respect and not force and os.getenv("ALL_PROXY")):
            os.environ["ALL_PROXY"] = url
            logger.info("已从主配置注入 ALL_PROXY")

    okx = px.get("okx") if isinstance(px.get("okx"), dict) else {}
    if okx.get("proxy_only") is True:
        os.environ["OPENCLAW_OKX_PROXY_ONLY"] = "1"
        logger.info("已从主配置设置 OPENCLAW_OKX_PROXY_ONLY=1")
    elif okx.get("proxy_only") is False:
        os.environ.pop("OPENCLAW_OKX_PROXY_ONLY", None)
    if okx.get("ignore_env_proxy") is True:
        os.environ["OPENCLAW_OKX_IGNORE_ENV_PROXY"] = "1"
        logger.info("已从主配置设置 OPENCLAW_OKX_IGNORE_ENV_PROXY=1")
    elif okx.get("ignore_env_proxy") is False:
        os.environ.pop("OPENCLAW_OKX_IGNORE_ENV_PROXY", None)


def egress_architecture_notes(px: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """产品/架构说明：网卡级与分流的责任划分（供验收 API 展示）。"""
    px = px if isinstance(px, dict) else {}
    model = str(px.get("egress_model") or "process_env").strip().lower()
    return {
        "egress_model": model,
        "host_clash_operational_guide": "deploy/HOST_CLASH_EGRESS.md",
        "process_env_scope": (
            "本应用设置 HTTP_PROXY/HTTPS_PROXY/NO_PROXY；仅影响 aiohttp/httpx/requests 等支持的客户端。"
        ),
        "nic_level_enforcement": (
            "网卡级接管与强制分流：在服务器宿主机 Clash/mihomo 上启用 TUN（auto-route、rules）；"
            "勿在交易进程内实现。容器未使用 host 网络时，可继续用 HTTP_PROXY 指向宿主机 mixed-port。"
        ),
        "intelligent_splitting": (
            "域名/IP/GEOIP 分流一律写在宿主机代理配置的 rules；"
            "本仓库 NO_PROXY 合并仅作直连白名单补充。"
        ),
        "recommended_compose": (
            "无宿主机 Clash 时：可选 compose egress-sidecar；有宿主机 Clash 时：优先 TUN + "
            "host.docker.internal 指向宿主机 mixed-port。"
        ),
    }


def proxy_url_for_data_sources(config_manager: Any) -> str:
    """
    供无法注入环境时的同步回退：优先环境变量，其次 ConfigManager 快照。
    """
    for key in (
        "HTTPS_PROXY",
        "https_proxy",
        "HTTP_PROXY",
        "http_proxy",
        "OPENCLAW_HTTPS_PROXY",
        "OPENCLAW_HTTP_PROXY",
    ):
        env_u = (os.getenv(key) or "").strip()
        if env_u:
            return env_u
    try:
        if config_manager and hasattr(config_manager, "get_config_sync"):
            px = config_manager.get_config_sync("proxy", {}) or {}
            u = build_proxy_url_from_config(px if isinstance(px, dict) else {})
            if u:
                return u
    except Exception:
        pass
    return ""
