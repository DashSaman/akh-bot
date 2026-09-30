# Social Platforms

| Platform | Status | Mechanism |
|---|---|---|
| Telegram (publish) | READY — awaiting bot token + staging channel | Bot API sendMessage/editMessageText, ledger-idempotent |
| Telegram (ingest) | READY — awaiting api_id/hash/session (Telethon) | reconcile polling + forward metadata |
| Website | LIVE (preview mode) | server-rendered + SEO layer |
| X | NOT_CONFIGURED | adapter placeholder; official API preferred; disabled cleanly without creds |
| Instagram | NOT_CONFIGURED | planned: branded cards via Pillow + caption |
| Threads | NOT_CONFIGURED | planned |
| Facebook | NOT_CONFIGURED | planned |

Status vocabulary: NOT_CONFIGURED / WAITING_FOR_AUTH / CONNECTED / ERROR / PAUSED.
A missing credential disables that platform cleanly — never crashes the system.
Platform-specific content variants are mandatory (no copy-paste everywhere).
