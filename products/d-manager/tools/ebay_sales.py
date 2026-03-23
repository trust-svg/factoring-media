"""eBay sales integration — fetches data from ebay-agent API."""

import json
import logging
import os
from typing import Dict

import httpx

logger = logging.getLogger(__name__)

EBAY_AGENT_URL = os.getenv("EBAY_AGENT_URL", "http://127.0.0.1:8000")


def get_ebay_sales_summary() -> Dict:
    """Get today's eBay sales summary from ebay-agent."""
    try:
        resp = httpx.get(f"{EBAY_AGENT_URL}/api/sales/today", timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return {"error": f"ebay-agent responded with {resp.status_code}"}
    except httpx.ConnectError:
        return {"error": "ebay-agentに接続できません。ローカルで起動していない可能性があります。"}
    except Exception as e:
        return {"error": str(e)}


def get_ebay_active_listings() -> Dict:
    """Get active listing count and stats."""
    try:
        resp = httpx.get(f"{EBAY_AGENT_URL}/api/dashboard", timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return {"error": f"ebay-agent responded with {resp.status_code}"}
    except httpx.ConnectError:
        return {"error": "ebay-agentに接続できません。"}
    except Exception as e:
        return {"error": str(e)}


def get_ebay_messages() -> Dict:
    """Get unread eBay messages."""
    try:
        resp = httpx.get(f"{EBAY_AGENT_URL}/api/messages/unread", timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return {"error": f"ebay-agent responded with {resp.status_code}"}
    except httpx.ConnectError:
        return {"error": "ebay-agentに接続できません。"}
    except Exception as e:
        return {"error": str(e)}
