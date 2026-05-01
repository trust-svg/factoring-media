from core.safety import is_blocked, BLOCK_WORDS


def test_blocks_real_actress():
    assert is_blocked("Photo of aragaki yui smiling")


def test_blocks_japanese_name():
    assert is_blocked("綾瀬はるかのような女性")


def test_passes_clean_prompt():
    assert not is_blocked("Portrait of a fictional woman")


def test_passes_empty():
    assert not is_blocked("")


def test_block_words_are_listed():
    assert "aragaki" in BLOCK_WORDS
    assert "綾瀬" in BLOCK_WORDS
    assert "celebrity" in BLOCK_WORDS
