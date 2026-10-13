"""Safety contract for the bounded incomplete-copy repair utility."""
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[1] / "scripts" /
          "repair_incomplete_public_copy.py").read_text(encoding="utf-8")


def test_repair_is_dry_run_by_default_and_never_sends_new_message():
    assert 'ap.add_argument("--apply", action="store_true")' in SCRIPT
    assert '"publish_edit"' in SCRIPT
    assert '"publish_send"' not in SCRIPT
    assert ".send_message(" not in SCRIPT
    assert ".send_media(" not in SCRIPT


def test_repair_versions_draft_and_syncs_canonical_story_columns():
    assert "stories.set_lifecycle(" in SCRIPT
    assert "UPDATE stories SET headline=?, lead=?, updated_at=?" in SCRIPT


def test_repair_has_fail_closed_public_copy_checks():
    assert '"بیشتر بخوانید" in text' in SCRIPT
    assert 'endswith(("…", "..."))' in SCRIPT
    assert "public_body_is_substantive(text)" in SCRIPT
