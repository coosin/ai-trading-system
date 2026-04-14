#!/usr/bin/env sh
# 容器内网络快检：路由、DNS、ping、HTTPS（不依赖 root；由 Dockerfile 提供 ping/ip）。
# 宿主机执行：docker exec openclaw-trading sh /app/scripts/diagnose_container_net.sh
set +e

echo "=== identity ==="
id
hostname 2>/dev/null || true

echo "=== default route / interfaces (head) ==="
ip route 2>/dev/null | head -8 || echo "(no ip route)"

echo "=== DNS www.okx.com ==="
getent hosts www.okx.com 2>/dev/null | head -3 || echo "(getent failed)"

echo "=== ping host.docker.internal (bridge 模式应有；host 网络可能无此名) ==="
ping -c1 -W2 host.docker.internal 2>&1

echo "=== ping docker bridge gateway (常见 172.x.0.1) ==="
gw=$(ip route 2>/dev/null | awk '/default/ {print $3; exit}')
if [ -n "$gw" ]; then
  ping -c1 -W2 "$gw" 2>&1
else
  echo "(no default gw)"
fi

echo "=== ping 1.1.1.1 ==="
ping -c1 -W2 1.1.1.1 2>&1

echo "=== curl https://www.okx.com (honors HTTP(S)_PROXY from env) ==="
curl -sS -o /dev/null -w "http_code=%{http_code} time_total=%{time_total}s\n" --max-time 20 https://www.okx.com/ 2>&1

echo "=== proxy env ==="
printf "HTTP_PROXY=%s\nHTTPS_PROXY=%s\nALL_PROXY=%s\nNO_PROXY=%s\n" \
  "${HTTP_PROXY:-}" "${HTTPS_PROXY:-}" "${ALL_PROXY:-}" "${NO_PROXY:-}"

echo "=== done ==="
