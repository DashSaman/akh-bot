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
    resp = admin_client.post("/admin/logout", follow_redirects=False)
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
