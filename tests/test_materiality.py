"""P3-F — materiality rules (§23): material updates edit; restatements don't."""
from app.newsroom.claim_model import ClaimClass, extract_structured
from app.newsroom.materiality import is_material_update


def _claim(text, cls=ClaimClass.CASUALTY, actor=None, certainty="ASSERTED",
           location=None):
    c = extract_structured(text, source_item_id=1)
    c.claim_class = cls
    if actor:
        c.actor = actor
    if certainty:
        c.certainty = certainty
    if location:
        c.location = location
    return c


def test_first_claim_is_material():
    m, reasons = is_material_update(_claim("در حمله ۱۰ نفر کشته شدند"), [])
    assert m and reasons == ["FIRST_CLAIM"]


def test_new_casualty_figure_is_material():
    prior = [_claim("در حمله ۱۰ نفر کشته شدند")]
    m, reasons = is_material_update(_claim("در حمله ۱۵۰ نفر کشته شدند"), prior)
    assert m and any(r.startswith("NEW_NUMBERS") for r in reasons)


def test_restatement_without_new_signal_is_not_material():
    prior = [_claim("در حمله ۱۰ نفر کشته شدند")]
    m, reasons = is_material_update(_claim("در حمله مذکور ۱۰ نفر کشته شدند"), prior)
    assert not m, reasons


def test_official_confirmation_is_material():
    prior = [_claim("گزارش شده که در حمله تلفاتی وارد شده است", certainty="REPORTED")]
    m, reasons = is_material_update(
        _claim("سخنگوی ارتش اعلام کرد در حمله ۵ نفر کشته شدند", certainty="ATTRIBUTED"),
        prior)
    assert m and "OFFICIAL_CONFIRMATION" in reasons


def test_status_transition_keyword_is_material():
    prior = [_claim("قرار بود آتش‌بس امشب آغاز شود")]
    m, reasons = is_material_update(_claim("آتش‌بس لغو شد و درگیری ادامه دارد"), prior)
    assert m and "STATUS_TRANSITION" in reasons


def test_negation_flip_is_material():
    prior = [_claim("حمله انجام خواهد شد", cls=ClaimClass.ATTACK)]
    m, reasons = is_material_update(_claim("حمله انجام نخواهد شد", cls=ClaimClass.ATTACK),
                                    prior)
    assert m and "STATUS_TRANSITION" in reasons


def test_new_target_is_material():
    prior = [_claim("حمله موشکی به پایگاه آمریکایی در عراق رخ داد",
                    cls=ClaimClass.ATTACK, location="عراق")]
    m, reasons = is_material_update(
        _claim("حمله موشکی به پایگاه آمریکایی در سوریه رخ داد",
               cls=ClaimClass.ATTACK, location="سوریه"),
        prior)
    assert m and "NEW_TARGET" in reasons


def test_minor_context_addition_is_not_material():
    prior = [_claim("در حمله ۱۰ نفر کشته شدند")]
    m, reasons = is_material_update(
        _claim("در حاله‌ای حمله رخ داد و ۱۰ نفر کشته شدند"), prior)
    assert not m
