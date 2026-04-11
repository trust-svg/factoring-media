from core.patterns import PATTERNS, get_batch_prompts, is_blocked

def test_patterns_has_five_types():
    assert set(PATTERNS.keys()) == {"A", "B", "C", "D", "E"}

def test_each_pattern_has_image_and_video_prompt():
    for key, p in PATTERNS.items():
        assert "image_prompt" in p, f"Pattern {key} missing image_prompt"
        assert "video_prompt" in p, f"Pattern {key} missing video_prompt"
        assert "theme" in p

def test_get_batch_prompts_returns_ten():
    batch = get_batch_prompts()
    assert len(batch) == 10

def test_get_batch_prompts_has_two_per_pattern():
    batch = get_batch_prompts()
    patterns_in_batch = [item["pattern"] for item in batch]
    for p in ["A", "B", "C", "D", "E"]:
        assert patterns_in_batch.count(p) == 2

def test_is_blocked_real_person():
    assert is_blocked("photo of Yui Aragaki smiling") is True

def test_is_blocked_safe_prompt():
    assert is_blocked("A Japanese woman in her 40s at a cafe") is False
