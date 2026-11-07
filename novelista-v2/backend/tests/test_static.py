from __future__ import annotations
from fastapi.testclient import TestClient

INDEX = "<html>SPA</html>"
JS = "console.log('app');"


def _load_app(monkeypatch, dist):
    monkeypatch.setenv("NOVELISTA_FRONTEND_DIST", str(dist))
    from app.main import app
    return app


def _make_dist(root):
    dist = root / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX, encoding="utf-8")
    (dist / "assets" / "app.js").write_text(JS, encoding="utf-8")
    return dist


def test_serves_spa_assets_and_api(tmp_path, monkeypatch):
    dist = _make_dist(tmp_path)
    (tmp_path / "secret.txt").write_text("root:secret", encoding="utf-8")
    with TestClient(_load_app(monkeypatch, dist)) as c:
        r = c.get("/")
        assert r.status_code == 200 and r.text == INDEX
        r = c.get("/books/abc/chapters/3")
        assert r.status_code == 200 and r.text == INDEX
        r = c.get("/assets/app.js")
        assert r.status_code == 200 and r.text == JS
        assert c.get("/api/health").json() == {"ok": True}
        assert c.get("/api/nope").status_code == 404
        for evil in ["/../../etc/passwd", "/..%2fsecret.txt", "/%2e%2e/secret.txt"]:
            r = c.get(evil)
            assert "root:secret" not in r.text
            assert r.status_code == 404 or r.text == INDEX


def test_no_dist_shows_placeholder(tmp_path, monkeypatch):
    with TestClient(_load_app(monkeypatch, tmp_path / "missing")) as c:
        r = c.get("/")
        assert r.status_code == 200 and "frontend build" in r.text
        assert c.get("/books/x").status_code == 404
        assert c.get("/api/health").json() == {"ok": True}


def test_no_cors_header(tmp_path, monkeypatch):
    with TestClient(_load_app(monkeypatch, _make_dist(tmp_path))) as c:
        r = c.get("/api/health", headers={"Origin": "http://evil.example"})
        assert "access-control-allow-origin" not in r.headers
