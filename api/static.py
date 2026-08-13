"""Serving the built React app from the same process as the API.

In development the SPA runs on its own port and Vite handles routing. In production there is one
process: uvicorn serves ``/api/*`` and everything else is the SPA.

**The catch-all is the whole point of this module.** React Router owns paths like
``/w/4/dashboard``, and those paths exist only in the browser. Ask the *server* for one — by
refreshing the page, or by pasting a link — and there is no file at that path, so a plain static
mount returns 404. The user sees a broken page on refresh, which is the single most common way a
deployed SPA is broken.

So unknown paths return ``index.html`` and let the client router decide. Three things that must
hold, and each has a test:

1. **``/api/*`` must never be swallowed.** A catch-all that answers before the API does turns a
   missing endpoint into a 200 with HTML in it, which is far harder to debug than a 404.
2. **A real asset must win.** ``/assets/index-abc.js`` has to return JavaScript, not the HTML
   shell — otherwise the browser refuses to execute it and the page is blank.
3. **It must not serve files outside the build directory.** A path like ``/../../.env`` is a
   request for a secret, not a route.

Absent a build, the app still starts and says what to run. A backend that refuses to boot because
the frontend was not built is hostile to anyone working on the API alone.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from core.config import ROOT
from core.logging import get_logger

log = get_logger("static")

DIST = ROOT / "web" / "dist"

# Paths owned by the API. The catch-all must decline these so FastAPI's own 404 is returned.
API_PREFIXES = ("api/", "docs", "redoc", "openapi.json")


def is_built() -> bool:
    return (DIST / "index.html").is_file()


def _shown(path: Path) -> str:
    """A readable path for a log line.

    `relative_to` raises when the target is not under ROOT, which is exactly the case in tests
    that point DIST at a temp directory — so a log line would crash the mount. Falls back to the
    absolute path instead of pretending it can always shorten it.
    """
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def mount_spa(app: FastAPI) -> None:
    """Serve ``web/dist`` for every path the API does not own.

    Call this **after** every router is registered. Route matching is ordered, so a catch-all
    added first would shadow the entire API.
    """
    if not is_built():
        log.warning(
            "No frontend build at %s — API only. Build it with: npm run build --prefix web",
            _shown(DIST),
        )

        @app.get("/", include_in_schema=False)
        def no_build() -> dict:
            return {
                "status": "api only",
                "detail": "The frontend is not built. Run: npm run build --prefix web",
                "api_docs": "/docs",
            }

        return

    # Hashed assets are immutable by construction — the filename changes when the content does —
    # so they can be cached hard. index.html deliberately is not, or a redeploy would leave
    # browsers pinned to the old asset names.
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        if full_path.startswith(API_PREFIXES):
            raise HTTPException(status_code=404, detail="Not found")

        if full_path:
            candidate = (DIST / full_path).resolve()
            # `resolve()` collapses `..` before this check, so a traversal attempt lands outside
            # DIST and is refused rather than reaching the filesystem above the build.
            if candidate.is_relative_to(DIST.resolve()) and candidate.is_file():
                return FileResponse(candidate)

        # An unknown path is a client-side route, not a missing file.
        return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-cache"})

    log.info("Serving the SPA from %s", _shown(DIST))
