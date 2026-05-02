# Tuning Channel (Manual + AI Proposal)

This folder contains a *semi-automated* tuning pipeline:

1. Fetch recent decision-traces from:
   - `/api/v1/modules/commander/decision-traces`
2. Fetch current execution-guard config from:
   - `/api/v1/ai/guards`
3. Generate an **AI-style proposal** (heuristics) for bounded tuning.
4. Manual approval (type `yes`) then apply via:
   - `POST /api/v1/ai/guards`
5. Validate behavior for ~30-60 minutes using:
   - trace funnel changes
   - realized realized quality over a realized horizon (default 60 minutes)
6. If triggers fail, rollback only the changed keys.

Run:

```bash
python3 /home/cool/ai-trading-system/scripts/tuning/tuning_channel.py --validation-minutes 45
```

