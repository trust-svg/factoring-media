"""管理者ダッシュボード — 鑑定の監修・承認・LINE送信・Threads OAuth"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from database.crud import (
    AsyncSessionLocal,
    approve_reading,
    approve_reply,
    get_pending_readings,
    get_pending_replies,
    get_reading_by_id,
    get_setting,
    mark_reading_sent,
    mark_reply_sent,
    set_setting,
    skip_reply,
)

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

ADMIN_KEY = os.environ.get("ADMIN_SECRET_KEY", "")


def _check_admin(key: str) -> None:
    if not ADMIN_KEY or key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/admin/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, key: str = Query("")):
    _check_admin(key)
    async with AsyncSessionLocal() as session:
        readings = await get_pending_readings(session)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "readings": readings, "key": key},
    )


@router.get("/admin/reading/{reading_id}", response_class=HTMLResponse)
async def edit_reading(request: Request, reading_id: int, key: str = Query("")):
    _check_admin(key)
    async with AsyncSessionLocal() as session:
        reading = await get_reading_by_id(session, reading_id)
    if reading is None:
        raise HTTPException(status_code=404, detail="Reading not found")
    return templates.TemplateResponse(
        "edit_reading.html",
        {"request": request, "reading": reading, "key": key},
    )


@router.post("/admin/reading/{reading_id}/approve")
async def approve_and_send(request: Request, reading_id: int, key: str = Query("")):
    _check_admin(key)

    form = await request.form()
    final_text = str(form.get("final_text", "")).strip()
    if not final_text:
        raise HTTPException(status_code=400, detail="鑑定テキストが空です")

    async with AsyncSessionLocal() as session:
        reading = await approve_reading(session, reading_id, final_text)
        if reading is None:
            raise HTTPException(status_code=400, detail="承認できません（既に処理済みか存在しません）")

        # LINE push送信
        from main import _push_message
        try:
            _push_message(reading.line_user_id, final_text)
            await mark_reading_sent(session, reading_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"LINE送信エラー: {e}")

    # ダッシュボードにリダイレクト
    return RedirectResponse(
        url=f"/admin/dashboard?key={key}",
        status_code=303,
    )


# ===================== Threads コメント返信管理 =====================


@router.get("/admin/replies", response_class=HTMLResponse)
async def replies_page(request: Request, key: str = Query("")):
    """コメント返信管理ページ"""
    _check_admin(key)
    async with AsyncSessionLocal() as session:
        replies = await get_pending_replies(session)
    return templates.TemplateResponse(
        "replies.html",
        {"request": request, "replies": replies, "key": key},
    )


@router.post("/admin/reply/{reply_id}/send")
async def send_reply(request: Request, reply_id: int, key: str = Query("")):
    """返信を承認してThreadsに送信する"""
    _check_admin(key)

    form = await request.form()
    final_text = str(form.get("final_text", "")).strip()
    if not final_text:
        raise HTTPException(status_code=400, detail="返信テキストが空です")

    from threads.api import ThreadsClient

    async with AsyncSessionLocal() as session:
        reply = await approve_reply(session, reply_id, final_text)
        if reply is None:
            raise HTTPException(status_code=400, detail="承認できません")

        try:
            client = ThreadsClient()
            reply_post_id = await client.reply_to_thread(reply.comment_id, final_text)
            await mark_reply_sent(session, reply_id, reply_post_id)
        except Exception as e:
            logger.error(f"Threads返信送信エラー: {e}")
            raise HTTPException(status_code=500, detail=f"送信エラー: {e}")

    return RedirectResponse(url=f"/admin/replies?key={key}", status_code=303)


@router.post("/admin/reply/{reply_id}/skip")
async def skip_reply_action(request: Request, reply_id: int, key: str = Query("")):
    """返信をスキップする"""
    _check_admin(key)
    async with AsyncSessionLocal() as session:
        await skip_reply(session, reply_id)
    return RedirectResponse(url=f"/admin/replies?key={key}", status_code=303)


# ===================== Threads トークン管理 =====================


@router.get("/admin/threads-token", response_class=HTMLResponse)
async def threads_token_page(request: Request, key: str = Query("")):
    """Threadsトークン管理ページ"""
    _check_admin(key)

    # 現在のトークン状態を確認
    async with AsyncSessionLocal() as session:
        saved_token = await get_setting(session, "threads_access_token")

    env_token = bool(os.environ.get("THREADS_ACCESS_TOKEN"))
    status = "DB保存済み" if saved_token else ("環境変数のみ" if env_token else "未設定")

    return templates.TemplateResponse(
        "threads_token.html",
        {"request": request, "key": key, "token_status": status, "message": ""},
    )


@router.post("/admin/threads-token")
async def threads_token_save(request: Request, key: str = Query("")):
    """トークンを保存し、長期トークンへの交換を試みる"""
    _check_admin(key)

    try:
        form = await request.form()
        token = str(form.get("token", "")).strip()
        if not token:
            raise HTTPException(status_code=400, detail="トークンが空です")

        app_secret = os.environ.get("META_APP_SECRET", "")
        message = ""
        final_token = token

        # 長期トークンへの交換を試みる
        if app_secret:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(
                        "https://graph.threads.net/access_token",
                        params={
                            "grant_type": "th_exchange_token",
                            "client_secret": app_secret,
                            "access_token": token,
                        },
                    )
                    if resp.status_code == 200:
                        final_token = resp.json()["access_token"]
                        message = "長期トークン（60日有効）に交換して保存しました。自動リフレッシュが有効です。"
                        logger.info("Threads短期→長期トークン交換成功")
                    else:
                        message = f"長期トークン交換に失敗（入力トークンをそのまま保存しました）"
                        logger.warning(f"Threads長期トークン交換失敗: {resp.text}")
            except Exception as e:
                message = f"交換リクエスト失敗（入力トークンをそのまま保存しました）"
                logger.error(f"Threadsトークン交換例外: {e}")
        else:
            message = "META_APP_SECRET未設定のため、入力トークンをそのまま保存しました。"

        # DBに保存
        async with AsyncSessionLocal() as session:
            await set_setting(session, "threads_access_token", final_token)

        status = "DB保存済み"

        return templates.TemplateResponse(
            "threads_token.html",
            {"request": request, "key": key, "token_status": status, "message": message},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"トークン保存エラー: {e}", exc_info=True)
        return HTMLResponse(f"<h2>エラー</h2><pre>{e}</pre>", status_code=500)


# ===================== Threads OAuth =====================

THREADS_OAUTH_SCOPES = "threads_basic,threads_content_publish,threads_read_replies,threads_manage_replies"


@router.get("/admin/threads-auth")
async def threads_auth(request: Request, key: str = Query("")):
    """Threads OAuth認証を開始する（Meta認証画面にリダイレクト）"""
    _check_admin(key)
    app_id = os.environ.get("META_APP_ID", "")
    if not app_id:
        raise HTTPException(status_code=500, detail="META_APP_ID が未設定です")

    base = str(request.base_url).rstrip("/").replace("http://", "https://", 1)
    redirect_uri = f"{base}/admin/threads-callback"
    auth_url = (
        f"https://threads.net/oauth/authorize"
        f"?client_id={app_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope={THREADS_OAUTH_SCOPES}"
        f"&response_type=code"
        f"&state={key}"
    )
    return RedirectResponse(url=auth_url)


@router.get("/admin/threads-callback")
async def threads_callback(request: Request, code: str = "", state: str = ""):
    """OAuthコールバック: 認証コード → 短期トークン → 長期トークン"""
    _check_admin(state)

    app_id = os.environ.get("META_APP_ID", "")
    app_secret = os.environ.get("META_APP_SECRET", "")
    base = str(request.base_url).rstrip("/").replace("http://", "https://", 1)
    redirect_uri = f"{base}/admin/threads-callback"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: 認証コード → 短期トークン
            resp = await client.post(
                "https://graph.threads.net/oauth/access_token",
                data={
                    "client_id": app_id,
                    "client_secret": app_secret,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                    "code": code,
                },
            )
            if resp.status_code != 200:
                logger.error(f"Threads短期トークン取得失敗: {resp.text}")
                return HTMLResponse(f"<h2>認証失敗</h2><p>{resp.text}</p>", status_code=400)

            short_token = resp.json()["access_token"]

            # Step 2: 短期トークン → 長期トークン（60日有効）
            resp2 = await client.get(
                "https://graph.threads.net/access_token",
                params={
                    "grant_type": "th_exchange_token",
                    "client_secret": app_secret,
                    "access_token": short_token,
                },
            )
            if resp2.status_code != 200:
                logger.error(f"Threads長期トークン交換失敗: {resp2.text}")
                return HTMLResponse(f"<h2>長期トークン交換失敗</h2><p>{resp2.text}</p>", status_code=400)

            long_token = resp2.json()["access_token"]

        # DBに保存
        async with AsyncSessionLocal() as session:
            await set_setting(session, "threads_access_token", long_token)

        logger.info("Threads長期トークン取得・保存完了")
        return HTMLResponse(
            "<h2>Threads認証完了</h2>"
            "<p>長期アクセストークン（60日有効）を保存しました。</p>"
            "<p>自動リフレッシュにより期限前に更新されます。</p>"
            f'<p><a href="/admin/dashboard?key={state}">ダッシュボードに戻る</a></p>'
        )
    except Exception as e:
        logger.error(f"Threads OAuth エラー: {e}", exc_info=True)
        return HTMLResponse(f"<h2>エラー</h2><pre>{e}</pre>", status_code=500)
