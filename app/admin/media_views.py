from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from .views import _ctx, require_login, templates, _db

router = APIRouter(prefix="/admin")


@router.get("/media", response_class=HTMLResponse)
async def media_page(request: Request):
    if (r := await require_login(request)):
        return r
    db = _db(request)
    rows = db.query(
        "SELECT m.*, (SELECT headline FROM stories s WHERE s.id=m.story_id) headline,"
        " (SELECT COUNT(*) FROM publications p WHERE p.story_id=m.story_id AND p.status='SENT') sent"
        " FROM media_cache m ORDER BY m.created_at DESC LIMIT 100")
    import os

    cache_mb = 0.0
    cd = os.path.join(os.environ.get("DATA_DIR", "/data"), "media-cache")
    if os.path.isdir(cd):
        cache_mb = round(sum(os.path.getsize(os.path.join(cd, f)) for f in os.listdir(cd)) / 1e6, 2)
    return templates.TemplateResponse(request, "admin/media.html",
                                      _ctx(request, rows=rows, cache_mb=cache_mb))
