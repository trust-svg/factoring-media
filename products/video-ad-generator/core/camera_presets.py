"""カメラ動作プリセット定義。
プロバイダーごとに「Klingは数値パラメータ／Seedance・Veo3はプロンプト埋め込み」を分岐する。
"""

from __future__ import annotations

CAMERA_PRESETS: dict[str, dict] = {
    "static": {
        "label": "固定",
        "kling": {},
        "prompt_hint": "",
    },
    "dolly_in": {
        "label": "ドリーイン",
        "kling": {"zoom": 5},
        "prompt_hint": "slow dolly-in toward subject",
    },
    "dolly_out": {
        "label": "ドリーアウト",
        "kling": {"zoom": -5},
        "prompt_hint": "slow dolly-out away from subject",
    },
    "pan_left": {
        "label": "左パン",
        "kling": {"pan": -5},
        "prompt_hint": "smooth pan left",
    },
    "pan_right": {
        "label": "右パン",
        "kling": {"pan": 5},
        "prompt_hint": "smooth pan right",
    },
    "tilt_up": {
        "label": "上ティルト",
        "kling": {"tilt": 5},
        "prompt_hint": "tilt up gently",
    },
    "orbit_left": {
        "label": "左オービット",
        "kling": {"horizontal": -5},
        "prompt_hint": "camera orbits left around subject",
    },
}


def get_kling_params(preset_key: str | None) -> dict:
    """Kling 用の camera_control 数値パラメータを返す。"""
    if preset_key is None:
        return {}
    if preset_key not in CAMERA_PRESETS:
        raise KeyError(f"Unknown camera preset: {preset_key}")
    return dict(CAMERA_PRESETS[preset_key]["kling"])


def get_prompt_hint(preset_key: str | None) -> str:
    """Seedance/Veo3 用のプロンプト埋め込み文字列を返す。"""
    if preset_key is None:
        return ""
    if preset_key not in CAMERA_PRESETS:
        raise KeyError(f"Unknown camera preset: {preset_key}")
    return CAMERA_PRESETS[preset_key]["prompt_hint"]


def list_preset_keys() -> list[str]:
    return list(CAMERA_PRESETS.keys())
