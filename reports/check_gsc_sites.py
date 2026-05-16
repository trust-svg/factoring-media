#!/usr/bin/env python3
"""GSCで認証済みアカウントが持つサイト一覧を表示する。"""

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from gsc_client import get_service

service = get_service()
sites = service.sites().list().execute()
for s in sites.get("siteEntry", []):
    print(s["siteUrl"], "-", s["permissionLevel"])
