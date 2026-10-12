"""Preserve the actual production-only news-safety checks in repository releases."""
import inspect

from app.newsroom.quality_gates import liveblog_boilerplate, publication_quality_gate
from app.jobs.runner import make_send_handler


def test_liveblog_welcome_is_metadata_not_news():
    headline = "به پوشش زنده ما خوش آمدید"
    assert liveblog_boilerplate(headline)
    assert publication_quality_gate(None, headline, "", 99) == "HOLD_LIVEBLOG_BOILERPLATE"


def test_liveblog_end_marker_is_metadata():
    headline = "پایان این پوشش زنده"
    assert publication_quality_gate(None, headline, "", 99) == "HOLD_LIVEBLOG_BOILERPLATE"


def test_metadata_only_in_lead_must_be_checked():
    headline = "تحولات منطقه گزارش شد"
    lead = "به پوشش زنده ما خوش آمدید"
    assert publication_quality_gate(None, headline, lead, 99) == "HOLD_LIVEBLOG_BOILERPLATE"


def test_real_material_iran_report_is_not_liveblog_metadata():
    headline = "خبرگزاری از گفت‌وگوی ایران درباره تحریم‌های جدید خبر داد"
    assert not liveblog_boilerplate(headline, "جزئیات مذاکرات اعلام شد.")


def test_send_time_gate_reads_lead_as_well_as_details():
    # Guard against the deployed-only hotfix disappearing from source.
    source = inspect.getsource(make_send_handler)
    assert '_d.get("lead")' in source
    assert 'publication_quality_gate' in source
