# Expand Free Translation Providers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand Rasteh's zero-cost translation capacity with additional qualified free providers while preserving translation fidelity and leaving GrowthOS and unrelated services untouched.

**Architecture:** Keep the existing Rasteh → 9Router integration as the only production routing layer. Add only official/free provider credentials or documented anonymous routes to 9Router, benchmark candidate models outside the publish/DB path, then promote only language-safe models into Rasteh's existing per-language fallback lists. FreeLLMAPI is a discovery/reference source, not a second production router.

**Tech Stack:** Python/FastAPI Rasteh app, 9Router, Docker, pytest, official provider APIs.

**Spec:** User-approved architecture in the 2026-10-06 conversation: mine FreeLLMAPI's free-provider catalog, connect useful providers to existing 9Router, test EN/AR translation, and deploy only qualified fallbacks.

## Global Constraints

- Zero-cost only: no paid plans, cards, purchases, trials that auto-bill, or paid API calls.
- Use one legitimate Rasteh account per provider; do not create quota-evasion multi-accounts.
- Never print, commit, or log passwords/API keys.
- Do not touch GrowthOS or unrelated containers/services.
- Candidate tests must bypass DB/publisher; no test content may be published.
- Preserve protected entities, dates, numbers, negation, countries, and political/technical terms.
- Existing working production route remains available until the replacement deployment is verified.
- Providers whose terms restrict free access to evaluation/non-production are benchmark-only unless their production use is permitted.
- Full `python -m pytest tests -q` must pass before completion.

## Review Focus

- A candidate returns fluent Persian but changes a named entity/date/number/negation → reject it.
- A provider is fast but intermittently emits empty/malformed JSON → do not promote it.
- A provider requires paid billing/card or production use violates its free-tier terms → do not activate it in production.
- One provider reaches 429/5xx → next validated language-safe fallback must run before the generic combo.
- Test harness must use direct inference/`db=None` and never enqueue or publish a story.

---

### Task 1: Safe provider onboarding and isolated inventory

**Files:**
- Modify only provider state/config owned by 9Router; no Rasteh code yet.
- Record non-secret results in `docs/CHANGELOG.md` only after qualification.

**Interfaces:**
- Consumes: existing 9Router endpoint and credentials.
- Produces: list of newly usable provider/model IDs with credentials stored outside git.

- [ ] **Step 1:** Snapshot Rasteh/9Router/GrowthOS health and current non-secret provider names/models.
- [ ] **Step 2:** On official provider sites, create/sign in to a single Rasteh account where needed, using the user-supplied Rasteh credentials; stop at any CAPTCHA/email verification that cannot be completed safely.
- [ ] **Step 3:** Add only zero-cost credentials/routes for candidates such as Cerebras, direct Mistral, Gemini, HuggingFace, NVIDIA, and documented anonymous OVH/AI Horde/OpenCode routes when supported.
- [ ] **Step 4:** Verify each new connection with a harmless models/health request and record only provider/model/status, never secrets.

### Task 2: Translation qualification

**Files:**
- No production-code modifications.
- Temporary benchmark output under `/tmp` only.

**Interfaces:**
- Consumes: candidate model IDs from Task 1.
- Produces: per-language allowlist of models that preserve the fixture facts.

- [ ] **Step 1:** Send the fixed English Araghchi/New York/Tuesday/3,200/negation/two-weeks fixture directly to every candidate with no DB/publisher.
- [ ] **Step 2:** Send the equivalent Arabic fixture through the same candidates.
- [ ] **Step 3:** Repeat promising models enough times to catch unstable 429/empty/malformed behavior.
- [ ] **Step 4:** Reject any model that changes protected facts or has unacceptable reliability; keep latency/reliability observations.
- [ ] **Step 5:** Specifically benchmark translation-focused candidates when accessible, including Cohere Command A Translate and NVIDIA Riva only for language pairs it officially supports.

### Task 3: Promote validated fallbacks with TDD

**Files:**
- Modify: `app/newsroom/translator.py`
- Modify only if routing interface needs it: `app/integrations/llm/router.py`
- Test: `tests/test_translation_ai.py`

**Interfaces:**
- Consumes: per-language allowlist from Task 2.
- Produces: deterministic EN/AR fallback order that keeps the current primaries and only inserts validated models.

- [ ] **Step 1: Write failing tests** asserting the exact EN and AR fallback order and that the legacy generic combo is reached only after all validated language-safe fallbacks.
- [ ] **Step 2: Run targeted tests** and confirm RED for the missing new qualified model(s).
- [ ] **Step 3: Implement the minimum fallback-list change** using the exact qualified 9Router model IDs; no generic auto-router in the protected translation path.
- [ ] **Step 4: Run targeted tests** and confirm GREEN.
- [ ] **Step 5: Run full regression** with the repo's declared pytest + pytest-asyncio test dependencies.
- [ ] **Step 6: Commit** a small conventional feature commit.

### Task 4: Safe deployment and no-publish verification

**Files:**
- Modify: `docs/00-CURRENT-STATUS.md`
- Modify: `docs/CHANGELOG.md`

**Interfaces:**
- Consumes: tested code commit from Task 3.
- Produces: healthy production deployment plus documented runtime evidence.

- [ ] **Step 1:** Deploy with the repo's safe deployment script; if its immediate curl races startup, independently wait for Docker health before diagnosing product failure.
- [ ] **Step 2:** Verify production SHA, `/health`, Rasteh container health, and GrowthOS health.
- [ ] **Step 3:** Run direct `translate_event(..., db=None)` EN/AR smoke tests, forcing earlier fallbacks to fail process-locally so each newly promoted fallback is actually exercised.
- [ ] **Step 4:** Confirm no test touched DB/publisher and scan recent production logs for ERROR/CRITICAL/Traceback.
- [ ] **Step 5:** Update bilingual status/changelog with provider qualification, rejected candidates, test count, and deployed SHA.
- [ ] **Step 6:** Re-run governance/full regression as required, commit docs only, and leave the branch unpushed unless separately authorized.
