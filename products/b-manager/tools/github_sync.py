"""GitHub sync — write files to obsidian-company repo."""

import base64
import json
import logging
import urllib.request
import urllib.error

import config

logger = logging.getLogger(__name__)

API_BASE = f"https://api.github.com/repos/{config.GITHUB_REPO}/contents"


def _headers() -> dict:
    return {
        "Authorization": f"token {config.GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "B-Manager",
    }


def _get_file_sha(path: str) -> str | None:
    """Get the SHA of an existing file (needed for updates)."""
    url = f"{API_BASE}/{path}"
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            return data.get("sha")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def _get_file_content(path: str) -> str | None:
    """Get the current content of a file."""
    url = f"{API_BASE}/{path}"
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            return base64.b64decode(data["content"]).decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def write_file(path: str, content: str, message: str = "update") -> bool:
    """Create or update a file in the GitHub repo."""
    if not config.GITHUB_TOKEN:
        logger.warning("GITHUB_TOKEN not set, skipping GitHub sync")
        return False

    url = f"{API_BASE}/{path}"
    sha = _get_file_sha(path)

    body = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
    }
    if sha:
        body["sha"] = sha

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_headers(), method="PUT")

    try:
        with urllib.request.urlopen(req) as resp:
            logger.info(f"GitHub sync: {path}")
            return True
    except Exception as e:
        logger.error(f"GitHub sync failed for {path}: {e}")
        return False


def append_to_file(path: str, new_line: str, template: str = "", message: str = "update") -> bool:
    """Append a line to an existing file, or create with template + line."""
    existing = _get_file_content(path)

    if existing:
        content = existing.rstrip("\n") + "\n" + new_line + "\n"
    else:
        content = template + new_line + "\n"

    return write_file(path, content, message)
