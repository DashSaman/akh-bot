# Rasteh scoped host retention / نگه‌داری محدود دیسک راسته

## Scope / محدوده
The previous shared-host policy (commits 78f7052 and 1775049) included generic
temporary files, global package caches and PV-Growth resources. Those historical
executions are recorded in Git and /opt/akhbot/audit/host-disk-20261012; they are
not evidence of compliance with the current Rasteh-only request.
This revision removes those foreign/global deletion paths.

فارسی: سیاست قبلی دامنه‌ای گسترده‌تر از راسته داشت. در این نسخه حذف منابع
PV-Growth، کش عمومی و tmp ناشناس حذف شده است. گزارش‌های قبلی حفظ می‌شوند؛
پاک‌سازی جدید فقط با محدودهٔ زیر اجرا می‌شود.

## Allowlist / فهرست مجاز
- Rasteh DB backups directly in /var/lib/docker/volumes/akhbot_data/_data/backups:
  strict akhbot timestamp names and pre-* timestamp names; age greater than five
  days. Always preserve the two newest DB files. Both must have the Rasteh schema
  and pass SQLite quick_check; uncertainty/corruption/empty backups blocks deletion.
  Strictly named Rasteh footer/duplicate JSON repair backups use the same age rule.
- Explicit disposable artifacts: /opt/akhbot/drill-013, drill-014, shadow-p3,
  dr-20261003T175910Z, dr-20261003T175923Z, dr-src.db and the data media-cache.
- Known test clones /tmp or /var/tmp/{cleanchk,cleanchk2,ghchk,relchk}; only
  directly located rasteh-* or akhbot-* .log/.tmp/.part/.exit artifacts.
  Generic tmp*, pytest*, node cache and arbitrary .log files are excluded.
- Apache rotations ONLY with rasteh/akhbot access/error names; foreign vhost and
  shared Apache logs remain excluded. Explicit owner exception: dated, compressed
  /var/log/x-ui/3xui-YYYY-MM-DDTHH-MM-SS.mmm.log.gz archives. No active logs.
- Docker images ONLY tagged akhbot-app and akhbot-qa-watch, older than five days,
  unreferenced by ANY running/stopped container. Preserve the two newest distinct
  image IDs and the newest unused distinct rollback. Aliases do not consume slots.
  Removal is by exact tag without force; no global prune.
- Strict akhbot_dr_YYYYMMDDTHHMMSSZ local volumes older than five days, without
  any running/stopped container mount reference, and no open files/mounts.
  Preserve the newest DR restore point from the previous recovery policy.
- Shared journald exception requested by owner: archived segments vacuumed to
  five days / 160M; configured caps 200M system and 100M runtime with 2G free.
  Versioned zzz-rasteh-retention-5d.conf is the final effective override of older
  conflicting retention files; legacy files are preserved.

فارسی: بکاپ‌های بیش از پنج روز با حفظ دو نسخهٔ جدید و معتبر؛ فقط آثار آزمایشی
نام‌برده و tmp با مالکیت معلوم؛ تصاویر و volumeهای نام‌گذاری‌شدهٔ راسته بدون
وابستگی کانتینر؛ حفظ rollback و آخرین DR. لاگ فعال و منابع ناشناس حذف نمی‌شوند.
برای Apache فقط نام لاگ راسته مجاز است. آرشیو فشردهٔ تاریخ‌دار x-ui و journal
استثناهای صریح درخواست مالک هستند.

## Guards / محافظت‌ها
Dry-run is the default. --apply is required for deletion. The internal nonblocking
flock covers manual and timer runs with the same /run/lock path. Every deletion
rechecks age, scope and liveness. Reject symlinks in ancestors/children, hardlinks,
special files, mounted trees (including same-filesystem bind mounts via mountinfo),
fresh children, oversized trees and incomplete /proc visibility. Check file
descriptors, mmap inode references and process working directories. Deletions
anchor the parent directory with O_NOFOLLOW descriptors. Python 3.10 uses a
verified parent cwd for symlink-resistant rmtree; Python 3.11+ uses dir_fd.

Before any --apply deletion, a durable START audit must be written. Each file
action is appended before continuing; a FINISH JSON includes planned/actions,
protected backups, exclusions and measured free bytes before/after. The report
lives at /data/reports/disk-maintenance.jsonl in the live data volume and is also
printed to journal. No secret/config/environment contents are recorded.
A failed inventory aborts; skips never mean a successful deletion. A lock file
is coordination state and is not removed on an age schedule.

فارسی: قفل مشترک، جلوگیری از symlink و mount، کنترل فایل باز و پوشهٔ کاری،
بازبینی بلافاصله قبل از حذف و ثبت ممیزی پایدار فعال است. شکست بازرسی Docker
یا نبود دسترسی کامل مانع حذف می‌شود. فایل قفل فعال را نباید با سن آن پاک کرد.

## Installation / نصب
Install only these versioned Rasteh files after tests and dry-run review:
```bash
install -m 0750 ops/host_disk_retention.py /usr/local/sbin/rasteh-host-disk-retention.py
install -m 0644 ops/rasteh-host-disk-maintenance.service /etc/systemd/system/
install -m 0644 ops/rasteh-host-disk-maintenance.timer /etc/systemd/system/
install -m 0644 ops/zzz-rasteh-retention-5d.conf /etc/systemd/journald.conf.d/
systemd-analyze verify /etc/systemd/system/rasteh-host-disk-maintenance.{service,timer}
systemctl daemon-reload
systemctl enable --now rasteh-host-disk-maintenance.timer
```
Timer: daily 03:40 UTC (07:10 Tehran), plus 0–10 minutes randomized delay.
Persistent missed runs catch up. No Docker/Apache/xray/VPN or application restart,
port, firewall, route or network change. Existing journald effective five-day
and size caps already match; the override normalizes persisted configuration.
Manual use:
```bash
python3 /usr/local/sbin/rasteh-host-disk-retention.py
python3 /usr/local/sbin/rasteh-host-disk-retention.py --apply
```
Disable only this maintenance with systemctl disable --now
rasteh-host-disk-maintenance.timer.

فارسی: هر روز ساعت ۰۷:۱۰ تهران با حداکثر ده دقیقه تأخیر تصادفی اجرا می‌شود.
تغییر یا توقف سرویس‌های برنامه، Docker، Apache، VPN یا شبکه انجام نمی‌شود.

## Verification / بررسی
Regression tests exercise real filesystem deletion/protection, dry-run, lock,
audit symlink refusal, corrupt/empty DB backups and mount guards. Docker boundary
fixtures cover foreign repos, aliases, stopped container refs and newest rollback.
Run python -m pytest tests -q; verify the runtime Python 3.10 timestamp and
directory deletion branch as well. Compare root df, container IDs/start/restart/
ports, unrelated service states/PIDs, akhbot /health and /ready, read-only SQLite
integrity_check, queue status/failures and the latest successful Telegram SEND.

فارسی: تست کامل و مقایسهٔ سلامت قبل/بعد الزامی است. اعداد آزادسازی از df
اندازه‌گیری می‌شوند؛ تغییر هم‌زمان فضای سایر برنامه‌ها ممکن است در اختلاف
خالص اثر بگذارد. حذف‌ها برگشت‌پذیر نیستند؛ محافظت‌ها قبل از حذف اعمال می‌شوند.

## 2026-10-12 scoped execution evidence / شواهد اجرای محدود
- Installed source SHA256: 0f9f503013223d6bdd1b02c606a6d269663993b6f36a084627bb589d3da160a6.
- Fresh pre-apply baseline: /opt/akhbot/audit/scoped-apply-before-20261012.json.
  Post-apply: /opt/akhbot/audit/scoped-after-20261012.json. Both read-only DB
  integrity checks returned ok. Pending jobs and six-hour failed jobs were zero.
  Successful Telegram SEND: job 7003 at 2026-10-12T01:43:02Z, remote_id 2297.
- All 41 planned paths removed: 24 DB backups, 7 exact artifacts/cache trees,
  10 named Rasteh exit markers. No image, DR volume or rotated application log
  deletion was eligible. Journal vacuum reported 24.0 MiB reclaimed.
- Before-plan allocated regular-file blocks: 326,942,720 bytes; with journal,
  at least 352,108,544 bytes of disposable storage removed, excluding directory
  blocks. This is NOT the measured net change in host free space.
- Service measured free-before=4,501,958,656 and free-after=4,396,560,384:
  net -105,398,272 bytes during live writes. Snapshot df available:
  4,499,464,192 before and 4,071,817,216 after (89% -> 90%).
  Do not claim the server gained free space overall: concurrent filesystem
  allocations outweighed cleanup. No foreign resource was deleted to compensate.
- Container IDs, image IDs, start times, restart counts and mapped ports were
  identical between the fresh pre/post baseline; related service states/PIDs
  and TCP listeners were unchanged. Nine running containers plus one exited
  Rasteh rollback remained. This task did not deploy/restart application services.
  A separate deployment changed akhbot-app to release-1775049d during preparation,
  before the fresh pre-apply baseline; its revision label identifies 1775049d.
- Protected newest two .db restore points:
  pre-liveblog-cleanup-20261008T231755Z.db and
  pre-liveblog-deploy-20261008T232723Z.db. All six Oct-8 DB backups, Oct-9 repair
  JSONs, the fresh Oct-12 compressed release backup, live DB/WAL, running and
  rollback images, newest akhbot_dr_20261003T180007Z and foreign resources remain.
  Unknown backup formats are preserved; the gzip release backup is not deleted.
- Service Result=success / ExecMainStatus=0. Timer enabled; next observed run:
  2026-10-12T03:45:20Z (07:15:20 Tehran), within the daily jitter window.
  Effective final journald settings are 5day / 200M system / 100M runtime /
  2G reserve. No journald restart was needed: existing effective caps match.
- Full fresh suite: 508 passed, 24 existing deprecation warnings. Twenty focused
  cleanup tests pass. Python 3.10 timestamp and real anchored directory deletion
  probes pass. systemd unit verification passes; unrelated snapd unit emits an
  existing RestartMode warning, and was not modified.
- Read-only unrelated inventory: three TwoID emulator *test* units have been
  failed since Oct-7; production TwoID containers remain running. SentinelX
  directory exists but no identifiable running process/unit was found. These
  states were not repaired or altered by the cleanup.

فارسی: ۴۱ مورد مجاز و ۲۴ مگابایت journal حذف شد؛ دست‌کم ۳۵۲٬۱۰۸٬۵۴۴ بایت
از فضای آثار زائد آزاد شد، اما نوشتن هم‌زمان روی دیسک باعث کاهش فضای آزاد خالص
شد. این گزارش آن دو اندازه‌گیری را جدا نگه می‌دارد. دیتابیس سالم، صف صفر،
کانتینرها/پورت‌ها و سرویس‌های فعال ثابت ماندند. دو بکاپ آخر، همهٔ بکاپ‌های تازه،
آخرین DR، تصاویر runtime/rollback و منابع سایر پروژه‌ها حفظ شدند.

### Concurrent activity after the cleanup / فعالیت هم‌زمان پس از پاک‌سازی
A later read-only observation (~02:04Z) found PV-Growth redeployed by a separate
actor to pv-growth-app:9f6c2a438dbdbe09e9a0656f535898864361ab9e, healthy on the
same 127.0.0.1:8350 mapping. This task issued no PV-Growth mutation. Container
comparison above refers specifically to the stored pre/post cleanup snapshots;
it must not be interpreted as all services remaining unchanged throughout
other operators' deployments. Latest df at that observation: 4,026,556,416
bytes available, 90% used.

فارسی: در بررسی بعدی، استقرار جداگانهٔ PV-Growth با همان پورت و وضعیت healthy
مشاهده شد. این کار از سوی این پاک‌سازی انجام نشده است. مقایسهٔ بدون تغییر
به snapshotهای ثبت‌شدهٔ قبل/بعد پاک‌سازی مربوط است؛ فضای آزاد بعدی حدود
۴٫۰۳ گیگابایت بود.
