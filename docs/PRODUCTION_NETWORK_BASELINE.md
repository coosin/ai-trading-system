# Production Network Baseline

This baseline locks the network/proxy behavior that was validated in troubleshooting:

- Clash in `Rule` mode
- Main selector fixed to `♻️ 自动选择`
- DNS hardened for mixed exchange/API traffic (fake-ip + safe nameservers + okx filters)
- Container proxy env fixed to `OPENCLAW_*_PROXY=http://host.docker.internal:7890`
- Runtime probes for OKX/Binance/CoinGecko/Coinbase/Kraken via proxy + TLS verify

## One-command baseline apply

```bash
python3 scripts/production_network_baseline.py --apply
```

## Check-only mode

```bash
python3 scripts/production_network_baseline.py --check-only
```

## Suggested ops routine

1. Run apply command after any Clash subscription refresh or host changes.
2. Run check-only in daily cron/monitor.
3. Alert if `BASELINE_CHECK=FAIL`.

## Notes

- `api.okx.com` may still be unstable in this environment; production should use `www.okx.com`.
- Binance may have regional restriction behavior depending on line/node. The probe validates current proxy egress behavior.
