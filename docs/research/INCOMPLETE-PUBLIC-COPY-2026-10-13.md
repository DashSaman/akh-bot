# Incident: incomplete Telegram public copy — 2026-10-13

## Symptom
Owner screenshot showed a real `@RastehNews` publication ending mid-claim with an ellipsis and a naked source CTA:

- Telegram remote_id **2636**, Story **5803**, IranWire Telegram.
- Public copy ended with `…` and then `بیشتر بخوانید:` without the actual source link.
- A second recent IranWire Story **5780 / remote_id 2623** had the same underlying overlap/CTA issue.
- Historical IranWire Story **5305 / remote_id 2439** exposed an orphan `بیشتر بخوانید:` line even though its headline itself was complete.

Read-only 24h ledger scan at incident time: **413** SENT ledger revisions, **25** story headlines ending in an artificial ellipsis, **4** rows whose stored Telegram variant contained `بیشتر بخوانید`, **2** with a standalone empty CTA line. Revisions with the same remote_id are EDIT history, not additional Telegram messages.

## Root cause
The deterministic source path contained the full sentence in the claim/detail, but public rendering did this in the wrong order:

1. source URL/foreign handle was stripped;
2. paragraph dedup ran while the first line was the clipped headline;
3. the **longer, complete detail** was considered a duplicate and removed;
4. the old `squash_duplicate_lead` repair ran too late;
5. URL stripping left the standalone text `بیشتر بخوانید:`.

Headline fitting also deliberately created `…` after a hard character cap, which violated the owner's self-contained-news requirement.

## Permanent prevention
Merged PR #8 / main release content:
- complete-sentence headline fitting: prefer an actual sentence boundary and never manufacture an ellipsis clip;
- remove standalone read-more/continue/detail CTAs after URL and foreign-handle sanitization;
- repair overlapping headline/body **before** paragraph dedup;
- if a full headline is repeated at the start of detail, preserve only the genuinely new suffix sentence;
- final public body gate rejects any payload whose headline still ends in `…` / `...`;
- exact IranWire screenshot fixture plus multi-sentence suffix regression.

Verification before merge: 20 focused tests PASS; **502 full tests PASS**; governance PASS; GitHub Actions GREEN. Production image:
`akhbot-app:release-1d97299e`, immutable revision
`1d97299ec59d4a759bfcc432fb97f0d6cce18dc3`, Docker HEALTHY.

## Repair of already-public messages
`scripts/repair_incomplete_public_copy.py` is **dry-run by default**. It rebuilds public copy strictly from the existing canonical Event/Claims, preserves the existing caution marker, validates the new text, versions the Story draft, and enqueues `publish_edit` only. It never enqueues `publish_send`, never invents facts, and does not modify RawItems/Claims.

Applied only to explicitly reviewed incidents:
- Story 5803 -> same remote_id **2636**
- Story 5780 -> same remote_id **2623**
- Story 5305 -> same remote_id **2439**

All three `publish_edit` jobs completed `done` with zero errors; corresponding new publication ledger rows have status SENT and the **same remote_id**. Canonical Story headline/lead columns were then synchronized with the corrected draft so future lifecycle edits cannot resurrect the old ellipsis. SQLite `PRAGMA integrity_check` remained `ok`.

Pre-edit public-copy backup:
`/data/backups/public-copy-repair-2026-10-13T184118_0000.json`
(mode 0600 inside Rasteh data volume).

## Operational rule
Do not mass-edit every historical headline merely because it once contained an ellipsis. Future copy is fail-closed. Historical repair requires a canonical complete claim, a successful dry-run, a same-message SENT target, final body-gate PASS, and an explicit bounded story list. No synthetic public news is used for acceptance.
