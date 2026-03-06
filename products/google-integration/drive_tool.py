import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from auth import get_credentials


def _service():
    return build("drive", "v3", credentials=get_credentials())


def search_drive_files(query: str, max_results: int = 10) -> list[dict]:
    """Google Drive内のファイルを検索する。

    Args:
        query: 検索キーワード（ファイル名や内容）
        max_results: 取得件数（デフォルト10件）
    """
    # ファイル名・全文検索
    drive_query = f"name contains '{query}' or fullText contains '{query}'"
    drive_query += " and trashed = false"

    result = (
        _service()
        .files()
        .list(
            q=drive_query,
            pageSize=max_results,
            fields="files(id, name, mimeType, modifiedTime, size)",
        )
        .execute()
    )
    files = result.get("files", [])
    return [
        {
            "id": f["id"],
            "name": f["name"],
            "mimeType": f["mimeType"],
            "modifiedTime": f.get("modifiedTime", ""),
            "size": f.get("size", ""),
        }
        for f in files
    ]


def read_drive_file(file_id: str) -> dict:
    """Google Driveのファイル内容を読み取る。

    Args:
        file_id: ファイルID（search_drive_files で取得した id）

    対応形式:
        - Google ドキュメント → テキスト変換して返す
        - Google スプレッドシート → CSV変換して返す
        - テキスト系ファイル（.txt, .md, .py など）→ そのまま返す
    """
    file_meta = _service().files().get(fileId=file_id, fields="name,mimeType").execute()
    name = file_meta["name"]
    mime = file_meta["mimeType"]

    # Google ドキュメント
    if mime == "application/vnd.google-apps.document":
        content = _export_file(file_id, "text/plain")
        return {"name": name, "content": content, "type": "document"}

    # Google スプレッドシート
    if mime == "application/vnd.google-apps.spreadsheet":
        content = _export_file(file_id, "text/csv")
        return {"name": name, "content": content, "type": "spreadsheet"}

    # Google スライド
    if mime == "application/vnd.google-apps.presentation":
        content = _export_file(file_id, "text/plain")
        return {"name": name, "content": content, "type": "presentation"}

    # バイナリ/その他（テキスト系として試みる）
    content = _download_file(file_id)
    return {"name": name, "content": content, "type": "file"}


def _export_file(file_id: str, export_mime: str) -> str:
    """Google Workspace ファイルをエクスポートする。"""
    request = _service().files().export_media(fileId=file_id, mimeType=export_mime)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue().decode("utf-8", errors="replace")


def _download_file(file_id: str) -> str:
    """通常ファイルをダウンロードしてテキストとして返す。"""
    request = _service().files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue().decode("utf-8", errors="replace")


def update_drive_file(file_id: str, new_content: str) -> dict:
    """Google Driveのファイル内容を更新する（テキストファイル・Google ドキュメント）。

    Args:
        file_id: ファイルID
        new_content: 新しいテキスト内容
    """
    file_meta = _service().files().get(fileId=file_id, fields="name,mimeType").execute()
    name = file_meta["name"]
    mime = file_meta["mimeType"]

    # Google ドキュメントの場合はプレーンテキストでアップロード
    if mime == "application/vnd.google-apps.document":
        upload_mime = "text/plain"
    else:
        upload_mime = mime if mime else "text/plain"

    media = MediaIoBaseUpload(
        io.BytesIO(new_content.encode("utf-8")),
        mimetype=upload_mime,
        resumable=False,
    )
    updated = (
        _service()
        .files()
        .update(fileId=file_id, media_body=media, fields="id,name,modifiedTime")
        .execute()
    )
    return {
        "id": updated.get("id"),
        "name": updated.get("name"),
        "modifiedTime": updated.get("modifiedTime"),
    }
