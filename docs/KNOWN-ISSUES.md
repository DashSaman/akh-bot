# Known Issues

- **Credentials missing (BLOCKED_EXTERNAL):** GLM API key, Telegram bot token,
  staging chat id, Telethon session → pipeline runs rules-only; publishing waits.
- Docker Compose plugin absent on the host → deployment uses `docker run`
  (equivalent flags; compose file kept for portability).
- Baseline claim extraction (LLM-off mode) is conservative: most claims stay
  UNVERIFIED — acceptable by design; GLM mode refines them.
- Velocity metric is a 1-hour approximation, not a rolling window.
- Admin login throttle is per-process in-memory (single-container deployment: fine;
  revisit if workers > 1).
- `docs/images/` real screenshots pending first UI access via tunnel.
