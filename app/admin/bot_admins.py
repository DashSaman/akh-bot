"""§7 FINAL-HARDENING: /admin/bot-admins — multi-admin management.

Small, integrated, same house pattern as platforms.py: login required,
CSRF-checked mutations, permission rows edited server-side, prefer-disable
over delete. Audit trail = created_by/updated_at columns (§E6)."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .views import _ctx, _csrf_reject, require_login, templates, _db

router = APIRouter(prefix="/admin")

_PERMS = ("can_submit", "can_publish", "can_edit", "can_cancel",
          "can_manage_admins")
_ROLES = ("OWNER", "EDITOR", "PUBLISHER")


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@router.get("/bot-admins", response_class=HTMLResponse)
async def bot_admins_page(request: Request):
    if (r := await require_login(request)):
        return r
    rows = _db(request).query(
        "SELECT * FROM bot_admins ORDER BY enabled DESC, id")
    return templates.TemplateResponse(
        request, "admin/bot_admins.html", _ctx(request, admins=rows,
                                               perms=_PERMS, roles=_ROLES))


@router.post("/bot-admins/add")
async def bot_admins_add(request: Request, telegram_user_id: str = Form(""),
                         display_name: str = Form(""),
                         role: str = Form("EDITOR"), csrf: str = Form("")):
    if (r := await require_login(request)) or (c := _csrf_reject(request, csrf)):
        return r or c
    tid = telegram_user_id.strip()
    role = role.upper() if role.upper() in _ROLES else "EDITOR"
    if tid.lstrip("-").isdigit():
        db = _db(request)
        db.execute(
            "INSERT OR IGNORE INTO bot_admins (telegram_user_id, display_name,"
            " role, created_by, created_at, updated_at)"
            " VALUES (?, ?, ?, 'admin-ui', ?, ?)", (tid, display_name[:60],
                                                    role, _now(), _now()))
    return RedirectResponse("/admin/bot-admins", status_code=303)


@router.post("/bot-admins/{admin_id}/update")
async def bot_admins_update(request: Request, admin_id: int,
                            csrf: str = Form(""),
                            action: str = Form(""),
                            role: str = Form(""),
                            **perms: str):
    if (r := await require_login(request)) or (c := _csrf_reject(request, csrf)):
        return r or c
    db = _db(request)
    row = db.query_one("SELECT * FROM bot_admins WHERE id=?", (admin_id,))
    if row and row["role"] != "OWNER":  # OWNER row is immutable from the UI
        if action == "disable":
            db.execute("UPDATE bot_admins SET enabled=0, updated_at=? WHERE id=?",
                       (_now(), admin_id))
        elif action == "enable":
            db.execute("UPDATE bot_admins SET enabled=1, updated_at=? WHERE id=?",
                       (_now(), admin_id))
        else:  # permission/role edit
            sets = ["updated_at=?"]
            args: list = [_now()]
            if role.upper() in ("EDITOR", "PUBLISHER"):
                sets.append("role=?")
                args.append(role.upper())
            for p in _PERMS:
                sets.append(f"{p}=?")
                args.append(1 if perms.get(p) == "on" else 0)
            args.append(admin_id)
            db.execute(f"UPDATE bot_admins SET {', '.join(sets)} WHERE id=?",
                       args)
    return RedirectResponse("/admin/bot-admins", status_code=303)
