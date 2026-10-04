"""§7 FINAL-HARDENING: /admin/editorial-inbox — pending submissions view.

Read-heavy audit view of manual_submissions with the SAME server-side
approval semantics as the Telegram buttons (activation flip only — the
canonical pipeline does everything else). Mutations CSRF-checked."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .views import _ctx, _csrf_reject, require_login, templates, _db

router = APIRouter(prefix="/admin")

_ACTIONS = {"approve": ("SUBMITTED", 1), "review": ("SUBMITTED", 1),
            "cancel": ("CANCELLED", 0)}


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@router.get("/editorial-inbox", response_class=HTMLResponse)
async def editorial_inbox_page(request: Request):
    if (r := await require_login(request)):
        return r
    db = _db(request)
    rows = db.query(
        "SELECT s.*, a.display_name submitter, a.telegram_user_id submitter_id,"
        " ri.title item_title, ri.forward_from origin, ri.activation_ok act,"
        " ri.media_json media, e.verification verification, e.id event_id,"
        " st.id story_id FROM manual_submissions s"
        " LEFT JOIN bot_admins a ON a.id = s.submitter_admin_id"
        " LEFT JOIN raw_items ri ON ri.id = s.raw_item_id"
        " LEFT JOIN stories st ON st.id = s.story_id"
        " LEFT JOIN events e ON e.id = st.event_id"
        " ORDER BY s.id DESC LIMIT 100")
    return templates.TemplateResponse(
        request, "admin/editorial_inbox.html", _ctx(request, subs=rows))


@router.post("/editorial-inbox/{sub_id}/action")
async def editorial_inbox_action(request: Request, sub_id: int,
                                 action: str = Form(""), csrf: str = Form("")):
    if (r := await require_login(request)) or (c := _csrf_reject(request, csrf)):
        return r or c
    if action not in _ACTIONS:
        return RedirectResponse("/admin/editorial-inbox", status_code=303)
    status, activate = _ACTIONS[action]
    db = _db(request)
    sub = db.query_one("SELECT * FROM manual_submissions WHERE id=?", (sub_id,))
    if sub and sub["status"] in ("RECEIVED", "PREVIEW", "HELD"):
        db.execute(
            "UPDATE raw_items SET activation_ok=?, processed_state='NEW'"
            " WHERE id=?", (activate, sub["raw_item_id"]))
        db.execute(
            "UPDATE manual_submissions SET status=?, approved_at=? WHERE id=?",
            (status, _now() if activate else sub["approved_at"], sub_id))
    return RedirectResponse("/admin/editorial-inbox", status_code=303)
