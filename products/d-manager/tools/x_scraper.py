"""X (Twitter) scraper — guest token API, no paid account required.

Fetches public tweets from user timelines and searches using X's
internal guest token authentication.
"""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# X bearer token (public, same across all Twitter clients)
_BEARER = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3DZFO5CfI8cTlVoZCRRR6ykBN6UoEacIXiLSqjM9k4fq2I0ks0NF"

_guest_token: Optional[str] = None
_guest_token_ts: float = 0
_GUEST_TOKEN_TTL = 3600  # refresh every hour


def _get_session():
    """Return a requests Session with X headers."""
    import requests
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {_BEARER}",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept-Language": "ja,en;q=0.9",
        "x-twitter-client-language": "ja",
    })
    return s


def _ensure_guest_token() -> Optional[str]:
    """Get or refresh guest token."""
    global _guest_token, _guest_token_ts

    if _guest_token and (time.time() - _guest_token_ts) < _GUEST_TOKEN_TTL:
        return _guest_token

    try:
        s = _get_session()
        resp = s.post(
            "https://api.twitter.com/1.1/guest/activate.json",
            timeout=10,
        )
        if resp.status_code == 200:
            _guest_token = resp.json().get("guest_token")
            _guest_token_ts = time.time()
            logger.info(f"X guest token refreshed")
            return _guest_token
        else:
            logger.warning(f"Guest token fetch failed: {resp.status_code}")
            return None
    except Exception as e:
        logger.warning(f"Guest token error: {e}")
        return None


def _api_get(url: str, params: dict = None) -> Optional[dict]:
    """Make authenticated GET to X API."""
    token = _ensure_guest_token()
    if not token:
        return None
    try:
        s = _get_session()
        s.headers["x-guest-token"] = token
        resp = s.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        logger.warning(f"X API {resp.status_code}: {url}")
        return None
    except Exception as e:
        logger.warning(f"X API error: {e}")
        return None


def get_user_tweets(username: str, count: int = 10) -> str:
    """Fetch recent tweets from a public X account.

    Args:
        username: X handle (with or without @)
        count: number of tweets to fetch (max 20)

    Returns:
        Formatted tweet list as text
    """
    username = username.lstrip("@")
    count = min(count, 20)

    # Step 1: Resolve user ID
    data = _api_get(
        "https://api.twitter.com/1.1/users/show.json",
        params={"screen_name": username, "include_entities": "false"},
    )
    if not data or "id_str" not in data:
        return f"[X] @{username} のユーザー情報を取得できませんでした。"

    user_id = data["id_str"]
    display_name = data.get("name", username)
    followers = data.get("followers_count", 0)

    # Step 2: Fetch timeline
    timeline = _api_get(
        "https://api.twitter.com/1.1/statuses/user_timeline.json",
        params={
            "user_id": user_id,
            "count": count,
            "tweet_mode": "extended",
            "exclude_replies": "true",
            "include_rts": "false",
        },
    )
    if not timeline:
        return f"[X] @{username} のタイムラインを取得できませんでした。"

    lines = [f"📊 **@{username}** ({display_name}) フォロワー: {followers:,}\n"]
    for tweet in timeline[:count]:
        text = tweet.get("full_text", tweet.get("text", ""))
        # Remove t.co URLs at the end
        import re
        text = re.sub(r'\s*https://t\.co/\S+$', '', text).strip()
        created = tweet.get("created_at", "")[:16]
        likes = tweet.get("favorite_count", 0)
        rt = tweet.get("retweet_count", 0)
        lines.append(f"• {text}")
        lines.append(f"  ❤️{likes} 🔁{rt}  {created}")

    return "\n".join(lines)


def search_tweets(query: str, count: int = 10, lang: str = "ja") -> str:
    """Search X for tweets matching a query.

    Args:
        query: search query (hashtags, keywords, etc.)
        count: number of results (max 20)
        lang: language filter (default: ja)

    Returns:
        Formatted search results as text
    """
    count = min(count, 20)

    data = _api_get(
        "https://api.twitter.com/1.1/search/tweets.json",
        params={
            "q": query,
            "count": count,
            "lang": lang,
            "tweet_mode": "extended",
            "result_type": "recent",
        },
    )
    if not data:
        return f"[X] 「{query}」の検索に失敗しました。"

    statuses = data.get("statuses", [])
    if not statuses:
        return f"[X] 「{query}」の検索結果が見つかりませんでした。"

    lines = [f"🔍 **X検索: {query}** ({len(statuses)}件)\n"]
    for tweet in statuses:
        user = tweet.get("user", {}).get("screen_name", "?")
        text = tweet.get("full_text", tweet.get("text", ""))
        import re
        text = re.sub(r'\s*https://t\.co/\S+$', '', text).strip()
        likes = tweet.get("favorite_count", 0)
        rt = tweet.get("retweet_count", 0)
        lines.append(f"@{user}: {text}")
        lines.append(f"  ❤️{likes} 🔁{rt}")

    return "\n".join(lines)


def get_trending(woeid: int = 1118370) -> str:
    """Get trending topics for a location.

    Args:
        woeid: Yahoo Where On Earth ID (default: 1118370 = Japan)
               Tokyo=1118370, Japan=23424856, Worldwide=1

    Returns:
        Formatted trending topics
    """
    data = _api_get(
        "https://api.twitter.com/1.1/trends/place.json",
        params={"id": woeid},
    )
    if not data or not isinstance(data, list):
        return "[X] トレンド情報を取得できませんでした。"

    trends = data[0].get("trends", [])[:10]
    location = data[0].get("locations", [{}])[0].get("name", "")
    lines = [f"🔥 **Xトレンド ({location})**\n"]
    for i, t in enumerate(trends, 1):
        name = t.get("name", "")
        volume = t.get("tweet_volume")
        vol_str = f"  {volume:,}ツイート" if volume else ""
        lines.append(f"{i}. {name}{vol_str}")

    return "\n".join(lines)
