from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.config import settings
from backend.core.logging_config import setup_logging
from backend.core.startup import AppState, startup, shutdown
from backend.api import (
    websocket, calls, benchmark, voices, training, devices, phones, setup,
    voice_training, scenarios, reports, notify, data_sources,
    fillers as fillers_api,
    knowledge as knowledge_api,
    logs as logs_api,
    luat_kiem as luat_kiem_api,
)

setup_logging(settings.log_level)

app_state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await startup(app_state)
    yield
    await shutdown(app_state)


app = FastAPI(
    title="AI Banking Call System",
    version="1.0.0",
    lifespan=lifespan,
)

# API routes
app.include_router(websocket.router)
app.include_router(calls.router)
app.include_router(benchmark.router)
app.include_router(voices.router)
app.include_router(training.router)
app.include_router(devices.router)
app.include_router(phones.router)
app.include_router(setup.router)
app.include_router(voice_training.router)
app.include_router(scenarios.router)
app.include_router(reports.router)
app.include_router(notify.router)
app.include_router(data_sources.router)
# Trang Logs truoc day la vo rong: chi co clearLogs() xoa noi dung, khong co
# nguon du lieu nao va khong co endpoint. Hien 'Dang cho ket noi server...' mai.
app.include_router(logs_api.router)
app.include_router(knowledge_api.router)
app.include_router(fillers_api.router)
app.include_router(luat_kiem_api.router)

# Mỗi menu của SPA có một URL thật. Các route này đều trả cùng app shell;
# frontend/app.js đọc location.pathname để mở đúng trang. Nhờ vậy reload/F5
# `/contacts`, `/devices`, ... không rơi về Tổng quan.
FRONTEND_PAGES = (
    "overview", "chat", "messaging", "contacts", "reports",
    "scenarios", "datasources", "knowledge", "fillers", "voice",
    "devices", "settings", "sessions", "voice-test", "voice-training",
    "training", "models", "benchmark", "logs",
)
FRONTEND_PATHS = {"/"} | {f"/{page}" for page in FRONTEND_PAGES}


# Frontend must never be cached: without Cache-Control, Chromium applies
# heuristic freshness (10% of file age) and Electron can keep serving a
# months-old UI from disk cache.
@app.middleware("http")
async def no_cache_frontend(request: Request, call_next):
    response = await call_next(request)
    if request.url.path in FRONTEND_PATHS or request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-cache"
    return response


# Serve frontend
app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse("frontend/index.html")


async def frontend_page():
    return FileResponse("frontend/index.html")


for _page in FRONTEND_PAGES:
    app.add_api_route(
        f"/{_page}", frontend_page, methods=["GET"],
        include_in_schema=False, name=f"frontend-{_page}",
    )
