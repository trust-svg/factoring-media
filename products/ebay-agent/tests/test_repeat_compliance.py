"""compliance_check() のユニットテスト"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat.repeat_engine import compliance_check, has_block_flag


def test_clean_body_no_flags():
    body = (
        "Hi taro, thank you for your kind feedback. If you'd like to see new arrivals, "
        "please tap Save Seller on my eBay store."
    )
    flags = compliance_check(body)
    assert flags == []
    assert not has_block_flag(flags)


def test_external_url_blocked():
    body = "Visit https://example.com for more"
    flags = compliance_check(body)
    assert any(f == "block:external_url" for f in flags)
    assert has_block_flag(flags)


def test_ebay_url_is_allowed():
    body = "See my store on https://www.ebay.com/str/foo"
    flags = compliance_check(body)
    assert not any(f == "block:external_url" for f in flags)


def test_email_blocked():
    body = "Contact me at seller@example.com"
    flags = compliance_check(body)
    assert "block:email_address" in flags
    assert has_block_flag(flags)


def test_off_platform_channel_blocked():
    body = "Find me on WhatsApp or Instagram"
    flags = compliance_check(body)
    assert "block:off_platform_channel" in flags


def test_pushy_sales_warn_only():
    body = "Act now before this deal is gone"
    flags = compliance_check(body)
    assert "warn:pushy_sales" in flags
    assert not has_block_flag(flags)


def test_length_warn():
    body = "x" * 801
    flags = compliance_check(body)
    assert "warn:length" in flags
