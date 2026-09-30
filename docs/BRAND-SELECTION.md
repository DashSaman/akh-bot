# Brand Selection

**BRAND_STATUS = UNDECIDED** (do not change without explicit owner approval).

## Rules
- Internal project name `akh-bot`, infrastructure namespace `akhbot` (container,
  network, volume, paths) — **never** the public brand.
- Public surfaces (site, footer, OG, schema, RSS, telegram signature, emails) read
  ONLY from `config/brand.yml` + `PUBLIC_BASE_URL`.
- Changing the brand later requires NO database/network/path/code renames.
- Placeholder preview values in `config/brand.example.yml` are explicitly NOT a brand.

## Workflow (later, owner-driven)
1. Owner shortlists candidate names.
2. Availability checks (see `BRAND-AVAILABILITY.md` template): domain (whois/RDY),
   Telegram, X, Instagram, Threads, Facebook, YouTube handles. **Absence from a
   Google search is NOT proof of availability.**
3. Owner decides → update `config/brand.yml` (`brand_status: DECIDED`), set
   `PUBLIC_BASE_URL`, wire Apache vhost + SSL, register official accounts, fill
   `same_as`.
