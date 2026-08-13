# Two stages, because the tools that *build* the frontend have no business being in the image
# that *runs* it. Node and node_modules are ~400 MB and are never needed at runtime — the output
# is a folder of static files. Only that folder is copied forward.

# ----------------------------------------------------------------- stage 1: build the SPA
FROM node:22-slim AS web

WORKDIR /build

# Manifests first, so `npm ci` is only re-run when dependencies actually change. Copying the
# whole source first would invalidate this layer on every edit and reinstall from scratch.
COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ ./
# Same-origin in production: uvicorn serves the API and this bundle from one host, so the client
# uses relative paths and there is no cross-origin cookie problem to solve.
ENV VITE_API_URL=""
RUN npm run build


# --------------------------------------------------------------- stage 2: the runtime image
FROM python:3.13-slim AS runtime

# PYTHONUNBUFFERED so logs reach the platform's log viewer as they happen rather than when a
# buffer fills — the difference between watching a deploy and guessing at it.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Hugging Face Spaces runs the container as uid 1000 and mounts nothing writable by default, so
# the app owns its own directory. Running as root would work and is worth not doing.
RUN useradd --create-home --uid 1000 appuser

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser api/ ./api/
COPY --chown=appuser:appuser core/ ./core/
COPY --chown=appuser:appuser db/ ./db/
COPY --chown=appuser:appuser schemas/ ./schemas/
COPY --chown=appuser:appuser services/ ./services/
COPY --chown=appuser:appuser skills/ ./skills/
COPY --chown=appuser:appuser --from=web /build/dist ./web/dist

# Uploads land here. On Spaces this is ephemeral — a restart loses the files, though the
# database rows survive because DATABASE_URL points at Neon. Documented rather than pretended
# otherwise; a persistent volume is the fix when one is available.
RUN mkdir -p /app/data/uploads && chown -R appuser:appuser /app/data

USER appuser

# Spaces routes to 7860 by default; PORT overrides it elsewhere.
ENV PORT=7860
EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",7860)}/api/health').read()"

# `sh -c` so $PORT is expanded. One worker on purpose: the rate limiter counts in-process, so
# N workers would multiply every limit by N. Scale by replicas with a shared store instead.
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-7860} --workers 1"]
