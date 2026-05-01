from core.camera_presets import (
    CAMERA_PRESETS,
    get_kling_params,
    get_prompt_hint,
    list_preset_keys,
)


def test_static_preset_exists():
    assert "static" in CAMERA_PRESETS


def test_seven_presets():
    assert len(CAMERA_PRESETS) == 7


def test_get_kling_params_for_dolly_in():
    assert get_kling_params("dolly_in") == {"zoom": 5}


def test_get_kling_params_for_static_returns_empty():
    assert get_kling_params("static") == {}


def test_get_kling_params_for_none_returns_empty():
    assert get_kling_params(None) == {}


def test_get_prompt_hint_for_pan_left():
    assert "pan left" in get_prompt_hint("pan_left").lower()


def test_get_prompt_hint_for_static_returns_empty():
    assert get_prompt_hint("static") == ""


def test_get_prompt_hint_for_none_returns_empty():
    assert get_prompt_hint(None) == ""


def test_unknown_preset_raises():
    import pytest

    with pytest.raises(KeyError):
        get_kling_params("nonexistent_preset")


def test_list_preset_keys():
    keys = list_preset_keys()
    assert set(keys) == {
        "static",
        "dolly_in",
        "dolly_out",
        "pan_left",
        "pan_right",
        "tilt_up",
        "orbit_left",
    }
