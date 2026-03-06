"""eBay Listing SEO Optimizer — メインエントリーポイント"""
from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

load_dotenv()

from config import APP_HOST, APP_PORT, LOGS_DIR, STATIC_DIR, TEMPLATES_DIR

# ログ設定
LOGS_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / "optimizer.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    from database.crud import init_db
    await init_db()
    logger.info("データベース初期化完了")
    yield


app = FastAPI(title="eBay Listing SEO Optimizer", lifespan=lifespan)

# Chrome拡張からのリクエストを許可
app.add_middleware(
    CORSMiddleware,
    allow_origins=["chrome-extension://*"],
    allow_origin_regex=r"^chrome-extension://.*$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# APIルーターを登録
from api.listings import router as listings_router
from api.analysis import router as analysis_router
from api.competitor import router as competitor_router
from api.optimization import router as optimization_router
from api.apply import router as apply_router

app.include_router(listings_router)
app.include_router(analysis_router)
app.include_router(competitor_router)
app.include_router(optimization_router)
app.include_router(apply_router)


# ============================================================
# HTMLページ
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/listing/{sku}", response_class=HTMLResponse)
async def listing_detail(request: Request, sku: str):
    return templates.TemplateResponse(
        "listing_detail.html", {"request": request, "sku": sku}
    )


@app.get("/batch", response_class=HTMLResponse)
async def batch_page(request: Request):
    return templates.TemplateResponse("batch.html", {"request": request})


@app.get("/health")
async def health():
    return {"status": "ok", "service": "eBay Listing SEO Optimizer"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=APP_HOST, port=APP_PORT)
