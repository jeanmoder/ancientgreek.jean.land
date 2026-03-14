from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import (
    get_allowed_hosts,
    get_allowed_origins,
    get_protected_api_paths,
    settings,
)
from backend.db import close_db, init_db
from backend.routers import dictionary, texts
from backend.services.logeion import warm_local_dictionary_cache
from backend.services.syntax import ensure_odycy_model


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle."""
    await init_db()
    ensure_odycy_model()
    # Warm small local dictionary data and catalog metadata to avoid cold-start latency.
    warm_local_dictionary_cache()
    await texts.get_catalog()
    yield
    await close_db()


app = FastAPI(
    title="Ancient Greek Learning API",
    version="0.1.0",
    lifespan=lifespan,
)

# -- CORS for the Vite dev server ------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_HOSTS = set(get_allowed_hosts())
ALLOWED_ORIGINS = set(get_allowed_origins())
PROTECTED_API_PATHS = tuple(get_protected_api_paths())
INTERNAL_API_KEY = settings.INTERNAL_API_KEY.strip()


@app.middleware("http")
async def host_origin_guard(request: Request, call_next):
    if INTERNAL_API_KEY and request.url.path.startswith("/api/"):
        provided_key = request.headers.get("x-internal-api-key", "")
        if provided_key != INTERNAL_API_KEY:
            return JSONResponse({"detail": "Missing or invalid internal API key"}, status_code=403)

    host = request.headers.get("host", "").split(":", 1)[0].lower()
    if ALLOWED_HOSTS and host and host not in ALLOWED_HOSTS and host not in {"test", "testserver"}:
        return JSONResponse({"detail": "Invalid host header"}, status_code=400)

    if (
        settings.REQUIRE_ORIGIN_ON_PROTECTED_API
        and request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and request.url.path.startswith(PROTECTED_API_PATHS)
    ):
        origin = request.headers.get("origin")
        referer = request.headers.get("referer")

        if origin:
            if origin not in ALLOWED_ORIGINS:
                return JSONResponse({"detail": "Blocked origin"}, status_code=403)
        elif referer:
            parsed = urlparse(referer)
            referer_origin = f"{parsed.scheme}://{parsed.netloc}"
            if referer_origin not in ALLOWED_ORIGINS:
                return JSONResponse({"detail": "Blocked referer"}, status_code=403)
        else:
            return JSONResponse(
                {"detail": "Origin or Referer required for this endpoint"},
                status_code=403,
            )

    return await call_next(request)

# -- Routers ----------------------------------------------------------------
app.include_router(dictionary.router, prefix="/api")
app.include_router(texts.router, prefix="/api")


# -- Health check -----------------------------------------------------------
@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}
