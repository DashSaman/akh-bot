# Resource Baseline (measured 2026-09-30, host Hetzner 2 vCPU / 3.7 GB)

## akhbot-app container

| Metric | Value | Target | Verdict |
|---|---|---|---|
| Idle + workers RAM | **45.9 MiB** | ≤200 MB | ✅ 23% of budget |
| CPU (idle + workers) | ≤0.31% | low | ✅ |
| Peak observed (build time excluded) | ~46 MiB | ≤300 MB processing | ✅ |
| Docker image | 288 MB | small | ✅ (python:3.12-slim + telethon/pillow) |
| DB size | ~36 KB (schema + 29 live items) | negligible | ✅ |
| Disk added | <350 MB (image + volume) | — | ✅ 21 GB free before |

## Host impact
- RAM available before/after deploy: 2.2 Gi → 2.2 Gi (no measurable change).
- No memory limit enforced by default (avoids OOM); measured usage justifies none.
- Logs rotated (10 MB × 3). Backups retained 14 days (~KB-scale).

## Notes
- Processing peaks (GLM calls, clustering) will add modestly; LLM work is API-bound,
  not RAM-bound. Re-measure after credentials are wired and real volume flows.
- Swap remains 0 (owner approval required to change — see PREFLIGHT-HETZNER.md).
