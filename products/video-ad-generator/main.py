"""Video Ad Generator — FastAPI メインサーバー"""
from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from pathlib import Path
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from database import init_db
from api.generate import router as generate_router
from api.approve import router as approve_router
from api.jobs import router as jobs_router
from config import APP_HOST, APP_PORT, BASE_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("video-ad-generator")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("DB初期化完了")
    yield


app = FastAPI(title="Video Ad Generator", lifespan=lifespan)

app.include_router(generate_router)
app.include_router(approve_router)
app.include_router(jobs_router)

# output ディレクトリを静的ファイルとして配信（画像・動画プレビュー用）
app.mount("/output", StaticFiles(directory=str(BASE_DIR / "output")), name="output")


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = BASE_DIR / "static" / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    uvicorn.run("main:app", host=APP_HOST, port=APP_PORT, reload=True)
