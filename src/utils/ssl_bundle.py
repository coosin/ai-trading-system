"""
合并 CA 供 aiohttp 等客户端使用。

当环境变量将 SSL_CERT_FILE 指向不完整或仅含企业根的 bundle 时，单独使用会导致
「unable to get local issuer certificate」。本模块始终以 certifi 为基底，再追加
OPENCLAW_SSL_CA_BUNDLE 以及首个可用的 SSL_CERT_FILE / REQUESTS_CA_BUNDLE / CURL_CA_BUNDLE
（去重后合并）。
"""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from pathlib import Path
from typing import List, Optional, Set

import certifi

logger = logging.getLogger(__name__)

_merged_path_cache: str | None = None
_merge_inputs_cache: str | None = None


def _project_root() -> Path:
    """…/ai-trading-system（本文件位于 src/utils/ssl_bundle.py）。"""
    return Path(__file__).resolve().parent.parent.parent


def _merged_ca_output_path(digest: str) -> Path:
    """
    选择可写目录写入合并 PEM（避免仅用 /tmp 时被其它 uid 占坑导致 PermissionError）。

    优先级：
    1. OPENCLAW_SSL_MERGED_CA_DIR
    2. $XDG_CACHE_HOME/openclaw/ssl
    3. ~/.cache/openclaw/ssl
    4. 项目内 data/.ssl_merged_ca（不依赖 HOME 权限，适合 systemd / 受限用户）
    5. /tmp/openclaw_ssl_<uid>/
    """
    override = (os.getenv("OPENCLAW_SSL_MERGED_CA_DIR") or "").strip()
    candidates: List[Path] = []
    if override:
        candidates.append(Path(override))
    xdg = (os.getenv("XDG_CACHE_HOME") or "").strip()
    if xdg:
        candidates.append(Path(xdg) / "openclaw" / "ssl")
    home = Path.home()
    if str(home) != "/" and home.exists():
        candidates.append(home / ".cache" / "openclaw" / "ssl")
    try:
        candidates.append(_project_root() / "data" / ".ssl_merged_ca")
    except Exception:
        pass
    candidates.append(Path(tempfile.gettempdir()) / f"openclaw_ssl_uid_{os.getuid()}")

    last_err: Optional[OSError] = None
    for base in candidates:
        try:
            base.mkdir(parents=True, mode=0o700, exist_ok=True)
            return base / f"merged_ca_{digest}.pem"
        except OSError as e:
            last_err = e
            logger.debug("CA merge: skip dir %s (%s)", base, e)
            continue
    if last_err is not None:
        raise OSError(last_err.errno, f"CA merge: no writable dir: {last_err}") from last_err
    raise OSError(0, "CA merge: no writable dir")


def openclaw_merged_cafile() -> str:
    """返回 ssl.create_default_context(cafile=...) 可用的 PEM 路径。"""
    global _merged_path_cache, _merge_inputs_cache

    certifi_path = os.path.realpath(certifi.where())
    chunks: List[bytes] = [Path(certifi_path).read_bytes().strip()]
    seen: Set[str] = {certifi_path}

    def _append_file(label: str, raw: str) -> None:
        p = raw.strip()
        if not p or not os.path.isfile(p):
            return
        rp = os.path.realpath(p)
        if rp in seen:
            return
        seen.add(rp)
        chunks.append(Path(p).read_bytes().strip())
        logger.debug("CA merge: append %s -> %s", label, p)

    extra = (os.getenv("OPENCLAW_SSL_CA_BUNDLE") or "").strip()
    if extra:
        _append_file("OPENCLAW_SSL_CA_BUNDLE", extra)
    for envk in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        v = (os.getenv(envk) or "").strip()
        if v:
            _append_file(envk, v)

    if len(chunks) == 1:
        return certifi_path

    key = "|".join(sorted(seen))
    if _merged_path_cache and _merge_inputs_cache == key and os.path.isfile(_merged_path_cache):
        return _merged_path_cache

    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    merged = _merged_ca_output_path(digest)
    body = b"\n".join(chunks) + b"\n"
    try:
        tmp = merged.with_suffix(merged.suffix + ".tmp")
        tmp.write_bytes(body)
        os.replace(tmp, merged)
    except OSError as e:
        logger.warning(
            "CA merge: write failed (%s); falling back to certifi only at %s",
            e,
            certifi_path,
        )
        _merge_inputs_cache = None
        _merged_path_cache = None
        return certifi_path
    _merged_path_cache = str(merged)
    _merge_inputs_cache = key
    logger.info("CA merge: certifi + extras -> %s (n=%d)", merged, len(chunks))
    return _merged_path_cache
