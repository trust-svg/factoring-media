"""Provider capabilities API。"""

from __future__ import annotations

from fastapi import APIRouter

from core.video_providers.kling import Kling3ProProvider
from core.video_providers.seedance import SeedanceProvider
from core.video_providers.veo3 import Veo3LiteProvider

router = APIRouter(prefix="/api")

PROVIDERS = [SeedanceProvider(), Veo3LiteProvider(), Kling3ProProvider()]


@router.get("/providers/capabilities")
def list_capabilities():
    return [
        {
            "name": p.name,
            "supported_aspects": list(p.supported_aspects),
            "supported_qualities": list(p.supported_qualities),
            "supported_durations": list(p.supported_durations),
            "rate_map": p.RATE_MAP,
            "cost_basis": p.cost_basis,
        }
        for p in PROVIDERS
    ]
