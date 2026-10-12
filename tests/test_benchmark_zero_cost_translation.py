"""Offline-only regression tests for the isolated free-model benchmark."""
from scripts.benchmark_zero_cost_translation import (
    ALLOWED_FREE_MODELS, FIXTURES, evaluate,
)

def test_benchmark_has_explicit_free_model_allowlist():
    assert ALLOWED_FREE_MODELS
    assert len(ALLOWED_FREE_MODELS) == len(set(ALLOWED_FREE_MODELS))

def test_benchmark_fixtures_cover_english_arabic_hebrew():
    assert set(FIXTURES) == {"en", "ar", "he"}

def test_benchmark_detects_dropped_protected_news_facts():
    issues = evaluate(FIXTURES["en"], "یک توافق تصویب شد", "خبر قطعی اعلام شد.")
    assert "DROPPED_NUMBER" in issues
    assert "DROPPED_NAME" in issues
    assert "DROPPED_PLACE" in issues
    assert "LOST_NEGATION" in issues
