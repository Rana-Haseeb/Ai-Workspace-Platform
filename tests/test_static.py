"""Serving the SPA from the API process.

The catch-all in ``api/static.py`` is the piece of deployment most likely to be silently wrong:
it either swallows the API, or breaks refresh, or serves the HTML shell where JavaScript was
asked for. None of those show up until the thing is deployed, so they are pinned here against a
fake build directory rather than the real one — the tests must pass whether or not anyone has
run ``npm run build``.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import static


@pytest.fixture
def dist(tmp_path, monkeypatch):
    """A minimal stand-in for `web/dist`."""
    build = tmp_path / "dist"
    (build / "assets").mkdir(parents=True)
    (build / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    (build / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (build / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    # A secret one directory above the build, to prove traversal cannot reach it.
    (tmp_path / "secret.env").write_text("JWT_SECRET=leaked", encoding="utf-8")

    monkeypatch.setattr(static, "DIST", build)
    return build


@pytest.fixture
def app(dist):
    application = FastAPI()

    @application.get("/api/health")
    def health():
        return {"status": "ok"}

    static.mount_spa(application)
    return TestClient(application)


# ------------------------------------------------------------------ the SPA is served
def test_the_root_returns_the_app_shell(app):
    response = app.get("/")
    assert response.status_code == 200
    assert "<div id=root>" in response.text


@pytest.mark.parametrize("route", [
    "/w/4/dashboard",
    "/w/4/c/12",
    "/login",
    "/register",
    "/w/4/documents",
])
def test_a_client_side_route_survives_a_refresh(app, route):
    """The bug this exists to prevent: refreshing a React Router path 404s on a plain mount."""
    response = app.get(route)
    assert response.status_code == 200, route
    assert "<div id=root>" in response.text


# ------------------------------------------------- the API keeps its own paths
def test_the_api_still_answers(app):
    assert app.get("/api/health").json() == {"status": "ok"}


@pytest.mark.parametrize("path", [
    "/api/does-not-exist",
    "/api/workspaces/999",
])
def test_an_unknown_api_path_404s_instead_of_returning_html(app, path):
    """A catch-all that answers for /api turns a missing endpoint into a 200 full of HTML."""
    response = app.get(path)
    assert response.status_code == 404, path
    assert "<div id=root>" not in response.text


def test_the_schema_endpoint_is_not_shadowed_by_the_catch_all(app):
    """`/openapi.json` is a real route and must keep returning the schema, not the app shell.

    It is in API_PREFIXES for exactly this reason — not to be 404'd, but so the catch-all
    declines it and FastAPI's own handler answers.
    """
    response = app.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["openapi"].startswith("3.")
    assert "<div id=root>" not in response.text


# ----------------------------------------------------------- real files win
def test_a_hashed_asset_returns_javascript_not_the_shell(app):
    """If the shell is served here the browser refuses to execute it and the page is blank."""
    response = app.get("/assets/index-abc123.js")
    assert response.status_code == 200
    assert "console.log(1)" in response.text
    assert "<div id=root>" not in response.text


def test_a_root_level_file_is_served(app):
    assert app.get("/favicon.svg").text == "<svg/>"


# --------------------------------------------------------------- no escaping the build
@pytest.mark.parametrize("attack", [
    "/../secret.env",
    "/../../secret.env",
    "/assets/../../secret.env",
])
def test_path_traversal_cannot_read_outside_the_build(app, attack):
    response = app.get(attack)
    assert "JWT_SECRET" not in response.text, attack


# ------------------------------------------------------- absent a build, the API still runs
def test_the_api_starts_without_a_frontend_build(tmp_path, monkeypatch):
    """Refusing to boot because the SPA was not built would block backend-only work."""
    monkeypatch.setattr(static, "DIST", tmp_path / "nothing-here")
    application = FastAPI()

    @application.get("/api/health")
    def health():
        return {"status": "ok"}

    static.mount_spa(application)
    client = TestClient(application)

    assert client.get("/api/health").status_code == 200
    body = client.get("/").json()
    assert "npm run build" in body["detail"]
