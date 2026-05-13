"""ローカル開発用: Telegram webhook が無くても offer を approve / reject できる CLI。

使い方:
    python scripts/approve_offer.py 12 approve
    python scripts/approve_offer.py 12 reject
    python scripts/approve_offer.py 12 show
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.models import OutboundOffer, get_db  # noqa: E402


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: python scripts/approve_offer.py <offer_id> <approve|reject|show>")
        return 1
    offer_id = int(sys.argv[1])
    action = sys.argv[2]

    if action == "show":
        db = get_db()
        try:
            offer = db.query(OutboundOffer).filter(OutboundOffer.id == offer_id).first()
            if not offer:
                print(f"offer_id {offer_id} not found")
                return 2
            print(
                json.dumps(
                    {
                        "id": offer.id,
                        "buyer": offer.buyer_username,
                        "status": offer.status,
                        "subject": offer.draft_subject,
                        "body": offer.draft_body,
                        "compliance_flags": offer.compliance_flags_json,
                        "due_at": offer.due_at.isoformat() if offer.due_at else None,
                        "past_order_item_id": offer.past_order_item_id,
                        "error_message": offer.error_message,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        finally:
            db.close()

    if action == "approve":
        from chat.repeat_engine import dispatch_send

        result = dispatch_send(offer_id, approved_by="cli")
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("sent") else 3

    if action == "reject":
        cb = {"from": {"username": "cli"}, "message": {}}
        from chat.repeat_engine import handle_telegram_action

        result = handle_telegram_action("reject", offer_id, cb)
        print(json.dumps(result, ensure_ascii=False))
        return 0

    print(f"unknown action: {action}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
