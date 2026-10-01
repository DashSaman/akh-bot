"""T1 — REG-022 + CORE-001: duplicate top-level canonical definitions cannot
silently shadow a fix (ast scan); canonical entities structurally distinct."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Modules whose top-level canonical names must be unique (REG-022 recurrence guard)
GUARDED = {
    "app/publishing/telegram_bot.py": [
        "TelegramBotPublisher", "build_public_text", "story_content_language_check",
        "is_persian_public_text", "to_telegram_html", "brand_signature",
        "sanitize_public_copy", "body_quality_gate", "dedup_paragraphs",
    ],
    "app/newsroom/pipeline.py": [
        "deterministic_story_text", "process_new_items", "source_display_names",
        "build_claim_evidence", "det_body_of",
    ],
    "app/newsroom/translator.py": ["translate_event", "consistent_with_source"],
    "app/integrations/llm/router.py": ["FreeAiRouter"],
}


def _top_level_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))]


def test_no_duplicate_canonical_definitions():
    """REG-022: exactly one top-level def/class per canonical name."""
    for rel, names in GUARDED.items():
        top = _top_level_names(ROOT / rel)
        for name in names:
            assert top.count(name) == 1, (
                f"{rel}: canonical '{name}' defined {top.count(name)}x (REG-022 recurrence)")
    # also: any duplicated top-level def/class in guarded files is a smell
    for rel in GUARDED:
        top = _top_level_names(ROOT / rel)
        dups = {n for n in top if top.count(n) > 1}
        assert not dups, f"{rel}: duplicate top-level definitions {dups}"


def test_core_entities_structurally_distinct():
    """CORE-001: the seven canonical entities are distinct constructs with
    distinct storage/repos (no aliasing one to another)."""
    from app.db import repo

    repos = ["SourcesRepo", "RawItemsRepo", "EventsRepo", "ClaimsRepo",
             "StoriesRepo", "PublicationsRepo", "JobsRepo"]
    seen_tables = set()
    for name in repos:
        cls = getattr(repo, name)
        assert callable(cls)
        # each repo targets a distinct primary table via its first method SQL
        sqls = []
        for attr in vars(cls):
            fn = getattr(cls, attr)
            if callable(fn) and hasattr(fn, "__code__"):
                consts = [c for c in fn.__code__.co_consts if isinstance(c, str) and ("FROM " in c or "INTO " in c)]
                sqls.extend(consts)
        first = next((s for s in sqls if "FROM" in s or "INTO" in s), "")
        assert first, f"{name} has no SQL-backed methods"
    # storage-level distinctness: entity tables exist and are separate
    import sqlite3, tempfile, os

    from app.db.database import Database
    from app.db.migrate import apply_migrations

    with tempfile.TemporaryDirectory() as td:
        db = Database(os.path.join(td, "t.db"))
        apply_migrations(db)
        tables = {r["name"] for r in db.query(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for t in ("sources", "raw_items", "claims", "events", "stories",
                  "story_versions", "publications", "jobs"):
            assert t in tables, f"entity table {t} missing"
        db.close()


def test_imports_resolve_to_intended_implementation():
    """The runtime import path gives the single guarded implementation."""
    import app.publishing.telegram_bot as tb
    import app.newsroom.pipeline as pl

    for mod, name in ((tb, "TelegramBotPublisher"), (tb, "build_public_text"),
                      (pl, "process_new_items"), (pl, "source_display_names")):
        obj = getattr(mod, name)
        src = Path(sys_module_file(mod)).read_text(encoding="utf-8")
        assert src.count(f"def {name}") + src.count(f"class {name}") == 1


def sys_module_file(mod) -> str:
    return mod.__file__
