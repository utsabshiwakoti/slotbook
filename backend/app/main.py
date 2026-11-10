from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import settings
from .database import SessionLocal, engine, ensure_schema
from .routers import admin, auth, public


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_schema(engine)
    if settings.seed_demo:
        from .demo import seed_demo

        with SessionLocal() as db:
            seed_demo(db)
    yield


app = FastAPI(
    title="SlotBook API",
    version="1.0.0",
    description="Multi-business appointment booking: public booking pages and an admin API per business.",
    lifespan=lifespan,
)
# The Vite dev server proxies /api and production serves everything from one origin,
# so CORS only matters if the front end is hosted somewhere else.
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(public.router)


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok"}


def mount_frontend(application: FastAPI, directory: str | Path) -> None:
    """Serve the built React app from the same origin as the API, falling back to index.html so
    client-side routes like /b/demo survive a refresh. Registered last so it can't shadow the API."""
    root = Path(directory).resolve()
    index = root / "index.html"

    @application.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):  # no ../ escapes
            # Vite fingerprints everything under assets/, so those files can be cached forever.
            cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
            return FileResponse(candidate, headers={"Cache-Control": cache})
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


_dist = Path(settings.static_dir) if settings.static_dir else Path(__file__).resolve().parents[2] / "frontend" / "dist"
if (_dist / "index.html").is_file():
    mount_frontend(app, _dist)
