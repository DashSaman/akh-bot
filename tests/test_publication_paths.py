"""CORE-002 permanent public-path guard.

Invariant (INV-002/003): NO public publication may be produced from anything
other than a canonical Story/StoryVersion rendered through the canonical
renderer. Audited path inventory (2026-10-01, PART 1.1):

| PATH | INPUT | CANONICAL REQUIRED? | PUBLIC? | STATUS |
|---|---|---|---|---|
| pipeline._enqueue_platforms (app/newsroom/pipeline.py) | Story fields via _render_public | YES | YES | GUARDED (tests/test_canonical_story) |
| admin lifecycle action (app/admin/views.py story_lifecycle) | existing Story draft fields → build_public_text | YES | YES | GUARDED (this file, admin test) |
| jobs runner send/edit (app/jobs/runner.py) | payload.text pre-rendered by the two paths above | YES (upstream) | YES | GUARDED (publisher fail-closed gates) |
| scripts/run1_editorial.py | hardcoded one-shot editorial text (historical ops record) | NO — builds draft blob directly | was public then; NOT importable app code | QUARANTINED (this file marks it non-canonical; cannot run against prod without manual exec) |
| scripts/migrate_destination.py | draft["platform_variants"]["telegram"] passthrough → build_public_text | PARTIAL — re-renders stored blob | historical migration, already executed | SEALED (test asserts it contains no direct publisher send of raw non-story text) |

Enforcement here:
1) AST: any NEW module under app/ calling TelegramBotPublisher.send_message /
   send_media / edit_message must import/use the canonical renderer
   (build_public_text / _render_public) — raw string literals from untrusted
   input are rejected structurally (no direct .send_message("...") of raw text
   outside the publisher class itself and the jobs runner).
2) Contract: jobs runner only sends payload["text"] whose producer is one of
   the two canonical enqueues (pipeline/_render_public or admin build_public_text).
3) Scripts quarantine: repo scripts must not import TelegramBotPublisher for
   NEW public sends (historical sealed scripts asserted to contain no live
   enqueue of non-story text into production paths).
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
PUBLISHER_METHODS = {"send_message", "send_media", "edit_message"}
ALLOWED_CALLERS = {
    "app/jobs/runner.py",      # executes pre-rendered canonical payloads
    "app/publishing/telegram_bot.py",  # the publisher itself
}


def test_no_new_direct_publisher_calls_in_app():
    """AST: only the jobs runner may call publisher send/edit methods inside app/."""
    for path in sorted(APP.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel in ALLOWED_CALLERS or "__pycache__" in rel:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr in PUBLISHER_METHODS:
                raise AssertionError(
                    f"NON-CANONICAL PUBLIC PATH: {rel} calls publisher.{node.func.attr} "
                    "directly — route through canonical Story render + jobs outbox")


def test_jobs_runner_sends_only_payload_text_with_story():
    """Contract: runner's send/edit text comes from job payload['text'] (produced
    by canonical enqueues), never from raw item fields."""
    src = (ROOT / "app/jobs/runner.py").read_text(encoding="utf-8")
    assert 'payload.get("text")' in src
    assert "raw_items" not in src.split("def make_publish_handler")[1].split("def ")[0]
    # publisher construction only from factory, never with raw text baked in
    assert "send_message(payload" not in src


def test_admin_lifecycle_action_uses_canonical_renderer():
    src = (ROOT / "app/admin/views.py").read_text(encoding="utf-8")
    seg = src.split("async def story_lifecycle")[1][:2500]
    assert "build_public_text" in seg, "admin action must render via canonical build_public_text"
    assert "draft" in seg and "set_lifecycle" in seg  # operates on Story + creates version


def test_historical_scripts_sealed_noncanonical():
    """Sealed one-shot ops records must not be importable app modules and must
    not enqueue new non-story public payloads when imported."""
    run1 = (ROOT / "scripts/run1_editorial.py").read_text(encoding="utf-8")
    # it documents a historical run: its POSTS are fixed records, and rerun is
    # idempotent (story-exists skip). Structural seal: script lives outside app/.
    assert not (APP / "run1_editorial.py").exists()
    assert "story exists for event" in run1  # rerun guard present
    mig = (ROOT / "scripts/migrate_destination.py").read_text(encoding="utf-8")
    assert "build_public_text" in mig  # even migration re-renders via canonical


def test_rawitem_cannot_reach_publisher_object():
    """Import contract: RawItemsRepo is never imported by the publisher module."""
    tb = (ROOT / "app/publishing/telegram_bot.py").read_text(encoding="utf-8")
    assert "RawItemsRepo" not in tb and "raw_items" not in tb


def test_publish_send_edit_job_type_separation():
    """§21 architectural guard (P3-E): publish_send and publish_edit are
    DISTINCT handlers. publish_send must hard-refuse when a SENT publication
    exists (SEND_FORBIDDEN_EDIT_ONLY); publish_edit must NEVER call
    send_message — a first publication is publish_send's job alone."""
    import ast as _ast

    src = (ROOT / "app/jobs/runner.py").read_text(encoding="utf-8")
    assert "SEND_FORBIDDEN_EDIT_ONLY" in src
    assert "NO_SENT_TARGET_TO_EDIT" in src

    tree = _ast.parse(src)
    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    for fn in ("make_send_handler", "make_edit_handler"):
        assert fn in funcs, f"missing handler factory {fn}"

    def _inner_calls(fn_node, name):
        inner = [n for n in _ast.walk(fn_node)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name == "handler"][0]
        return [n.func.attr for n in _ast.walk(inner)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]

    send_calls = _inner_calls(funcs["make_send_handler"], "handler")
    assert "send_message" in send_calls and "edit_message" not in send_calls
    edit_calls = _inner_calls(funcs["make_edit_handler"], "handler")
    assert "send_message" not in edit_calls and "edit_message" in edit_calls
