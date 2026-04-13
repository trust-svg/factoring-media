# tests/test_square_webhook.py
import pytest
from unittest.mock import AsyncMock, patch

from payment.square_webhook import (
    generate_checkout_url,
    parse_subscription_event,
    SquareEvent,
)


def test_parse_subscription_created():
    payload = {
        "type": "subscription.created",
        "data": {
            "object": {
                "subscription": {
                    "id": "sub_abc123",
                    "customer_id": "cust_xyz",
                    "plan_variation_id": "plan_standard_id",
                    "status": "ACTIVE",
                    "metadata": {"line_user_id": "Uabc123"},
                }
            }
        }
    }
    event = parse_subscription_event(payload, standard_plan_id="plan_standard_id", premium_plan_id="plan_premium_id")
    assert event.event_type == "created"
    assert event.line_user_id == "Uabc123"
    assert event.plan == "standard"
    assert event.subscription_id == "sub_abc123"


def test_parse_subscription_canceled():
    payload = {
        "type": "subscription.updated",
        "data": {
            "object": {
                "subscription": {
                    "id": "sub_abc123",
                    "customer_id": "cust_xyz",
                    "plan_variation_id": "plan_standard_id",
                    "status": "CANCELED",
                    "metadata": {"line_user_id": "Uabc123"},
                }
            }
        }
    }
    event = parse_subscription_event(payload, standard_plan_id="plan_standard_id", premium_plan_id="plan_premium_id")
    assert event.event_type == "canceled"


def test_parse_unknown_event_returns_none():
    payload = {"type": "payment.completed", "data": {}}
    event = parse_subscription_event(payload, standard_plan_id="s", premium_plan_id="p")
    assert event is None
