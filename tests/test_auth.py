def test_admin_requires_login(client):
    resp = client.get("/admin", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/login"


def test_login_wrong_password(client):
    csrf = client.get("/admin/login").cookies.get("akh_csrf")
    resp = client.post("/admin/login", data={"username": "admin", "password": "nope", "csrf": csrf})
    assert resp.status_code == 401


def test_login_logout_flow(admin_client):
    resp = admin_client.get("/admin")
    assert resp.status_code == 200
    assert "داشبورد" in resp.text
    resp = admin_client.post("/admin/logout",
                             data={"csrf": admin_client.cookies.get("akh_csrf", "")},
                             follow_redirects=False)
    assert resp.status_code == 303
    resp = admin_client.get("/admin", follow_redirects=False)
    assert resp.status_code == 303


def test_login_throttled_after_failures(client):
    csrf = client.get("/admin/login").cookies.get("akh_csrf")
    for _ in range(5):
        client.post("/admin/login", data={"username": "admin", "password": "bad", "csrf": csrf})
    resp = client.post("/admin/login", data={"username": "admin", "password": "test-pass-123", "csrf": csrf})
    assert resp.status_code == 429


def test_admin_pages_render(admin_client):
    for path in ("/admin/sources", "/admin/items", "/admin/events", "/admin/publications", "/admin/settings"):
        resp = admin_client.get(path)
        assert resp.status_code == 200, path


def test_dashboard_shows_truthful_integration_statuses(admin_client):
    """Unconfigured integrations must show BLOCKED_EXTERNAL/WAITING — never 'live'."""
    html = admin_client.get("/admin").text
    assert "جمع‌آور RSS" in html and "LIVE_VERIFIED" in html
    assert "نویسنده GLM" in html and "BLOCKED_EXTERNAL" in html
    assert "ناشر تلگرام" in html and "BLOCKED_EXTERNAL" in html
    assert "جمع‌آور تلگرام" in html and "WAITING_FOR_CREDENTIALS" in html
    for absent in ("X", "Instagram", "Threads"):
        assert absent in html and "NOT_CONFIGURED" in html
    assert "برند عمومی" in html and "UNDECIDED" in html
    # fixture runs with PUBLIC_BASE_URL set → "LIVE"; unset → "PREVIEW (NOINDEX)"
    assert "ایندکس وب‌سایت" in html and ("LIVE" in html or "PREVIEW (NOINDEX)" in html)


def test_dashboard_upgrades_to_live_verified_after_verification(admin_client):
    from app.db.repo import SettingsRepo

    SettingsRepo(admin_client.app.state.db).set("glm_verified_at", "2030-01-01|glm-4.6|123")
    html = admin_client.get("/admin").text
    glm_section = html.split("نویسنده GLM")[1][:120]
    assert "LIVE_VERIFIED" in glm_section


def _csrf_of(client):
    return client.cookies.get("akh_csrf") or client.get("/admin/login").cookies.get("akh_csrf")


def test_admin_mutations_require_csrf(admin_client):
    """Every admin POST without a valid CSRF token must be rejected with 403."""
    cases = [
        ("/admin/sources", {"name": "x", "platform": "rss", "url": "https://x.example/f"}),
        ("/admin/settings/pause", {"key": "pause_all", "value": "1"}),
        ("/admin/logout", {}),
    ]
    for path, fields in cases:
        resp = admin_client.post(path, data=fields, follow_redirects=False)
        assert resp.status_code == 403, (path, resp.status_code)


def test_admin_mutations_with_csrf_pass(admin_client):
    token = _csrf_of(admin_client)
    resp = admin_client.post(
        "/admin/settings/pause",
        data={"key": "pause_all", "value": "1", "csrf": token},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    # cleanup: unpause
    admin_client.post("/admin/settings/pause",
                      data={"key": "pause_all", "value": "0", "csrf": token})
